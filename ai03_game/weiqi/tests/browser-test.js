/**
 * 用 Chrome --dump-dom 抓 probe 结果（避免 console 路由问题）
 * 加载一个 wrapper HTML，里面 iframe 加载真正的 index.html
 * 在 wrapper 里用 setTimeout 循环把 iframe 内部状态读到 wrapper 顶层 DOM
 * 最后 dump-dom 时所有结果都在 wrapper DOM 里
 */
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const indexPath = path.resolve(__dirname, '../index.html');
const indexUrl = 'file://' + indexPath;

const probeScript = `
(async function () {
  const results = {};
  const out = document.getElementById('result');
  function set(k, v) { results[k] = v; out.textContent = JSON.stringify(results); }
  try {
    const f = document.getElementById('game');
    // wait for iframe load
    await new Promise(r => f.addEventListener('load', r, { once: true }));
    // wait for GoNeon ready
    let waited = 0;
    while (!f.contentWindow.GoNeon && waited < 3000) {
      await new Promise(r => setTimeout(r, 50));
      waited += 50;
    }
    const w = f.contentWindow;
    const d = w.document;
    set('GoNeon_loaded', !!w.GoNeon);
    set('menu_present', !!d.getElementById('menu'));
    set('menu_has_start_btn', !!d.getElementById('m-start'));

    // 选 9 路 + AI low + black
    const setOpt = (group, value) => {
      d.querySelectorAll('[data-group="' + group + '"] .opt-btn').forEach(b => b.classList.remove('active'));
      d.querySelector('[data-group="' + group + '"] .opt-btn[data-v="' + value + '"]').classList.add('active');
    };
    setOpt('size', '9'); setOpt('opp', 'ai'); setOpt('lvl', 'low'); setOpt('my', 'black');
    d.getElementById('m-start').click();

    await new Promise(r => setTimeout(r, 200));

    set('game_active', d.getElementById('game').classList.contains('active'));
    const canvases = d.querySelectorAll('#board-host canvas');
    set('canvas_count', canvases.length);

    // 通过 fx canvas dispatchEvent click
    const fxC = d.querySelector('#board-host canvas[data-layer="fx"]');
    set('fx_canvas_present', !!fxC);

    function clickCell(x, y) {
      const rect = fxC.getBoundingClientRect();
      const cellPx = Math.floor((Math.min(rect.width, rect.height) * 0.92) / 9);
      const padPx = Math.floor(cellPx * 1.2);
      const px = padPx + x * cellPx;
      const py = padPx + y * cellPx;
      const ev = new w.MouseEvent('click', {
        bubbles: true, cancelable: true,
        clientX: rect.left + px, clientY: rect.top + py,
      });
      fxC.dispatchEvent(ev);
    }

    const beforeNum = parseInt(d.getElementById('m-num').textContent, 10);
    set('move_count_initial', beforeNum);

    clickCell(4, 4);
    // AI low 立即回应，等够时间收尾
    await new Promise(r => setTimeout(r, 800));
    const afterAI = parseInt(d.getElementById('m-num').textContent, 10);
    set('move_count_after_ai', afterAI);
    set('human_and_ai_played', afterAI === 2);

    // 悔棋（应一次性撤回 AI + 人类两步）
    d.getElementById('b-undo').click();
    await new Promise(r => setTimeout(r, 300));
    const afterUndo = parseInt(d.getElementById('m-num').textContent, 10);
    set('move_count_after_undo', afterUndo);
    set('undo_works', afterUndo === 0);

    // 把 GoNeon 暴露到 wrapper 顶层不可行（跨 frame 受限）
    // 改为：通过 UI 验证 — 落子 + 保存 SGF（点击按钮触发下载，我们检查没有错误）
    // 测试棋谱信息：点保存 SGF 看是否触发任何错误
    let sgfClickError = null;
    try { d.getElementById('b-save').click(); } catch (e) { sgfClickError = e.message; }
    set('sgf_save_no_error', sgfClickError === null);

    set('DONE', true);
  } catch (e) {
    set('FATAL', e.message + ' :: ' + (e.stack || '').slice(0, 200));
  }
})();
`;

const wrapperHtml = `<!doctype html>
<html><head><meta charset="utf-8"></head>
<body>
<pre id="result">init</pre>
<iframe id="game" src="${indexUrl}" style="width:1024px;height:800px;border:0"></iframe>
<script>${probeScript}</script>
</body></html>`;

const wrapperPath = '/tmp/goneon-probe.html';
fs.writeFileSync(wrapperPath, wrapperHtml);

const args = [
  '--headless=new',
  '--disable-gpu',
  '--no-sandbox',
  '--virtual-time-budget=10000',
  '--run-all-compositor-stages-before-draw',
  '--allow-file-access-from-files',
  '--dump-dom',
  'file://' + wrapperPath,
];

console.log('Launching Chrome...');
const proc = spawn(CHROME, args, { stdio: ['ignore', 'pipe', 'pipe'] });
let out = '';
proc.stdout.on('data', d => out += d);
proc.on('close', code => {
  const m = out.match(/<pre id="result">([\s\S]*?)<\/pre>/);
  if (!m) {
    console.error('未找到 result pre 标签');
    console.error('STDOUT 前 500 字符:', out.slice(0, 500));
    process.exit(1);
  }
  let parsed;
  try { parsed = JSON.parse(m[1]); }
  catch (e) {
    console.error('JSON 解析失败:', m[1].slice(0, 200));
    process.exit(1);
  }
  console.log('--- probe ---');
  for (const [k, v] of Object.entries(parsed)) console.log('  ', k, '=', JSON.stringify(v));

  const checks = {
    menu_present: parsed.menu_present === true,
    game_active: parsed.game_active === true,
    canvas_count: parsed.canvas_count === 3,
    fx_canvas_present: parsed.fx_canvas_present === true,
    human_and_ai_played: parsed.human_and_ai_played === true,
    undo_works: parsed.undo_works === true,
    sgf_save_no_error: parsed.sgf_save_no_error === true,
    DONE: parsed.DONE === true,
    NO_FATAL: !parsed.FATAL,
  };
  console.log('\n--- checks ---');
  let pass = 0, fail = 0;
  for (const [k, v] of Object.entries(checks)) {
    console.log((v ? '✓' : '✗'), k);
    v ? pass++ : fail++;
  }
  console.log(`\n${pass}/${pass+fail} 通过${fail ? ' — ✗ 失败 ' + fail : ''}`);
  if (parsed.FATAL) console.log('FATAL:', parsed.FATAL);
  process.exit(fail ? 1 : 0);
});
setTimeout(() => proc.kill(), 15000);
