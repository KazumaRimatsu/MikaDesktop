from PySide6.QtWidgets import QWidget, QApplication, QLabel
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
            
            # 屏蔽常见的关闭窗口的快捷键组合
            if (
                (modifiers == Qt.ControlModifier and key == Qt.Key_Q) or  # Ctrl+Q
                (modifiers == Qt.ControlModifier and key == Qt.Key_W) or  # Ctrl+W
                (modifiers == Qt.AltModifier and key == Qt.Key_F4) or     # Alt+F4
                (modifiers == Qt.ControlModifier and modifiers == Qt.ShiftModifier and key == Qt.Key_W) or  # Ctrl+Shift+W
                (key == Qt.Key_Escape)  # Escape
            ):
                print(f"壁纸窗口阻止快捷键: {modifiers.name() if modifiers else '无修饰键'}+{event.text() if event.text() else key}")
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
        """加载并优化壁纸图片"""
        if self.image_path and self.image_path != "":
            try:
                # 优化：使用Qt的图像加载优化参数
                pixmap = QPixmap()
                pixmap.load(self.image_path, format=None, flags=Qt.AutoColor)
                
                if pixmap.isNull():
                    print(f"无法加载图像: {self.image_path}")
                    self.pixmap = None
                    self.setStyleSheet("background-color: #36393F;")  # 默认深色背景
                else:
                    # 优化：预处理图像以提高绘制性能
                    self.pixmap = pixmap
                    self.setStyleSheet("background-color: transparent; border: none; margin: 0px; padding: 0px;")
                    
            except Exception as e:
                print(f"加载壁纸图像时出错: {e}")
                self.pixmap = None
                self.setStyleSheet("background-color: #36393F;")  # 默认深色背景
        else:
            # 如果没有壁纸路径，使用默认背景
            self.pixmap = None
            self.setStyleSheet("background-color: #36393F;")
        
        # 无论是否成功加载，都触发重绘
        self.update()  # 优化：使用update()而非repaint()，让Qt选择最佳重绘时机

    def set_wallpaper(self, image_path):
        self.image_path = image_path
        self.load_image()
        self.repaint()  # 强制重新绘制窗口

    def paintEvent(self, event):
        """优化的绘制事件，提高性能"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)  # 优化：关闭平滑变换以提高性能
        
        if self.pixmap and not self.pixmap.isNull():
            # 优化：只在需要时进行缩放，避免每次绘制都重新缩放
            scaled_pixmap = self.pixmap.scaled(
                self.size(),
                Qt.KeepAspectRatioByExpanding,
                Qt.FastTransformation  # 优化：使用快速变换而非平滑变换
            )
            
            # 计算图片在窗口中的居中位置
            x = (self.width() - scaled_pixmap.width()) // 2
            y = (self.height() - scaled_pixmap.height()) // 2
            
            # 绘制图片
            painter.drawPixmap(x, y, scaled_pixmap)
        else:
            # 如果没有图片，则绘制默认背景色
            painter.fillRect(self.rect(), QColor("#36393F"))
            
        painter.end()

    def resizeEvent(self, event):
        """优化的窗口大小改变事件处理"""
        # 优化：不需要重新加载图片，只需要触发重绘即可
        self.update()
        super().resizeEvent(event)
        
    def show_ime_notification(self):
        """在屏幕右下角显示输入法切换提示"""
        try:
            # 创建或获取提示标签
            if not hasattr(self, 'ime_label'):
                self.ime_label = QLabel("输入法切换", self)
                self.ime_label.setAlignment(Qt.AlignCenter)
                self.ime_label.setStyleSheet("""
                    QLabel {
                        color: white;
                        background-color: rgba(0, 0, 0, 180);
                        border-radius: 10px;
                        padding: 15px;
                        font-size: 16px;
                        font-weight: bold;
                    }
                """)
                self.ime_label.setFixedSize(200, 80)
                self.ime_label.hide()  # 初始隐藏
            
            # 计算位置：屏幕右下角，与主窗口垂直对齐
            screen = QApplication.primaryScreen().geometry()
            x = screen.width() - self.ime_label.width() - 20  # 距离右边缘20像素
            y = screen.height() - self.ime_label.height() - 20  # 距离底部边缘20像素
            
            # 设置位置并显示
            self.ime_label.move(x, y)
            self.ime_label.setWindowOpacity(0.0)  # 重置透明度
            self.ime_label.show()
            
            # 设置透明度动画
            from PySide6.QtCore import QPropertyAnimation
            self.fade_in = QPropertyAnimation(self.ime_label, b"windowOpacity")
            self.fade_in.setDuration(300)  # 300ms
            self.fade_in.setStartValue(0.0)
            self.fade_in.setEndValue(1.0)
            self.fade_in.start()
            
            # 1.5秒后自动关闭
            from PySide6.QtCore import QTimer
            QTimer.singleShot(1500, self.fade_out_ime_notification)
            
        except Exception as e:
            print(f"显示输入法提示时出错: {e}")
    
    def fade_out_ime_notification(self):
        """淡出并关闭输入法提示"""
        try:
            if hasattr(self, 'ime_label') and self.ime_label.isVisible():
                from PySide6.QtCore import QPropertyAnimation
                self.fade_out = QPropertyAnimation(self.ime_label, b"windowOpacity")
                self.fade_out.setDuration(300)  # 300ms
                self.fade_out.setStartValue(1.0)
                self.fade_out.setEndValue(0.0)
                self.fade_out.finished.connect(self.ime_label.hide)
                self.fade_out.start()
        except Exception as e:
            print(f"淡出输入法提示时出错: {e}")
    
    def closeEvent(self, event):
        # 忽略关闭事件，防止窗口意外关闭
        event.ignore()