import http.server
import socketserver
import urllib.parse
import json
import threading
import time
from typing import Dict, List, Any, Optional
from PySide6.QtCore import Signal, QTimer, Qt, Slot, QPropertyAnimation, QEasingCurve, QThread
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QApplication
from PySide6.QtGui import QPainter, QColor, QFont

from .. import log_maker

log = log_maker.logger()


class NotificationRequestHandler(http.server.BaseHTTPRequestHandler):
    """HTTP请求处理器，处理通知请求"""
    
    def do_GET(self):
        """处理GET请求"""
        # 解析路径和查询参数
        parsed_path = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_path.query)
        
        # 只处理/notify路径
        if parsed_path.path == '/notify':
            log.warning("GET请求已弃用，请使用POST请求")
            self.handle_notify_request(query_params)
        else:
            self.send_error(404, "Not Found")
    
    def do_POST(self):
        """处理POST请求"""
        # 解析路径
        parsed_path = urllib.parse.urlparse(self.path)
        
        # 只处理/notify路径
        if parsed_path.path != '/notify':
            self.send_error(404, "Not Found")
            return
        
        # 获取内容长度
        content_length = self.headers.get('Content-Length')
        if not content_length:
            self.send_error(411, "Length Required")
            return
        
        try:
            content_length = int(content_length)
        except ValueError:
            self.send_error(400, "Invalid Content-Length")
            return
        
        # 读取请求体
        body = self.rfile.read(content_length).decode('utf-8')
        if not body:
            self.send_error(400, "Empty request body")
            return
        
        # 解析JSON
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return
        
        # 将JSON数据转换为与GET查询参数相同的格式（字典，值为列表）
        query_params = {}
        for key, value in data.items():
            if isinstance(value, list):
                query_params[key] = value
            else:
                query_params[key] = [str(value)]
        
        # 处理通知请求
        self.handle_notify_request(query_params)
    
    def handle_notify_request(self, query_params: Dict[str, List[str]]):
        """处理通知请求"""
        try:
            # 解析参数
            title = self.get_param(query_params, 'title')
            context = self.get_param(query_params, 'context')
            level = self.get_param(query_params, 'level', 'default')
            notification_type = self.get_param(query_params, 'type', 'default')
            timelimit = self.get_param(query_params, 'timelimit')
            icon = self.get_param(query_params, 'icon')
            
            # 验证必要参数
            if not title or not context:
                self.send_error(400, "Missing required parameters: title and context")
                return
            
            # 验证level参数
            if level not in ['default', 'warn', 'error']:
                self.send_error(400, "Invalid level parameter. Must be 'default', 'warn', or 'error'")
                return
            
            # 验证type参数
            if notification_type not in ['default', 'interaction']:
                self.send_error(400, "Invalid type parameter. Must be 'default' or 'interaction'")
                return
            
            # 处理交互式通知
            choices = []
            if notification_type == 'interaction':
                choices = self.get_param_list(query_params, 'choice')
                if not choices:
                    self.send_error(400, "Missing required parameter 'choice' for interaction type")
                    return
                
                if len(choices) > 4:
                    self.send_error(400, "Too many choices. Maximum is 4")
                    return
                if len(choices) == 0:
                    self.send_error(400, "No valid choices provided")
                    return
            
            # 解析wait参数
            wait_for_response = False
            wait_param = self.get_param(query_params, 'wait')
            if wait_param and wait_param.lower() == 'true':
                wait_for_response = True
            
            # 解析超时时间
            timeout = None
            if timelimit:
                try:
                    timeout = int(timelimit)
                    if timeout <= 0:
                        raise ValueError("Timeout must be positive")
                    if timeout > 60:
                        raise ValueError("Timeout must be less than or equal to 60 seconds")
                except ValueError:
                    self.send_error(400, f"Invalid timelimit parameter. Must be a positive integer between 1 and 60 seconds")
                    return
            
            # 创建通知数据
            notification_data = {
                'title': title,
                'context': context,
                'level': level,
                'type': notification_type,
                'timeout': timeout,
                'icon': icon,
                'choices': choices,
                'timestamp': time.time(),
                'wait_for_response': wait_for_response
            }
            
            # 如果需要等待响应，创建同步事件
            if wait_for_response and notification_type == 'interaction':
                notification_data['_response_event'] = threading.Event()
                notification_data['_response_result'] = None
            
            log.info(f"收到通知请求: {title} - {context} (level: {level}, type: {notification_type})")
            
            # 发送到UI线程显示
            if hasattr(self.server, 'notification_callback'):
                self.server.notification_callback(notification_data)
            
            # 返回响应
            if wait_for_response and notification_type == 'interaction' and '_response_event' in notification_data:
                # 等待用户选择或超时
                event = notification_data['_response_event']
                # 计算等待超时时间：使用通知超时时间（如果存在），否则使用最大60秒
                wait_timeout = timeout if timeout is not None else 60
                # 等待事件
                event_triggered = event.wait(wait_timeout)
                if event_triggered:
                    # 获取结果
                    result = notification_data.get('_response_result')
                    if result is not None and result != 'timeout':
                        response = {'status': 'success', 'choice': result}
                    else:
                        response = {'status': 'timeout', 'message': 'No choice made before timeout'}
                else:
                    # 超时
                    response = {'status': 'timeout', 'message': 'No choice made before timeout'}
            else:
                # 默认响应
                response = {'status': 'success', 'message': 'Notification received'}
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))
            
        except Exception as e:
            log.error(f"处理通知请求时出错: {e}")
            self.send_error(500, f"Internal Server Error: {str(e)}")
    
    def get_param(self, query_params: Dict[str, List[str]], key: str, default: Optional[str] = None) -> Optional[str]:
        """从查询参数中获取单个值"""
        if key in query_params and query_params[key]:
            return query_params[key][0]
        return default
    
    def get_param_list(self, query_params: Dict[str, List[str]], key: str, default: Optional[List[str]] = None) -> List[str]:
        """从查询参数中获取列表值"""
        if default is None:
            default = []
        if key in query_params:
            return query_params[key]
        return default
    
    def log_message(self, format, *args):
        """自定义日志消息格式"""
        log.info(f"HTTP请求: {format % args}")


