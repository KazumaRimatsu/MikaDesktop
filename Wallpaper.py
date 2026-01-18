from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtGui import QPainter, QPixmap, QColor
from PySide6.QtCore import Qt, QEvent


class WallpaperWindow(QWidget):
    def __init__(self, image_path=None):
        super().__init__()
        self.image_path = image_path
        self.pixmap = None
        
        self.init_ui()
        self.load_image()
        
    def eventFilter(self, obj, event):
        """
        过滤键盘事件，屏蔽关闭窗口相关的快捷键
        """
        if event.type() == QEvent.KeyPress:
            key = event.key()
            modifiers = event.modifiers()
            
            # 屏蔽常见的关闭窗口快捷键组合
            if (
                (modifiers == Qt.ControlModifier and key == Qt.Key_Q) or  # Ctrl+Q
                (modifiers == Qt.ControlModifier and key == Qt.Key_W) or  # Ctrl+W
                (modifiers == Qt.AltModifier and key == Qt.Key_F4) or     # Alt+F4
                (modifiers == Qt.ControlModifier and modifiers == Qt.ShiftModifier and key == Qt.Key_W) or  # Ctrl+Shift+W
                (key == Qt.Key_Escape)  # Escape
            ):
                print(f"壁纸窗口阻止快捷键: {modifiers.name() if modifiers else 'No Modifiers'}+{event.text() if event.text() else key}")
                return True  # 表示事件已被处理，不再传递
        
        # 其他事件按正常流程处理
        return super().eventFilter(obj, event)

    def init_ui(self):
        # 设置窗口标志，使其成为桌面壁纸级别的窗口
        self.setWindowFlags(
            Qt.FramelessWindowHint | 
            Qt.WindowStaysOnBottomHint | 
            Qt.SubWindow  # 防止窗口获取焦点
        )
        
        # 设置窗口属性
        self.setAttribute(Qt.WA_TranslucentBackground, True)  # 背景透明
        self.setAttribute(Qt.WA_X11DoNotAcceptFocus, True)  # 不接受焦点（X11系统）
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)  # 显示时不激活
        
        # 安装事件过滤器，屏蔽关闭快捷键
        self.installEventFilter(self)
        
        # 获取屏幕尺寸并设置窗口大小
        screen = QApplication.primaryScreen()
        screen_size = screen.size()
        self.resize(screen_size)
        self.move(0, 0)
        
        # 设置样式
        self.setStyleSheet("border: none; margin: 0px; padding: 0px;")
        
    def load_image(self):
        if self.image_path and self.image_path != "":
            try:
                self.pixmap = QPixmap(self.image_path)
                if self.pixmap.isNull():
                    print(f"无法加载图像: {self.image_path}")
                    self.setStyleSheet("background-color: #36393F;")  # 默认深色背景
                else:
                    # 图片将在paintEvent中进行缩放和绘制
                    # 设置背景为透明，避免覆盖图片
                    self.setStyleSheet("background-color: transparent; border: none; margin: 0px; padding: 0px;")
            except Exception as e:
                print(f"加载壁纸图像时出错: {e}")
                self.setStyleSheet("background-color: #36393F;")  # 默认深色背景
        else:
            # 如果没有壁纸路径，使用默认背景
            self.setStyleSheet("background-color: #36393F;")
        
        # 无论是否成功加载，都触发重绘
        self.repaint()

    def set_wallpaper(self, image_path):
        self.image_path = image_path
        self.load_image()
        self.repaint()  # 强制重新绘制窗口

    def paintEvent(self, event):
        if self.pixmap and not self.pixmap.isNull():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            
            # 缩放图片以适应窗口大小
            scaled_pixmap = self.pixmap.scaled(
                self.size(),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation
            )
            
            # 计算图片在窗口中的居中位置
            x = (self.width() - scaled_pixmap.width()) // 2
            y = (self.height() - scaled_pixmap.height()) // 2
            
            # 绘制图片
            painter.drawPixmap(x, y, scaled_pixmap)
        else:
            # 如果没有图片，则绘制默认背景色
            painter = QPainter(self)
            painter.fillRect(self.rect(), QColor("#36393F"))

    def resizeEvent(self, event):
        # 当窗口大小改变时，重新加载和缩放图片
        if self.image_path and self.image_path != "":
            self.load_image()
        super().resizeEvent(event)
        
    def closeEvent(self, event):
        # 忽略关闭事件，防止窗口意外关闭
        event.ignore()