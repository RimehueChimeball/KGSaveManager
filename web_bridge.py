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
        "function connect(){\n"
        "  var ws;\n"
        "  try{ ws=new WebSocket('" + ws_url + "'); }catch(e){ return; }\n"
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
        "          var ls=window.LCstorage||window.localStorage;\n"
        "          if(ls){ ls.setItem(KGSM_SAVE_KEY, msg.data); }\n"
        "          ws.send(JSON.stringify({type:'apply_ok',id:msg.id}));\n"
        "          setTimeout(function(){ location.reload(); }, 120);\n"
        "        }catch(e2){ ws.send(JSON.stringify({type:'apply_err',id:msg.id,err:String(e2)})); }\n"
        "      }\n"
        "    }catch(e){}\n"
        "  };\n"
        "  ws.onclose=function(){ setTimeout(connect, 3000); };\n"
        "}\n"
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
        self._pending = None      # {'id','event','data'}
        self._next_id = 1
        self._ui_queue = None
        self.port = None

    def set_ui_queue(self, queue):
        """注入 UI 事件队列，用于把连接状态回显到「启动游戏」页日志。"""
        self._ui_queue = queue

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
        """向已连接的页面请求一次存档；返回文本或 None。

        优先用最新连接的客户端；发送失败自动剔除并换下一个候选，
        避免页面刷新后残留的旧连接把请求全部带超时。
        """
        candidates = self._pick_clients()
        if not candidates:
            return None
        if self._pending is not None:
            return None          # 已有请求在进行
        for client in candidates:
            if self._pending is not None:
                self._pending = None
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
                self._drop_client(client)
                continue
            event.wait(min(timeout, 8.0))
            with self._lock:
                pend = self._pending
                self._pending = None
            if pend and pend['data'] is not None:
                self._log(f"save data received: {len(pend['data'])} chars "
                          f"(source: {pend.get('source') or 'unknown'})")
                return pend['data']
            self._log("save request timed out, trying next client if any")
        self._log("save request timed out: page did not respond")
        return None

    def apply_save(self, blob, timeout=5.0):
        """把存档文本下发给页面（页面写入本地存档后自动刷新）。

        :return: True 表示已发送给已连接的页面；无连接/出错返回 False
        """
        candidates = self._pick_clients()
        if not candidates:
            return False
        for client in candidates:
            try:
                self._send_text(client, json.dumps(
                    {"type": "apply_save", "id": self._next_id,
                     "data": blob}))
                self._log(f"save sent to page: {len(blob)} chars")
                return True
            except Exception:
                self._log("apply send failed, dropping stale client")
                self._drop_client(client)
                continue
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
