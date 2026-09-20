"""
web_bridge：KGSM 与游戏页面的本地 WebSocket 桥（仅 127.0.0.1）。

- 游戏页由 KGSM 启动时，被注入 bridge.js，页面连到本服务；
- KGSM 点「自动存档」→ 服务端向页面发 request_save → 页面回传当前
  存档文本（原样，不重新编码）→ 服务端转交 KGSM 写入槽位。
- 纯标准库实现最小 WebSocket（RFC6455 服务端）；
- 空闲连接由服务端定时 ping 保活（页面自动回 pong），不再因为
  「一段时间没有数据」而断开重连。

页面注入脚本的两个关键点：
1. 引擎必须在页面 boot 完成后才能取到。<div id="game"> 存在时，
   window.game 会被命名访问解析成那个 DOM 元素（truthy 但没有 save()），
   因此候选对象要排除 DOM 节点，并在引擎出现前持续重试（hello 也会
   在引擎就绪后补发一次）。
2. request_save 触发时若引擎尚未就绪，先等待一段时间再回退到
   localStorage 快照，并把数据来源（engine/localStorage）回报给服务端。
"""

import base64
import hashlib
import json
import socket
import struct
import threading
import time

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

WS_PING_INTERVAL = 20.0      # 秒：空闲时向页面发 ping 的间隔
WS_IDLE_TIMEOUT = 75.0       # 秒：既无数据也无 pong 视为断线
WS_POLL = 1.0                # 秒：socket 轮询粒度


class _IdleTimeout(Exception):
    """空闲超时：本轮什么都没读到（不代表连接断开）。"""


