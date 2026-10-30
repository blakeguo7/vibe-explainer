# -*- coding: utf-8 -*-
"""vibe-explainer 的预览、截图、渲染和自动检查。

  python render.py <工程目录> --serve              浏览器预览：http://127.0.0.1:8765/?play（空格暂停，左右键跳 2 秒）
  python render.py <工程目录> --stills 2.5 9       原尺寸截几帧，存进 review/
  python render.py <工程目录> --sheet 16           全片均匀取 16 帧拼一张；也可以写具体时刻：--sheet 3 8.5 20
  python render.py <工程目录> --motion 8 10.5      这段时间里均匀取 12 帧拼一张，看转场
  python render.py <工程目录> --clip 0 30 head     只渲 0–30 秒，存成 renders/head.mp4
  python render.py <工程目录>                      渲全片，存成 renders/raw.mp4（没有声音）
  python render.py <工程目录> --jobs 4             全片分 4 段同时渲，再拼起来
  python render.py <工程目录> --check              自动检查：同一帧渲两次一样吗、字幕会不会太宽太快、字幕区有没有被占；另外提醒音效太密的地方
  python render.py <工程目录> --events             导出音效表 audio/events.json，交给 audio.py

工程目录里放 index.html 和 film.js；引擎由这里的小服务器挂在 /engine/ 下。
"""
import argparse, base64, http.server, io, json, subprocess, sys, threading, time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import unquote

from audio import MIN_GAP, thin                                     # 音效太不太密，和合成时用同一个筛子判断

ENGINE = Path(__file__).resolve().parent


