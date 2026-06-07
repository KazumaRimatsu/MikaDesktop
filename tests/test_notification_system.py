"""通知系统测试套件

架构说明：
  测试框架启动内置的 WebSocket 测试服务器（TestServer），
  NotificationClient 作为客户端连接该服务器，模拟真实生产环境的连接与通信流程。
  测试覆盖：连接认证、消息接收、格式异常、断线重连、高并发、心跳保活等场景。

用法：
  cd 项目根目录
  python -m tests.test_notification_system
"""

import asyncio
import json
import os
import sys
import unittest
from typing import Optional

# 在导入 Qt 之前设置 offscreen 模式，避免无显示器环境报错
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import websockets
from websockets.asyncio.server import serve

from core.notification_system import (
    NotificationClient,
    ConnectionState,
    MessageType,
)


# ======================================================================
# 内置 WebSocket 测试服务器
# ======================================================================
class TestServer:
    """测试用 WebSocket 服务器，实现通知协议并记录客户端行为"""

    def __init__(self):
        self.server = None
        self.connections: set = set()
        self.port = 0
        self.received_messages: list[dict] = []

    async def start(self):
        """启动服务器（绑定端口 0 以自动分配可用端口）"""
        self.server = await serve(self._handler, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return self.port

    async def _handler(self, ws):
        """处理客户端连接"""
        self.connections.add(ws)
        try:
            async for raw in ws:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue  # 模拟生产环境，静默丢弃无效消息
                self.received_messages.append(data)
                await self._auto_reply(ws, data)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.connections.discard(ws)

    async def _auto_reply(self, ws, data: dict):
        """根据协议自动回复"""
        mt = data.get("type")
        if mt == MessageType.AUTH:
            await ws.send(json.dumps({
                "type": MessageType.AUTH_RESULT, "status": "success"
            }))
        elif mt == MessageType.SUBSCRIBE:
            await ws.send(json.dumps({
                "type": MessageType.SUBSCRIBE_RESULT,
                "status": "success",
                "topics": data.get("topics", []),
            }))
        elif mt == MessageType.PING:
            await ws.send(json.dumps({"type": MessageType.PONG}))
        # interaction_response 只需记录，无需回复

    async def send_notification(self, data: dict, interaction_id: Optional[str] = None):
        """向所有客户端推送通知"""
        msg: dict = {"type": "notification", "data": data}
        if interaction_id:
            msg["interaction_id"] = interaction_id
        payload = json.dumps(msg)
        for conn in list(self.connections):
            await conn.send(payload)

    async def send_raw(self, text: str):
        """发送原始文本（用于模拟非法消息）"""
        for conn in list(self.connections):
            await conn.send(text)

    async def close_clients(self):
        """断开所有客户端连接"""
        for conn in list(self.connections):
            await conn.close()

    async def stop(self):
        """停止服务器并回收资源"""
        await self.close_clients()
        if self.server:
            self.server.close()
            await self.server.wait_closed()


# ======================================================================
# 测试用例
# ======================================================================
class TestNotificationClient(unittest.IsolatedAsyncioTestCase):
    """NotificationClient 自动化测试"""

    # ---- 夹具 ----

    async def asyncSetUp(self):
        """每个用例启动一个独立的测试服务器"""
        self.server = TestServer()
        await self.server.start()

        self.received_notifications: list[dict] = []
        self.state_changes: list[ConnectionState] = []
        self.errors: list[str] = []

        self.client = NotificationClient(config={
            "ws_url": f"ws://127.0.0.1:{self.server.port}",
            "auth_token": "test_token",
            "client_id": "test_client",
            "topics": ["notification"],
            "reconnect_delay": 1,
            "reconnect_max_retries": 5,
        })
        self.client.on_notification = lambda d: self.received_notifications.append(d)
        self.client.on_state_change = lambda s: self.state_changes.append(s)
        self.client.on_error = lambda e: self.errors.append(e)

    async def asyncTearDown(self):
        """每个用例回收资源"""
        self.client.stop()
        if hasattr(self, '_task') and self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, RuntimeError):
                pass
        await self.server.stop()

    # ---- 辅助方法 ----

    async def _start_client(self):
        """启动客户端主协程"""
        self.client._running = True
        self.client._loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(self.client._run())

    async def _wait_for_state(self, target: ConnectionState, timeout: float = 8):
        """轮询等待客户端达到指定状态"""
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if self.client.state == target:
                return
            await asyncio.sleep(0.05)
        self.fail(
            f"状态未在 {timeout}s 内达到 {target.value}"
            f"（当前 {self.client.state.value}）"
        )

    # ---- 用例 ----

    async def test_01_full_connection_flow(self):
        """TC01 — 完整连接流程：建连 → 认证 → 订阅 → CONNECTED"""
        await self._start_client()
        await self._wait_for_state(ConnectionState.CONNECTED)

        self.assertTrue(self.client.authenticated, "客户端应标记为已验证")
        types_in = [m["type"] for m in self.server.received_messages]
        self.assertIn(MessageType.AUTH, types_in, "服务器应收到 auth 消息")
        self.assertIn(MessageType.SUBSCRIBE, types_in, "服务器应收到 subscribe 消息")

    async def test_02_receive_normal_notification(self):
        """TC02 — 接收并解析标准通知"""
        await self._start_client()
        await self._wait_for_state(ConnectionState.CONNECTED)

        await self.server.send_notification({
            "title": "测试标题",
            "context": "测试内容",
            "level": "warn",
            "type": "default",
            "timeout": 10,
        })
        await asyncio.sleep(0.3)

        self.assertEqual(len(self.received_notifications), 1)
        n = self.received_notifications[0]
        self.assertEqual(n["title"], "测试标题")
        self.assertEqual(n["context"], "测试内容")
        self.assertEqual(n["level"], "warn")

    async def test_03_malformed_json_does_not_crash(self):
        """TC03 — 无效 JSON 不导致崩溃，后续消息正常接收"""
        await self._start_client()
        await self._wait_for_state(ConnectionState.CONNECTED)

        await self.server.send_raw("{{{ 不是合法 JSON }}}")
        await asyncio.sleep(0.2)

        # 正常消息应仍能送达
        await self.server.send_notification({"title": "正常", "context": "正常"})
        await asyncio.sleep(0.3)

        self.assertEqual(len(self.received_notifications), 1)
        self.assertEqual(len(self.errors), 0, "无效 JSON 不应触发 on_error")

    async def test_04_incomplete_notification_ignored(self):
        """TC04 — 缺少 title/context 的通知被静默忽略"""
        await self._start_client()
        await self._wait_for_state(ConnectionState.CONNECTED)

        # 缺 title
        await self.server.send_raw(json.dumps({
            "type": "notification", "data": {"context": "无标题"}
        }))
        # 缺 context
        await self.server.send_raw(json.dumps({
            "type": "notification", "data": {"title": "无内容"}
        }))
        await asyncio.sleep(0.3)

        self.assertEqual(len(self.received_notifications), 0)

    async def test_05_interaction_response_flow(self):
        """TC05 — 交互式通知的 interaction_id 传递与回传"""
        await self._start_client()
        await self._wait_for_state(ConnectionState.CONNECTED)

        # 服务器推送交互通知
        await self.server.send_notification(
            {"title": "请选择", "context": "请选择", "type": "interaction", "choices": ["A", "B"]},
            interaction_id="abc-123",
        )
        await asyncio.sleep(0.3)

        self.assertEqual(len(self.received_notifications), 1)
        self.assertEqual(self.received_notifications[0]["_interaction_id"], "abc-123")

        # 客户端回传结果
        self.client.send_interaction_response("abc-123", "A")
        await asyncio.sleep(0.2)

        resp = [m for m in self.server.received_messages
                if m.get("type") == MessageType.INTERACTION_RESPONSE]
        self.assertEqual(len(resp), 1)
        self.assertEqual(resp[0]["interaction_id"], "abc-123")
        self.assertEqual(resp[0]["choice"], "A")

    async def test_06_auto_reconnect_on_disconnect(self):
        """TC06 — 断线自动重连并恢复消息接收"""
        await self._start_client()
        await self._wait_for_state(ConnectionState.CONNECTED)
        self.state_changes.clear()

        # 服务端断开
        await self.server.close_clients()
        await asyncio.sleep(0.5)

        self.assertIn(
            ConnectionState.RECONNECTING, self.state_changes,
            "应经过 RECONNECTING 状态",
        )

        # 等待重连
        await self._wait_for_state(ConnectionState.CONNECTED, timeout=10)

        # 重连后应能继续接收
        await self.server.send_notification({"title": "重连后", "context": "正常"})
        await asyncio.sleep(0.3)
        self.assertEqual(len(self.received_notifications), 1)

    async def test_07_high_concurrency_notifications(self):
        """TC07 — 高并发消息全部正确接收"""
        await self._start_client()
        await self._wait_for_state(ConnectionState.CONNECTED)

        N = 30
        await asyncio.gather(*[
            self.server.send_notification({
                "title": f"并发 {i}", "context": f"内容 {i}",
            })
            for i in range(N)
        ])
        await asyncio.sleep(0.8)

        self.assertEqual(len(self.received_notifications), N)

    async def test_08_ping_keepalive(self):
        """TC08 — 心跳保活正常发送"""
        self.client._ping_interval = 2  # 缩短间隔加速测试
        await self._start_client()
        await self._wait_for_state(ConnectionState.CONNECTED)

        await asyncio.sleep(5)

        ping_msgs = [m for m in self.server.received_messages
                     if m.get("type") == MessageType.PING]
        self.assertGreaterEqual(len(ping_msgs), 1, "心跳消息应至少发送 1 次")

    async def test_09_server_error_triggers_callback(self):
        """TC09 — 服务器 error 消息触发 on_error 回调"""
        await self._start_client()
        await self._wait_for_state(ConnectionState.CONNECTED)

        await self.server.send_raw(json.dumps({
            "type": "error", "message": "服务端异常",
        }))
        await asyncio.sleep(0.3)

        self.assertIn("服务端异常", self.errors)

    async def test_10_unknown_message_no_crash(self):
        """TC10 — 未知消息类型不引发异常，后续消息正常"""
        await self._start_client()
        await self._wait_for_state(ConnectionState.CONNECTED)

        await self.server.send_raw(json.dumps({
            "type": "gibberish_type_xyz", "data": "test",
        }))
        await asyncio.sleep(0.3)

        # 如果因上下文切换断开，等待重连
        if self.client.state != ConnectionState.CONNECTED:
            await self._wait_for_state(ConnectionState.CONNECTED, timeout=5)

        await self.server.send_notification({"title": "正常", "context": "正常"})
        await asyncio.sleep(0.5)
        self.assertEqual(len(self.received_notifications), 1)

    async def test_11_state_machine_terminates_on_stop(self):
        """TC11 — 主动停止客户端后状态变为 CLOSED"""
        await self._start_client()
        await self._wait_for_state(ConnectionState.CONNECTED)

        self.client.stop()
        await asyncio.sleep(0.3)
        self.assertEqual(self.client.state, ConnectionState.CLOSED)

    async def test_12_multiple_reconnects(self):
        """TC12 — 多次连续断线重连后仍正常工作"""
        await self._start_client()
        await self._wait_for_state(ConnectionState.CONNECTED)

        for _ in range(3):
            await self.server.close_clients()
            await asyncio.sleep(0.5)
            await self._wait_for_state(ConnectionState.CONNECTED, timeout=10)

        # 恢复后能收消息
        await self.server.send_notification({"title": "多次重连", "context": "OK"})
        await asyncio.sleep(0.3)
        self.assertEqual(len(self.received_notifications), 1)


# ======================================================================
# 入口
# ======================================================================
if __name__ == "__main__":
    unittest.main(verbosity=2)
