/* 引擎演示：一个数据包找路（15 秒）
 * 外观卡是 looks/blueprint.md（蓝图）。这条片用来演示引擎怎么用：画在底层的实心机器、沿路走的数据包、
 * 逐字亮起的字幕、计数、片名卡、闪、音效表。新片照自己的分镜表现写，不要从这里搬画面。 */
(function () {
'use strict';
const { prog, soft, ease } = VE;

/* 外观：数值来自 looks/blueprint.md */
const LOOK = {
  canvas: '16:9',
  bg: { type: 'grid', color: '#0B1826', glow: '#163650', glowA: .5, line: '#4C7FA8', step: 48 },
  colors: {
    ink: '#E6EEF5',                                         // 主体字
    dim: '#8AA3B8',                                         // 标注
    accent: '#FFB547',                                      // 数据，正在走的东西
    cool: '#5CC8FF',                                        // 设备和线路，平常的状态
    warn: '#FF6B6B',                                        // 故障、断开
  },
  bloom: .45, grain: .035, vignette: .5,
  subs: { font: 'sans', weight: 500, mode: 'type', shadow: .7 },
};

const P = { pc: [240, 480], r1: [640, 330], r2: [960, 560], r3: [1280, 330], r4: [1180, 720], r5: [1500, 700], sv: [1680, 480] };
const LEG1 = [P.pc, P.r1, P.r2], LEG2 = [P.r2, P.r4, P.r5, P.sv];   // 原路是 r2 → r3 → 服务器；r2 到 r3 断了以后绕 r4、r5
const T = { end: 15, leg1: [1.2, 4.6], cut: 7.2, leg2: [7.8, 10.6], title: 11.1 };

const SUBS = [
  { a: 0.6, b: 3.6, zh: '一个数据包，从你的电脑出发。' },
  { a: 3.9, b: 7.0, zh: '每经过一台{路由器}，就决定下一步往哪走。' },
  { a: 7.4, b: 10.4, zh: '前面的线断了，它就{!绕远路}。' },
];
const SFX = [[0.7, 'pop'], [T.cut, 'thud', { gain: .7 }], [T.leg2[1], 'tick'], [T.title, 'chime']];

/* 一条折线上，每个拐点在全程的什么位置（0 到 1） */
function knots(pts) {
  const d = [0];
  for (let i = 1; i < pts.length; i++) d.push(d[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  return d.map(v => v / d[d.length - 1]);
}
/* 走到全程 q 处是第几秒（数据包是先加速后减速走的，所以要反着算） */
function arrival(q, [a, b]) {
  let lo = 0, hi = 1;
  for (let i = 0; i < 24; i++) { const m = (lo + hi) / 2; if (ease.inOut(m) < q) lo = m; else hi = m; }
  return a + (b - a) * hi;
}
const K1 = knots(LEG1), K2 = knots(LEG2);
const ARRIVE = { r1: arrival(K1[1], T.leg1), r2: T.leg1[1], r4: arrival(K2[1], T.leg2), r5: arrival(K2[2], T.leg2), sv: T.leg2[1] };
const lit = (t, at) => t < at ? 0 : Math.exp(-(t - at) * 1.6);          // 数据包经过时亮一下，再慢慢暗回去

/* 机器画在底层：有体积的实心东西不吃辉光 */
function router(f, [x, y], glow) {
  f.under(() => {
    f.line(x - 46, y - 24, x - 58, y - 66, { stroke: '#5E7F9E', w: 5 });
    f.line(x + 46, y - 24, x + 58, y - 66, { stroke: '#5E7F9E', w: 5 });
    f.rect(x - 72, y - 26, 144, 52, { fill: f.grad(0, y - 26, 0, y + 26, [[0, '#3A5571'], [1, '#1A2A3A']]), r: 10 });
    f.rect(x - 72, y - 26, 144, 52, { stroke: '#6A8CAB', w: 1.5, r: 10, a: .8 });
    for (let i = 0; i < 4; i++) f.rect(x - 56 + i * 22, y - 7, 14, 14, { fill: '#0E1A26', r: 2 });
  });
  f.circle(x + 52, y, 5, { fill: glow > .05 ? 'accent' : 'cool', a: .9 });
  f.glow(x, y, 130, 'accent', .45 * glow);
  f.text('路由器', x, y + 58, { font: 'sans', size: 20, color: 'dim', track: 4 });
}
function laptop(f, [x, y]) {
  f.under(() => {
    f.rect(x - 84, y - 70, 168, 108, { fill: '#203243', r: 8 });
    f.rect(x - 74, y - 61, 148, 90, { fill: f.grad(0, y - 61, 0, y + 29, [[0, '#14324A'], [1, '#0C1C2B']]), r: 3 });
    f.path([[x - 104, y + 38], [x + 104, y + 38], [x + 92, y + 54], [x - 92, y + 54]], { fill: '#2C4359', close: true });
  });
  f.text('你的电脑', x, y + 86, { font: 'sans', size: 20, color: 'dim', track: 4 });
}
function server(f, [x, y], glow) {
  f.under(() => {
    f.rect(x - 64, y - 104, 128, 208, { fill: f.grad(0, y - 104, 0, y + 104, [[0, '#33506B'], [1, '#172636']]), r: 8 });
    for (let i = 0; i < 4; i++) f.rect(x - 50, y - 88 + i * 46, 100, 34, { fill: '#0F1C29', r: 3 });
  });
  for (let i = 0; i < 4; i++) f.circle(x + 36, y - 71 + i * 46, 4, { fill: glow > .05 ? 'accent' : 'cool', a: .85 });
  f.glow(x, y, 190, 'accent', .5 * glow);
  f.text('服务器', x, y + 134, { font: 'sans', size: 20, color: 'dim', track: 4 });
}
/* 数据包：一个小信封，沿路走。走过的轨迹画在底层，让机器把它盖住 */
function packet(f, pts, k) {
  f.under(() => f.path(pts, { k, stroke: 'accent', w: 3, a: .55 }));
  const [x, y, ang] = f.along(pts, k);
  f.glow(x, y, 60, 'accent', .6);
  f.g({ at: [x, y], rot: ang }, () => {
    f.rect(-17, -11, 34, 22, { fill: 'accent', r: 3 });
    f.path([[-17, -11], [0, 2], [17, -11]], { stroke: '#7A4A00', w: 2 });
  });
}

/* 第一场：网络和数据包 / 数据包沿线走，断线后绕路 / 路由器一站站决定往哪走 */
function network(f, t, a) {
  const cut = soft(t, T.cut, T.cut + .4);
  const link = (p, q, o = {}) => f.line(p[0], p[1], q[0], q[1], { stroke: 'cool', w: 2, a: .35, ...o });
  f.under(() => {                                                 // 连线画在底层，机器画在它上面，线头被机器盖住
    link(P.pc, P.r1); link(P.r1, P.r2); link(P.r3, P.sv);
    for (const [p, q] of [[P.r2, P.r4], [P.r4, P.r5], [P.r5, P.sv]]) link(p, q, { dash: [8, 8] });
    if (cut <= 0) link(P.r2, P.r3);
    else {                                                        // 断线：中间裂开一个口子，变成红色
      f.line(P.r2[0], P.r2[1], ...lerp2(P.r2, P.r3, .5 - .08 * cut), { stroke: 'warn', w: 2, a: .8 });
      f.line(...lerp2(P.r2, P.r3, .5 + .08 * cut), P.r3[0], P.r3[1], { stroke: 'warn', w: 2, a: .8 });
    }
  });
  if (cut > 0) {
    const [mx, my] = lerp2(P.r2, P.r3, .5);
    f.glow(mx, my, 90, 'warn', .7 * (1 - soft(t, T.cut + .2, T.cut + 1.6)) + .15);
    f.text('×', mx, my - 2, { font: 'sans', weight: 300, size: 46, color: 'warn', a: cut });
  }
  laptop(f, P.pc);
  router(f, P.r1, lit(t, ARRIVE.r1)); router(f, P.r2, lit(t, ARRIVE.r2) + lit(t, T.leg2[0]) * .6); router(f, P.r3, 0);
  router(f, P.r4, lit(t, ARRIVE.r4)); router(f, P.r5, lit(t, ARRIVE.r5));
  server(f, P.sv, lit(t, ARRIVE.sv));

  if (t > T.leg1[0] && t < T.leg2[0]) packet(f, LEG1, ease.inOut(prog(t, ...T.leg1)));
  if (t >= T.leg2[0]) packet(f, LEG2, ease.inOut(prog(t, ...T.leg2)));

  const hops = ['r1', 'r2', 'r4', 'r5'].filter(k => t >= ARRIVE[k]).length;   // 右上角的尺子：经过了几台路由器
  f.text('经过路由器', 1636, 150, { font: 'sans', size: 22, color: 'dim', align: 'r', track: 4, a });
  f.text(String(hops), 1690, 148, { font: 'mono', weight: 600, size: 44, color: 'accent', a });
}
const lerp2 = (p, q, k) => [p[0] + (q[0] - p[0]) * k, p[1] + (q[1] - p[1]) * k];

VE.film({
  look: LOOK, dur: T.end, subs: SUBS, sfx: SFX,
  draw(f, t) {
    f.scene(0, T.title + .5, (lt, a) => network(f, t, a), .6, .6);
    f.scene(T.title - .1, T.end, lt => f.titleCard(lt, { zh: '数据包', sub: '总能找到下一条路', en: 'PACKET · ROUTING', font: 'sans', weight: 800 }), .2, .8);
    f.flash(T.title, { color: 'accent', peak: .35 });
  },
});
})();
