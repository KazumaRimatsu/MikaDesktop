# 通知系统使用指南

## 概述

通知系统是一个 WebSocket 客户端模块，作为 dock.py 的内置组件运行。它连接到外部的 WebSocket 通知服务器，通过标准的身份验证→订阅→推送流程接收通知，并在屏幕上以浮窗形式展示。支持普通通知和交互式通知（带选项按钮），同时具备自动重连、心跳保活等生产级特性。

## 架构变更（v2）

通知系统已从 **HTTP 服务器模式**重构为 **WebSocket 客户端模式**：

| 旧架构（废弃） | 新架构 |
|---|---|
| 内置 HTTP Server，监听 `127.0.0.2:8848` | 作为客户端连接外部 WebSocket 服务器 |
| 通过 GET/POST 请求接收通知 | 遵循标准协议：认证 → 订阅 → 推送 |
| 无连接状态管理 | 状态机：CONNECTING → AUTH → SUBSCRIBE → CONNECTED |
| 无自动重连 | 指数退避自动重连 + 心跳保活 |

## 架构概览

```
┌─────────────────────────────────────────────────┐
│                 外部 WebSocket 服务器              │
│  (独立部署，ws://host:port)                       │
└──────────────┬──────────────────────┬────────────┘
               │ ① 连接              │ ④ 推送通知
               ▼                      ▼
┌─────────────────────────────────────────────────┐
│              NotificationClient                   │
│  认证 → 订阅 → 消息循环 → 自动重连                │
└──────────────────────┬──────────────────────────┘
                       │ Qt Signal (跨线程)
                       ▼
┌─────────────────────────────────────────────────┐
│             NotificationWindow (UI)              │
│         浮窗显示、交互按钮、动画效果               │
└─────────────────────────────────────────────────┘
```

## 连接配置

通知系统的配置项存储在 `settings.json` 的 `notify` 字段中：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `ws_url` | `ws://127.0.0.2:8848` | WebSocket 服务器地址 |
| `auth_token` | `""` | 身份验证令牌（空则不验证） |
| `client_id` | `"dock"` | 客户端标识 |
| `topics` | `["notification"]` | 订阅主题列表 |
| `reconnect_delay` | `3` | 重连初始延迟（秒） |
| `reconnect_max_retries` | `0` | 最大重连次数（0=无限） |
| `default_timeout` | `0` | 默认通知超时（秒，0=不超时） |

## 通信协议

通知系统使用 JSON 格式的 WebSocket 消息与服务器通信。以下是完整的协议定义：

### 1. 身份验证

客户端连接后，首先发送认证消息：

```json
{
  "type": "auth",
  "token": "your_auth_token",
  "client_id": "dock",
  "version": 1
}
```

服务器必须回复：

```json
{
  "type": "auth_result",
  "status": "success"
}
```

认证失败时客户端将断开连接并记录错误。

### 2. 主题订阅

认证成功后，客户端发送订阅请求：

```json
{
  "type": "subscribe",
  "topics": ["notification"]
}
```

服务器回复：

```json
{
  "type": "subscribe_result",
  "status": "success",
  "topics": ["notification"]
}
```

### 3. 通知推送

服务器向客户端推送通知消息：

```json
{
  "type": "notification",
  "data": {
    "title": "通知标题",
    "context": "通知内容",
    "level": "default",
    "type": "default",
    "timeout": 5,
    "icon": "图标路径",
    "choices": ["选项1", "选项2"]
  },
  "interaction_id": "uuid"           // 交互式通知时携带
}
```

**data 字段说明**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `title` | string | 是 | 通知标题 |
| `context` | string | 是 | 通知内容 |
| `level` | string | 否 | `default` / `warn` / `error`，默认 `default` |
| `type` | string | 否 | `default` / `interaction`，默认 `default` |
| `timeout` | integer | 否 | 自动关闭秒数，1-60 |
| `icon` | string | 否 | 图标文件路径 |
| `choices` | array | 当 type=interaction 时必需 | 选项列表，最多 4 个 |

### 4. 交互响应

当用户点击交互式通知的按钮时，客户端向服务器回传结果：

```json
{
  "type": "interaction_response",
  "interaction_id": "uuid",
  "choice": "用户选择的选项"
}
```

### 5. 心跳保活

客户端每隔 25 秒发送心跳：

```json
{ "type": "ping" }
```

服务器回复：

```json
{ "type": "pong" }
```

### 6. 服务端错误

服务器可主动推送错误消息：

```json
{
  "type": "error",
  "message": "错误描述"
}
```

## 连接状态机

客户端内部维护以下状态，可通过 `connectionStateChanged` 信号监听：

```
DISCONNECTED → CONNECTING → AUTHENTICATING → CONNECTED
                                                    │
                     ┌──────────────────────────────┤
                     ▼                              ▼
               RECONNECTING ← ─ ─ ─ ─ 连接断开
                     │
                     ▼
               CONNECTING → ... (重试循环)
                     │
               CONNECTED（恢复）
                     │
               CLOSED（主动停止或达最大重连次数）
```

