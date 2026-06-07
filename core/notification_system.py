import json
import asyncio
import time
from typing import Dict, Any, Optional, Callable
from enum import Enum
from PySide6.QtCore import Signal, QTimer, Qt, Slot, QPropertyAnimation, QEasingCurve, QThread
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QApplication
from PySide6.QtGui import QPainter, QColor, QFont, QResizeEvent, QPaintEvent
import websockets
from core import log_maker
from core.config_manager import load_config, save_config


log = log_maker.logger()

# ---------------------------------------------------------------------------
# 默认配置
# ---------------------------------------------------------------------------
DEFAULT_NOTIFY_CONFIG = {
    "default_timeout": 0,
    "ws_url": "ws://127.0.0.1:8848",
    "auth_token": "",
    "client_id": "dock",
    "reconnect_delay": 3,
    "reconnect_max_retries": 0,
    "topics": ["notification"],
}

# ---------------------------------------------------------------------------
# 通信协议常量
# ---------------------------------------------------------------------------
class MessageType:
    """WebSocket 通信协议消息类型"""
    AUTH                = "auth"
    AUTH_RESULT         = "auth_result"
    SUBSCRIBE           = "subscribe"
    SUBSCRIBE_RESULT    = "subscribe_result"
    NOTIFICATION        = "notification"
    INTERACTION_RESPONSE = "interaction_response"
    PING                = "ping"
    PONG                = "pong"
    ERROR               = "error"


class ConnectionState(Enum):
    """客户端连接状态"""
    DISCONNECTED    = "disconnected"
    CONNECTING      = "connecting"
    AUTHENTICATING  = "authenticating"
    CONNECTED       = "connected"
    RECONNECTING    = "reconnecting"
    CLOSED          = "closed"


# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------
def load_notify_config(config_path: Optional[str] = None) -> dict:
    """从配置文件加载通知系统配置，合并默认值"""
    if config_path:
        cfg = load_config(config_path)
    else:
        from core import config_manager as cm
        cfg = cm.DEFAULT_CONFIG.copy()

    notify_cfg = cfg.get("notify", {})
    result = dict(DEFAULT_NOTIFY_CONFIG)
    result.update(notify_cfg)
    return result


