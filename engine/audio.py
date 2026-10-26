# -*- coding: utf-8 -*-
"""按音效表合成声音，再和画面合成成片。

  python audio.py <工程目录>                          只有音效（默认）
  python audio.py <工程目录> --music 音乐.mp3          加上背景音乐；--music-gain 调音量，默认 0.2

读 audio/events.json（先跑 render.py --events），写出 audio/sfx.wav；
如果 renders/raw.mp4 已经渲好，就合成 renders/final.mp4。
音效都是用数学现场合成的，不用任何录音素材。背景音乐默认不加；加的时候会循环到片长、头尾淡入淡出，
每当有音效响起，音乐自动让开一些，不盖过音效。

音效名字（film.js 的 SFX 表里写 [时刻, 名字, 选项]）：
  tick    一声轻"嗒"：计数、点亮一个小东西            选项 pitch（半音，可正可负）
  pop     短促的"啵"：小东西出现、落位
  thud    低沉的落地声：东西落下、砸到桌上
  stamp   盖章：thud 加一声硬的"嗒"
  chime   一记短钟声，2 秒内收掉：章节开头、片名      选项 root（半音）
  reveal  揭晓：钟声加一点亮光感，全片最重要的那一下用
  rise    往上滑的音：揭晓前的一点期待                选项 dur（秒）
  swish   一阵风声：翻页、撕掉、甩出去
  noise   一段沙沙的噪声：讲到"噪声、干扰"时才用        选项 dur（秒）
  hush    从这一刻起彻底静音                          选项 dur（秒）
每个音效都可以加 gain（音量倍数，默认 1）和 pan（左右，-1 到 1）。
"""
import argparse, json, subprocess, sys, wave
from pathlib import Path
import numpy as np

SR = 48000


def secs(d):
    return np.arange(int(d * SR)) / SR


def lowpass(x, cutoff):
    """一阶低通：把高于 cutoff 赫兹的声音削掉一些。"""
    a = np.exp(-2 * np.pi * cutoff / SR)
    try:
        from scipy.signal import lfilter
        return lfilter([1 - a], [1, -a], x)
    except ImportError:
        y, acc = np.empty_like(x), 0.0
        for i, v in enumerate(x):
            acc = (1 - a) * v + a * acc
            y[i] = acc
        return y


def noise(n, seed):
    return np.random.default_rng(seed).standard_normal(n)


def sweep(f0, f1, d):
    """频率从 f0 平滑地滑到 f1 的正弦。"""
    t = secs(d)
    f = f0 * (f1 / f0) ** (t / d)
    return np.sin(2 * np.pi * np.cumsum(f) / SR), t


def attack(x, ms=3):
    n = min(len(x), int(SR * ms / 1000))
    x[:n] *= np.linspace(0, 1, n)
    return x


def s_tick(o):
    t = secs(.07)
    f = 1900 * 2 ** (o.get("pitch", 0) / 12)
    body = np.sin(2 * np.pi * f * t) * np.exp(-t / .012)
    click = noise(len(t), 3) * np.exp(-t / .002) * .3
    return attack(body + click, 1) * .5


def s_pop(o):
    s, t = sweep(900, 320, .09)
    return attack(s * np.exp(-t / .028), 1) * .6


def s_thud(o):
    s, t = sweep(110, 46, .38)
    body = s * np.exp(-t / .1)
    dust = lowpass(noise(len(t), 5), 900) * np.exp(-t / .03) * 1.5
    return attack(body + dust, 2) * .9


def s_stamp(o):
    a, b = s_thud(o), s_tick({"pitch": -10})
    a[:len(b)] += b * 1.2
    return a


def s_chime(o):
    d = min(o.get("dur", 1.8), 2.0)
    t = secs(d)
    f0 = 587.33 * 2 ** (o.get("root", 0) / 12)
    out = np.zeros_like(t)
    for ratio, amp, tau in ((1, 1, .55), (2.01, .32, .35), (2.92, .2, .25), (5.43, .08, .12)):
        out += amp * np.sin(2 * np.pi * f0 * ratio * t) * np.exp(-t / tau)
    fade, m = np.ones_like(t), min(len(t), int(.25 * SR))
    fade[len(t) - m:] = np.linspace(1, 0, m)
    return attack(out * fade, 4) * .35


def s_reveal(o):
    base = s_chime({"root": o.get("root", 0) + 7, "dur": 1.8})
    t = secs(len(base) / SR)
    shine = np.zeros_like(t)
    for k, f in enumerate((2637, 3136, 3951)):
        shine += np.sin(2 * np.pi * f * t + k) * np.exp(-t / .4) * (1 + .3 * np.sin(2 * np.pi * 7 * t))
    return base + attack(shine, 20) * .025


