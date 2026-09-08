"""
web_bridge：KGSM 与游戏页面的本地 WebSocket 桥（仅 127.0.0.1）。

- 游戏页由 KGSM 启动时，被注入 bridge.js，页面连到本服务；
- KGSM 点「自动存档」→ 服务端向页面发 request_save → 页面回传当前
  存档文本（原样，不重新编码）→ 服务端转交 KGSM 写入槽位。
- 纯标准库实现最小 WebSocket（RFC6455 服务端）。
"""

import base64
import hashlib
import json
import socket
import struct
import threading

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def bridge_js(ws_url):
    """生成注入页面的桥接脚本（连接 ws 并响应 request_save）。"""
    return (
        "(function(){\n"
        "var KGSM_SAVE_KEY='com.nuclearunicorn.kittengame.savedata';\n"
        "function currentSave(){\n"
        "  try{\n"
        "    if(window.game && typeof window.game.save==='function'){\n"
        "      var json=JSON.stringify(window.game.save());\n"
        "      if(json && json[0]==='{'){\n"
        "        if(window.game.compressLZData){return window.game.compressLZData(json);}\n"
        "        if(window.LZString){return LZString.compressToBase64(json);}\n"
        "        return json;\n"
        "      }\n"
        "    }\n"
        "  }catch(e){}\n"
        "  try{\n"
        "    var ls=window.LCstorage||window.localStorage;\n"
        "    var raw=ls?ls.getItem(KGSM_SAVE_KEY):null;\n"
        "    return raw||'';\n"
        "  }catch(e2){return '';}\n"
        "}\n"
        "function bridgeInfo(){\n"
        "  var g=window.game;\n"
        "  return {type:'hello',\n"
        "    hasGame: !!(g && typeof g.save==='function'),\n"
        "    hasLZ: !!window.LZString,\n"
        "    hasCompress: !!(g && typeof g.compressLZData==='function'),\n"
        "    hasLC: !!((window.LCstorage||window.localStorage))};\n"
        "}\n"
        "function connect(){\n"
        "  var ws;\n"
        "  try{ ws=new WebSocket('" + ws_url + "'); }catch(e){ return; }\n"
        "  ws.onopen=function(){ try{ ws.send(JSON.stringify(bridgeInfo())); }catch(e){} };\n"
        "  ws.onmessage=function(ev){\n"
        "    try{\n"
        "      var msg=JSON.parse(ev.data);\n"
        "      if(msg && msg.type==='request_save'){\n"
        "        var data=currentSave();\n"
        "        ws.send(JSON.stringify({type:'save_data',id:msg.id,data:data}));\n"
        "      } else if(msg && msg.type==='apply_save' && typeof msg.data==='string' && msg.data){\n"
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

    # ---------------- 请求存档 ----------------
    def request_save(self, timeout=15.0):
        """向已连接的页面请求一次存档；返回文本或 None。"""
        with self._lock:
            client = next((c for c in self._clients if not c.closed), None)
            if client is None:
                return None
            if self._pending is not None:
                return None          # 已有请求在进行
            req_id = self._next_id
            self._next_id += 1
            event = threading.Event()
            self._pending = {"id": req_id, "event": event, "data": None}
        try:
            self._send_text(client, json.dumps(
                {"type": "request_save", "id": req_id}))
        except Exception:
            self._clear_pending(req_id)
            return None
        event.wait(timeout)
        with self._lock:
            pend = self._pending
            self._pending = None
        if pend and pend['data'] is not None:
            self._log(f"save data received: {len(pend['data'])} chars")
            return pend['data']
        self._log("save request timed out: page did not respond")
        return None

    def apply_save(self, blob, timeout=5.0):
        """把存档文本下发给页面（页面写入本地存档后自动刷新）。

        :return: True 表示已发送给已连接的页面；无连接/出错返回 False
        """
        with self._lock:
            client = next((c for c in self._clients if not c.closed), None)
            if client is None:
                return False
        try:
            self._send_text(client, json.dumps(
                {"type": "apply_save", "id": self._next_id, "data": blob}))
            self._log(f"save sent to page: {len(blob)} chars")
            return True
        except Exception as e:
            self._log(f"failed to send save to page: {e}")
            return False

    def _clear_pending(self, req_id):
        with self._lock:
            if self._pending and self._pending['id'] == req_id:
                self._pending = None

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
        conn.settimeout(30)
        while True:
            try:
                head = self._recv_exact(conn, 2)
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
            if masked:
                payload = bytes(b ^ mask_key[i % 4]
                                for i, b in enumerate(payload))
            if opcode == 0x8:        # close
                try:
                    self._send_raw(conn, b"\x88\x00")
                except Exception:
                    pass
                return
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
            chunk = conn.recv(n - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf

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
                 ("hasGame", "hasLZ", "hasCompress", "hasLC")
                 if k in msg}))
            return
        if mtype != "save_data":
            return
        req_id = msg.get("id")
        data = msg.get("data")
        if not isinstance(data, str):
            self._log("save_data ignored: data is not a string")
            return
        with self._lock:
            pend = self._pending
            if pend and pend['id'] == req_id:
                pend['data'] = data
                pend['event'].set()
            else:
                self._log("save_data ignored: no matching request id")