class NotificationServer:
    """通知服务器类"""
    
    def __init__(self, host: str = '127.0.0.2', port: int = 8848):
        self.host = host
        self.port = port
        self.server = None
        self.server_thread = None
        self.running = False
        self.notification_callback = None
    
    def start(self, notification_callback):
        """启动通知服务器"""
        if self.running:
            log.warning("通知服务器已在运行")
            return False
        
        self.notification_callback = notification_callback
        
        try:
            # 创建HTTP服务器
            handler = NotificationRequestHandler
            self.server = socketserver.TCPServer((self.host, self.port), handler)
            
            # 设置回调函数
            self.server.notification_callback = notification_callback
            
            # 启动服务器线程
            self.server_thread = threading.Thread(target=self._run_server, daemon=True)
            self.server_thread.start()
            
            self.running = True
            log.info(f"通知服务器已启动在 {self.host}:{self.port}")
            return True
            
        except Exception as e:
            log.error(f"启动通知服务器失败: {e}")
            return False
    
    def _run_server(self):
        """运行服务器（在线程中）"""
        try:
            self.server.serve_forever()
        except Exception as e:
            log.error(f"服务器运行错误: {e}")
        finally:
            self.running = False
    
    def stop(self):
        """停止通知服务器"""
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
                log.info("通知服务器已停止")
            except Exception as e:
                log.error(f"停止通知服务器时出错: {e}")
            finally:
                self.server = None
                self.running = False


