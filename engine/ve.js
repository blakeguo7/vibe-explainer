/* ve.js — vibe-explainer 的画面引擎。
 *
 *   VE.film({ look, dur, fps, subs, sfx, draw(f, t) })
 *
 * 一条片只有三样输入：外观（LOOK，外观卡里的数值）、字幕表、一个按时间画画面的函数 draw。
 * 每一帧只由时间 t 决定，没有跨帧的状态：所以能跳着截图、分段同时渲染，同一帧渲两次一模一样。
 *
 * 画面分四层，从下到上：底（背景）、底层（实心的东西，不发光）、内容（会发光）、字幕。
 * 出帧时把内容层模糊后用加法叠回去，亮的东西就自带光晕。
 */
(function (G) {
'use strict';

/* ---------- 时间和数学 ---------- */
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lerp = (a, b, k) => a + (b - a) * k;
const prog = (t, a, b) => clamp((t - a) / (b - a));                 // t 在 a 到 b 之间走到了哪（0 到 1）
const smooth = x => x * x * (3 - 2 * x);
const soft = (t, a, b) => smooth(prog(t, a, b));                     // 最常用：a 到 b 之间平滑地从 0 变到 1
const env = (t, a, b, fin = .5, fout = .5) => Math.min(soft(t, a, a + fin), 1 - soft(t, b - fout, b));   // 出现、停留、消失
const ease = {
  lin: x => x,
  in: x => x * x * x,
  out: x => 1 - Math.pow(1 - x, 3),
  inOut: x => x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2,
  outExpo: x => x >= 1 ? 1 : 1 - Math.pow(2, -10 * x),
  outBack: x => 1 + 2.4 * Math.pow(x - 1, 3) + 1.4 * Math.pow(x - 1, 2),
};

/* 关键帧：keys([[0, 1], [2, 3.5], [4, 3.5]], t)。值可以是数，也可以是等长的数组（比如 [x, y]）；相邻两帧之间平滑过渡 */
function keys(list, t) {
  if (t <= list[0][0]) return list[0][1];
  for (let i = 1; i < list.length; i++) {
    const [t1, v1] = list[i];
    if (t > t1) continue;
    const [t0, v0] = list[i - 1], k = soft(t, t0, t1);
    return Array.isArray(v0) ? v0.map((v, j) => lerp(v, v1[j], k)) : lerp(v0, v1, k);
  }
  return list[list.length - 1][1];
}
const zoom = (s0, s1, k) => Math.exp(lerp(Math.log(s0), Math.log(s1), k));   // 推拉镜头：缩放在对数里走，不会先慢后猛冲

/* 确定的随机：同一个种子永远给出同一串数。不要用 Math.random() 和 Date.now() */
const hash = n => { const x = Math.sin(n * 91.345 + 47.853) * 24634.6345; return x - Math.floor(x); };
const rng = seed => { let s = (seed >>> 0) || 1; return () => { s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; }; };
const wobble = x => { const i = Math.floor(x); return lerp(hash(i), hash(i + 1), smooth(x - i)) * 2 - 1; };   // 平滑的抖动，-1 到 1

/* 数字滚上去：a 到 b 秒之间从 from 走到 to，先快后慢 */
const count = (t, a, b, from, to) => Math.round(lerp(from, to, ease.out(prog(t, a, b))));
const fmt = n => n.toLocaleString('en-US');
/* "暗一下"：在 times 里每个时刻前后 half 秒内变暗，返回暗的程度（0 到 1），交给 f.darken() */
const dip = (t, times, half = .5) => Math.max(0, ...times.map(c => 1 - soft(Math.abs(t - c), 0, half)));

/* ---------- 颜色 ---------- */
const hex = c => { let h = c.replace('#', ''); if (h.length === 3) h = [...h].map(x => x + x).join(''); return [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16)); };
const rgba = (c, a = 1) => { if (c[0] !== '#') return c; const [r, g, b] = hex(c); return `rgba(${r},${g},${b},${a})`; };
const mix = (c1, c2, k) => { const b = hex(c2); return '#' + hex(c1).map((v, i) => Math.round(lerp(v, b[i], k)).toString(16).padStart(2, '0')).join(''); };

/* ---------- 字体 ----------
 * sans 思源黑体、serif 思源宋体（都能用 100–900 的字重）、mono 等宽、latin 西文衬线（英文和公式用，它的数字高低不齐，数字用前三种） */
const FAMILY = { sans: '"VE Sans", sans-serif', serif: '"VE Serif", serif', mono: '"VE Mono", monospace', latin: '"VE Latin", serif' };
const fontOf = o => `${o.italic ? 'italic ' : ''}${o.weight || 400} ${o.size || 32}px ${FAMILY[o.font || 'sans'] || o.font}`;

/* ---------- 画布和字幕区 ---------- */
const CANVAS = { '16:9': [1920, 1080], '9:16': [1080, 1920] };
const BAND = { '16:9': [.80, .95], '9:16': [.70, .82] };            // 字幕区（纵向比例），这里只放字幕；竖屏往上提，避开平台的按钮
const MARGIN = .05;                                                 // 左右各留 5%

/* ---------- 底 ----------
 * look.bg = { type, color, glow, glowA, ... }
 *   solid 纯色；stars 暗场加细星点（stars 个数）；grid 网格（line 线色、step 间距）；paper 纸面（mottle 斑驳程度） */
let paperCache = null;
function paperTexture(W, H, bg) {
  const key = `${W}x${H}:${bg.mottle}:${bg.seed}`;
  if (paperCache && paperCache.key === key) return paperCache.c;
  const w = W / 8, h = H / 8, small = document.createElement('canvas'); small.width = w; small.height = h;
  const sx = small.getContext('2d'), img = sx.createImageData(w, h), r = rng(bg.seed || 5), m = bg.mottle ?? .08;
  for (let i = 0; i < w * h; i++) { const v = r() < .5 ? 0 : 255; img.data.set([v, v, v, Math.round(r() * m * 255)], i * 4); }
  sx.putImageData(img, 0, 0);
  const c = document.createElement('canvas'); c.width = W; c.height = H;
  const cx = c.getContext('2d'); cx.imageSmoothingEnabled = true; cx.filter = 'blur(6px)'; cx.drawImage(small, 0, 0, W, H);
  paperCache = { key, c }; return c;
}
function paintBg(x, W, H, bg, t) {
  x.fillStyle = bg.color || '#000'; x.fillRect(0, 0, W, H);
  if (bg.glow) {
    const R = Math.max(W, H) * .62, g = x.createRadialGradient(W / 2, H * .45, 0, W / 2, H * .45, R);
    g.addColorStop(0, rgba(bg.glow, bg.glowA ?? .6)); g.addColorStop(1, rgba(bg.glow, 0));
    x.fillStyle = g; x.fillRect(0, 0, W, H);
  }
  if (bg.type === 'stars') {
    const r = rng(bg.seed || 11), n = bg.stars ?? 240;
    for (let i = 0; i < n; i++) {
      const px = r() * W, py = r() * H, s = .6 + r() * 1.4, ph = r() * 6.283, sp = .4 + r() * 1.1, base = .2 + .5 * r();
      x.fillStyle = rgba(bg.starColor || '#DCE5EE', base * (.65 + .35 * Math.sin(t * sp + ph)));
      x.fillRect(px, py, s, s);
    }
  }
  if (bg.type === 'grid') {
    const step = bg.step || 48, line = bg.line || '#3D6A92';
    for (const [dir, len] of [['x', W], ['y', H]]) {
      const first = (len / 2) % step;
      for (let p = first, i = Math.round((first - len / 2) / step); p < len; p += step, i++) {
        x.fillStyle = rgba(line, i % 5 === 0 ? (bg.majorA ?? .22) : (bg.lineA ?? .1));
        if (dir === 'x') x.fillRect(Math.round(p), 0, 1, H); else x.fillRect(0, Math.round(p), W, 1);
      }
    }
  }
  if (bg.type === 'paper') x.drawImage(paperTexture(W, H, bg), 0, 0);
}

/* ---------- 画面对象 f：draw(f, t) 里所有的画都通过它 ---------- */
class Frame {
  constructor(W, H, look, band) { this.W = W; this.H = H; this.look = look; this.band = band; this.t = 0; this.frame = 0; this.posts = []; this.tmp = []; this.depth = 0; this.clips = []; }

  col(c) { return (c && this.look.colors && this.look.colors[c]) || c; }    // 颜色可以写外观卡里的名字（'accent'），也可以直接写 '#……'
  get safe() { const m = this.W * MARGIN; return { x0: m, x1: this.W - m, y0: this.H * .04, y1: this.band[0] * this.H }; }   // 主体能用的范围

  /* 成组：在一组位移 / 旋转 / 缩放 / 透明度里画 fn。o = { at:[x,y], rot, s, a, add, clip:[x,y,w,h], blur } */
  g(o, fn) {
    const x = this.x; x.save();
    if (o.at) x.translate(o.at[0], o.at[1]);
    if (o.rot) x.rotate(o.rot);
    if (o.s != null) Array.isArray(o.s) ? x.scale(o.s[0], o.s[1]) : x.scale(o.s, o.s);
    if (o.a != null) x.globalAlpha *= o.a;
    if (o.add) x.globalCompositeOperation = 'lighter';
    if (o.clip) { x.beginPath(); x.rect(...o.clip); x.clip(); this.clips.push([x.getTransform(), o.clip]); }   // 记下来，f.under() 里也要裁
    if (o.blur) x.filter = `blur(${o.blur}px)`;
    try { fn(); } finally { if (o.clip) this.clips.pop(); x.restore(); }
  }
  /* 先画到一张临时画布上，再整组合成。一组互相重叠的半透明形状要一起淡入淡出时用它，否则重叠处会透 */
  layer(o, fn) {
    const a = o.a ?? 1; if (a <= 0) return;
    if (!this.tmp[this.depth]) { const c = document.createElement('canvas'); c.width = this.W; c.height = this.H; this.tmp[this.depth] = c; }
    const c = this.tmp[this.depth++], tx = c.getContext('2d'), keep = this.x;
    tx.setTransform(1, 0, 0, 1, 0, 0); tx.globalAlpha = 1; tx.globalCompositeOperation = 'source-over'; tx.filter = 'none'; tx.clearRect(0, 0, this.W, this.H);
    this.x = tx;
    try { fn(); } finally { this.x = keep; this.depth--; }
    keep.save(); keep.setTransform(1, 0, 0, 1, 0, 0); keep.globalAlpha *= a;
    if (o.add) keep.globalCompositeOperation = 'lighter';
    if (o.blur) keep.filter = `blur(${o.blur}px)`;
    keep.drawImage(c, 0, 0); keep.restore();
  }
  /* 画到底层：有体积的实心东西（机器、书、角色、场景）画在这里，不参加辉光。
   * 外面的位移、缩放、透明度（比如 f.scene 的淡入淡出）和 f.g 的裁剪范围，都会一起带进来 */
  under(fn) {
    const keep = this.x, u = this.U;
    u.save();
    for (const [m, r] of this.clips) { u.setTransform(m); u.beginPath(); u.rect(...r); u.clip(); }
    u.setTransform(keep.getTransform()); u.globalAlpha = keep.globalAlpha;
    this.x = u;
    try { fn(); } finally { this.x = keep; u.restore(); }
  }

  /* ---- 线和形。选项 o：stroke 描边色、fill 填充、w 线宽、a 透明度、dash 虚线、add 加法混合、cap ---- */
  paint(o, build) {
    const x = this.x; x.save();
    x.globalAlpha *= o.a ?? 1;
    if (o.add) x.globalCompositeOperation = 'lighter';
    x.beginPath(); build(x);
    if (o.fill) { x.fillStyle = typeof o.fill === 'string' ? this.col(o.fill) : o.fill; x.fill(); }
    if (o.stroke || !o.fill) {
      x.strokeStyle = typeof o.stroke === 'object' ? o.stroke : this.col(o.stroke || 'ink');
      x.lineWidth = o.w ?? 2; x.lineCap = o.cap || 'round'; x.lineJoin = 'round';
      if (o.dash) x.setLineDash(o.dash);
      x.stroke();
    }
    x.restore();
  }
  cut(pts, k) {                                                    // 一条折线只取前 k 那么长
    const lens = []; let total = 0;
    for (let i = 1; i < pts.length; i++) { const d = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); lens.push(d); total += d; }
    let left = total * clamp(k); const out = [pts[0]];
    for (let i = 1; i < pts.length; i++) {
      if (left >= lens[i - 1]) { out.push(pts[i]); left -= lens[i - 1]; continue; }
      const q = lens[i - 1] ? left / lens[i - 1] : 0;
      out.push([lerp(pts[i - 1][0], pts[i][0], q), lerp(pts[i - 1][1], pts[i][1], q)]); break;
    }
    return out;
  }
  /* 折线。o.k（0 到 1）只画前 k 那么长：线"长出来"就靠它；o.close 闭合 */
  path(pts, o = {}) {
    const k = o.k ?? 1; if (k <= 0 || pts.length < 2) return;
    const p = k < 1 ? this.cut(pts, k) : pts;
    this.paint(o, x => { x.moveTo(p[0][0], p[0][1]); for (let i = 1; i < p.length; i++) x.lineTo(p[i][0], p[i][1]); if (o.close && k >= 1) x.closePath(); });
  }
  line(x1, y1, x2, y2, o = {}) { this.path([[x1, y1], [x2, y2]], o); }
  /* 沿折线走到 k 处的位置和方向：[x, y, 角度]。给线头安一个光点，或者让东西沿路走 */
  along(pts, k) {
    const p = this.cut(pts, k), a = p[p.length - 1], b = p.length > 1 ? p[p.length - 2] : null;
    const ang = b ? Math.atan2(a[1] - b[1], a[0] - b[0]) : Math.atan2(pts[1][1] - pts[0][1], pts[1][0] - pts[0][0]);
    return [a[0], a[1], ang];
  }
  circle(cx, cy, r, o = {}) { if (r > 0) this.paint(o, x => x.arc(cx, cy, r, 0, Math.PI * 2)); }
  arc(cx, cy, r, a0, a1, o = {}) { if (r > 0) this.paint(o, x => x.arc(cx, cy, r, a0, a1)); }
  ellipse(cx, cy, rx, ry, o = {}) { this.paint(o, x => x.ellipse(cx, cy, rx, ry, o.rot || 0, 0, Math.PI * 2)); }
  rect(x0, y0, w, h, o = {}) { this.paint(o, x => o.r ? x.roundRect(x0, y0, w, h, o.r) : x.rect(x0, y0, w, h)); }
  /* 渐变，交给 fill 或 stroke 用。stops = [[位置, 颜色, 透明度], …] */
  grad(x0, y0, x1, y1, stops) { const g = this.x.createLinearGradient(x0, y0, x1, y1); for (const [p, c, a] of stops) g.addColorStop(p, rgba(this.col(c), a ?? 1)); return g; }
  rgrad(cx, cy, r0, r1, stops) { const g = this.x.createRadialGradient(cx, cy, r0, cx, cy, r1); for (const [p, c, a] of stops) g.addColorStop(p, rgba(this.col(c), a ?? 1)); return g; }

  /* ---- 光 ---- */
  glow(cx, cy, r, color, a = 1) {                                  // 一团柔光（加法）
    if (a <= 0 || r <= 0) return;
    const x = this.x, c = this.col(color), g = x.createRadialGradient(cx, cy, 0, cx, cy, r);
    g.addColorStop(0, rgba(c, a)); g.addColorStop(.35, rgba(c, a * .35)); g.addColorStop(1, rgba(c, 0));
    x.save(); x.globalCompositeOperation = 'lighter'; x.fillStyle = g; x.fillRect(cx - r, cy - r, 2 * r, 2 * r); x.restore();
  }
  dot(cx, cy, r, color, a = 1) {                                   // 光点：白色的芯 + 一圈色晕
    this.glow(cx, cy, r * 6, color, a * .45);
    this.glow(cx, cy, r * 2.2, color, a * .9);
    this.circle(cx, cy, r, { fill: '#FFFFFF', a });
  }

  /* ---- 字。选项 o：font（sans/serif/mono/latin）、weight、size、italic、color、a、align（c/l/r）、track 字距（像素）、shadow 投影浓度、blur ---- */
  font(o) { const x = this.x; x.font = fontOf(o); x.letterSpacing = `${o.track || 0}px`; x.textBaseline = 'middle'; x.textAlign = 'left'; }
  measure(str, o = {}) { this.x.save(); this.font(o); const w = this.x.measureText(str).width - (o.track || 0); this.x.restore(); return Math.max(0, w); }
  shade(x, o) { if (!o.shadow) return; const s = o.size || 32; x.shadowColor = `rgba(0,0,0,${o.shadow})`; x.shadowBlur = s * .35; x.shadowOffsetY = s * .05; }
  text(str, x0, y0, o = {}) {
    const x = this.x; x.save(); this.font(o);
    const w = x.measureText(str).width - (o.track || 0), al = o.align || 'c';
    x.globalAlpha *= o.a ?? 1; this.shade(x, o);
    if (o.blur) x.filter = `blur(${o.blur}px)`;
    x.fillStyle = typeof o.color === 'object' ? o.color : this.col(o.color || 'ink');
    x.fillText(str, al === 'c' ? x0 - w / 2 : al === 'r' ? x0 - w : x0, y0);
    x.restore(); return w;
  }
  /* 逐字画：per(i, 字) 返回 { a, color, blur, dy, s } 改这个字的样子。逐字显影、打字、单字变色都用它 */
  chars(str, x0, y0, o = {}, per = () => null) {
    const x = this.x, cs = Array.from(str), tr = o.track || 0;
    x.save(); this.font({ ...o, track: 0 });
    const ws = cs.map(c => x.measureText(c).width), total = ws.reduce((s, w) => s + w, 0) + tr * (cs.length - 1);
    const al = o.align || 'c', base = x.globalAlpha * (o.a ?? 1);
    let cx = al === 'c' ? x0 - total / 2 : al === 'r' ? x0 - total : x0;
    cs.forEach((c, i) => {
      const p = per(i, c) || {}, a = base * (p.a ?? 1);
      if (a > .003) {
        x.save(); x.globalAlpha = a; this.shade(x, o);
        if (p.blur > .2) x.filter = `blur(${p.blur}px)`;
        x.fillStyle = this.col(p.color || o.color || 'ink');
        const y = y0 + (p.dy || 0);
        if (p.s != null && p.s !== 1) { x.translate(cx + ws[i] / 2, y); x.scale(p.s, p.s); x.fillText(c, -ws[i] / 2, 0); }
        else x.fillText(c, cx, y);
        x.restore();
      }
      cx += ws[i] + tr;
    });
    x.restore(); return total;
  }

  /* ---- 场景和全幅效果 ---- */
  /* 只在 a 到 b 秒之间画 fn(本地时间, 透明度)，并替它乘好淡入淡出。相邻两个场景的时间重叠半秒，就不会硬切 */
  scene(a, b, fn, fin = .5, fout = .5) {
    const t = this.t; if (t < a || t > b) return;
    const k = env(t, a, b, fin, fout); if (k <= 0) return;
    this.g({ a: k }, () => fn(t - a, k));
  }
  /* 闪：t0 前 rise 秒升到最亮，之后 fall 秒落回。压在内容之上、字幕之下 */
  flash(t0, o = {}) {
    const t = this.t, rise = o.rise ?? .06, fall = o.fall ?? .45;
    const k = t < t0 ? soft(t, t0 - rise, t0) : 1 - soft(t, t0, t0 + fall); if (k <= 0) return;
    const c = this.col(o.color || '#FFFFFF'), peak = o.peak ?? .7;
    this.posts.push(x => { x.save(); x.globalCompositeOperation = 'lighter'; x.fillStyle = rgba(c, peak * k); x.fillRect(0, 0, this.W, this.H); x.restore(); });
  }
  darken(a) { if (a > 0) this.posts.push(x => { x.fillStyle = `rgba(0,0,0,${clamp(a)})`; x.fillRect(0, 0, this.W, this.H); }); }

  /* 片名卡：大字逐字由虚变实，一条细线从中间展开，副题和外文随后淡入。lt 是片名卡的本地时间（0 = 开始） */
  titleCard(lt, o) {
    const W = this.W, cy = o.y ?? this.H * .42, size = o.size ?? Math.round(W * (W > this.H ? .08 : .12));
    const n = Array.from(o.zh).length, a = o.a ?? 1, end = .55 + n * .12;
    this.chars(o.zh, W / 2, cy, { font: o.font || 'serif', weight: o.weight || 700, size, track: size * (o.track ?? .12), color: o.color || 'ink', a },
      i => { const k = soft(lt, .15 + i * .12, .55 + i * .12); return { a: k, blur: (1 - k) * 10 }; });
    const lw = W * .26 * ease.out(prog(lt, end - .1, end + .8)), ly = cy + size * .74;
    this.line(W / 2 - lw, ly, W / 2 + lw, ly, { stroke: o.line || 'accent', w: 1.5, a: a * .8 });
    if (o.sub) this.text(o.sub, W / 2, cy + size * 1.16, { font: o.subFont || o.font || 'serif', weight: 500, size: Math.round(size * .26), track: o.subTrack ?? size * .08, color: o.subColor || 'accent', a: a * soft(lt, end + .3, end + 1.1) });
    if (o.en) this.text(o.en, W / 2, cy + size * 1.55, { font: 'mono', size: Math.round(size * .13), track: size * .07, color: 'dim', a: a * soft(lt, end + .7, end + 1.5) });
  }
}

