# -*- coding: utf-8 -*-
"""下载引擎要用的开源字体（SIL Open Font License），已经有的跳过。

  python get_fonts.py

用 curl 下载：有些 Python 没配好证书，直接用 Python 下载会失败。
"""
import subprocess, sys
from pathlib import Path

DIR = Path(__file__).resolve().parent / "fonts"
BASE = "https://github.com/google/fonts/raw/main/ofl/"
FONTS = [                                                           # （存成的文件名, 在 Google Fonts 仓库里的路径）
    ("NotoSansSC-VF.ttf", "notosanssc/NotoSansSC%5Bwght%5D.ttf"),
    ("NotoSerifSC-VF.ttf", "notoserifsc/NotoSerifSC%5Bwght%5D.ttf"),
    ("JetBrainsMono.ttf", "jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf"),
    ("CormorantGaramond.ttf", "cormorantgaramond/CormorantGaramond%5Bwght%5D.ttf"),
    ("CormorantGaramond-Italic.ttf", "cormorantgaramond/CormorantGaramond-Italic%5Bwght%5D.ttf"),
    ("OFL-NotoSansSC.txt", "notosanssc/OFL.txt"),
    ("OFL-NotoSerifSC.txt", "notoserifsc/OFL.txt"),
    ("OFL-JetBrainsMono.txt", "jetbrainsmono/OFL.txt"),
    ("OFL-CormorantGaramond.txt", "cormorantgaramond/OFL.txt"),
]

DIR.mkdir(exist_ok=True)
failed = []
for name, path in FONTS:
    out = DIR / name
    if out.exists() and out.stat().st_size > 1000:
        print(f"已经有了：{name}")
        continue
    print(f"下载：{name}")
    r = subprocess.run(["curl", "-sSL", "--fail", "-o", str(out), BASE + path])
    if r.returncode != 0:
        failed.append(name)
        out.unlink(missing_ok=True)
sys.exit(f"这几个没下载成功：{', '.join(failed)}" if failed else "字体齐了。")
