/*
 * 注入脚本（bridge_js）行为测试夹具。
 *
 * 用法： node bridge_harness.js <bridge.js 路径> [saveWaitMs] [helloTimeoutMs]
 * 输出： 一行 JSON（结果对象）；断言失败时向 stderr 打印并 exit 1。
 *
 * 模拟浏览器环境：window / WebSocket / LCstorage / location 都是替身，
 * 用来验证“DOM 元素误判”和“引擎晚到”两条时序问题。
 */

const fs = require('fs');
const vm = require('vm');

const bridgePath = process.argv[2];
const saveWaitMs = parseInt(process.argv[3] || '5000', 10);
const helloTimeoutMs = parseInt(process.argv[4] || '120000', 10);

const failures = [];
function check(cond, msg) {
  if (!cond) { failures.push(msg); }
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function waitFor(fn, timeoutMs, stepMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (fn()) { return true; }
    await sleep(stepMs || 20);
  }
  return fn();
}

async function main() {
  const win = {};
  const results = {
    hellos: [],
    saves: [],
    applied: [],
    reloads: 0,
    setItems: {},
    ok: false,
    failures,
  };

  win.LCstorage = {
    getItem: (k) => (k === 'com.nuclearunicorn.kittengame.savedata'
      ? (win.__stored === undefined ? null : win.__stored) : null),
    setItem: (k, v) => { results.setItems[k] = v; },
  };
  // 先放一个 <div id="game"> 造成的命名访问假象：truthy 但没有 save()
  win.game = {
    nodeType: 1,
    appendChild() {},
    getElementsByTagName() { return []; },
  };

  let ws = null;
  class FakeWebSocket {
    constructor(url) {
      this.url = url;
      this.readyState = 1;      // 像真 WebSocket 一样，连上后就是 OPEN
      ws = this;
      results.url = url;
    }
    send(text) { results.sentByPage = results.sentByPage || []; }
  }
  // 自动续玩：脚本会往 window 上挂 pagehide/beforeunload，这里收集起来手动触发
  const listeners = {};
  win.addEventListener = (name, fn) => {
    listeners[name] = listeners[name] || [];
    listeners[name].push(fn);
  };
  global.window = win;
  global.WebSocket = FakeWebSocket;
  global.location = { reload() { results.reloads += 1; } };

  let code = fs.readFileSync(bridgePath, 'utf8');
  vm.runInThisContext(code, { filename: 'bridge.js' });
  check(!!ws, '注入脚本没有创建 WebSocket 连接');
  if (!ws) { finish(results); return; }

  // ---- 场景 1：引擎未就绪（window.game 是 DOM 元素）----
  const helloSink = [];
  const originalSend = FakeWebSocket.prototype.send;
  FakeWebSocket.prototype.send = function (text) {
    const msg = JSON.parse(text);
    if (msg.type === 'hello') { results.hellos.push(msg); }
    else if (msg.type === 'save_data') { results.saves.push(msg); }
    else if (msg.type === 'apply_ok' || msg.type === 'apply_err') {
      results.applied.push(msg);
    }
    return originalSend.call(this, text);
  };

  ws.onopen();
  await waitFor(() => results.hellos.length >= 1, 2000, 10);
  check(results.hellos.length >= 1, '连接后没有发送 hello');
  const first = results.hellos[0] || {};
  check(first.ready === false, 'hello.ready 应为 false（引擎未就绪）');
  check(first.hasGame === false, 'hello.hasGame 应为 false（DOM 元素不是引擎）');
  check((first.foundKeys || []).indexOf('game') < 0,
    'DOM 元素不应出现在 foundKeys 里');
  check((first.domKeys || []).indexOf('game') >= 0,
    'DOM 元素应被记入 domKeys');

  // ---- 场景 2：引擎晚到，hello 应补发且 ready=true ----
  win.game = {
    save() { return { a: 1, name: 'kitten' }; },
    compressLZData(json) { return 'LZ:' + json; },
    resPool: {},
  };
  const gotReady = await waitFor(
    () => results.hellos.some((h) => h.ready === true &&
      h.hasGame === true && h.hasCompress === true && h.hasLZ === false),
    4000, 50);
  check(gotReady, '引擎就绪后没有补发 ready=true 的 hello');

  // ---- 场景 3：request_save 走引擎 ----
  ws.onmessage({ data: JSON.stringify({ type: 'request_save', id: 7 }) });
  await waitFor(() => results.saves.length >= 1, 3000, 20);
  const save1 = results.saves[0] || {};
  check(save1.id === 7, 'save_data.id 应与请求 id 一致');
  check(save1.source === 'engine', 'save_data.source 应为 engine');
  check(save1.data === 'LZ:{"a":1,"name":"kitten"}',
    'save_data.data 应为压缩后的引擎存档，实际: ' + save1.data);

  // ---- 场景 4：apply_save 写入本地存档并刷新 ----
  ws.onmessage({
    data: JSON.stringify({ type: 'apply_save', id: 9, data: 'BLOB' }),
  });
  await waitFor(() => results.applied.length >= 1, 2000, 20);
  check(results.applied[0] && results.applied[0].type === 'apply_ok',
    'apply_save 后应回 apply_ok');
  check(results.setItems['com.nuclearunicorn.kittengame.savedata'] === 'BLOB',
    'apply_save 应写入 localStorage');
  await waitFor(() => results.reloads >= 1, 2000, 20);
  check(results.reloads >= 1, 'apply_save 后应刷新页面');

  // ---- 场景 5：引擎消失时回退到 localStorage 快照 ----
  delete win.game;
  win.__stored = 'RAW-SNAPSHOT';
  const before = results.saves.length;
  ws.onmessage({ data: JSON.stringify({ type: 'request_save', id: 8 }) });
  const gotFallback = await waitFor(
    () => results.saves.length > before, saveWaitMs + 4000, 50);
  check(gotFallback, '引擎缺失时也应返回存档（回退 localStorage）');
  const save2 = results.saves[results.saves.length - 1] || {};
  check(save2.id === 8, '回退存档的 id 应与请求一致');
  check(save2.source === 'localStorage',
    '回退存档的 source 应为 localStorage，实际: ' + save2.source);
  check(save2.data === 'RAW-SNAPSHOT', '回退存档内容应为 localStorage 快照');

  // ---- 场景 6：关闭游戏时把当前进度交给 KGSM（自动续玩）----
  const snapshots = [];
  const sendBefore = FakeWebSocket.prototype.send;
  FakeWebSocket.prototype.send = function (text) {
    const msg = JSON.parse(text);
    if (msg.type === 'session_snapshot') { snapshots.push(msg.data); }
    return sendBefore.call(this, text);
  };
  // 引擎的 save() 返回对象（和游戏里一样），压缩交给 compressLZData
  win.game = {
    save() { return { a: 1 }; },
    compressLZData(json) { return 'LZ:' + json; },
    resPool: {}, managers: {},
  };
  const handlers = listeners.pagehide || [];
  check(handlers.length >= 1, '脚本未监听 pagehide（关闭游戏时无法保存进度）');
  handlers.forEach((fn) => {
    try {
      fn();
    } catch (err) {
      failures.push('pagehide 处理器抛错: ' + (err && err.stack || err));
    }
  });
  check(snapshots.length === 1 && snapshots[0] === 'LZ:{"a":1}',
    '关闭游戏时应把当前存档发给 KGSM，实际: ' + JSON.stringify(snapshots));

  // ---- 场景 7：游戏内删档（localStorage 已清空）→ 要发空内容，让 KGSM 也删掉 ----
  // 真实情况：点删档/重置时游戏清掉 localStorage 并刷新，而刷新前那一刻引擎里
  // 还留着旧进度；若这里发旧进度，下次打开就会被灌回来，看起来像「删档没用」。
  snapshots.length = 0;
  win.__stored = null;                  // LCstorage.getItem 返回 null = 已清空
  ws.readyState = 1;
  (listeners.pagehide || []).forEach((fn) => fn());
  check(snapshots.length === 1 && snapshots[0] === '',
    '删档后应发空内容（实际: ' + JSON.stringify(snapshots) + '）');

  results.ok = failures.length === 0;
  finish(results);
}

function finish(results) {
  process.stdout.write(JSON.stringify(results));
  if (failures.length) {
    process.stderr.write('FAILURES:\n' + failures.join('\n') + '\n');
    process.exit(1);
  }
}

main().catch((err) => {
  process.stderr.write('harness error: ' + (err && err.stack || err) + '\n');
  process.exit(2);
});