def bridge_js(ws_url, save_wait_ms=5000, hello_timeout_ms=120000):
    """生成注入页面的桥接脚本（连接 ws、响应 request_save、等待引擎就绪）。

    :param save_wait_ms: 收到 request_save 后等待引擎就绪的最长时间
    :param hello_timeout_ms: 引擎未就绪时重复上报 hello 的最长时间
    """
    return (
        "(function(){\n"
        "var KGSM_SAVE_KEY='com.nuclearunicorn.kittengame.savedata';\n"
        "var ENGINE_NAMES=['game','gamePage','kg','engine','ui','Game'];\n"
        f"var HELLO_TIMEOUT={int(hello_timeout_ms)};\n"
        f"var SAVE_WAIT={int(save_wait_ms)};\n"
        "var cached=null;\n"
        "var cachedInfo=null;\n"
        "var lastDeepScan=0;\n"
        "function isDomNode(v){\n"
        "  try{\n"
        "    if(!v || typeof v!=='object'){ return false; }\n"
        "    if(typeof v.nodeType==='number' && v.nodeType===1){ return true; }\n"
        "    if(typeof v.appendChild==='function'"
        " && typeof v.getElementsByTagName==='function'){ return true; }\n"
        "  }catch(e){}\n"
        "  return false;\n"
        "}\n"
        "function isEngine(v){\n"
        "  if(!v || typeof v!=='object' || isDomNode(v)){ return false; }\n"
        "  try{ return typeof v.save==='function'; }catch(e){ return false; }\n"
        "}\n"
        "function remember(engine,hits,doms){\n"
        "  cached=engine;\n"
        "  cachedInfo={hits:hits,doms:doms};\n"
        "  return {engine:engine,hits:hits,domKeys:doms};\n"
        "}\n"
        "function findEngine(force){\n"
        "  if(!force && cached && isEngine(cached)){\n"
        "    return {engine:cached,hits:cachedInfo.hits,domKeys:cachedInfo.doms};\n"
        "  }\n"
        "  var hits=[],doms=[],i,k,v;\n"
        "  for(i=0;i<ENGINE_NAMES.length;i++){\n"
        "    v=window[ENGINE_NAMES[i]];\n"
        "    if(!v){ continue; }\n"
        "    if(isDomNode(v)){ doms.push(ENGINE_NAMES[i]); continue; }\n"
        "    hits.push(ENGINE_NAMES[i]);\n"
        "    if(isEngine(v)){ return remember(v,hits,doms); }\n"
        "    for(k in v){\n"
        "      try{ if(isEngine(v[k]) && (v[k].resPool||v[k].managers)){"
        " return remember(v[k],hits,doms); } }catch(e){}\n"
        "    }\n"
        "  }\n"
        "  var now=Date.now();\n"
        "  if(force || now-lastDeepScan>=1000){\n"
        "    lastDeepScan=now;\n"
        "    for(k in window){\n"
        "      try{\n"
        "        v=window[k];\n"
        "        if(isEngine(v) && (v.resPool||v.managers)){"
        " return remember(v,hits,doms); }\n"
        "      }catch(e){}\n"
        "    }\n"
        "  }\n"
        "  return {engine:null,hits:hits,domKeys:doms};\n"
        "}\n"
        "function compressJson(json){\n"
        "  var e=findEngine(false).engine;\n"
        "  if(e && typeof e.compressLZData==='function'){ return e.compressLZData(json); }\n"
        "  if(window.LZString && typeof LZString.compressToBase64==='function'){"
        " return LZString.compressToBase64(json); }\n"
        "  return json;\n"
        "}\n"
        "function currentSave(){\n"
        "  var e=findEngine(true).engine;\n"
        "  if(e){\n"
        "    try{\n"
        "      var json=JSON.stringify(e.save());\n"
        "      if(json && json[0]==='{'){ return {data:compressJson(json),source:'engine'}; }\n"
        "    }catch(err){}\n"
        "  }\n"
        "  try{\n"
        "    var ls=window.LCstorage||window.localStorage;\n"
        "    var raw=ls?ls.getItem(KGSM_SAVE_KEY):null;\n"
        "    return {data:raw||'',source:raw?'localStorage':''};\n"
        "  }catch(e2){ return {data:'',source:''}; }\n"
        "}\n"
        "function bridgeInfo(){\n"
        "  var found=findEngine(true);\n"
        "  return {type:'hello',\n"
        "    ready: !!found.engine,\n"
        "    hasGame: !!(found.engine && typeof found.engine.save==='function'),\n"
        "    foundKeys: found.hits,\n"
        "    domKeys: found.domKeys,\n"
        "    hasLZ: !!window.LZString,\n"
        "    hasCompress: !!(found.engine && typeof found.engine.compressLZData==='function'),\n"
        "    hasLC: !!((window.LCstorage||window.localStorage))};\n"
        "}\n"
        "function announce(ws){\n"
        "  var info=bridgeInfo();\n"
        "  try{ ws.send(JSON.stringify(info)); }catch(e){ return; }\n"
        "  if(info.ready){ return; }\n"
        "  if(Date.now()-started<HELLO_TIMEOUT){\n"
        "    setTimeout(function(){ announce(ws); },1000);\n"
        "  }\n"
        "}\n"
        "var started=Date.now();\n"
        # ws 提到外层：自动续玩的快照函数也要用它（放在 connect() 里会取不到）
        "var ws=null;\n"
        "function connect(){\n"
        "  try{ ws=new WebSocket('" + ws_url + "'); }catch(e){ ws=null; return; }\n"
        "  ws.onopen=function(){ announce(ws); };\n"
        "  ws.onmessage=function(ev){\n"
        "    try{\n"
        "      var msg=JSON.parse(ev.data);\n"
        "      if(!msg){ return; }\n"
        "      if(msg.type==='request_save'){\n"
        "        var rid=msg.id;\n"
        "        var deadline=Date.now()+SAVE_WAIT;\n"
        "        var send=function(){\n"
        "          if(!findEngine(true).engine && Date.now()<deadline){\n"
        "            setTimeout(send,200);\n"
        "            return;\n"
        "          }\n"
        "          var res=currentSave();\n"
        "          ws.send(JSON.stringify({type:'save_data',id:rid,"
        "data:res.data,source:res.source}));\n"
        "        };\n"
        "        send();\n"
        "      } else if(msg.type==='apply_save' && typeof msg.data==='string' && msg.data){\n"
        "        try{\n"
        "          var eng=findEngine(true).engine;\n"
        "          if(eng && typeof eng.isReadOnly==='function' && eng.isReadOnly()){\n"
        "            ws.send(JSON.stringify({type:'apply_err',id:msg.id,"
        "err:'read-only preview'}));\n"
        "            return;\n"
        "          }\n"
        "          var ls=window.LCstorage||window.localStorage;\n"
        "          // 与游戏自己的导入一致：先确认能解出以 { 开头的 JSON，再写进存储\n"
        "          if(eng && typeof eng.decompressLZData==='function'){\n"
        "            var probe=(msg.data[0]==='{')?msg.data:eng.decompressLZData(msg.data);\n"
        "            if(!probe || probe[0]!=='{'){ throw new Error('Integrity check failure'); }\n"
        "          }\n"
        "          if(ls){ ls.setItem(KGSM_SAVE_KEY, msg.data); }\n"
        "          ws.send(JSON.stringify({type:'apply_ok',id:msg.id}));\n"
        "          if(eng && typeof eng.load==='function'){\n"
        "            // 就地重新载入（游戏自己的导入就是这么做的）：直接刷新页面会被\n"
        "            // 游戏退出时的自动保存覆盖掉，看起来就像「自动读档没反应」\n"
        "            setTimeout(function(){\n"
        "              try{\n"
        "                eng.load();\n"
        "                if(typeof eng.render==='function'){ eng.render(); }\n"
        "              }catch(e3){ console.log('KGSM: engine reload failed', e3); }\n"
        "            }, 120);\n"
        "          } else {\n"
        "            setTimeout(function(){ location.reload(); }, 120);\n"
        "          }\n"
        "        }catch(e2){ ws.send(JSON.stringify({type:'apply_err',id:msg.id,err:String(e2)})); }\n"
        "      }\n"
        "    }catch(e){}\n"
        "  };\n"
        "  ws.onclose=function(){ setTimeout(connect, 3000); };\n"
        "}\n"
        "function sendSessionSnapshot(){\n"
        "  // 关闭游戏（关窗口/关标签/刷新）时把当前进度交给 KGSM：\n"
        "  // 游戏的存档在 localStorage 里按来源（含端口）隔离，端口一变就是新来源，\n"
        "  // 所以由 KGSM 自己存一份，下次打开再灌回去（自动续玩）。\n"
        "  //\n"
        "  // cleared 表示游戏自己的 localStorage 里已经没有存档了：\n"
        "  //   - 游戏内删档/重置就是这种状态，KGSM 存的那份必须一起删掉，否则下次\n"
        "  //     打开会把旧存档灌回来，看起来像「删档没用」；\n"
        "  //   - 但刚开局、游戏还没自动保存过时 localStorage 也是空的，那时引擎里\n"
        "  //     的进度是真的，要照常存下来。\n"
        "  // 区分办法：由 KGSM 侧决定——已存过就按删档处理，没存过就照常保存。\n"
        "  try{\n"
        "    if(!ws){ return; }\n"
        "    var ls=window.LCstorage||window.localStorage;\n"
        "    var raw=ls?ls.getItem(KGSM_SAVE_KEY):null;\n"
        "    var res=currentSave();\n"
        "    if(!raw && ls){\n"
        "      // currentSave() 会调用引擎的 save()，而它会顺手把当前状态写回\n"
        "      // localStorage。游戏自己的存储里本来没有存档时（删档/重置，或还没自动\n"
        "      // 保存过）必须把这个副作用清掉，否则删档会被我们“救”回来。\n"
        "      try{ ls.removeItem(KGSM_SAVE_KEY); }catch(e4){}\n"
        "    }\n"
        "    var data=(res&&res.data)||raw||'';\n"
        "    ws.send(JSON.stringify({type:'session_snapshot',data:data,"
        "cleared:!raw}));\n"
        "  }catch(e){}\n"
        "}\n"
        "window.addEventListener('pagehide',sendSessionSnapshot);\n"
        "window.addEventListener('beforeunload',sendSessionSnapshot);\n"
        "connect();\n"
        "})();"
    )