# ---------------------------------------------------------------------------
# NotificationClient  —  WebSocket 客户端（身份验证 / 订阅 / 消息接收 / 重连）
# ---------------------------------------------------------------------------
class NotificationClient:
    """WebSocket 通知客户端

    连接外部 WebSocket 服务器，依次完成：
      1. 身份验证  →  2. 主题订阅  →  3. 消息接收循环
    断线时自动指数退避重连。
    """

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_notify_config()
        self.ws_url                  = self.config["ws_url"]
        self.auth_token              = self.config["auth_token"]
        self.client_id               = self.config["client_id"]
        self.topics                  = self.config["topics"]
        self.reconnect_delay         = self.config["reconnect_delay"]
        self.reconnect_max_retries   = self.config.get("reconnect_max_retries", 0)

        # 运行时状态
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False
        self._retry_count = 0
        self._ping_interval = 25  # 秒

        # 外部回调
        self.on_notification: Optional[Callable[[dict], None]] = None
        self.on_state_change: Optional[Callable[[ConnectionState], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

        self.state = ConnectionState.DISCONNECTED
        self.authenticated = False

    # ---- 公开方法 ----

    def start(self, loop: asyncio.AbstractEventLoop):
        """在指定事件循环中启动客户端"""
        self._running = True
        self._loop = loop
        asyncio.run_coroutine_threadsafe(self._run(), loop)

    def stop(self):
        """停止客户端（线程安全）"""
        self._running = False
        if self._ws:
            asyncio.run_coroutine_threadsafe(self._ws.close(), self._loop)
            self._ws = None
        self._set_state(ConnectionState.CLOSED)

    def send_interaction_response(self, interaction_id: str, choice: str):
        """发送交互式通知的用户选择结果到服务器（线程安全）"""
        if not self._ws or not self._loop:
            return
        msg = {
            "type": MessageType.INTERACTION_RESPONSE,
            "interaction_id": interaction_id,
            "choice": choice,
        }
        asyncio.run_coroutine_threadsafe(self._ws.send(json.dumps(msg)), self._loop)

    # ---- 内部逻辑 ----

    async def _run(self):
        """主循环 — 连接 → 断开 → 等待 → 重连（直到被停止）"""
        while self._running:
            try:
                await self._connect()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"客户端运行异常: {e}")
            finally:
                self._ws = None
                self.authenticated = False
                # 断开后等待再重试（由 _run 统一管理，避免并发 _connect）
                if self._running:
                    await self._reconnect_delay()

    async def _reconnect_delay(self):
        """指数退避等待 + 状态变更（在 _run 循环内调用）"""
        if self.reconnect_max_retries > 0 and self._retry_count >= self.reconnect_max_retries:
            log.warning(f"[通知客户端] 已达最大重连次数 ({self.reconnect_max_retries})，停止重连")
            self._set_state(ConnectionState.CLOSED)
            return

        self._set_state(ConnectionState.RECONNECTING)
        delay = min(self.reconnect_delay * (1.5 ** self._retry_count), 30)
        self._retry_count += 1
        log.info(f"[通知客户端] {delay:.1f} 秒后重连 (第 {self._retry_count} 次)")
        await asyncio.sleep(delay)

    async def _connect(self):
        """单次连接 — 建连 → 认证 → 订阅 → 消息循环"""
        self._set_state(ConnectionState.CONNECTING)
        try:
            self._ws = await websockets.connect(self.ws_url)
            log.info(f"[通知客户端] 已连接到 {self.ws_url}")

            await self._authenticate()
            await self._subscribe()
            self._retry_count = 0
            self._set_state(ConnectionState.CONNECTED)
            await self._message_loop()

        except websockets.exceptions.ConnectionClosed as e:
            log.warning(f"[通知客户端] 连接已断开: {e.code} {e.reason}")
        except ConnectionRefusedError as e:
            log.error(f"[通知客户端] {e}")
            if self.on_error:
                self.on_error(str(e))
        except OSError as e:
            log.error(f"[通知客户端] 网络错误: {e}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.error(f"[通知客户端] 连接异常: {e}")

    async def _authenticate(self):
        """身份验证握手"""
        self._set_state(ConnectionState.AUTHENTICATING)
        auth_msg = {
            "type": MessageType.AUTH,
            "token": self.auth_token,
            "client_id": self.client_id,
            "version": 1,
        }
        await self._ws.send(json.dumps(auth_msg))

        raw = await asyncio.wait_for(self._ws.recv(), timeout=10)
        response = json.loads(raw)

        if response.get("type") != MessageType.AUTH_RESULT:
            raise ConnectionRefusedError(f"认证响应类型错误: {response.get('type')}")
        if response.get("status") != "success":
            raise ConnectionRefusedError(f"认证失败: {response.get('message', '未知错误')}")

        self.authenticated = True
        log.info("[通知客户端] 身份验证成功")

    async def _subscribe(self):
        """主题订阅"""
        sub_msg = {
            "type": MessageType.SUBSCRIBE,
            "topics": self.topics,
        }
        await self._ws.send(json.dumps(sub_msg))

        raw = await asyncio.wait_for(self._ws.recv(), timeout=10)
        response = json.loads(raw)

        if response.get("type") != MessageType.SUBSCRIBE_RESULT:
            log.warning(f"[通知客户端] 订阅响应类型异常: {response.get('type')}")
        elif response.get("status") != "success":
            log.warning(f"[通知客户端] 订阅失败: {response.get('message', '未知错误')}")
        else:
            log.info(f"[通知客户端] 已订阅主题: {response.get('topics', self.topics)}")

    async def _message_loop(self):
        """消息接收与分发循环"""
        while self._running and self._ws:
            try:
                message = await asyncio.wait_for(self._ws.recv(), timeout=self._ping_interval)
                await self._dispatch_message(message)
            except asyncio.TimeoutError:
                # 心跳保活
                try:
                    await self._ws.send(json.dumps({"type": MessageType.PING}))
                except websockets.exceptions.ConnectionClosed:
                    break
            except websockets.exceptions.ConnectionClosed:
                break
            except Exception as e:
                log.error(f"[通知客户端] 消息循环异常: {e}")
                break

    async def _dispatch_message(self, raw: str):
        """反序列化并分发单条消息"""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            log.warning(f"[通知客户端] 收到无效 JSON: {raw[:120]}")
            return

        msg_type = data.get("type")

        if msg_type == MessageType.NOTIFICATION:
            await self._on_notification(data)

        elif msg_type == MessageType.PONG:
            pass  # 心跳回复，无需处理

        elif msg_type == MessageType.ERROR:
            err_msg = data.get("message", "未知错误")
            log.error(f"[通知客户端] 服务器错误: {err_msg}")
            if self.on_error:
                self.on_error(err_msg)

        elif msg_type == MessageType.AUTH_RESULT:
            pass  # 已在 _authenticate 中处理

        elif msg_type == MessageType.SUBSCRIBE_RESULT:
            pass  # 已在 _subscribe 中处理

        else:
            log.debug(f"[通知客户端] 未知消息类型: {msg_type}")

    async def _on_notification(self, data: dict):
        """处理推送的通知消息"""
        notif_data = data.get("data", {})
        if not notif_data.get("title") or not notif_data.get("context"):
            log.warning("[通知客户端] 通知数据缺少 title/context，忽略")
            return

        if "timestamp" not in notif_data:
            notif_data["timestamp"] = time.time()

        # 携带 interaction_id（如果有），供 UI 回传
        interaction_id = data.get("interaction_id")
        if interaction_id:
            notif_data["_interaction_id"] = interaction_id

        log.info(f"[通知客户端] 收到通知: {notif_data.get('title')}")
        if self.on_notification:
            self.on_notification(notif_data)

    def _set_state(self, state: ConnectionState):
        self.state = state
        if self.on_state_change:
            self.on_state_change(state)


# ---------------------------------------------------------------------------
# NotificationWindow  — 通知 UI 窗口
# ---------------------------------------------------------------------------
class NotificationWindow(QWidget):
    """通知 UI 浮窗"""

    notification_closed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        log.info("[NotificationWindow] 创建实例")
        self.notification_data = None
        self.timeout_timer: Optional[QTimer] = None
        self.choice_buttons: list[QPushButton] = []
        self.show_animation: Optional[QPropertyAnimation] = None
        self.hide_animation: Optional[QPropertyAnimation] = None
        self._timed_out = False
        self.manager = None  # 由 NotificationManager 设置，用于回传交互结果

        self.init_ui()
        self.setup_styles()

    def init_ui(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        self.title_label = QLabel()
        self.title_label.setWordWrap(True)
        font = QFont()
        font.setPointSize(24)
        font.setBold(True)
        self.title_label.setFont(font)
        self.title_label.setStyleSheet("background-color: transparent;")
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)

        self.context_label = QLabel()
        self.context_label.setWordWrap(True)
        self.context_label.setFont(QFont("Microsoft YaHei", 20))
        self.context_label.setStyleSheet("background-color: transparent;")
        self.context_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.context_label)

        self.button_container = QWidget()
        self.button_layout = QHBoxLayout(self.button_container)
        self.button_layout.setContentsMargins(0, 10, 0, 0)
        self.button_layout.setSpacing(10)
        self.button_container.setStyleSheet("background-color: transparent;")
        layout.addWidget(self.button_container)

    def setup_styles(self):
        pass  # 由 show_notification 根据 level 动态设置

    def show_notification(self, notification_data: dict):
        log.info(f"[NotificationWindow] 显示通知: {notification_data.get('title')}")
        self._timed_out = False
        self.notification_data = notification_data

        self.title_label.setText(notification_data["title"])
        self.context_label.setText(notification_data["context"])

        level = notification_data.get("level", "default")
        bg = {"warn": "#FFC53D", "error": "#FF643D"}.get(level, "#94BFFF")
        self.setStyleSheet(f"""
            QWidget {{ background-color: {bg}; color: #FFFFFF; }}
            QLabel  {{ background-color: transparent; color: #FFFFFF; }}
        """)

        self.clear_choice_buttons()
        if notification_data.get("type") == "interaction" and notification_data.get("choices"):
            for item in notification_data["choices"]:
                btn = QPushButton(item)
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(255,255,255,0.2);
                        border: 1px solid rgba(87,154,255,0.3);
                        border-radius: 6px; padding: 8px 16px;
                        color: inherit; font-size: 18px;
                    }
                    QPushButton:hover {
                        background-color: rgba(26,117,255,0.3);
                    }
                """)
                btn.clicked.connect(lambda checked, c=item: self.handle_choice(c))
                self.button_layout.addWidget(btn)
                self.choice_buttons.append(btn)

        self.adjustSize()
        self.update_position()
        self.show_with_animation()
        self.raise_()
        self.activateWindow()

        if notification_data.get("timeout"):
            self.setup_timeout(notification_data["timeout"])

    def clear_choice_buttons(self):
        for btn in self.choice_buttons:
            btn.deleteLater()
        self.choice_buttons.clear()

    def setup_timeout(self, timeout: int):
        if self.timeout_timer:
            self.timeout_timer.stop()
        self.timeout_timer = QTimer(self)
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self.on_timeout)
        self.timeout_timer.start(timeout * 1000)

    def on_timeout(self):
        self._timed_out = True
        for btn in self.choice_buttons:
            btn.setEnabled(False)
        self.close_notification()

    def update_position(self):
        screen = QApplication.primaryScreen()
        geo = screen.availableGeometry()
        self.move(
            geo.x() + (geo.width() - self.width()) // 2,
            64,
        )

    def handle_choice(self, choice: str):
        if self._timed_out:
            log.info(f"[NotificationWindow] 已超时，忽略选择: {choice}")
            return

        log.info(f"[NotificationWindow] 用户选择: {choice}")
        self.notification_data["user_choice"] = choice

        # 向外部服务器回传交互结果
        interaction_id = self.notification_data.get("_interaction_id")
        if interaction_id and self.manager and self.manager.client:
            self.manager.client.send_interaction_response(interaction_id, choice)

        for btn in self.choice_buttons:
            btn.setEnabled(False)
        self.close_notification()

    def show_with_animation(self):
        if self.show_animation is not None:
            try:
                self.show_animation.stop()
            except RuntimeError:
                pass
        self.setWindowOpacity(0.0)
        self.show()
        self.show_animation = QPropertyAnimation(self, b"windowOpacity", self)
        self.show_animation.setDuration(300)
        self.show_animation.setStartValue(0.0)
        self.show_animation.setEndValue(1.0)
        self.show_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.show_animation.start()

    def hide_with_animation(self):
        if self.hide_animation is not None:
            try:
                self.hide_animation.stop()
            except RuntimeError:
                pass
        self.hide_animation = QPropertyAnimation(self, b"windowOpacity", self)
        self.hide_animation.setDuration(250)
        self.hide_animation.setStartValue(1.0)
        self.hide_animation.setEndValue(0.0)
        self.hide_animation.setEasingCurve(QEasingCurve.InCubic)
        self.hide_animation.finished.connect(self.hide)
        self.hide_animation.start()

    def close_notification(self):
        if self.timeout_timer:
            self.timeout_timer.stop()

        if self.notification_data:
            if self._timed_out:
                self.hide()
            else:
                self.hide_with_animation()
            self.notification_closed.emit(self.notification_data)
            self.notification_data = None
        else:
            self.hide()

        self.clear_choice_buttons()

    # ---- 事件重写 ----
    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 30))
        painter.drawRoundedRect(2, 2, self.width(), self.height(), 12, 12)
        super().paintEvent(event)


# ---------------------------------------------------------------------------
# NotificationManager  — 线程协调器
# ---------------------------------------------------------------------------
class NotificationManager(QThread):
    """通知管理器，在独立线程中运行 WebSocket 客户端并桥接 UI"""

    show_notification_signal   = Signal(dict)
    errorOccurred              = Signal(str)
    connectionStateChanged     = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._name = "NotificationManager"
        self._paused = False
        self._stop_requested = False

        self.client = NotificationClient()
        self.notification_window = NotificationWindow()
        self.notification_window.manager = self
        self.current_notifications: list[dict] = []

        # 客户端回调 → Qt 信号（跨线程安全）
        self.client.on_notification = self._on_notification
        self.client.on_state_change = self._on_state_change
        self.client.on_error        = self._on_client_error

        # UI 信号
        self.notification_window.notification_closed.connect(self._on_window_closed)
        self.show_notification_signal.connect(self._show_in_main_thread)

    # ---- 线程控制 ----
    def get_name(self) -> str:
        return self._name

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def is_paused(self) -> bool:
        return self._paused

    def quit(self):
        self._stop_requested = True
        self.client.stop()
        super().quit()

    def run(self):
        log.info(f"[NotificationManager] 线程启动: {self._name}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            self.client.start(loop)
            loop.run_forever()
        except Exception as e:
            log.error(f"[NotificationManager] 异常: {e}")
            self.errorOccurred.emit(str(e))
        finally:
            self.client.stop()
            loop.close()
            self.notification_window.close()
            self.current_notifications.clear()
            log.info(f"[NotificationManager] 线程结束: {self._name}")

    # ---- 回调（从子线程调用）→ emit 信号到主线程 ----
    def _on_notification(self, data: dict):
        self.show_notification_signal.emit(data)

    def _on_state_change(self, state: ConnectionState):
        self.connectionStateChanged.emit(state.value)

    def _on_client_error(self, msg: str):
        self.errorOccurred.emit(msg)

    # ---- 主线程槽 ----
    @Slot(dict)
    def _show_in_main_thread(self, data: dict):
        try:
            self.notification_window.show_notification(data)
            self.current_notifications.append(data)
        except Exception as e:
            log.error(f"[NotificationManager] 显示通知失败: {e}")

    @Slot(dict)
    def _on_window_closed(self, data: dict):
        if data in self.current_notifications:
            self.current_notifications.remove(data) # pyright: ignore[reportUndefinedVariable]