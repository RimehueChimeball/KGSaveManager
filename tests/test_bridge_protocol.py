"""web_bridge 协议测试：用假 WebSocket 客户端驱动真实服务端。

覆盖：
- 握手 / hello / request_save / save_data 往返（含来源标记）
- apply_save 下发
- 旧连接失效后自动改用新连接
- 空闲保活：会回 pong 的连接不被断开；完全不响应的连接被回收
"""

import base64
import json
import os
import socket
import struct
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import web_bridge  # noqa: E402
from web_bridge import WebSocketBridge  # noqa: E402

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class FakePage:
    """最小 WebSocket 客户端（模拟游戏页面的注入脚本）。"""

    def __init__(self, port, auto_pong=True, name="page"):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.name = name
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            "GET / HTTP/1.1\r\n"
            "Host: 127.0.0.1\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(1024)
            if not chunk:
                raise RuntimeError("handshake failed")
            buf += chunk
        assert b"101" in buf.split(b"\r\n")[0]
        self.frames = []
        self._stop = threading.Event()
        self.auto_pong = auto_pong
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()

    # ---------- 帧读写 ----------
    def _reader(self):
        while not self._stop.is_set():
            try:
                frame = self._read_frame()
            except Exception:
                return
            if frame is None:
                return
            opcode, payload = frame
            if opcode == 0x9 and self.auto_pong:          # ping -> pong
                try:
                    self._send_frame(0xA, payload)
                except Exception:
                    return
            elif opcode == 0x1:
                self.frames.append(payload.decode("utf-8"))
            elif opcode == 0xA:
                pass

    def _read_frame(self):
        head = self._recv_exact(2)
        if head is None:
            return None
        opcode = head[0] & 0x0F
        length = head[1] & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._recv_exact(8))[0]
        payload = self._recv_exact(length) if length else b""
        return opcode, payload or b""

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf

    def _send_frame(self, opcode, payload=b""):
        data = payload if isinstance(payload, bytes) else payload.encode()
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        header = bytes([0x80 | opcode])
        if len(data) < 126:
            header += bytes([0x80 | len(data)])
        elif len(data) < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", len(data))
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", len(data))
        self.sock.sendall(header + mask + masked)

    # ---------- 协议动作 ----------
    def send_json(self, obj):
        self._send_frame(0x1, json.dumps(obj))

    def wait_frames(self, count=1, timeout=5.0):
        deadline = time.time() + timeout
        while time.time() < deadline and len(self.frames) < count:
            time.sleep(0.02)
        return [json.loads(f) for f in self.frames[:count]]

    def close(self):
        self._stop.set()
        try:
            self.sock.close()
        except Exception:
            pass