/* ---------- 字幕 ----------
 * 一条：{ a, b, zh, en?, big? }。a 是开始出现的时刻，b 是完全消失的时刻。
 * zh 里 {词} 染强调色（look.subs.accent，默认 'accent'），{!词} 染警示色（look.subs.warn，默认 'warn'）。
 * 出现方式 look.subs.mode：fade 整行淡入；type 逐字亮起；focus 逐字由虚变实。 */
function parse(s) {
  const out = [], cs = Array.from(s); let tone = null;
  for (let i = 0; i < cs.length; i++) {
    const c = cs[i];
    if (c === '{') { if (cs[i + 1] === '!') { tone = 'warn'; i++; } else tone = 'accent'; }
    else if (c === '}') tone = null;
    else out.push({ ch: c, tone });
  }
  return out;
}
function subStyle(st, s) {
  const size = s.big ? Math.round(st.size * (s.big === 2 ? 1.45 : 1.2)) : st.size;
  return { font: st.font, weight: st.weight, size, track: size * (st.track ?? .06), color: st.color || 'ink', shadow: st.shadow ?? .55 };
}
function drawSubs(f, list, st, t) {
  const W = f.W, y = st.y * f.H;
  for (const s of list) {
    if (t < s.a || t > s.b) continue;
    const parts = parse(s.zh), str = parts.map(p => p.ch).join(''), o = subStyle(st, s), out = 1 - soft(t, s.b - .35, s.b);
    const tone = p => p.tone === 'warn' ? (st.warn || 'warn') : p.tone === 'accent' ? (st.accent || 'accent') : null;
    if (st.plate) {                                                // 字幕底板：一条很淡的暗带，压在亮底上时用
      const k = soft(t, s.a, s.a + .3) * out, h = o.size * 2.4;
      f.rect(0, y - h / 2, W, h, { fill: f.grad(0, y - h / 2, 0, y + h / 2, [[0, '#000000', 0], [.5, '#000000', st.plate * k], [1, '#000000', 0]]) });
    }
    if ((st.mode || 'fade') === 'fade') {
      const k = soft(t, s.a, s.a + .45) * out;
      f.chars(str, W / 2, y, { ...o, a: k }, i => ({ color: tone(parts[i]) }));
    } else {
      const n = parts.length, stg = Math.min(.06, .9 / n), rise = st.mode === 'focus' ? .3 : .14;
      f.chars(str, W / 2, y, o, i => { const k = prog(t, s.a + i * stg, s.a + i * stg + rise); return { a: smooth(k) * out, blur: st.mode === 'focus' ? (1 - k) * 8 : 0, color: tone(parts[i]) }; });
    }
    if (s.en && st.en !== false) {
      const e = st.en || {};
      f.text(s.en, W / 2, y + (e.dy ?? o.size * 1.3), { font: e.font || 'latin', italic: e.italic ?? true, weight: e.weight || 400, size: e.size || Math.round(o.size * .64), color: e.color || 'dim', a: soft(t, s.a + .18, s.a + .63) * out });
    }
  }
}