class _Client:
    def __init__(self, conn, addr):
        self.conn = conn
        self.addr = addr
        self.closed = False


class WebSocketBridge:
    """本地 WebSocket 服务端：页面连入后等待 KGSM 的存档请求。"""

    def __init__(self):
        self._server_sock = None
        self._thread = None
        self._clients = []
        self._lock = threading.Lock()
        self._pending = None      # {'id','event','data','source'} 取存档请求
        self._apply = None        # {'id','event','ok','err'} 下发存档的确认
        self._next_id = 1
        self._ui_queue = None
        self._on_connect = None
        self._on_snapshot = None
        self.port = None

    def set_ui_queue(self, queue):
        """注入 UI 事件队列，用于把连接状态回显到「启动游戏」页日志。"""
        self._ui_queue = queue

    def set_session_hooks(self, on_connect=None, on_snapshot=None):
        """自动续玩用的两个回调。

        :param on_connect: 页面连上时调用（在单独线程里跑，避免在读取线程里
            等 apply_ok 造成死锁）
        :param on_snapshot: 页面在关闭/刷新前把当前进度发过来时调用，参数是存档文本
        """
        self._on_connect = on_connect
        self._on_snapshot = on_snapshot

    def _safe_hook(self, hook, *args):
        """跑自动续玩的回调：任何异常都只记日志，不影响桥本身。"""
        try:
            hook(*args)
        except Exception as e:
            self._log(f"session hook failed: {e}")

    def _log(self, msg):
        if self._ui_queue is not None:
            try:
                self._ui_queue.put(("bridge_log", msg))
            except Exception:
                pass

    # ---------------- 生命周期 ----------------
    def start(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        s.listen(4)
        s.settimeout(0.5)
        self._server_sock = s
        self.port = s.getsockname()[1]
        self._thread = threading.Thread(target=self._accept_loop,
                                        name="kgsm-ws", daemon=True)
        self._thread.start()
        return self.port

    def stop(self):
        with self._lock:
            clients = list(self._clients)
            self._clients = []
            sock = self._server_sock
            self._server_sock = None
            pending = self._pending
            self._pending = None
        for c in clients:
            try:
                c.conn.close()
            except Exception:
                pass
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        if pending:
            pending['data'] = None
            pending['event'].set()

    @property
    def has_client(self):
        with self._lock:
            return any(not c.closed for c in self._clients)

    def _pick_clients(self):
        """取候选客户端（最新连接在前）；同时剔除已关闭的。"""
        with self._lock:
            self._clients = [c for c in self._clients if not c.closed]
            return list(reversed(self._clients))

    def _drop_client(self, client):
        with self._lock:
            try:
                self._clients.remove(client)
            except ValueError:
                pass
            try:
                client.conn.close()
            except Exception:
                pass

    # ---------------- 请求存档 ----------------
    def request_save(self, timeout=15.0):
        """向已连接的页面请求一次存档；返回存档文本或 None。

        - 优先用最新连接的客户端；发送失败自动剔除换下一个候选，避免页面刷新
          后残留的旧连接把请求全部带超时。
        - 若已有请求在途（例如编辑器与自动存档同时发起），先等它结束再发自己
          的请求，而不是立刻返回 None（旧行为会让界面误报"超时/解码失败"）。
        - 等待时长用调用方给的 timeout（不再被硬性截断成 8 秒）。
        """
        candidates = self._pick_clients()
        if not candidates:
            return None
        self._wait_pending(float(timeout))
        for client in candidates:
            req_id = self._next_id
            self._next_id += 1
            event = threading.Event()
            with self._lock:
                self._pending = {"id": req_id, "event": event,
                                 "data": None, "source": None}
            try:
                self._send_text(client, json.dumps(
                    {"type": "request_save", "id": req_id}))
            except Exception:
                self._log("request send failed, dropping stale client")
                with self._lock:
                    if self._pending and self._pending["id"] == req_id:
                        self._pending = None
                self._drop_client(client)
                continue
            got_it = event.wait(timeout)
            with self._lock:
                pend = self._pending
                if pend is not None and pend["id"] == req_id:
                    self._pending = None
            if pend is not None and pend.get("id") != req_id:
                # 已经被别的请求接管（极罕见）：不要误用别人的数据
                self._log("save request superseded by another request")
                pend = None
            if pend and pend['data'] is not None:
                self._log(f"save data received: {len(pend['data'])} chars "
                          f"(source: {pend.get('source') or 'unknown'})")
                return pend['data']
            if not got_it:
                self._log("save request timed out, trying next client if any")
        self._log("save request timed out: page did not respond")
        return None

    def _wait_pending(self, timeout):
        """等前一个请求结束（最多 timeout 秒），避免并发时立刻失败。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                pend = self._pending
            if pend is None:
                return True
            pend["event"].wait(0.2)
        return False

    def apply_save(self, blob, timeout=8.0):
        """把存档下发给页面，并等待页面确认写入结果。

        :return: True=页面确认写入（apply_ok）
                 False=页面报错或发送失败
                 None=已发送但页面没在 timeout 内确认（例如页面正在刷新）
        """
        candidates = self._pick_clients()
        if not candidates:
            return False
        for client in candidates:
            req_id = self._next_id
            self._next_id += 1
            event = threading.Event()
            with self._lock:
                self._apply = {"id": req_id, "event": event, "ok": None,
                               "err": None}
            try:
                self._send_text(client, json.dumps(
                    {"type": "apply_save", "id": req_id, "data": blob}))
            except Exception:
                self._log("apply send failed, dropping stale client")
                with self._lock:
                    self._apply = None
                self._drop_client(client)
                continue
            self._log(f"save sent to page: {len(blob)} chars, waiting for ack")
            if event.wait(timeout):
                with self._lock:
                    result = self._apply
                    self._apply = None
                if result and result["ok"]:
                    self._log("page confirmed the save was applied")
                    return True
                detail = (result or {}).get("err") or "unknown"
                self._log(f"page reported apply error: {detail}")
                return False
            with self._lock:
                self._apply = None
            self._log("page did not confirm within the timeout")
            return None
        return False

    # ---------------- 服务器内部 ----------------
    def _accept_loop(self):
        while True:
            sock = self._server_sock
            if sock is None:
                return
            try:
                conn, addr = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(target=self._handle_client,
                             args=(conn, addr), daemon=True).start()

    def _handle_client(self, conn, addr):
        try:
            if not self._handshake(conn):
                conn.close()
                return
            with self._lock:
                self._clients.append(_Client(conn, addr))
            self._log(f"game page connected ({addr[0]}:{addr[1]})")
            self._read_loop(conn)
        except Exception:
            pass
        finally:
            with self._lock:
                self._clients = [c for c in self._clients
                                 if c.conn is not conn]
            self._log("game page disconnected")

    def _handshake(self, conn):
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = conn.recv(1024)
            if not chunk:
                return False
            data += chunk
            if len(data) > 65536:
                return False
        headers = {}
        lines = data.decode("utf-8", "replace").split("\r\n")
        for line in lines[1:]:
            if ":" in line:
                k, _, v = line.partition(":")
                headers[k.strip().lower()] = v.strip()
        key = headers.get("sec-websocket-key", "")
        if not key or "websocket" not in headers.get("upgrade", "").lower():
            return False
        accept = base64.b64encode(
            hashlib.sha1((key + WS_GUID).encode()).digest()).decode()
        resp = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
        )
        conn.sendall(resp.encode())
        return True

    def _read_loop(self, conn):
        """读取页面帧；空闲时发 ping 保活，长时间无响应才断开。"""
        conn.settimeout(WS_POLL)
        active = time.time()          # 最近一次收到完整帧的时刻
        pinged = 0.0
        while True:
            try:
                head = self._recv_exact(conn, 2)
            except _IdleTimeout:
                now = time.time()
                if now - pinged >= WS_PING_INTERVAL:
                    pinged = now
                    try:
                        self._send_ping(conn)
                    except Exception:
                        return
                if now - active > WS_IDLE_TIMEOUT:
                    self._log(
                        f"bridge idle {int(now - active)}s without any "
                        f"frame, closing connection")
                    return
                continue
            except Exception:
                return
            if head is None:
                return
            b1, b2 = head[0], head[1]
            opcode = b1 & 0x0F
            length = b2 & 0x7F
            masked = (b2 & 0x80) != 0
            if length == 126:
                ext = self._recv_exact(conn, 2)
                if ext is None:
                    return
                length = struct.unpack(">H", ext)[0]
            elif length == 127:
                ext = self._recv_exact(conn, 8)
                if ext is None:
                    return
                length = struct.unpack(">Q", ext)[0]
            mask_key = b""
            if masked:
                mask_key = self._recv_exact(conn, 4)
                if mask_key is None:
                    return
            payload = self._recv_exact(conn, length)
            if payload is None:
                return
            active = time.time()
            if masked:
                payload = bytes(b ^ mask_key[i % 4]
                                for i, b in enumerate(payload))
            if opcode == 0x8:        # close
                try:
                    self._send_raw(conn, b"\x88\x00")
                except Exception:
                    pass
                return
            if opcode == 0xA:        # pong：保活确认，已由 active 记录
                continue
            if opcode == 0x9:        # ping -> pong
                try:
                    self._send_raw(conn, bytes([0x8A]) +
                                   self._frame_len(len(payload)) + payload)
                except Exception:
                    pass
                continue
            if opcode == 0x1:        # text
                self._on_message(conn, payload.decode("utf-8", "replace"))

    def _recv_exact(self, conn, n):
        buf = b""
        while len(buf) < n:
            try:
                chunk = conn.recv(n - len(buf))
            except socket.timeout:
                if not buf:
                    raise _IdleTimeout()
                raise
            if not chunk:
                return None
            buf += chunk
        return buf

    def _send_ping(self, conn):
        """发送空 ping 帧；浏览器按 RFC6455 自动回 pong。"""
        self._send_raw(conn, bytes([0x89]) + self._frame_len(0))

    def _frame_len(self, length):
        if length < 126:
            return bytes([length])
        if length < 65536:
            return b"\x7e" + struct.pack(">H", length)
        return b"\x7f" + struct.pack(">Q", length)

    def _send_raw(self, conn, payload):
        conn.sendall(payload)

    def _send_text(self, client, text):
        data = text.encode("utf-8")
        conn = client.conn
        conn.sendall(bytes([0x81]) + self._frame_len(len(data)) + data)

    def _on_message(self, conn, text):
        try:
            msg = json.loads(text)
        except Exception:
            return
        if not isinstance(msg, dict):
            return
        mtype = msg.get("type")
        if mtype == "hello":
            self._log("hello from page: " + json.dumps(
                {k: msg[k] for k in
                 ("ready", "hasGame", "foundKeys", "domKeys", "hasLZ",
                  "hasCompress", "hasLC")
                 if k in msg}))
            hook = self._on_connect
            if hook is not None:
                # 单独线程：回调里会下发存档并等页面确认，不能在读取线程里等
                threading.Thread(target=self._safe_hook, args=(hook,),
                                 name="kgsm-session", daemon=True).start()
            return
        if mtype == "session_snapshot":
            data = msg.get("data")
            cleared = bool(msg.get("cleared"))
            hook = self._on_snapshot
            if hook is not None and isinstance(data, str):
                self._safe_hook(hook, data, cleared)
            return
        if mtype == "apply_ok":
            with self._lock:
                ap = self._apply
                if ap and ap["id"] == msg.get("id"):
                    ap["ok"] = True
                    ap["event"].set()
            return
        if mtype == "apply_err":
            with self._lock:
                ap = self._apply
                if ap and ap["id"] == msg.get("id"):
                    ap["ok"] = False
                    ap["err"] = str(msg.get("err") or "page reported an error")
                    ap["event"].set()
            return
        if mtype != "save_data":
            return
        req_id = msg.get("id")
        data = msg.get("data")
        source = msg.get("source") or "unknown"
        if not isinstance(data, str):
            self._log("save_data ignored: data is not a string")
            return
        with self._lock:
            pend = self._pending
            if pend and pend['id'] == req_id:
                pend['data'] = data
                pend['source'] = source
                pend['event'].set()
            else:
                self._log("save_data ignored: no matching request id")
