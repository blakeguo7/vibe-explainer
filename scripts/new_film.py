# -*- coding: utf-8 -*-
"""建一个新片工程。

  python new_film.py <工程目录> [--canvas 16:9|9:16] [--force]

建出来四个文件：
  look.md         外观卡，按 references/look.md 现推，先写它
  storyboard.md   分镜表，按 references/explain.md 写
  film.js         代码骨架：LOOK 照外观卡填，SUBS 照分镜表填，画面一镜一镜现写
  index.html      页面，不用改（长片按章拆文件时，在这里加 <script>）
引擎留在 skill 目录里，由 engine/render.py 挂载。
"""
import argparse, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LOOK_MD = """# 外观卡：《片名》

为什么这样选：题材是……；语气是……；主体主要是……；观众在……看。

底：
颜色：（每种一个意思，全片不破例）
  ink      #……  主体字
  dim      #……  标注
  accent   #……  = ……（字幕里 {词} 用它）
  warn     #……  = ……（字幕里 {!词} 用它）
字体：字幕 …… / 大字 …… / 小标 ……
画法：
辉光：
字幕：字号 ……，出现方式 ……，每句停留约 …… 秒，有没有英文行
常驻元素：
转场：
片名卡：
音色：
"""

STORYBOARD_MD = """# 分镜表：《片名》

论点：
全片的形象：
尺子：
外观卡：look.md
同一个画面的几镜：

| # | 时间 | 字幕 | 演法 | 屏上是什么，在干什么 | 小字 | 观众明白了什么 | 声音 |
|---|---|---|---|---|---|---|---|
| 1 | 0.5–4.5 |  |  |  |  |  |  |

数的来历：
示意的地方：
估出来的时长：（python scripts/estimate.py <工程目录> --hold 每句停留秒数）
"""

FILM_JS = """/* 《片名》
 * 外观卡在 look.md，分镜表在 storyboard.md。LOOK 照外观卡填，SUBS 照分镜表填。
 * 每一镜现写；函数头上先写一行：这是什么 / 它在干什么 / 观众明白了什么。 */
(function () {
'use strict';
const { clamp, lerp, prog, soft, env, ease, keys, zoom, rng, count, fmt, rgba, mix } = VE;

/* 外观：数值全部来自 look.md。改外观先改卡，再改这里 */
const LOOK = {
  canvas: '__CANVAS__',                                     // '16:9' 横屏，'9:16' 竖屏
  bg: { type: 'solid', color: '#0A0C10' },                  // type：solid 纯色 / stars 星点 / grid 网格 / paper 纸面
  colors: {                                                 // 每种颜色全片一个意思
    ink: '#EEF1F4',                                         // 主体字
    dim: '#808B96',                                         // 标注
    accent: '#F2C46D',                                      // 字幕里 {词} 用它：……
    warn: '#EF5A6F',                                        // 字幕里 {!词} 用它：……
  },
  bloom: .6, grain: .04, vignette: .4,                      // 辉光、颗粒、四角压暗
  subs: { font: 'sans', weight: 500, mode: 'fade' },        // mode：fade 整行淡入 / type 逐字亮起 / focus 逐字由虚变实
};

const T = { end: 30 };                                      // end 是全片时长，按分镜表算出来再改；关键时刻也集中写在这里
const SUBS = [                                              // 一句一行，和分镜表对着写
  // { a: 0.8, b: 4.2, zh: '……' },
];
const SFX = [                                               // [时刻, 名字, 选项]：小动作一声轻的，关键那一下重的
  // [1.4, 'slide', { gain: .6 }],
  // [3.2, 'thud'],
];

/* 第一镜：这是什么 / 它在干什么 / 观众明白了什么 */
function shot1(f, t) {
}

VE.film({
  look: LOOK, dur: T.end, subs: SUBS, sfx: SFX,
  draw(f, t) {
    shot1(f, t);
  },
});
})();
"""


def main():
    ap = argparse.ArgumentParser(description="建一个新片工程")
    ap.add_argument("proj", type=Path)
    ap.add_argument("--canvas", choices=["16:9", "9:16"], default="16:9")
    ap.add_argument("--force", action="store_true", help="覆盖已有的文件")
    a = ap.parse_args()
    proj = a.proj.resolve()
    proj.mkdir(parents=True, exist_ok=True)
    files = {"look.md": LOOK_MD, "storyboard.md": STORYBOARD_MD, "film.js": FILM_JS.replace("__CANVAS__", a.canvas)}
    exists = [n for n in list(files) + ["index.html"] if (proj / n).exists()]
    if exists and not a.force:
        sys.exit(f"这些文件已经存在：{', '.join(exists)}。要覆盖，加 --force。")
    for name, text in files.items():
        (proj / name).write_text(text, encoding="utf-8", newline="\n")
    shutil.copy(ROOT / "engine" / "index.html", proj / "index.html")
    render = ROOT / "engine" / "render.py"
    print(f"建好了：{proj}（{a.canvas}）\n"
          f"  先写 look.md 和 storyboard.md，再写 film.js\n"
          f"  预览  python \"{render}\" \"{proj}\" --serve\n"
          f"  截图  python \"{render}\" \"{proj}\" --stills 2 5")


if __name__ == "__main__":
    main()
