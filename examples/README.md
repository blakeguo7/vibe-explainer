# 例子

这里的东西是"我们自己做过一次"，不是零件库。新片的每一镜都照自己的分镜表现写，不要把这里的路由器、信封搬过去。
能带走的是做法：先写外观卡和分镜表、实心的东西画在底层、连线画在设备下面、截图看过再改。

`engine-tour/`：引擎演示《数据包》，15 秒，蓝图外观。一个小信封经过几台路由器，前面的线断了就绕路。
它的用处是演示引擎怎么用：外观卡怎么变成 `LOOK`、底层的实心机器、沿路走的数据包、逐字亮起的字幕、计数、片名卡、闪、音效表。
工程里四个文件齐全（`look.md`、`storyboard.md`、`film.js`、`index.html`），`demo.gif` 是成片的缩小预览。
想要原尺寸带声音的成片，照下面的命令渲一遍，会生成 `renders/final.mp4`。

```bash
python engine/render.py examples/engine-tour --serve      # 预览
python engine/render.py examples/engine-tour --sheet 16   # 拼图
python engine/render.py examples/engine-tour --check      # 自动检查
python engine/render.py examples/engine-tour --jobs 3 && python engine/render.py examples/engine-tour --events && python engine/audio.py examples/engine-tour
```

以后每做完一条满意的片子，挑一段放进来，写清楚它的形象、尺子和外观卡是怎么定的。