class NotificationWindow(QWidget):
    """通知窗口类"""
    
    notification_closed = Signal(dict)  # 通知关闭信号，传递通知数据
    
    def __init__(self, parent=None):
        super().__init__(parent)
        log.info("创建NotificationWindow实例")
        self.notification_data = None
        self.timeout_timer = None
        self.choice_buttons = []
        self.show_animation = None
        self.hide_animation = None
        self._timed_out = False  # 超时标志
        
        self.init_ui()
        self.setup_styles()
        log.info(f"NotificationWindow初始化完成，窗口标志: {self.windowFlags()}")
    
    def init_ui(self):
        """初始化UI"""
        # 设置窗口属性
        self.setWindowFlags(
            Qt.FramelessWindowHint | 
            Qt.WindowStaysOnTopHint |
            Qt.WindowDoesNotAcceptFocus
        )
        
        # 创建主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(10)
        
        # 标题标签
        self.title_label = QLabel()
        self.title_label.setWordWrap(True)
        font = QFont()
        font.setPointSize(24)
        font.setBold(True)
        self.title_label.setFont(font)
        self.title_label.setStyleSheet("background-color: transparent;")
        self.title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.title_label)
        
        # 内容标签
        self.context_label = QLabel()
        self.context_label.setWordWrap(True)
        self.context_label.setFont(QFont("Microsoft YaHei", 20))
        self.context_label.setStyleSheet("background-color: transparent;")
        self.context_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.context_label)
        
        # 交互按钮容器
        self.button_container = QWidget()
        self.button_layout = QHBoxLayout(self.button_container)
        self.button_layout.setContentsMargins(0, 10, 0, 0)
        self.button_layout.setSpacing(10)
        self.button_container.setStyleSheet("background-color: transparent;")
        main_layout.addWidget(self.button_container)
    
    def setup_styles(self):
        """设置样式"""
        # 基础样式会在show_notification中根据级别设置
    
    def show_notification(self, notification_data: Dict[str, Any]):
        """显示通知"""
        log.info(f"准备显示通知窗口: {notification_data['title']}")
        # 重置超时标志
        self._timed_out = False
        self.notification_data = notification_data
        
        # 更新内容
        self.title_label.setText(notification_data['title'])
        self.context_label.setText(notification_data['context'])
        
        # 根据级别设置样式
        level = notification_data['level']
        if level == 'warn':
            self.setStyleSheet("""
                QWidget {
                    background-color: #FFC53D;
                    color: #FFFFFF;
                }
                QLabel {
                    background-color: transparent;
                    color: #FFFFFF;
                }
            """)
        elif level == 'error':
            self.setStyleSheet("""
                QWidget {
                    background-color: #FF643D;
                    color: #FFFFFF;
                }
                QLabel {
                    background-color: transparent;
                    color: #FFFFFF;
                }
            """)
        else:  # default
            self.setStyleSheet("""
                QWidget {
                    background-color: #94BFFF;
                    color: #FFFFFF;
                }
                QLabel {
                    color: #FFFFFF;
                    background-color: transparent;
                }
            """)
        
        # 清除旧的交互按钮
        self.clear_choice_buttons()
        
        # 如果是交互式通知，添加按钮
        if notification_data['type'] == 'interaction' and notification_data['choices']:
            for item in notification_data['choices']:
                button = QPushButton(item)
                button.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(255, 255, 255, 0.2);
                        border: 1px solid rgba(87, 154, 255, 0.3);
                        border-radius: 6px;
                        padding: 8px 16px;
                        color: inherit;
                        font-size: 18px;
                    }
                    QPushButton:hover {
                        background-color: rgba(26, 117, 255, 0.3);
                        font-size: 18px;
                    }
                """)
                button.clicked.connect(lambda checked, c=item: self.handle_choice(c))
                self.button_layout.addWidget(button)
                self.choice_buttons.append(button)
        
        # 设置窗口大小和位置
        self.adjustSize()
        self.update_position()
        
        # 显示窗口（使用动画）
        log.info(f"调用show()显示窗口，窗口大小: {self.width()}x{self.height()}, 位置: {self.pos()}")
        self.show_with_animation()
        self.raise_()
        self.activateWindow()
        
        # 记录窗口状态
        log.info(f"窗口可见性: {self.isVisible()}, 是否最小化: {self.isMinimized()}")
        
        # 设置超时（如果有）
        if notification_data.get('timeout'):
            self.setup_timeout(notification_data['timeout'])
    
    def clear_choice_buttons(self):
        """清除交互按钮"""
        for button in self.choice_buttons:
            button.deleteLater()
        self.choice_buttons.clear()
    
    def setup_timeout(self, timeout: int):
        """设置超时定时器"""
        if self.timeout_timer:
            self.timeout_timer.stop()
        
        self.timeout_timer = QTimer()
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self.on_timeout)
        self.timeout_timer.start(timeout * 1000)  # 转换为毫秒
    
    def on_timeout(self):
        """超时处理"""
        self._timed_out = True
        # 禁用所有交互按钮
        for button in self.choice_buttons:
            button.setEnabled(False)
        # 立即关闭通知
        self.close_notification()
    
    def update_position(self):
        """更新窗口位置（屏幕中间，靠近上边缘）"""
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        
        # 计算位置
        x = screen_geometry.x() + (screen_geometry.width() - self.width()) // 2
        y = 64
        
        self.move(x, y)
    
    def handle_choice(self, choice: str):
        """处理交互选择"""
        # 检查是否已超时
        if self._timed_out:
            log.info(f"通知已超时，忽略用户选择: {choice}")
            return
        
        log.info(f"用户选择了: {choice}")
        self.notification_data['user_choice'] = choice
        
        # 设置响应结果并触发事件（如果存在）
        if '_response_event' in self.notification_data and '_response_result' in self.notification_data:
            self.notification_data['_response_result'] = choice
            self.notification_data['_response_event'].set()
        
        # 禁用所有按钮，防止多次点击
        for button in self.choice_buttons:
            button.setEnabled(False)
        
        self.close_notification()
    
    def show_with_animation(self):
        """使用动画显示窗口"""
        # 停止并丢弃已有动画（如果存在）
        if self.show_animation is not None:
            try:
                self.show_animation.stop()
            except:
                pass
        
        # 设置初始透明度为0
        self.setWindowOpacity(0.0)
        self.show()
        
        # 创建透明度动画
        self.show_animation = QPropertyAnimation(self, b"windowOpacity", self)
        self.show_animation.setDuration(300)  # 毫秒
        self.show_animation.setStartValue(0.0)
        self.show_animation.setEndValue(1.0)
        self.show_animation.setEasingCurve(QEasingCurve.OutCubic)
        
        self.show_animation.start()
    
    def hide_with_animation(self):
        """使用动画隐藏窗口"""
        # 停止并丢弃已有动画（如果存在）
        if self.hide_animation is not None:
            try:
                self.hide_animation.stop()
            except:
                pass
        
        # 创建透明度动画
        self.hide_animation = QPropertyAnimation(self, b"windowOpacity", self)
        self.hide_animation.setDuration(250)  # 毫秒
        self.hide_animation.setStartValue(1.0)
        self.hide_animation.setEndValue(0.0)
        self.hide_animation.setEasingCurve(QEasingCurve.InCubic)
        
        # 动画完成后隐藏窗口
        self.hide_animation.finished.connect(lambda: self.hide())
        self.hide_animation.start()
    
    def close_notification(self):
        """关闭通知"""
        if self.timeout_timer:
            self.timeout_timer.stop()
        
        # 如果存在等待响应的事件且尚未设置结果，则设置为超时
        if self.notification_data and '_response_event' in self.notification_data and '_response_result' in self.notification_data:
            if self.notification_data['_response_result'] is None:
                self.notification_data['_response_result'] = 'timeout'
                self.notification_data['_response_event'].set()
        
        self.clear_choice_buttons()
        
        if self._timed_out:
            # 超时后直接隐藏，不使用动画
            self.hide()
        else:
            self.hide_with_animation()
        
        # 发出关闭信号
        if self.notification_data:
            self.notification_closed.emit(self.notification_data)
            self.notification_data = None
    
    def resizeEvent(self, event):
        """窗口大小变化事件"""
        super().resizeEvent(event)
    
    def paintEvent(self, event):
        """绘制事件，添加阴影效果"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制阴影（在背景下面）
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 30))
        painter.drawRoundedRect(2, 2, self.width(), self.height(), 12, 12)
        
        # 绘制背景（由样式表处理）
        super().paintEvent(event)


