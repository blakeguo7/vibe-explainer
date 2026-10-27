# -*- coding: utf-8 -*-
"""按音效表合成声音，再和画面合成成片。

  python audio.py <工程目录>

读 audio/events.json（先跑 render.py --events），写出 audio/sfx.wav；
如果 renders/raw.mp4 已经渲好，就合成 renders/final.mp4。
只有音效，没有背景音乐。每种声音都是用数学现场合成的，不用任何录音素材。

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
下面四种是轻音，给画面里频繁出现的小动作用，音量本来就小，连着用也不吵：
  tap     一声很轻的木头"笃"：卡片落位、小东西点亮      选项 pitch（半音）
  blip    一声柔和的"嘟"：一步步往下走、一格格亮起；     选项 pitch（半音）
          连着几步时音高依次变（比如 7、4、0），听得出在一步步走
  slide   纸滑过去的"沙"：卡片、单子、面板滑进滑出
  keys    一串轻轻的打字声：命令行里打字               选项 dur（秒）、rate（每秒几下，默认 12）
每个音效都可以加 gain（音量倍数，默认 1）和 pan（左右，-1 到 1）。

合成前先筛一遍（thin）：thud、stamp、chime、reveal 这几种重音全留；
其余的轻音，离上一声不到 1.5 秒就去掉，免得挤成一片，去掉了哪几个会打印出来。
一串有节奏的动作（比如一路扫过去、一格格亮起）想全留，就在选项里写 keep: 1。
render.py --check 用的是同一个筛子，会提前报出哪些地方太密。
"""
import json, subprocess, sys, wave
from pathlib import Path
import numpy as np

HEAVY = {"thud", "stamp", "chime", "reveal"}           # 重音：这一镜最关键的那一下，全留
MIN_GAP = 1.5                                          # 轻音离上一声至少隔这么多秒


def thin(events):
    """筛一遍音效表，返回 (留下的, 去掉的)。
    重音全留；写了 keep 的照留；其余的轻音离上一个留下的声音不到 MIN_GAP 秒，就去掉。hush 是静音，不算一声。"""
    kept, dropped, last = [], [], -1e9
    for e in sorted(events, key=lambda e: e[0]):
        t, name, o = e[0], e[1], (e[2] if len(e) > 2 and e[2] else {})
        if name == "hush" or name in HEAVY or o.get("keep") or t - last >= MIN_GAP:
            kept.append(e)
            if name != "hush":
                last = t
        else:
            dropped.append(e)
    return kept, dropped

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


def s_tap(o):
    t = secs(.08)
    f = 620 * 2 ** (o.get("pitch", 0) / 12)
    body = np.sin(2 * np.pi * f * t) * np.exp(-t / .016)
    knock = lowpass(noise(len(t), 17), 2200) * np.exp(-t / .004) * .6
    return attack(body + knock, 1) * .3


def s_blip(o):
    t = secs(.14)
    f = 784 * 2 ** (o.get("pitch", 0) / 12)
    tone = np.sin(2 * np.pi * f * t) + .25 * np.sin(4 * np.pi * f * t)
    return attack(tone * np.exp(-t / .045), 4) * .2


def s_slide(o):
    t = secs(.22)
    n = noise(len(t), 21)
    band = lowpass(n, 5000) - lowpass(n, 1400)
    return band * np.sin(np.pi * t / t[-1]) ** 2 * .35


def s_keys(o):
    """一串打字声：每一下的时刻和轻重都由固定的种子决定，同一张表合成两次一模一样。"""
    d, rate = o.get("dur", 1.5), o.get("rate", 12)
    out, rng = np.zeros(int(d * SR) + int(.05 * SR)), np.random.default_rng(29)
    hit = secs(.03)
    for k in range(int(d * rate)):
        i = int((k + rng.uniform(-.3, .3)) / rate * SR)
        if i < 0:
            continue
        click = lowpass(noise(len(hit), 100 + k), 3000) * np.exp(-hit / .005) + np.sin(2 * np.pi * 320 * hit) * np.exp(-hit / .008) * .5
        out[i:i + len(hit)] += click[:len(out) - i] * rng.uniform(.6, 1)
    return out * .12


SOUNDS = {"tick": s_tick, "pop": s_pop, "thud": s_thud, "stamp": s_stamp, "chime": s_chime,
          "reveal": s_reveal, "rise": s_rise, "swish": s_swish, "noise": s_noise,
          "tap": s_tap, "blip": s_blip, "slide": s_slide, "keys": s_keys}


def mix(events, end):
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
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    proj = Path(sys.argv[1]).resolve()
    src = proj / "audio" / "events.json"
    if not src.exists():
        sys.exit("还没有音效表。先跑：python engine/render.py <工程目录> --events")
    data = json.loads(src.read_text(encoding="utf-8"))
    events, dropped = thin(data["events"])
    if dropped:
        shown = "、".join(f"第 {e[0]:g} 秒 {e[1]}" for e in dropped[:8]) + ("……" if len(dropped) > 8 else "")
        print(f"去掉了 {len(dropped)} 个挨得太近的轻音（离上一声不到 {MIN_GAP:g} 秒）：{shown}")
    audio = mix(events, data["end"])
    wav = proj / "audio" / "sfx.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((audio * 32767).astype("<i2").tobytes())
    print(f"存好了：{wav}（{len(events)} 个音效，平均每 {data['end'] / max(1, len(events)):.1f} 秒一声）")
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
