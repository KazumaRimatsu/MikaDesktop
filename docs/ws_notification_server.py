"""WebSocket 通知服务器样板

一个独立的 WebSocket 通知服务器，实现通知协议（认证 → 订阅 → 推送），
便于其他开发者本地测试通知系统。

用法：
    # 启动服务器（默认 ws://127.0.0.1:8848）
    python docs/ws_notification_server.py

    # 指定端口
    python docs/ws_notification_server.py --port 9000

    # 启动后，用 test_notification.py 连接测试即可
"""

import argparse
import asyncio
import json
import uuid
from datetime import datetime

import websockets
from websockets.asyncio.server import serve


# ============================================================================
# 协议常量（与 core/notification_system.py 保持一致）
# ============================================================================
class MT:
    AUTH = "auth"
    AUTH_RESULT = "auth_result"
    SUBSCRIBE = "subscribe"
    SUBSCRIBE_RESULT = "subscribe_result"
    NOTIFICATION = "notification"
    INTERACTION_RESPONSE = "interaction_response"
    PING = "ping"
    PONG = "pong"
    ERROR = "error"


# ============================================================================
# WebSocket 通知服务器
# ============================================================================
class NotificationServer:
    """实现通知协议的服务端

    协议流程:
      客户端连接 → 身份验证(AUTH) → 主题订阅(SUBSCRIBE) → 消息推送(NOTIFICATION)

    同时提供 CLI 交互式菜单，方便手动发送通知。
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8848):
        self.host = host
        self.port = port
        self.clients: dict[websockets.WebSocketServerProtocol, dict] = {}
        self._server = None

    # ---- 启动 / 停止 ----

    async def start(self):
        self._server = await serve(self._handler, self.host, self.port)
        print(f"[服务器] 已启动: ws://{self.host}:{self.port}")
        print("[服务器] 等待客户端连接...")
        print("[服务器] 输入 'help' 查看可用命令\n")

    # ---- 客户端处理 ----

    async def _handler(self, ws: websockets.WebSocketServerProtocol):
        addr = ws.remote_address
        info = {"authenticated": False, "subscribed_topics": []}
        self.clients[ws] = info
        print(f"[连接] 新客户端: {addr} (当前连接数: {len(self.clients)})")

        try:
            async for raw in ws:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send(json.dumps({
                        "type": MT.ERROR, "message": "无效的 JSON 格式"
                    }))
                    continue

                await self._dispatch(ws, data)

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.clients.pop(ws, None)
            print(f"[断开] 客户端 {addr} 已断开 (当前连接数: {len(self.clients)})")

    async def _dispatch(self, ws, data: dict):
        mt = data.get("type")

        if mt == MT.AUTH:
            await self._on_auth(ws, data)
        elif mt == MT.SUBSCRIBE:
            await self._on_subscribe(ws, data)
        elif mt == MT.PING:
            await ws.send(json.dumps({"type": MT.PONG}))
        elif mt == MT.INTERACTION_RESPONSE:
            await self._on_interaction_response(ws, data)
        else:
            await ws.send(json.dumps({
                "type": MT.ERROR,
                "message": f"未知消息类型: {mt}",
            }))

    # ---- 协议处理 ----

    async def _on_auth(self, ws, data: dict):
        token = data.get("token", "")
        client_id = data.get("client_id", "unknown")

        # 样板服务器接受任意 token
        self.clients[ws]["authenticated"] = True
        self.clients[ws]["client_id"] = client_id

        await ws.send(json.dumps({
            "type": MT.AUTH_RESULT,
            "status": "success",
            "client_id": client_id,
        }))
        print(f"[认证] 客户端 {client_id} ({ws.remote_address}) 验证通过")

    async def _on_subscribe(self, ws, data: dict):
        topics = data.get("topics", [])
        self.clients[ws]["subscribed_topics"] = topics

        await ws.send(json.dumps({
            "type": MT.SUBSCRIBE_RESULT,
            "status": "success",
            "topics": topics,
        }))
        print(f"[订阅] 客户端 {self.clients[ws].get('client_id')} 订阅: {topics}")

    async def _on_interaction_response(self, ws, data: dict):
        interaction_id = data.get("interaction_id")
        choice = data.get("choice")
        client_id = self.clients[ws].get("client_id", "unknown")
        print(f"[交互] 客户端 {client_id} 对交互 {interaction_id} 选择了: {choice}")

    # ---- 广播通知 ----

    async def broadcast(self, notification: dict):
        """向所有已认证客户端推送通知"""
        interaction_id = notification.pop("_interaction_id", None)
        msg: dict = {
            "type": MT.NOTIFICATION,
            "data": notification,
        }
        if interaction_id:
            msg["interaction_id"] = interaction_id

        payload = json.dumps(msg)
        sent = 0
        for ws, info in self.clients.items():
            if info.get("authenticated"):
                try:
                    await ws.send(payload)
                    sent += 1
                except websockets.exceptions.ConnectionClosed:
                    pass

        title = notification.get("title", "(无标题)")
        print(f"[推送] '{title}' → {sent} 个客户端")


# ============================================================================
# 预设通知样板
# ============================================================================
PRESETS = {
    "1": {
        "name": "默认通知",
        "data": {
            "title": "通知",
            "context": "这是一条默认通知，5秒后自动关闭",
            "level": "default",
            "type": "default",
            "timeout": 5,
        },
    },
    "2": {
        "name": "警告通知",
        "data": {
            "title": "警告",
            "context": "磁盘空间不足，请及时清理！",
            "level": "warn",
            "type": "default",
            "timeout": 8,
        },
    },
    "3": {
        "name": "错误通知",
        "data": {
            "title": "错误",
            "context": "网络连接失败，请检查网络设置",
            "level": "error",
            "type": "default",
            "timeout": 0,  # 不自动关闭
        },
    },
    "4": {
        "name": "交互式通知",
        "data": {
            "title": "请确认",
            "context": "是否要删除选中的文件？",
            "level": "default",
            "type": "interaction",
            "choices": ["确认删除", "取消"],
            "timeout": 30,
        },
        "interaction_id": lambda: str(uuid.uuid4())[:8],
    },
}


# ============================================================================
# CLI 交互菜单
# ============================================================================
async def cli_loop(server: NotificationServer):
    """终端交互循环，用于手动发送通知"""
    HELP = (
        "\n命令列表:\n"
        "  1 / 2 / 3 / 4    发送预设通知\n"
        "  s                 发送自定义通知（按提示输入）\n"
        "  list              列出当前已连接的客户端\n"
        "  help              显示此帮助\n"
        "  quit              退出服务器\n"
    )
    print(HELP)

    loop = asyncio.get_running_loop()

    while True:
        try:
            cmd = (await loop.run_in_executor(None, input, "> ")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            cmd = "quit"

        if cmd == "quit":
            print("[服务器] 正在关闭...")
            break

        elif cmd == "help":
            print(HELP)

        elif cmd == "list":
            if not server.clients:
                print("  当前无客户端连接")
            else:
                for ws, info in server.clients.items():
                    auth = "已认证" if info["authenticated"] else "未认证"
                    cid = info.get("client_id", "-")
                    print(f"  {cid} ({ws.remote_address}) - {auth}")

        elif cmd in PRESETS:
            preset = PRESETS[cmd]
            data = dict(preset["data"])
            interaction_id = None
            if "interaction_id" in preset:
                interaction_id = preset["interaction_id"]()
                data["_interaction_id"] = interaction_id
            await server.broadcast(data)
            print(f"  已发送: {preset['name']}")

        elif cmd == "s":
            await send_custom(server)

        else:
            print(f"  未知命令: '{cmd}'，输入 help 查看帮助")

    # 清理
    await server.stop()


async def send_custom(server: NotificationServer):
    """手动构造并发送通知"""
    loop = asyncio.get_running_loop()

    try:
        title = (await loop.run_in_executor(None, input, "  标题: ")).strip()
        if not title:
            print("  标题不能为空")
            return

        context = (await loop.run_in_executor(None, input, "  内容: ")).strip()
        if not context:
            print("  内容不能为空")
            return

        level_input = (await loop.run_in_executor(
            None, input, "  级别 (default/warn/error，默认 default): "
        )).strip().lower()
        level = level_input if level_input in ("default", "warn", "error") else "default"

        interaction_input = (
            await loop.run_in_executor(
                None, input, "  交互式? (y/n，默认 n): "
            )
        ).strip().lower()

        notification_type = "default"
        choices = None
        interaction_id = None

        if interaction_input == "y":
            notification_type = "interaction"
            choices_str = (
                await loop.run_in_executor(
                    None, input, "  选项 (逗号分隔，如: 是,否,稍后): "
                )
            ).strip()
            choices = [c.strip() for c in choices_str.split(",") if c.strip()]
            if choices:
                interaction_id = str(uuid.uuid4())[:8]

        timeout_str = (
            await loop.run_in_executor(
                None, input, "  超时秒数 (0=不超时，默认 5): "
            )
        ).strip()
        try:
            timeout = int(timeout_str) if timeout_str else 5
        except ValueError:
            timeout = 5

        data = {
            "title": title,
            "context": context,
            "level": level,
            "type": notification_type,
            "timeout": timeout,
        }
        if choices:
            data["choices"] = choices
        if interaction_id:
            data["_interaction_id"] = interaction_id

        await server.broadcast(data)
        now = datetime.now().strftime("%H:%M:%S")
        print(f"  [{now}] 已发送自定义通知: {title}")

    except (EOFError, KeyboardInterrupt):
        print()


# ============================================================================
# 服务器关闭
# ============================================================================
async def stop(self: NotificationServer):
    """关闭所有客户端连接和服务器"""
    for ws in list(self.clients.keys()):
        try:
            await ws.close()
        except Exception:
            pass
    self.clients.clear()
    if self._server:
        self._server.close()
        await self._server.wait_closed()
    print("[服务器] 已停止")


NotificationServer.stop = stop  # monkey-patch 实例方法


# ============================================================================
# 入口
# ============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="WebSocket 通知服务器样板",
    )
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="监听地址 (默认: 127.0.0.1)",
    )
    parser.add_argument(
        "--port", "-p", type=int, default=8848,
        help="监听端口 (默认: 8848)",
    )
    args = parser.parse_args()

    server = NotificationServer(host=args.host, port=args.port)

    async def run():
        await server.start()
        await cli_loop(server)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n[服务器] 收到中断信号，已退出")


if __name__ == "__main__":
    main()