def s_rise(o):
    d = o.get("dur", .8)
    s, t = sweep(260, 780, d)
    shape = (t / d) ** 2
    shape[-int(.02 * SR):] *= np.linspace(1, 0, int(.02 * SR))
    return s * shape * .22


def s_swish(o):
    t = secs(.36)
    n = noise(len(t), 9)
    band = lowpass(n, 3500) - lowpass(n, 500)
    return band * np.sin(np.pi * t / t[-1]) ** 2 * .9


def s_noise(o):
    d = o.get("dur", 2.0)
    t = secs(d)
    n = lowpass(noise(len(t), 13), 4500)
    shape = np.minimum(1, np.minimum(t / .4, (d - t) / .4))
    return n * shape * .18


SOUNDS = {"tick": s_tick, "pop": s_pop, "thud": s_thud, "stamp": s_stamp, "chime": s_chime,
          "reveal": s_reveal, "rise": s_rise, "swish": s_swish, "noise": s_noise}


def load_music(path, n):
    """用 ffmpeg 把任意格式的音乐解成 48k 立体声；比片子短就从头循环，截到 n 个采样点，头尾淡入淡出。"""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "2", "-ar", str(SR), "-"],
                         capture_output=True).stdout
    m = np.frombuffer(raw, "<i2").reshape(-1, 2) / 32768.0
    if not len(m):
        sys.exit(f"读不出这个音乐文件：{path}")
    m = np.tile(m, (n // len(m) + 1, 1))[:n].copy()
    fi, fo = min(n, SR), min(n, int(2.5 * SR))
    m[:fi] *= np.linspace(0, 1, fi)[:, None]
    m[n - fo:] *= np.linspace(1, 0, fo)[:, None]
    return m


def mix(events, end, music=None, music_gain=.2):
    n = int(end * SR) + SR
    out, mutes = np.zeros((n, 2)), []
    for t, name, o in events:
        if name == "hush":
            mutes.append((t, t + o.get("dur", 2.0)))
            continue
        if name not in SOUNDS:
            print(f"  跳过不认识的音效：{name}（第 {t} 秒）")
            continue
        s = SOUNDS[name](o) * o.get("gain", 1)
        pan = (o.get("pan", 0) + 1) * np.pi / 4
        i = int(t * SR)
        s = s[:max(0, n - i)]
        out[i:i + len(s), 0] += s * np.cos(pan) * 1.414
        out[i:i + len(s), 1] += s * np.sin(pan) * 1.414
    if music is not None:                                          # 配乐：音效响的时候，音乐自动让开一些
        level = lowpass(np.abs(out).max(axis=1), 6)
        duck = 1 - .6 * np.clip(level / .05, 0, 1)
        out += load_music(music, n) * music_gain * duck[:, None]
    for a, b in mutes:                                             # 静音：前后各留 15 毫秒的渐变，不会"咔"一声
        i, j, r = int(a * SR), int(b * SR), int(.015 * SR)
        out[max(0, i - r):i] *= np.linspace(1, 0, min(r, i))[:, None]
        out[i:j] = 0
        out[j:j + r] *= np.linspace(0, 1, len(out[j:j + r]))[:, None]
    out = out[:int(end * SR)]
    peak = np.abs(out).max()
    if peak > .89:
        out *= .89 / peak
    return out


def main():
    ap = argparse.ArgumentParser(description="合成音效（可选加背景音乐），再和画面合成成片")
    ap.add_argument("proj", type=Path)
    ap.add_argument("--music", type=Path, help="背景音乐文件（mp3、wav、m4a 都行）；不写就只有音效")
    ap.add_argument("--music-gain", type=float, default=.2, help="背景音乐的音量，默认 0.2，比音效轻很多")
    a = ap.parse_args()
    proj = a.proj.resolve()
    src = proj / "audio" / "events.json"
    if not src.exists():
        sys.exit("还没有音效表。先跑：python engine/render.py <工程目录> --events")
    if a.music and not a.music.exists():
        sys.exit(f"找不到音乐文件：{a.music}")
    data = json.loads(src.read_text(encoding="utf-8"))
    audio = mix(data["events"], data["end"], a.music, a.music_gain)
    wav = proj / "audio" / "sfx.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((audio * 32767).astype("<i2").tobytes())
    print(f"存好了：{wav}（{len(data['events'])} 个音效{'，加了背景音乐' if a.music else ''}）")
    raw = proj / "renders" / "raw.mp4"
    if not raw.exists():
        print("还没有 renders/raw.mp4，渲完全片再跑一次就能合成成片。")
        return
    final = proj / "renders" / "final.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-i", str(wav), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(final)], check=True)
    print(f"存好了：{final}")


if __name__ == "__main__":
    main()