## 通知样式

- **default**: 蓝色背景（`#94BFFF`）
- **warn**: 黄色背景（`#FFC53D`）
- **error**: 红色背景（`#FF643D`）

交互式通知会显示选项按钮，点击后通知关闭并回传结果。

## 使用示例

### Python 客户端示例（发送通知）

```python
import asyncio
import json
import websockets

async def send_notification():
    async with websockets.connect("ws://127.0.0.2:8848") as ws:
        # 认证
        await ws.send(json.dumps({
            "type": "auth", "token": "", "client_id": "my_app"
        }))
        auth_resp = json.loads(await ws.recv())
        assert auth_resp["status"] == "success"

        # 订阅
        await ws.send(json.dumps({
            "type": "subscribe", "topics": ["notification"]
        }))
        sub_resp = json.loads(await ws.recv())
        assert sub_resp["status"] == "success"

        # 推送普通通知
        await ws.send(json.dumps({
            "type": "notification",
            "data": {
                "title": "测试通知",
                "context": "这是一个测试通知",
                "level": "default",
                "type": "default",
                "timeout": 5
            }
        }))
        result = json.loads(await ws.recv())
        print(f"发送结果: {result}")

asyncio.run(send_notification())
```

### 交互式通知示例（等待用户选择）

```python
import asyncio
import json
import uuid
import websockets

connected_clients = {}

async def notify_handler(ws):
    """服务端处理函数示例"""
    async for raw in ws:
        data = json.loads(raw)
        if data["type"] == "auth":
            await ws.send(json.dumps({
                "type": "auth_result", "status": "success"
            }))
        elif data["type"] == "subscribe":
            await ws.send(json.dumps({
                "type": "subscribe_result",
                "status": "success",
                "topics": data.get("topics", [])
            }))
            connected_clients[id(ws)] = ws
        elif data["type"] == "interaction_response":
            print(f"用户选择: {data['choice']} (交互ID: {data['interaction_id']})")

async def push_interaction():
    """向客户端推送交互式通知"""
    interaction_id = str(uuid.uuid4())
    for ws in connected_clients.values():
        await ws.send(json.dumps({
            "type": "notification",
            "data": {
                "title": "请确认",
                "context": "您确定要执行此操作吗？",
                "level": "warn",
                "type": "interaction",
                "choices": ["确认", "取消"]
            },
            "interaction_id": interaction_id
        }))

asyncio.run(push_interaction())
```

## 线程管理

通知系统通过 `NotificationManager(QThread)` 集成到线程管理器中：

```python
from core.notification_system import NotificationManager

self.notification_manager = NotificationManager(parent=self)
notification_system_id = self.thread_manager.create(
    name=self.notification_manager.get_name(),
    start_when_create=True,
    worker=self.notification_manager
)
```

### 可用信号

| 信号 | 类型 | 说明 |
|------|------|------|
| `show_notification_signal` | `Signal(dict)` | 通知数据到达时发射 |
| `errorOccurred` | `Signal(str)` | 错误发生时发射 |
| `connectionStateChanged` | `Signal(str)` | 连接状态变更时发射 |

## 测试

测试套件位于 `tests/test_notification_system.py`，使用内置的 WebSocket 测试服务器模拟外部服务器：

```bash
cd 项目根目录
python -m tests.test_notification_system
```

测试覆盖场景（12 个用例）：

| 编号 | 场景 | 说明 |
|------|------|------|
| TC01 | 完整连接流程 | 建连 → 认证 → 订阅 → CONNECTED |
| TC02 | 标准通知接收 | 服务器推送通知，客户端正确解析 |
| TC03 | 无效 JSON 容错 | 非法 JSON 不崩溃，后续消息正常 |
| TC04 | 不完整通知忽略 | 缺少 title/context 的通知被静默丢弃 |
| TC05 | 交互响应回传 | interaction_id 传递与用户选择回传 |
| TC06 | 断线自动重连 | 连接断开后自动恢复 |
| TC07 | 高并发消息 | 30 条并发消息全部正确接收 |
| TC08 | 心跳保活 | ping/pong 正常发送 |
| TC09 | 服务端错误回调 | error 消息触发 on_error |
| TC10 | 未知消息类型 | 不引起异常，后续正常接收 |
| TC11 | 主动停止 | stop() 后状态变为 CLOSED |
| TC12 | 多次重连 | 连续 3 次断线重连后仍正常 |

## 错误处理

- **认证失败**: 客户端断开，记录错误，按重连策略重试
- **连接断开**: 触发指数退避重连（1.5 倍递增，最长 30 秒间隔）
- **无效消息**: 静默丢弃，不影响后续消息处理
- **服务端错误**: 通过 `errorOccurred` 信号上报
- **依赖要求**: `websockets>=13.0`
