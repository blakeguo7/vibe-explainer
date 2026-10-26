# 引擎：命令、写法，和怎么把外观卡变成代码

一张 Canvas，一个 `seek(t)`。**每一帧只由时间 t 决定**：没有时间线对象，没有跨帧的状态。
所以能跳着截图、只渲一段、分几段同时渲，同一帧渲两次一模一样。

```
engine/
  ve.js         引擎：时间工具、画面对象 f（画线、画字、画光）、四种底、字幕、出帧（辉光、暗角、颗粒）
  index.html    页面模板（new_film.py 会拷进工程）
  render.py     预览、截图、拼图、渲染、自动检查、导出音效表
  audio.py      按音效表合成声音，再和画面合成成片
  get_fonts.py  字体缺了就下载
  fonts/        开源字体和它们的许可文件
```

工程目录里放 `look.md`（外观卡）、`storyboard.md`（分镜表）、`film.js`、`index.html`。引擎由 `render.py` 里的小服务器挂在 `/engine/` 下。

## 一、命令

```bash
python scripts/new_film.py <工程目录> [--canvas 16:9|9:16]   # 建工程
python scripts/estimate.py <工程目录> --hold 4                # 按分镜表估时长
python engine/render.py <工程目录> --serve                    # 预览 http://127.0.0.1:8765/?play（空格暂停，左右键跳 2 秒）
python engine/render.py <工程目录> --stills 2.5 8.5           # 原尺寸截几帧 → review/
python engine/render.py <工程目录> --sheet 16                 # 全片均匀 16 帧拼一张 → review/sheet.jpg；也可以写具体时刻
python engine/render.py <工程目录> --motion 8.2 10.6          # 这段时间里取 12 帧拼一张，看转场
python engine/render.py <工程目录> --clip 0 30 head           # 只渲 0–30 秒 → renders/head.mp4
python engine/render.py <工程目录> --check                    # 自动检查（见 review.md 第四节）
python engine/render.py <工程目录> --jobs 4                   # 全片分 4 段同时渲 → renders/raw.mp4（没有声音）
python engine/render.py <工程目录> --events                   # 导出音效表 → audio/events.json
python engine/audio.py <工程目录>                             # 合成音效，和画面合成 → renders/final.mp4
python engine/audio.py <工程目录> --music 音乐.mp3             # 同上，再加一段背景音乐（只在用户要求时）
```

速度：演示片实测单路每秒约 40 帧（一分钟成片不到一分钟）；画面越复杂越慢，长片用 `--jobs 4` 分段同时渲。先看拼图，再渲片段，最后才渲全片。
依赖：Python 的 `playwright`（用本机安装的 Chrome）、`numpy`、`Pillow`、`scipy`（可选），以及 `ffmpeg`。字体缺了跑 `python engine/get_fonts.py`。

## 二、film.js 的样子

```js
(function () {
'use strict';
const { prog, soft, env, ease, keys, zoom, rng, count } = VE;

const LOOK = { … };                                  // 照外观卡填，见第三节
const T = { end: 42, hook: [0, 8], title: 8.4 };     // 关键时刻集中写在这里，挪动时只改一处
const SUBS = [ { a: 0.6, b: 3.8, zh: '一本一千页的书，{锁}字在哪一页？' }, … ];
const SFX = [ [1.2, 'thud'], [T.title, 'chime'] ];

/* 一镜一个函数；函数头上写：这是什么 / 它在干什么 / 观众明白了什么 */
function book(f, t, a) { … }

VE.film({
  look: LOOK, dur: T.end, subs: SUBS, sfx: SFX,
  draw(f, t) {
    f.scene(0, 9, (lt, a) => book(f, t, a));         // 相邻两个场景的时间窗重叠半秒，各自淡入淡出，不会硬切
    f.scene(8.3, 14, lt => f.titleCard(lt, { zh: '索引', sub: '为什么快' }));
    f.flash(T.title);
  },
});
})();
```

字幕不用自己画：`SUBS` 交给 `VE.film`，引擎会在最上层按外观卡的样式画。长片超过 400 行就按章拆文件：
在 `index.html` 里 `film.js` 前面加 `<script src="ch1.js"></script>`，每个文件往 `window.CH` 上挂自己的函数，`film.js` 只留字幕表和调度。

## 三、外观卡怎么变成代码

外观卡（`look.md`）里的每一项，都对应 `LOOK` 里的一个字段：