class TestBridgeProtocol(unittest.TestCase):
    def setUp(self):
        self.bridge = WebSocketBridge()
        self.bridge.start()
        self.addCleanup(self.bridge.stop)

    def test_hello_is_logged(self):
        logs = []
        self.bridge.set_ui_queue(_Queue(logs))
        page = FakePage(self.bridge.port)
        self.addCleanup(page.close)
        page.send_json({"type": "hello", "ready": True, "hasGame": True,
                        "foundKeys": ["game"], "domKeys": []})
        found = _wait_for(lambda: next(
            (l for l in logs if "hello from page" in l), None), 3.0)
        self.assertIsNotNone(found, f"未记录 hello 日志: {logs}")
        self.assertIn("hasGame", found)
        self.assertIn("ready", found)

    def test_request_save_roundtrip_with_source(self):
        page = FakePage(self.bridge.port)
        self.addCleanup(page.close)
        self._wait_client()

        result = {}

        def requester():
            result["data"] = self.bridge.request_save(timeout=5)

        t = threading.Thread(target=requester)
        t.start()
        msgs = page.wait_frames(1, timeout=5)
        self.assertEqual(msgs[0]["type"], "request_save")
        page.send_json({"type": "save_data", "id": msgs[0]["id"],
                        "data": "SAVEDATA", "source": "engine"})
        t.join(timeout=6)
        self.assertEqual(result.get("data"), "SAVEDATA")

    def test_apply_save_is_delivered(self):
        page = FakePage(self.bridge.port)
        self.addCleanup(page.close)
        self._wait_client()
        self.assertTrue(self.bridge.apply_save("BLOB"))
        msgs = page.wait_frames(1, timeout=5)
        self.assertEqual(msgs[0]["type"], "apply_save")
        self.assertEqual(msgs[0]["data"], "BLOB")

    def test_request_save_without_client_returns_none(self):
        self.assertIsNone(self.bridge.request_save(timeout=0.2))
        self.assertFalse(self.bridge.apply_save("X"))

    def test_stale_client_is_dropped_and_newest_used(self):
        stale = FakePage(self.bridge.port, name="stale")
        self._wait_client()
        stale.sock.close()          # 模拟页面刷新后残留的死连接
        time.sleep(0.1)
        fresh = FakePage(self.bridge.port, name="fresh")
        self.addCleanup(fresh.close)
        self._wait_client()

        result = {}

        def requester():
            result["data"] = self.bridge.request_save(timeout=5)

        t = threading.Thread(target=requester)
        t.start()
        msgs = fresh.wait_frames(1, timeout=5)
        self.assertTrue(msgs, "新连接应收到 request_save")
        fresh.send_json({"type": "save_data", "id": msgs[0]["id"],
                         "data": "NEW-SAVE", "source": "engine"})
        t.join(timeout=6)
        self.assertEqual(result.get("data"), "NEW-SAVE")

    # ---------- 保活 ----------
    def _fast_keepalive(self):
        """把保活参数调到秒级，便于测试（生产值是 20s/75s/1s）。"""
        for name, value in (("WS_PING_INTERVAL", 0.3),
                            ("WS_IDLE_TIMEOUT", 1.0),
                            ("WS_POLL", 0.05)):
            old = getattr(web_bridge, name)
            setattr(web_bridge, name, value)
            self.addCleanup(setattr, web_bridge, name, old)

    def test_responsive_client_survives_idle_timeout(self):
        """会回 pong 的连接在“空闲”超过旧阈值后仍在（不再 30 秒断连）。"""
        self._fast_keepalive()
        page = FakePage(self.bridge.port, auto_pong=True)
        self.addCleanup(page.close)
        self._wait_client()
        time.sleep(2.5)
        self.assertTrue(self.bridge.has_client,
                        "回 pong 的连接不应被断开")

    def test_silent_client_is_reclaimed(self):
        """完全不回应的连接在空闲阈值后被回收（无需等 30 秒）。"""
        self._fast_keepalive()
        page = FakePage(self.bridge.port, auto_pong=False)
        self.addCleanup(page.close)
        self._wait_client()
        deadline = time.time() + 4
        while time.time() < deadline and self.bridge.has_client:
            time.sleep(0.05)
        self.assertFalse(self.bridge.has_client, "静默连接应被回收")

    def _wait_client(self, timeout=3.0):
        deadline = time.time() + timeout
        while time.time() < deadline and not self.bridge.has_client:
            time.sleep(0.02)
        self.assertTrue(self.bridge.has_client, "客户端未连入桥")


class _Queue:
    """只收集 bridge_log 的最小队列替身。"""

    def __init__(self, sink):
        self.sink = sink

    def put(self, item):
        if item and item[0] == "bridge_log":
            self.sink.append(item[1])


def _wait_for(getter, timeout=3.0, step=0.02):
    """轮询直到 getter 返回真值，超时返回最后一次结果。"""
    deadline = time.time() + timeout
    value = None
    while time.time() < deadline:
        value = getter()
        if value:
            return value
        time.sleep(step)
    return value


if __name__ == "__main__":
    unittest.main()