class NotificationManager(QThread):
    """通知管理器，协调服务器和UI，适配新的线程管理器"""
    
    # 错误信号
    errorOccurred = Signal(str)  # 错误消息信号
    
    # 信号定义
    show_notification_signal = Signal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 线程控制
        self._name = "NotificationManager"
        self._paused = False
        self._stop_requested = False
        
        # 原有成员初始化
        self.server = NotificationServer()
        self.notification_window = NotificationWindow()
        self.current_notifications = []
        
        # 连接信号
        self.notification_window.notification_closed.connect(self.handle_notification_closed)
        self.show_notification_signal.connect(self._show_notification_in_main_thread)
    # 线程控制方法
    def get_name(self) -> str:
        """获取线程名称"""
        return self._name
    
    def pause(self):
        """暂停线程"""
        self._paused = True
    
    def resume(self):
        """恢复线程"""
        self._paused = False
    
    def is_paused(self) -> bool:
        """检查线程是否暂停"""
        return self._paused
    


    def quit(self):
        """停止线程"""
        self._stop_requested = True
        super().quit()
    

    def run(self):
        """线程主循环 - 运行通知系统"""
        log.info(f"通知系统开始运行: {self.get_name()}")
        
        try:
            # 初始化服务器
            if not self.server.start(self.show_notification):
                log.error("无法启动通知服务器")
                self.errorOccurred.emit("无法启动通知服务器")
                return
            
            # 主循环：等待停止事件
            while not self.isInterruptionRequested():
                # 检查是否暂停
                if self._paused:
                    time.sleep(0.1)
                    continue
                
                # 短暂睡眠以避免忙等待
                time.sleep(1.0)
            
            # 清理资源
            log.info(f"清理通知系统资源: {self.get_name()}")
            self.server.stop()
            self.notification_window.close()
            self.current_notifications.clear()
            log.info(f"通知系统资源清理完成: {self.get_name()}")
            
            log.info(f"通知系统运行结束: {self.get_name()}")
            
        except Exception as e:
            error_msg = f"通知系统运行时发生未捕获异常: {str(e)}"
            log.error(error_msg)
            self.errorOccurred.emit(error_msg)
            raise
    

    
    def show_notification(self, notification_data: Dict[str, Any]):
        """显示通知（从服务器线程调用）"""
        import threading
        current_thread = threading.current_thread()
        log.info(f"收到通知显示请求: {notification_data['title']} (线程: {current_thread.name})")
        
        # 使用信号确保在主线程中执行
        try:
            self.show_notification_signal.emit(notification_data)
            log.info(f"已发射信号安排在主线程显示通知")
        except Exception as e:
            log.error(f"发射通知信号时出错: {e}")
            import traceback
            traceback.print_exc()
    
    @Slot(dict)
    def _show_notification_in_main_thread(self, notification_data: Dict[str, Any]):
        """在主线程中显示通知"""
        try:
            self.notification_window.show_notification(notification_data)
            self.current_notifications.append(notification_data)
            log.info(f"显示通知: {notification_data['title']}")
        except Exception as e:
            log.error(f"显示通知时出错: {e}")
    
    def handle_notification_closed(self, notification_data: Dict[str, Any]):
        """处理通知关闭"""
        if notification_data in self.current_notifications:
            self.current_notifications.remove(notification_data)
        
        # 记录用户选择（如果有）
        if 'user_choice' in notification_data:
            log.info(f"通知 '{notification_data['title']}' 已关闭，用户选择了: {notification_data['user_choice']}")
        else:
            log.info(f"通知 '{notification_data['title']}' 已关闭")
