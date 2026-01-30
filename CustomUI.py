from PySide6.QtCore import QObject, QEvent
from PySide6.QtWidgets import (QApplication, QWidget, QPushButton, QVBoxLayout)
from PySide6.QtGui import QCursor
from PySide6.QtCore import Qt, QTimer, QRect, QEvent, QPoint

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
	
# 新增：自定义弹出菜单（避免被 Dock 遮挡）
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

		# 先测量最长文本以决定宽度
		from PySide6.QtGui import QFontMetrics
		fm = QFontMetrics(self.font())
		max_label_w = 0
		for label, _, _ in actions:
			w = fm.horizontalAdvance(label)
			if w > max_label_w:
				max_label_w = w
		# 左右 padding + 按钮内边距估算，最小200，最大420
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

		# 计算合适高度（不超过屏幕 60 %）并固定 popup 与 scroll_area 大小
		screen_rect = QApplication.primaryScreen().availableGeometry()
		max_h = int(screen_rect.height() * 0.6)
		content_h = min(max_h, len(actions) * (item_h + 2) + 12)
		# 设置固定尺寸
		self.setFixedSize(content_w, content_h)
		scroll_area.setFixedSize(content_w - 12, content_h - 12)
		content_widget.setFixedWidth(content_w - 12)

	# 重写 show_at_position: 始终优先在图标上方显示菜单，并确保显示所有选项
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
				print(f"ContextPopup位置计算错误: {e}")
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