```js
const LOOK = {
  canvas: '16:9',                                    // 画幅：'16:9' 或 '9:16'
  bg: { type: 'grid', color: '#0B1826', glow: '#163650', glowA: .5, line: '#4C7FA8', step: 48 },
  colors: { ink: '#E6EEF5', dim: '#8AA3B8', accent: '#FFB547', warn: '#FF6B6B', cool: '#5CC8FF' },
  bloom: .45, grain: .035, vignette: .5,             // 辉光、颗粒、四角压暗，都是 0 到 1
  subs: { font: 'sans', weight: 500, size: 44, mode: 'type', shadow: .7 },
};
```

- **底 `bg`**：`type` 是 `solid`（纯色）、`stars`（暗场加细星点，`stars` 个数）、`grid`（网格，`line` 线色、`step` 间距）、`paper`（纸面斑驳，`mottle` 程度）。
  都可以加 `glow`、`glowA`：中间一团淡淡的光。更复杂的底（一整幅场景）在 `draw` 里用 `f.under()` 画。
- **颜色 `colors`**：名字自己起，一个名字一个意思。`ink`（主体字）、`dim`（标注）、`accent`（字幕里 `{词}` 的颜色）、`warn`（字幕里 `{!词}` 的颜色）是引擎默认会用到的四个。
  画的时候写名字就行：`f.text('…', x, y, { color: 'accent' })`。
- **字幕 `subs`**：`font`（`sans` 黑体 / `serif` 宋体）、`weight`、`size`、`mode`（`fade` 整行淡入 / `type` 逐字亮起 / `focus` 逐字由虚变实）、
  `shadow`（投影浓度）、`plate`（字幕底板浓度，亮底时用）、`y`（字幕中线在画面高度的比例）、`en`（英文行的样式；写 `false` 不要英文行）。
  不写 `size` 和 `y` 时，引擎按画幅给默认值：横屏字幕在 87% 高度，竖屏在 76% 高度。
- **辉光 `bloom`**：0 到 1。暗场、以字和线为主的开大一点；有大块实心东西、亮底的开小或者关掉。`draw` 里写 `f.bloom = .2` 只改这一帧。

## 四、时间

| | |
|---|---|
| `prog(t, a, b)` | t 在 a 到 b 之间走到哪了，0 到 1，两头夹住 |
| `soft(t, a, b)` | 同上，再平滑一下。最常用：某个量在 a 到 b 秒之间从 0 变到 1 |
| `env(t, a, b, fin, fout)` | 出现、停留、消失：a 起经 fin 秒亮起，b 前 fout 秒暗下 |
| `ease.out / in / inOut / outExpo / outBack / lin` | 缓动。进场用 `out`，位移用 `inOut`，数字滚动用 `out` |
| `keys([[t, 值], …], t)` | 关键帧，值可以是数或者 `[x, y]`；机位、轨迹用它 |
| `zoom(s0, s1, k)` | 推拉镜头的缩放，在对数里走，不会先慢后猛冲 |
| `count(t, a, b, 从, 到)` | 数字滚上去，先快后慢；`fmt(n)` 加千分位 |
| `dip(t, [t1, t2…], half)` | "暗一下"的程度，交给 `f.darken()` |
| `rng(种子)`、`hash(n)`、`wobble(x)` | 确定的随机数和平滑抖动。**不要用 `Math.random()` 和 `Date.now()`** |

**模拟要真算，但要能回放。** 载入时把整场模拟算完存成表，每帧按时间查表；成千上万个小东西，每个的出发时刻和路径由它的序号决定，
某一帧的位置用"t 减出发时刻"直接算出来，不要一帧一帧累加。

## 五、画面对象 f

`f.t` 当前时间，`f.frame` 帧号，`f.W`、`f.H` 画布尺寸，`f.safe` 主体能用的范围，`f.x` 原生的 2D 画笔。
**位置尽量按 `f.W`、`f.H` 的比例写**，同一份代码换成竖屏时不至于全乱。

**成组**

| | |
|---|---|
| `f.g({ at:[x,y], rot, s, a, add, clip:[x,y,w,h], blur }, fn)` | 在一组位移 / 旋转 / 缩放 / 透明度里画 fn |
| `f.layer({ a, add, blur }, fn)` | 先画到临时画布再整组合成。互相重叠的半透明形状要一起淡入淡出时用它，否则重叠处会透 |
| `f.under(fn)` | 画到底层：有体积的实心东西（机器、书、角色、场景）画在这里，不吃辉光 |
| `f.scene(a, b, fn(lt, k), fin, fout)` | 只在 a 到 b 秒之间画 fn，并乘好淡入淡出；lt 是本地时间 |

