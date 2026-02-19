from PySide6.QtCore import QObject, Signal
from PySide6.QtCore import Qt, QTimer, QRect, QEvent, QPoint, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (QApplication, QWidget, QPushButton, QHBoxLayout, QVBoxLayout, QDialog, QLabel, QMessageBox)

# 添加Windows API导入，用于输入法切换
import win32con
import win32api


class IconHoverFilter(QObject):
	def __init__(self, parent):
		super().__init__(parent)
		self.parent = parent

	def eventFilter(self, obj, event):
		# 支持 Enter/Leave 以及 HoverEnter/HoverLeave，和 MouseMove
		et = event.type()
		if et in (QEvent.Enter, QEvent.HoverEnter):
			try:
				self.parent.show_icon_tooltip(obj, obj.toolTip())
			except Exception:
				pass
			return False
		if et in (QEvent.Leave, QEvent.HoverLeave):
			try:
				self.parent.hide_icon_tooltip()
			except Exception:
				pass
			return False
		if et == QEvent.MouseMove:
			# 更新位置以跟随鼠标/图标
			try:
				self.parent.update_icon_tooltip_position(obj)
			except Exception:
				pass
			return False
		return False

# 自定义弹出菜单（避免被 Dock 遮挡）
class ContextPopup(QWidget):
	def __init__(self, actions, parent=None):
		super().__init__(parent)
		flags = Qt.Popup | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
		self.setWindowFlags(flags)
		# 关闭窗口透明属性以确保样式背景可见
		self.setAttribute(Qt.WA_TranslucentBackground, False)
		self.setAttribute(Qt.WA_ShowWithoutActivating, True)
		self.setFocusPolicy(Qt.NoFocus)
		# 主布局
		layout = QVBoxLayout(self)
		layout.setContentsMargins(6, 6, 6, 6)
		layout.setSpacing(4)
		# 滚动区域
		from PySide6.QtWidgets import QScrollArea, QFrame
		scroll_area = QScrollArea()
		scroll_area.setWidgetResizable(True)
		scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
		scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
		scroll_area.setFrameStyle(QFrame.NoFrame)
		# 内容容器
		content_widget = QWidget()
		content_layout = QVBoxLayout(content_widget)
		content_layout.setContentsMargins(0, 0, 0, 0)
		content_layout.setSpacing(2)
		# 样式（不透明背景）
		self.setStyleSheet("""
			QWidget { 
				background: black;
				border: 1px solid rgba(255,255,255,20);
			}
			QPushButton { 
				color: #fff; 
				background: transparent; 
				border: none; 
				padding: 8px 12px; 
				text-align: center; 
			}
			QPushButton:hover { 
				background: rgba(255,255,255,0.08); 
			}
			QPushButton:disabled { 
				color: rgba(255,255,255,0.5); 
			}
		""")

		# 测量最长文本以决定宽度
		from PySide6.QtGui import QFontMetrics
		fm = QFontMetrics(self.font())
		max_label_w = 0
		for label, _, _ in actions:
			w = fm.horizontalAdvance(label)
			if w > max_label_w:
				max_label_w = w
		# 左右内边距 + 按钮内边距估算，最小200，最大420
		content_w = min(420, max(200, max_label_w + 60))
		# 动态创建按钮
		item_h = max(36, int(fm.height() * 1.6))
		for label, callback, enabled in actions:
			btn = QPushButton(label, self)
			btn.setEnabled(enabled)
			def make_handler(cb):
				def handler():
					try:
						self.close()
					except:
						pass
					if cb:
						QTimer.singleShot(0, cb)
				return handler
			btn.clicked.connect(make_handler(callback))
			content_layout.addWidget(btn)

		scroll_area.setWidget(content_widget)
		layout.addWidget(scroll_area)

		# 计算合适高度（不超过屏幕60%）并固定弹出菜单与滚动区域大小
		screen_rect = QApplication.primaryScreen().availableGeometry()
		max_h = int(screen_rect.height() * 0.6)
		content_h = min(max_h, len(actions) * (item_h + 2) + 12)
		# 设置固定尺寸
		self.setFixedSize(content_w, content_h)
		scroll_area.setFixedSize(content_w - 12, content_h - 12)
		content_widget.setFixedWidth(content_w - 12)

	# 重写显示位置方法：始终优先在图标上方显示菜单，并确保显示所有选项
	def show_at_position(self, pos, sender):
		offset = 8  # 图标与菜单的垂直间距
		if sender is not None:
			try:
				# 获取发送者（图标按钮）在屏幕上的位置和大小
				top_left = sender.mapToGlobal(QPoint(0, 0))
				sender_rect = QRect(top_left, sender.size())
				center_x = sender_rect.left() + sender_rect.width() // 2
				x = center_x - (self.width() // 2)

				# 优先放在图标上方
				y = sender_rect.top() - self.height() - offset

				# 确保菜单在屏幕范围内
				screen_rect = QApplication.primaryScreen().availableGeometry()

				# 水平边界检查
				if x < screen_rect.left():
					x = screen_rect.left()
				elif x + self.width() > screen_rect.right():
					x = screen_rect.right() - self.width()

				# 垂直边界检查 - 优先保证菜单显示在图标上方
				if y < screen_rect.top():
					# 如果上方空间不够，再尝试放到下方
					y = sender_rect.bottom() + offset
					# 如果下方也不够，则调整到屏幕范围内
					if y + self.height() > screen_rect.bottom():
						y = screen_rect.bottom() - self.height()
					if y < screen_rect.top():
						y = screen_rect.top()
			except Exception as e:
				# 如果发生错误，使用鼠标位置作为备选方案
				print(f"弹出菜单位置计算错误: {e}")
				global_pos = pos if isinstance(pos, QPoint) else QCursor.pos()
				x = global_pos.x() - (self.width() // 2)
				y = global_pos.y() - self.height() - offset
		else:
			# 没有发送者，使用鼠标位置
			global_pos = pos if isinstance(pos, QPoint) else QCursor.pos()
			x = global_pos.x() - (self.width() // 2)
			y = global_pos.y() - self.height() - offset

		# 确保最终位置是整数
		x, y = int(x), int(y)
		self.move(x, y)
		self.show()
		self.raise_()
		self.activateWindow()

class IMENotification(QWidget):
	"""输入法切换提示界面"""
	def __init__(self, parent=None):
		super().__init__(parent)
		self.setup_ui()
		self.setup_animation()
	
	def setup_ui(self):
		"""设置UI界面"""
		# 设置窗口标志
		self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
		self.setAttribute(Qt.WA_TranslucentBackground)
		self.setAttribute(Qt.WA_ShowWithoutActivating)
		
		# 设置固定大小
		self.setFixedSize(200, 80)
		
		# 主布局
		layout = QVBoxLayout(self)
		layout.setContentsMargins(0, 0, 0, 0)
		
		# 提示标签
		self.label = QLabel("输入法切换")
		self.label.setAlignment(Qt.AlignCenter)
		self.label.setStyleSheet("""
			QLabel {
				color: white;
				background-color: rgba(0, 0, 0, 180);
				border-radius: 10px;
				padding: 15px;
				font-size: 16px;
				font-weight: bold;
			}
		""")
		layout.addWidget(self.label)
	
	def setup_animation(self):
		"""设置动画效果"""
		# 淡入淡出动画
		self.fade_animation = QPropertyAnimation(self, b"windowOpacity")
		self.fade_animation.setDuration(300)  # 300ms
		self.fade_animation.setStartValue(0.0)
		self.fade_animation.setEndValue(1.0)
		self.fade_animation.setEasingCurve(QEasingCurve.InOutQuad)
	
	def show_notification(self, screen_center=None):
		"""显示提示"""
		# 如果没有指定位置，则显示在屏幕中央
		if screen_center is None:
			screen = QApplication.primaryScreen().geometry()
			x = (screen.width() - self.width()) // 2
			y = (screen.height() - self.height()) // 2
		else:
			x, y = screen_center
			
		self.move(x, y)
		self.show()
		
		# 播放淡入动画
		self.setWindowOpacity(0.0)
		self.fade_animation.start()
		
		# 1.5秒后自动关闭
		QTimer.singleShot(1500, self.fade_out_and_close)
	
	def fade_out_and_close(self):
		"""淡出并关闭"""
		self.fade_animation.finished.connect(self.close)
		self.fade_animation.setDirection(QPropertyAnimation.Backward)
		self.fade_animation.start()


class ShutdownDialog(QDialog):
	def __init__(self, parent=None):
		super().__init__(parent)
		self.parent = parent
		self.selected_action = None
		self.setWindowTitle("电源操作")
		self.setFixedSize(600, 150)
		self.setModal(True)

		self.init_ui()

	def init_ui(self):
		layout = QVBoxLayout()
		layout.setContentsMargins(20, 20, 20, 20)
		layout.setSpacing(10)

		# 标题
		title_label = QLabel("希望计算机执行？")
		title_label.setAlignment(Qt.AlignCenter)
		title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffffff; margin-bottom: 10px;")
		layout.addWidget(title_label)


		# 按钮容器
		button_layout = QHBoxLayout()
		button_layout.setSpacing(8)

		# 注销按钮
		logout_btn = QPushButton("注销")
		logout_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 12px;
                font-size: 14px;
                min-height: 20px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
        """)
		logout_btn.clicked.connect(lambda: self.select_action("logout"))
		button_layout.addWidget(logout_btn)

		# 重启按钮
		restart_btn = QPushButton("重启")
		restart_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 12px;
                font-size: 14px;
                min-height: 20px;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
            QPushButton:pressed {
                background-color: #E65100;
            }
        """)
		restart_btn.clicked.connect(lambda: self.select_action("restart"))
		button_layout.addWidget(restart_btn)

		# 关机按钮
		shutdown_btn = QPushButton("关机")
		shutdown_btn.setStyleSheet("""
            QPushButton {
                background-color: #F44336;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 12px;
                font-size: 14px;
                min-height: 20px;
            }
            QPushButton:hover {
                background-color: #D32F2F;
            }
            QPushButton:pressed {
                background-color: #B71C1C;
            }
        """)
		shutdown_btn.clicked.connect(lambda: self.select_action("shutdown"))
		button_layout.addWidget(shutdown_btn)

		# 休眠按钮
		hibernate_btn = QPushButton("休眠")
		hibernate_btn.setStyleSheet("""
            QPushButton {
                background-color: #607D8B;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 12px;
                font-size: 14px;
                min-height: 20px;
            }
            QPushButton:hover {
                background-color: #455A64;
            }
            QPushButton:pressed {
                background-color: #263238;
            }
        """)
		hibernate_btn.clicked.connect(lambda: self.select_action("hibernate"))
		button_layout.addWidget(hibernate_btn)

		# 取消按钮
		cancel_btn = QPushButton("取消")
		cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #9E9E9E;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 12px;
                font-size: 14px;
                min-height: 20px;
            }
            QPushButton:hover {
                background-color: #757575;
            }
            QPushButton:pressed {
                background-color: #616161;
            }
        """)
		cancel_btn.clicked.connect(self.reject)
		button_layout.addWidget(cancel_btn)

		layout.addLayout(button_layout)

		self.setLayout(layout)

		# 设置对话框样式
		self.setStyleSheet("""
            QDialog {
                background-color: #000000;
            }
        """)

	def select_action(self, action):
		"""选择操作并确认"""
		action_names = {
			"logout": "注销",
			"shutdown": "关机",
			"restart": "重启",
			"hibernate": "休眠"
		}

		reply = QMessageBox.question(
			self,
			"确认操作",
			f"确定要执行{action_names[action]}操作吗？\n\n请确保已保存所有工作！",
			QMessageBox.Yes | QMessageBox.No,
			QMessageBox.No
		)

		if reply == QMessageBox.Yes:
			self.selected_action = action
			self.accept()


# 全局快捷键处理类，用于实现Windows徽标键+空格键切换输入法
class GlobalHotkeyManager(QObject):
	"""
	全局快捷键管理器，使用PySide6的QShortcut实现快捷键监听
	"""
	# 定义信号
	hotkey_pressed = Signal()
	
	def __init__(self, parent=None):
		super().__init__(parent)
		self.shortcuts = []  # 存储快捷键对象
		self.active_shortcut = None  # 当前激活的快捷键
		self.hotkey_combo = None  # 记录使用的快捷键组合
		self.wallpaper_window = None  # 壁纸窗口引用
		self.ime_notification = None  # 输入法切换提示界面
		
	def start(self):
		"""启动快捷键管理器"""
		# 尝试注册快捷键组合
		if not self.try_register_shortcuts():
			print("无法注册任何快捷键，功能禁用")
			return False
		
		print(f"快捷键已注册: {self.hotkey_combo}")
		return True
	
	def try_register_shortcuts(self):
		"""尝试注册两种快捷键组合"""
		from PySide6.QtWidgets import QApplication
		from PySide6.QtGui import QKeySequence, QShortcut
		
		# 获取应用程序主窗口
		app = QApplication.instance()
		if not app:
			print("无法获取应用程序实例")
			return False
		
		# 只保留两种快捷键组合
		hotkey_combinations = [
			{"key": QKeySequence("Ctrl+Shift+Space"), "name": "Ctrl+Shift"},
			{"key": QKeySequence("Meta+Alt+Space"), "name": "Windows徽标键+Alt+空格键"}
		]
		
		# 尝试注册每个快捷键组合
		for combo in hotkey_combinations:
			try:
				# 创建快捷键对象
				shortcut = QShortcut(combo["key"], app.activeWindow() or app.focusWidget())
				if shortcut:
					# 连接激活信号
					shortcut.activated.connect(self.handle_hotkey)
					self.shortcuts.append(shortcut)
					self.hotkey_combo = combo["name"]
					self.active_shortcut = shortcut
					print(f"成功注册快捷键: {combo["name"]}")
					return True
			except Exception as e:
				print(f"注册快捷键失败: {combo['name']}，错误: {e}")
				continue
		
		return False
	
	def handle_hotkey(self):
		"""处理快捷键事件，切换输入法"""
		try:
			print(f"{self.hotkey_combo}被按下，切换输入法")
			
			# 显示输入法切换提示
			self.show_ime_notification()
			
			# 使用Windows API发送输入法切换消息
			# 尝试多种切换方式，以适应不同系统配置
			try:
				# 方法1: 尝试使用Win+Space（Windows 10/11默认方式）
				win32api.keybd_event(win32con.VK_LWIN, 0, 0, 0)
				win32api.keybd_event(0x20, 0, 0, 0)  # 空格键
				win32api.keybd_event(0x20, 0, win32con.KEYEVENTF_KEYUP, 0)
				win32api.keybd_event(win32con.VK_LWIN, 0, win32con.KEYEVENTF_KEYUP, 0)
			except:
				# 方法2: 如果方法1失败，尝试Ctrl+Shift
				win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
				win32api.keybd_event(win32con.VK_SHIFT, 0, 0, 0)
				win32api.keybd_event(win32con.VK_SHIFT, 0, win32con.KEYEVENTF_KEYUP, 0)
				win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
			
			# 发出信号，供其他组件响应
			self.hotkey_pressed.emit()
			
		except Exception as e:
			print(f"处理快捷键时出错: {e}")