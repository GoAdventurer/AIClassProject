// 在 Node 中跑核心逻辑测试（不含 DOM 模块）
// 从 index.html 抽出 GoNeon.* 定义并执行
const fs = require('fs');
const html = fs.readFileSync(__dirname + '/../index.html', 'utf8');

// 提取主 <script> 块（含 GoNeon 定义的那块）
const scriptMatch = html.match(/<script>\n([\s\S]*?)<\/script>/);
if (!scriptMatch) { console.error('未找到 <script>'); process.exit(1); }
const fullScript = scriptMatch[1];

// 我们需要执行直到 App 模块定义结束。
// App 用了 document.getElementById 等 DOM API，在 Node 里会崩。
// 策略：截到 GoNeon.AudioFx 结束（紧接 MenuUI 之前）。
// 我们要的核心：EventBus, BoardOps, Zobrist, Engine, Scoring, SGF, Storage,
//             AIHeuristics, AIEasy, AIMedium, AIMcts, AIRunner
// 这些都不依赖 DOM。AudioFx 用 window.AudioContext，UI/App 用 document。
// 我们把脚本切到 AudioFx 模块**之前**结束。

const cutMarker = '/* ============================================================\n * Theme — 暗夜霓虹色板';
const idx = fullScript.indexOf(cutMarker);
if (idx < 0) { console.error('找不到 Theme cut marker'); process.exit(1); }
const coreScript = fullScript.slice(0, idx);

// Fake Math.random 以保证 Zobrist 不出问题（实际不需要，Math.random 默认就在）
// 提供 window 占位（用不到）
// 把脚本里的 const GoNeon 改成 globalThis.GoNeon 让 vm 沙箱可见
const patched = coreScript.replace(/^const GoNeon = \{\};/m, 'globalThis.GoNeon = {};')
                          .replace(/\bconst GoNeon\b/g, 'GoNeon');

const sandbox = {
  console,
  window: {},
  setTimeout, clearTimeout, setInterval, clearInterval,
  // requestAnimationFrame 在 MCTS 里用得到
  requestAnimationFrame(cb) { return setTimeout(cb, 0); },
  // localStorage 给 Storage 用
  localStorage: { _: {}, setItem(k, v) { this._[k] = v; }, getItem(k) { return this._[k] || null; }, removeItem(k) { delete this._[k]; } },
  // BigInt 是内置全局，vm 自动有
};
sandbox.globalThis = sandbox;

const vm = require('vm');
vm.createContext(sandbox);
try {
  vm.runInContext(patched, sandbox);
} catch (e) {
  console.error('✗ 模块加载失败:', e.message);
  console.error(e.stack);
  process.exit(1);
}
const G = sandbox.GoNeon;
if (!G || !G.Engine) { console.error('GoNeon 未挂载'); process.exit(1); }

// 测试运行器
let pass = 0, fail = 0;
const failed = [];
function suite(name) { console.log('\n[' + name + ']'); }
function test(name, fn) {
  try { fn(); console.log('  ✓ ' + name); pass++; }
  catch (e) { console.log('  ✗ ' + name + ' — ' + e.message); fail++; failed.push(name + ': ' + e.message); }
}
function eq(a, b, msg) { if (a !== b) throw new Error((msg||'eq') + ': 期望 ' + JSON.stringify(b) + '，得到 ' + JSON.stringify(a)); }
function ok(x, msg) { if (!x) throw new Error(msg || ('期望真值, 得到 '+x)); }
function eqArr(a, b) {
  if (a.length !== b.length) throw new Error('数组长度: '+a.length+' vs '+b.length);
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) throw new Error('arr['+i+']: '+a[i]+' vs '+b[i]);
}
async function asyncTest(name, fn) {
  try { await fn(); console.log('  ✓ ' + name); pass++; }
  catch (e) { console.log('  ✗ ' + name + ' — ' + e.message); fail++; failed.push(name + ': ' + e.message); }
}