**线和形**（最后一个参数是选项：`stroke` 描边色、`fill` 填充、`w` 线宽、`a` 透明度、`dash` 虚线、`add` 加法混合、`cap`）

| | |
|---|---|
| `f.line(x1, y1, x2, y2, o)` | |
| `f.path(pts, o)` | 折线。`o.k`（0 到 1）只画前 k 那么长，线"长出来"就靠它；`o.close` 闭合 |
| `f.along(pts, k)` | 返回 `[x, y, 角度]`：沿折线走到 k 处的位置，给线头安光点、让东西沿路走 |
| `f.circle` `f.arc` `f.ellipse` `f.rect(x, y, w, h, { r })` | `r` 是圆角 |
| `f.grad(x0, y0, x1, y1, [[位置, 色, 透明度], …])` `f.rgrad(cx, cy, r0, r1, stops)` | 线性和径向渐变，交给 `fill` 或 `stroke` |

**光**：`f.glow(x, y, r, 色, a)` 一团柔光；`f.dot(x, y, r, 色, a)` 光点（白芯加色晕）。

**字**：`f.text(str, x, y, o)` 返回宽度。选项：`font`（`sans` / `serif` / `mono` / `latin`）、`weight`、`size`、`italic`、`color`、`a`、
`align`（`c` / `l` / `r`）、`track`（字距，像素）、`shadow`、`blur`。
`f.chars(str, x, y, o, per)` 逐字画：`per(i, 字)` 返回 `{ a, color, blur, dy, s }` 改这个字的样子，逐字显影、打字、单字变色都用它。
`f.measure(str, o)` 只量宽度。`latin` 字体的数字高低不齐，数字用另外三种。

**片名卡**：`f.titleCard(lt, { zh, sub, en, font, weight, size, y, color, subColor, line })`：大字逐字由虚变实，一条细线展开，副题和外文随后淡入。lt 是片名卡的本地时间。
片名卡的样子由外观卡决定；需要别的样子，就在 `film.js` 里自己画。

**全幅效果**：`f.flash(t0, { rise, fall, color, peak })` 闪一下；`f.darken(a)` 整幅压暗（配合 `dip`）。

## 六、声音

`film.js` 里的 `SFX` 表登记音效：`[时刻, 名字, 选项]`。名字和选项见 `audio.py` 开头的说明：
`tick` `pop` `thud` `stamp` `chime` `reveal` `rise` `swish` `noise` `hush`，都可以加 `gain`（音量倍数）和 `pan`（左右）。
登记多少，见 `SKILL.md` 第 8 步：只给关键的那几下。

背景音乐默认不加。用户要时，`audio.py` 加 `--music 音乐文件`（mp3、wav、m4a 都行）：
音乐比片子短就从头循环，开头 1 秒淡入、结尾 2.5 秒淡出；音效响的时候，音乐自动降低六成左右，不盖过音效；
`--music-gain` 调整体音量，默认 0.2。`hush` 静音的那几秒，音乐也一起静下来。

## 七、容易踩的坑

- **字幕区被占。** 横屏纵向 80%–95%、竖屏 70%–82% 只属于字幕。`--check` 会报出被占的时间段。
- **相邻两场硬切。** `if (t < 17) a(); else b();` 会切。用 `f.scene` 让两个时间窗重叠半秒。
- **辉光过曝。** 内容层越亮光晕越大。实心的大色块画进 `f.under()`，或者把 `bloom` 调低。
- **线压在东西上。** 线在内容层、东西在底层时，线会盖住东西。把线也画进底层，先画线再画东西。
- **推拉镜头。** 跨几个数量级的推近拉远，用 `zoom()` 算缩放；自己把点换算到屏幕坐标，不要直接缩放画布，线宽和字号才不会跟着变。
- **一帧画太多。** 上千个粒子用 `f.x.fillRect`，别每个都开模糊；慢的准备工作（算模拟、取字形）放在载入时，算好存起来。
- **时间写死在好几处。** 每场开头定一个本地时间 `lt = t - 开始时刻`，场内全用它；整场挪动时只改一个数。