def serve(proj, port):
    """起一个只给本机用的小服务器：/engine/… 指向引擎目录，其余指向工程目录。"""
    roots = {"engine": ENGINE.resolve(), "proj": proj.resolve()}

    class Handler(http.server.SimpleHTTPRequestHandler):
        def translate_path(self, path):
            p = unquote(path.split("?", 1)[0].split("#", 1)[0])
            base, rest = (roots["engine"], p[len("/engine/"):]) if p.startswith("/engine/") else (roots["proj"], p.lstrip("/") or "index.html")
            target = (base / rest).resolve()
            return str(target) if target.is_relative_to(base) else str(base / "__missing__")

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def log_message(self, *args):
            pass

    class Server(http.server.ThreadingHTTPServer):
        request_queue_size = 128                                    # 几路同时渲染时，浏览器会一下子要很多文件，默认的 5 个排不下
        daemon_threads = True

    srv = Server(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@contextmanager
def open_film(proj):
    """打开工程，等字体就绪；film.js 出错时直接报出来。"""
    from playwright.sync_api import sync_playwright
    srv = serve(proj, 0)
    errors = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome")
            pg = browser.new_page(viewport={"width": 1920, "height": 1920}, device_scale_factor=1)
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.on("console", lambda m: m.type == "error" and errors.append(f"{m.text}（{m.location.get('url', '')}）"))
            for attempt in range(3):                                    # 文件偶尔没加载上（机器很忙时），重新打开页面再试
                errors.clear()
                pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/?render")
                for _ in range(600):
                    if errors or pg.evaluate("window.READY === true"):
                        break
                    time.sleep(0.1)
                else:
                    sys.exit("等了 60 秒，画面还没准备好。检查字体是否齐全（python engine/get_fonts.py）。")
                if not errors:
                    break
                if attempt == 2 or not all("Failed to load resource" in e for e in errors):
                    sys.exit("film.js 出错了：\n  " + "\n  ".join(errors))
                time.sleep(1)
            w, h = pg.evaluate("SIZE")
            pg.set_viewport_size({"width": w, "height": h})
            pg.film = {"end": pg.evaluate("END"), "fps": pg.evaluate("FPS"), "size": (w, h)}
            pg.errors = errors
            yield pg
            browser.close()
    finally:
        srv.shutdown()


def shot(pg, t, fmt="png"):
    """画出第 t 秒，直接从画布导出图片。静帧和检查用无损的 PNG；视频用高质量 JPEG，快五倍，压成视频后看不出差别。"""
    url = pg.evaluate("([t, f]) => (seek(t), document.getElementById('ve').toDataURL(f, .97))", [t, f"image/{fmt}"])
    if pg.errors:
        sys.exit(f"第 {t:.2f} 秒出错了：\n  " + "\n  ".join(pg.errors))
    return base64.b64decode(url.split(",", 1)[1])


def tstr(t):
    return f"{t:.2f}".rstrip("0").rstrip(".")


def contact_sheet(images, labels, out):
    """把几帧缩小拼成一张，左下角标上时刻。"""
    from PIL import Image, ImageDraw, ImageFont
    first = Image.open(io.BytesIO(images[0]))
    w, h = first.size
    cols = (4 if w > h else 6) if len(images) > 6 else max(1, min(len(images), 3 if w > h else 4))
    tw = 1920 // cols if w > h else 1620 // cols
    th = round(tw * h / w)
    rows = -(-len(images) // cols)
    sheet = Image.new("RGB", (cols * tw + (cols + 1) * 6, rows * th + (rows + 1) * 6), (24, 24, 24))
    font = ImageFont.load_default(size=max(14, tw // 22))
    for i, (data, label) in enumerate(zip(images, labels)):
        im = Image.open(io.BytesIO(data)).convert("RGB").resize((tw, th), Image.LANCZOS)
        x, y = 6 + (i % cols) * (tw + 6), 6 + (i // cols) * (th + 6)
        sheet.paste(im, (x, y))
        d = ImageDraw.Draw(sheet)
        box = d.textbbox((0, 0), label, font=font)
        d.rectangle([x, y + th - box[3] - 10, x + box[2] + 12, y + th], fill=(0, 0, 0))
        d.text((x + 6, y + th - box[3] - 6), label, fill=(255, 255, 255), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=90)
    print(f"存好了：{out}")


def encode(pg, n0, n1, out, quiet=False):
    """把第 n0 帧到第 n1 帧（不含）逐帧截图，管道送进 ffmpeg。"""
    fps = pg.film["fps"]
    out.parent.mkdir(parents=True, exist_ok=True)
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(fps), "-i", "-",
                           "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
                          stdin=subprocess.PIPE)
    start = time.time()
    for i, n in enumerate(range(n0, n1)):
        ff.stdin.write(shot(pg, n / fps, "jpeg"))
        if not quiet and (i % 30 == 0 or n == n1 - 1):
            rate = (i + 1) / max(time.time() - start, 1e-6)
            print(f"\r{out.name}：{i + 1}/{n1 - n0} 帧，每秒 {rate:.1f} 帧", end="", flush=True)
    ff.stdin.close()
    if ff.wait() != 0:
        sys.exit("ffmpeg 出错了。")
    if not quiet:
        print(f"\n存好了：{out}")


def render_parallel(proj, jobs):
    with open_film(proj) as pg:
        total = round(pg.film["end"] * pg.film["fps"])
        fps = pg.film["fps"]
    cuts = [round(total * i / jobs) for i in range(jobs + 1)]
    parts = [proj / "renders" / f"_part{i}.mp4" for i in range(jobs)]
    procs = [subprocess.Popen([sys.executable, __file__, str(proj), "--frames", str(cuts[i]), str(cuts[i + 1]), parts[i].stem, "--quiet"])
             for i in range(jobs)]
    print(f"分 {jobs} 段同时渲染，共 {total} 帧……")
    if any(p.wait() != 0 for p in procs):
        sys.exit("有一段渲染失败了。")
    lst = proj / "renders" / "_parts.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    out = proj / "renders" / "raw.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)], check=True)
    for p in parts + [lst]:
        p.unlink()
    print(f"存好了：{out}（{total / fps:.1f} 秒）")


def sound_notes(events, end):
    """音效太密的地方。合成时会自动去掉，所以只是提醒，不算问题。返回几行提醒；没有就返回空列表。"""
    kept, dropped = thin(events)
    if not dropped and not (len(events) > 1 and end / len(events) < 3):
        return []
    head = f"登记了 {len(events)} 个音效，平均每 {end / max(1, len(events)):.1f} 秒一声"
    if not dropped:                                                 # 只是平均偏密，一个都不去掉
        return [head + "，比每 3–5 秒一声密一点；不过没有挨得太近的轻音，合成时一个都不会去掉。"]
    notes = [head + f"；有 {len(dropped)} 个轻音离上一声不到 {MIN_GAP:g} 秒，合成时会被去掉，"
             f"剩 {len(kept)} 个，平均每 {end / max(1, len(kept)):.1f} 秒一声。"
             f"要留下的就挪开一点；一串有节奏的动作可以在选项里写 keep: 1。会被去掉的在这些地方："]
    spans = []                                                      # 被去掉的轻音，隔得近的并成一段
    for e in dropped:
        if spans and e[0] - spans[-1][-1][0] <= 3:
            spans[-1].append(e)
        else:
            spans.append([e])
    items = [(f"{tstr(s[0][0])} 秒" if len(s) == 1 else f"{tstr(s[0][0])}–{tstr(s[-1][0])} 秒")
             + " " + "、".join(sorted({e[1] for e in s})) for s in spans]
    notes += ["；".join(items[i:i + 4]) for i in range(0, len(items), 4)]          # 一行放四段
    return notes


def check(pg):
    """能让程序查的，都在这里查。返回 (问题, 提醒)：问题要改；提醒是音效太密，合成时会自动处理。"""
    end, problems = pg.film["end"], []

    for t in (end * .2, end * .5, end * .8):                       # 1. 同一帧渲两次必须一模一样
        if shot(pg, t) != shot(pg, t):
            problems.append(f"第 {tstr(t)} 秒：同一帧渲两次不一样。检查有没有用 Math.random()、Date.now() 或跨帧保存的状态。")

    for s in pg.evaluate("subWidths()"):                            # 2. 字幕会不会超出左右边距
        if s["width"] > s["limit"]:
            problems.append(f"第 {tstr(s['a'])} 秒的字幕太宽（{s['width']}px，最多 {s['limit']}px）：{s['zh']}")

    subs = sorted(pg.evaluate("SUBS"), key=lambda s: s["a"])        # 3. 字幕读不读得完、会不会叠在一起
    for s, nxt in zip(subs, subs[1:] + [None]):
        n = len("".join(ch for ch in s["zh"] if ch not in "{}!"))
        stay = s["b"] - s["a"]
        if stay < 1.2 or n / stay > 7:
            problems.append(f"第 {tstr(s['a'])} 秒的字幕停留太短（{stay:.1f} 秒读 {n} 个字，每秒最多 7 个字）：{s['zh']}")
        if nxt and s["b"] > nxt["a"]:
            problems.append(f"第 {tstr(s['a'])} 秒和第 {tstr(nxt['a'])} 秒的字幕叠在一起了。")

    bad = []                                                        # 4. 字幕区里有没有画面伸进来
    steps = max(1, int(end / .5))
    for i in range(steps + 1):
        t = min(end, i * .5)
        if pg.evaluate("t => probe(t)", t) > .002:
            bad.append(t)
    if bad:
        spans, a = [], bad[0]
        for x, y in zip(bad, bad[1:] + [None]):
            if y is None or y - x > .51:
                spans.append((a, x)); a = y
        for a, b in spans:
            problems.append(f"第 {tstr(a)}–{tstr(b)} 秒：有画面伸进了字幕区。")
    return problems, sound_notes(pg.evaluate("events()"), end)            # 5. 音效太不太密


def main():
    ap = argparse.ArgumentParser(description="vibe-explainer：预览、截图、渲染、检查")
    ap.add_argument("proj", type=Path)
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--stills", nargs="+", type=float)
    ap.add_argument("--sheet", nargs="+", type=float)
    ap.add_argument("--motion", nargs="+", type=float, metavar="T")
    ap.add_argument("--clip", nargs=3, metavar=("A", "B", "NAME"))
    ap.add_argument("--frames", nargs=3, metavar=("N0", "N1", "NAME"), help=argparse.SUPPRESS)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--events", action="store_true")
    ap.add_argument("--quiet", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    proj = a.proj.resolve()
    if not (proj / "film.js").exists():
        sys.exit(f"{proj} 里没有 film.js。先用 scripts/new_film.py 建工程。")

    if a.serve:
        serve(proj, a.port)
        print(f"预览：http://127.0.0.1:{a.port}/?play （空格暂停，左右键跳 2 秒；?t=12 停在第 12 秒）。按 Ctrl+C 结束。")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return

    if a.jobs > 1 and not (a.stills or a.sheet or a.motion or a.clip or a.check or a.events):
        render_parallel(proj, a.jobs)
        return

    with open_film(proj) as pg:
        end, fps = pg.film["end"], pg.film["fps"]
        review = proj / "review"
        if a.stills:
            review.mkdir(exist_ok=True)
            for t in a.stills:
                out = review / f"still_{tstr(t)}.png"
                out.write_bytes(shot(pg, t))
                print(f"存好了：{out}")
        elif a.sheet:
            ts = [end * (i + .5) / int(a.sheet[0]) for i in range(int(a.sheet[0]))] if len(a.sheet) == 1 else a.sheet
            contact_sheet([shot(pg, t) for t in ts], [f"{tstr(t)}s" for t in ts], review / "sheet.jpg")
        elif a.motion:
            t0, t1 = a.motion[0], a.motion[1]
            n = int(a.motion[2]) if len(a.motion) > 2 else 12
            ts = [t0 + (t1 - t0) * i / (n - 1) for i in range(n)]
            contact_sheet([shot(pg, t) for t in ts], [f"{tstr(t)}s" for t in ts], review / f"motion_{tstr(t0)}-{tstr(t1)}.jpg")
        elif a.clip:
            t0, t1 = float(a.clip[0]), min(float(a.clip[1]), end)
            encode(pg, round(t0 * fps), round(t1 * fps), proj / "renders" / f"{a.clip[2]}.mp4")
        elif a.frames:
            encode(pg, int(a.frames[0]), int(a.frames[1]), proj / "renders" / f"{a.frames[2]}.mp4", quiet=a.quiet)
        elif a.check:
            problems, notes = check(pg)
            if notes:
                print("提醒：音效有点密（不算问题）。" + notes[0])
                for n in notes[1:]:
                    print("  " + n)
            if problems:
                print(f"发现 {len(problems)} 个问题：")
                for p in problems:
                    print("  - " + p)
                sys.exit(1)
            print("自动检查都通过了：同一帧渲两次一样；字幕宽度和停留时间合适；字幕区没有被画面占用。"
                  + ("" if notes else "音效疏密也合适。"))
        elif a.events:
            ev = pg.evaluate("events()")
            out = proj / "audio" / "events.json"
            out.parent.mkdir(exist_ok=True)
            out.write_text(json.dumps({"end": end, "fps": fps, "events": ev}, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"存好了：{out}（{len(ev)} 个音效）")
        else:
            encode(pg, 0, round(end * fps), proj / "renders" / "raw.mp4")


if __name__ == "__main__":
    main()