(async () => {

// ===== Engine.createGame =====
suite('Engine.createGame');
test('19x19 默认对局', () => {
  const s = G.Engine.createGame({ size: 19 });
  eq(s.size, 19); eq(s.board.length, 361); eq(s.toPlay, 1);
  eq(s.komi, 7.5); eq(s.phase, 'playing');
});
test('9x9 对局', () => {
  eq(G.Engine.createGame({ size: 9 }).board.length, 81);
});

// ===== Engine.tryMove 基础 =====
suite('Engine.tryMove (基础)');
test('落子并切换轮次', () => {
  let s = G.Engine.createGame({ size: 9 });
  const r = G.Engine.tryMove(s, 4, 4);
  ok(r.ok); eq(r.next.board[4*9+4], 1); eq(r.next.toPlay, 2);
});
test('已占位拒绝', () => {
  let s = G.Engine.createGame({ size: 9 });
  s = G.Engine.tryMove(s, 4, 4).next;
  eq(G.Engine.tryMove(s, 4, 4).reason, 'occupied');
});
test('越界拒绝', () => {
  const s = G.Engine.createGame({ size: 9 });
  eq(G.Engine.tryMove(s, -1, 0).reason, 'out_of_bounds');
  eq(G.Engine.tryMove(s, 9, 0).reason, 'out_of_bounds');
});

// ===== 提子 / 自杀 / 劫争 =====
suite('Engine.tryMove (提子 / 自杀 / 劫争)');
function setupBoard(rows, toPlay) {
  const size = rows.length;
  const s = G.Engine.createGame({ size });
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const c = rows[y][x];
    if (c === 'B') s.board[y*size+x] = 1;
    else if (c === 'W') s.board[y*size+x] = 2;
  }
  s.toPlay = toPlay;
  s.hash = G.Zobrist.computeHash(s.zob, s.board);
  s.seenHashes.set(s.hash, 1);
  return s;
}
test('提中央单子', () => {
  const s = setupBoard([
    '.....',
    '..B..',
    '.BWB.',
    '.....',
    '.....',
  ], 1);
  const r = G.Engine.tryMove(s, 2, 3);
  ok(r.ok); eq(r.next.board[2*5+2], 0); eq(r.next.captures.black, 1);
});
test('禁止自杀', () => {
  const s = setupBoard(['.W.','W.W','.W.'], 1);
  eq(G.Engine.tryMove(s, 1, 1).reason, 'suicide');
});
test('能提子的自杀形应允许（提子优先于自杀检查）', () => {
  // 4x4 经典：白单子位于角，黑围 3 面，黑下最后一气吃白
  //   W B . .
  //   B . . .
  //   . . . .
  // 白 (0,0) 邻居：(1,0)=B (0,1)=B；唯一气 = 棋盘外? 不，(0,0) 角只有 2 邻居，全是 B → 0 气
  // 那白子已经被吃了？错：白还在板上，那它必有 ≥1 气才合法，否则盘面无效。
  // 改用：5x5，白子 1 气
  //   . W . . .
  //   B B . . .
  //   . . . . .
  // 白 (1,0) 邻居：(0,0)=. (2,0)=. (1,1)=B；2 气。
  // 黑下 (0,0) 后白只剩 (2,0) 一气，仍非死。这例子不验证 capture-before-suicide。
  //
  // 简化目标：直接验 tryMove 内部 capture 顺序。构造一个白单子刚好死的局面：
  //   B W B    ← 白(1,0) 邻居 (0,0)=B (2,0)=B (1,1)=. 1 气在 (1,1)
  //   B . B    ← 黑下 (1,1)：白(1,0) 0 气被提，黑(1,1) 邻居 (0,1)=B(2,1)=B(1,0)=空(刚提)(1,2)=B 接到 4 子群，活
  //   . B .
  // 注意：黑壁是否一个连通群？(0,0)-(0,1)? 邻居关系：(0,0) 与 (0,1) 邻接 → 同群
  // 那么黑下 (1,1) 后，黑大群有气在多处 → 安全，白被提。
  const s = G.Engine.createGame({ size: 3 });
  s.board[0*3+0] = 1; s.board[0*3+1] = 2; s.board[0*3+2] = 1;
  s.board[1*3+0] = 1;                      s.board[1*3+2] = 1;
                       s.board[2*3+1] = 1;
  s.toPlay = 1;
  s.hash = G.Zobrist.computeHash(s.zob, s.board);
  s.seenHashes.clear();
  s.seenHashes.set(s.hash, 1);
  const r = G.Engine.tryMove(s, 1, 1);
  ok(r.ok, '应允许（提子优先于自杀）');
  eq(r.next.board[0*3+1], 0, '白被提');
  eq(r.next.captures.black, 1);
});
test('基本劫争禁止立即回提', () => {
  let s = G.Engine.createGame({ size: 5 });
  const place = (xx, yy, c) => s.board[yy*5+xx] = c;
  place(1,1,1); place(2,1,2);
  place(0,2,1); place(1,2,2); place(3,2,2);
  place(1,3,1); place(2,3,2);
  s.toPlay = 1;
  s.hash = G.Zobrist.computeHash(s.zob, s.board);
  s.seenHashes.set(s.hash, 1);
  const r1 = G.Engine.tryMove(s, 2, 2);
  ok(r1.ok); eq(r1.next.board[2*5+1], 0);
  const r2 = G.Engine.tryMove(r1.next, 1, 2);
  eq(r2.reason, 'ko');
});

// ===== undo / pass / resign =====
suite('Engine.undo / pass / resign');
test('undo 回退一步', () => {
  let s = G.Engine.createGame({ size: 9 });
  s = G.Engine.tryMove(s, 4, 4).next;
  s = G.Engine.tryMove(s, 3, 3).next;
  const u = G.Engine.undo(s);
  eq(u.board[3*9+3], 0); eq(u.board[4*9+4], 1);
  eq(u.toPlay, 2); eq(u.history.length, 1); eq(u.moveLog.length, 1);
});
test('两次连 pass 进入 scoring', () => {
  let s = G.Engine.createGame({ size: 9 });
  s = G.Engine.pass(s); s = G.Engine.pass(s);
  eq(s.phase, 'scoring');
});
test('resign 结束对局', () => {
  let s = G.Engine.createGame({ size: 9 });
  s = G.Engine.resign(s, 1);
  eq(s.phase, 'ended'); eq(s.winner, 2);
});

// ===== Scoring =====
suite('Scoring');
test('5x5 各占一半', () => {
  const s = G.Engine.createGame({ size: 5 });
  for (let y = 0; y < 5; y++) {
    s.board[y*5+0] = 1; s.board[y*5+1] = 1;
    s.board[y*5+3] = 2; s.board[y*5+4] = 2;
  }
  const r = G.Scoring.score(s);
  eq(r.black, 10); eq(r.white, 17.5); eq(r.winner, 2);
});
test('lone 白子在黑围中应判死', () => {
  const s = G.Engine.createGame({ size: 5 });
  const set = (x, y, c) => s.board[y*5+x] = c;
  for (let i = 0; i < 5; i++) { set(i, 0, 1); set(i, 4, 1); set(0, i, 1); set(4, i, 1); }
  set(2, 2, 2);
  const dead = G.Scoring.detectDeadStones(s);
  eq(dead.length, 1);
});

// ===== SGF =====
suite('SGF');
test('write 含 SZ/KM/RU', () => {
  const s = G.Engine.createGame({ size: 19 });
  const out = G.SGF.write(s);
  ok(out.startsWith('(;'));
  ok(out.includes('SZ[19]'));
  ok(out.includes('KM[7.5]'));
  ok(out.includes('RU[Chinese]'));
});
test('write 编码坐标 a-s', () => {
  let s = G.Engine.createGame({ size: 9 });
  s = G.Engine.tryMove(s, 0, 0).next;
  s = G.Engine.tryMove(s, 8, 8).next;
  const out = G.SGF.write(s);
  ok(out.includes(';B[aa]')); ok(out.includes(';W[ii]'));
});
test('write pass 为空括号', () => {
  let s = G.Engine.createGame({ size: 9 });
  s = G.Engine.pass(s);
  ok(G.SGF.write(s).includes(';B[]'));
});
test('round-trip', () => {
  let s = G.Engine.createGame({ size: 9 });
  s = G.Engine.tryMove(s, 4, 4).next;
  s = G.Engine.tryMove(s, 3, 3).next;
  s = G.Engine.tryMove(s, 5, 5).next;
  const text = G.SGF.write(s);
  const r = G.SGF.parse(text);
  eq(r.size, 9); eq(r.moveLog.length, 3);
  eqArr(Array.from(r.board), Array.from(s.board));
});
test('parse 手写 SGF', () => {
  const sgf = '(;FF[4]SZ[9]KM[7.5];B[ee];W[ce];B[];W[ge])';
  const s = G.SGF.parse(sgf);
  eq(s.size, 9); eq(s.moveLog.length, 4); ok(s.moveLog[2].pass);
});
test('parse 垃圾抛错', () => {
  let threw = false;
  try { G.SGF.parse('this is not sgf'); } catch (e) { threw = true; }
  ok(threw);
});

// ===== AI 合法性 =====
suite('AI 合法性');
test('Easy 给出合法着', () => {
  const s = G.Engine.createGame({ size: 9 });
  const m = G.AIEasy.pick(s);
  if (!m.pass) ok(G.Engine.tryMove(s, m.x, m.y).ok);
});
test('Easy 30 步自我对弈合法', () => {
  let s = G.Engine.createGame({ size: 9 });
  for (let i = 0; i < 30; i++) {
    const m = G.AIEasy.pick(s);
    if (m.pass) { s = G.Engine.pass(s); continue; }
    const r = G.Engine.tryMove(s, m.x, m.y);
    ok(r.ok, '第 ' + i + ' 步非法: ' + (r.reason || ''));
    s = r.next;
    if (s.phase !== 'playing') break;
  }
});
test('Medium 给出合法着', () => {
  const s = G.Engine.createGame({ size: 9 });
  const m = G.AIMedium.pick(s);
  if (!m.pass) ok(G.Engine.tryMove(s, m.x, m.y).ok);
});
test('Medium 20 步自我对弈合法', () => {
  let s = G.Engine.createGame({ size: 9 });
  for (let i = 0; i < 20; i++) {
    const m = G.AIMedium.pick(s);
    if (m.pass) { s = G.Engine.pass(s); continue; }
    const r = G.Engine.tryMove(s, m.x, m.y);
    ok(r.ok); s = r.next;
    if (s.phase !== 'playing') break;
  }
});
// MCTS 用 await（用了 requestAnimationFrame，但我们没提供）
// 在 Node 里 requestAnimationFrame 不存在；MCTS 调用它时会报 ReferenceError
// 临时打补丁
sandbox.requestAnimationFrame = cb => setTimeout(cb, 0);
await asyncTest('MCTS（simulations=20）给出合法着', async () => {
  const s = G.Engine.createGame({ size: 9 });
  // 注入到 vm context: 不能, vm 已隔离。改用直接重写 Engine 函数？
  // 简单做法: 因为 vm context 共享 sandbox, 但 requestAnimationFrame 是脚本里访问 globalThis 的
  // 检查：MCTS 写的是 await new Promise(r => requestAnimationFrame(r))
  // 在 vm context 里这个 requestAnimationFrame 必须在 sandbox 里
  // 我们把它注入到 sandbox 然后让 MCTS 取
  // -- 在脚本执行时已经求过值, 但 await 是运行时的，每次 await 都新查一次 -> OK
  const m = await G.AIMcts.pick(s, { simulations: 20 });
  if (!m.pass) ok(G.Engine.tryMove(s, m.x, m.y).ok);
});

// ===== Storage =====
// Storage 用了 localStorage（不存在）。补丁一个内存版
sandbox.localStorage = {
  _: {},
  setItem(k, v) { this._[k] = v; },
  getItem(k) { return this._[k] || null; },
  removeItem(k) { delete this._[k]; },
};
suite('Storage');
test('current 保存/读取', () => {
  G.Storage.saveCurrent({ sgf: '(;FF[4]SZ[9])', config: { size: 9 } });
  const got = G.Storage.loadCurrent();
  ok(got);
  eq(got.sgf, '(;FF[4]SZ[9])');
  G.Storage.clearCurrent();
  eq(G.Storage.loadCurrent(), null);
});

// 总结
console.log('\n========');
console.log(`${pass} 通过 / ${pass+fail} 总计 ${fail ? '— ✗ 失败 ' + fail : '— ✓ 全通过'}`);
if (fail > 0) { console.log('失败列表:', failed); process.exit(1); }
})();