/* ---------- 一条片 ---------- */
function makeGrain(n = 4, size = 256) {
  return Array.from({ length: n }, (_, k) => {
    const c = document.createElement('canvas'); c.width = c.height = size;
    const x = c.getContext('2d'), img = x.createImageData(size, size), r = rng(101 + k);
    for (let i = 0; i < size * size; i++) { const v = Math.round(r() * 255); img.data.set([v, v, v, 255], i * 4); }
    x.putImageData(img, 0, 0); return c;
  });
}

function film(spec) {
  const look = spec.look || {}, ratio = look.canvas || '16:9', [W, H] = CANVAS[ratio], fps = spec.fps || 30;
  const band = (look.subs && look.subs.band) || BAND[ratio];
  const st = Object.assign({ font: 'sans', weight: 500, size: Math.round(Math.min(W, H) * (ratio === '9:16' ? .052 : .041)), mode: 'fade', y: (band[0] + band[1]) / 2 }, look.subs || {});
  const subs = spec.subs || [];

  const out = document.getElementById('ve'); out.width = W; out.height = H;
  const mk = () => { const c = document.createElement('canvas'); c.width = W; c.height = H; return c; };
  const BG = mk(), U = mk(), L = mk(), S = mk(), small = document.createElement('canvas');
  small.width = W / 4; small.height = H / 4;
  const f = new Frame(W, H, look, band), grain = makeGrain();
  const reset = x => { x.setTransform(1, 0, 0, 1, 0, 0); x.globalAlpha = 1; x.globalCompositeOperation = 'source-over'; x.filter = 'none'; x.clearRect(0, 0, x.canvas.width, x.canvas.height); };

  function seek(t) {
    t = clamp(t, 0, spec.dur);
    f.t = t; f.frame = Math.round(t * fps); f.posts = []; f.clips = []; f.bloom = undefined;
    for (const c of [BG, U, L, S]) reset(c.getContext('2d'));
    paintBg(BG.getContext('2d'), W, H, look.bg || {}, t);
    f.U = U.getContext('2d'); f.x = L.getContext('2d');
    spec.draw(f, t);
    f.x = S.getContext('2d'); drawSubs(f, subs, st, t);
    compose();
  }
  function compose() {
    const x = out.getContext('2d'); reset(x);
    x.drawImage(BG, 0, 0); x.drawImage(U, 0, 0); x.drawImage(L, 0, 0);
    const bloom = f.bloom ?? look.bloom ?? .6;                     // draw 里可以写 f.bloom = … 临时改这一帧的辉光
    if (bloom > 0) {
      const sx = small.getContext('2d');
      for (const [r, a] of [[3, .5], [10, .35]]) {
        reset(sx); sx.filter = `blur(${r}px)`; sx.drawImage(L, 0, 0, small.width, small.height);
        x.save(); x.globalCompositeOperation = 'lighter'; x.globalAlpha = a * bloom; x.drawImage(small, 0, 0, W, H); x.restore();
      }
    }
    const vig = look.vignette ?? .4;
    if (vig > 0) {
      const R = Math.hypot(W, H) / 2, g = x.createRadialGradient(W / 2, H / 2, R * .45, W / 2, H / 2, R);
      g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(1, `rgba(0,0,0,${vig})`);
      x.fillStyle = g; x.fillRect(0, 0, W, H);
    }
    for (const p of f.posts) p(x);
    x.drawImage(S, 0, 0);
    const gr = look.grain ?? .04;
    if (gr > 0) {
      const ox = Math.floor(hash(f.frame) * 256), oy = Math.floor(hash(f.frame + 7) * 256);
      x.save(); x.globalCompositeOperation = 'overlay'; x.globalAlpha = gr; x.translate(-ox, -oy);
      x.fillStyle = x.createPattern(grain[f.frame % grain.length], 'repeat'); x.fillRect(0, 0, W + 256, H + 256); x.restore();
    }
  }

  /* 给 render.py 用的接口 */
  G.seek = seek; G.END = spec.dur; G.FPS = fps; G.SIZE = [W, H]; G.SUBS = subs;
  G.events = () => (spec.sfx || []).map(e => [e[0], e[1], e[2] || {}]).sort((a, b) => a[0] - b[0]);
  G.probe = t => {                                                  // 字幕区里有多少像素被画面占了（不算字幕和背景），0 到 1
    seek(t);
    const y0 = Math.floor(band[0] * H), y1 = Math.ceil(band[1] * H);
    const u = U.getContext('2d').getImageData(0, y0, W, y1 - y0).data, l = L.getContext('2d').getImageData(0, y0, W, y1 - y0).data;
    let ink = 0, n = 0;
    for (let i = 3; i < l.length; i += 16) { n++; if (l[i] > 25 || u[i] > 25) ink++; }
    return ink / n;
  };
  G.subWidths = () => {                                             // 每句字幕有多宽，会不会超出左右边距
    f.x = S.getContext('2d'); const limit = W * (1 - 2 * MARGIN);
    return subs.map(s => { const o = subStyle(st, s), w = f.measure(parse(s.zh).map(p => p.ch).join(''), o); return { a: s.a, zh: s.zh, width: Math.round(w), limit: Math.round(limit) }; });
  };

  /* 字体就绪以后才开始画；?play 实时播放，?t=12.5 停在某一刻，?render 给 render.py 原尺寸截图 */
  const q = new URLSearchParams(location.search);
  if (q.has('render')) document.body.classList.add('render');
  const faces = ['400 20px "VE Sans"', '400 20px "VE Serif"', '400 20px "VE Mono"', '400 20px "VE Latin"', 'italic 400 20px "VE Latin"'].map(s => document.fonts.load(s, '永A1'));
  Promise.all(faces).then(() => {
    G.READY = true;
    if (!q.has('play')) { seek(+q.get('t') || 0); return; }
    let t0 = performance.now() - (+q.get('t') || 0) * 1000, paused = false, at = 0;
    addEventListener('keydown', e => {
      if (e.key === ' ') { paused = !paused; if (!paused) t0 = performance.now() - at * 1000; }
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { at = clamp(at + (e.key === 'ArrowLeft' ? -2 : 2), 0, spec.dur); t0 = performance.now() - at * 1000; if (paused) seek(at); }
    });
    const loop = () => { if (!paused) { at = ((performance.now() - t0) / 1000) % spec.dur; seek(at); document.title = `${at.toFixed(1)}s`; } requestAnimationFrame(loop); };
    requestAnimationFrame(loop);
  });
}

G.VE = { clamp, lerp, prog, smooth, soft, env, ease, keys, zoom, hash, rng, wobble, count, fmt, dip, hex, rgba, mix, fontOf, film, CANVAS };
})(window);
