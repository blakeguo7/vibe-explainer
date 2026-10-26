# -*- coding: utf-8 -*-
"""按分镜表估全片时长。

  python estimate.py <工程目录或 storyboard.md> [--hold 4]

数分镜表里有字幕的句子，再按每句停留的秒数估出全片多长。
--hold 是外观卡里写的每句停留秒数：一行中文、逐字亮起的约 3 秒；带英文行、整行淡入的约 5 秒。
"""
import argparse, sys
from pathlib import Path

EMPTY = {"", "（无）", "(无)", "无", "—", "-"}


def count_lines(text):
    """数分镜表里有字幕的行：表头里写着"字幕"的那一列，跳过分隔行和写着（无）的行。"""
    n, col, in_table = 0, None, False
    for row in text.splitlines():
        s = row.strip()
        if not s.startswith("|"):
            in_table = False
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not in_table:                                            # 一张表的第一行是表头
            in_table, col = True, (cells.index("字幕") if "字幕" in cells else None)
            continue
        if col is None or set(s) <= set("|-: "):                    # 不是分镜表，或者是分隔行
            continue
        if col < len(cells) and cells[col] not in EMPTY:
            n += 1
    return n


def estimate_seconds(lines, hold, title=4.0, bare=.3):
    """lines 句字幕、每句停留 hold 秒，全片大约多少秒。

    字幕之外，片名卡固定占 title 秒；转场和画面自己演的段落，约占其余时间的 bare（三成）。"""
    return title + lines * hold / (1 - bare)


def main():
    ap = argparse.ArgumentParser(description="按分镜表估全片时长")
    ap.add_argument("path", type=Path)
    ap.add_argument("--hold", type=float, default=4.0, help="每句字幕停留的秒数")
    a = ap.parse_args()
    path = a.path / "storyboard.md" if a.path.is_dir() else a.path
    if not path.exists():
        sys.exit(f"找不到分镜表：{path}")
    n = count_lines(path.read_text(encoding="utf-8"))
    if n == 0:
        sys.exit("分镜表里没找到字幕。表头里要有一列叫'字幕'。")
    s = estimate_seconds(n, a.hold)
    print(f"有字幕的句子 {n} 句，每句停留约 {a.hold:g} 秒，全片约 {s:.0f} 秒（{s / 60:.1f} 分钟）。")


if __name__ == "__main__":
    main()
