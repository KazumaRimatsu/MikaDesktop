import os
import json
from PySide6.QtWidgets import (QMainWindow)
from PySide6.QtGui import QPixmap, QPalette
from PySide6.QtCore import Qt


class WallpaperWindow(QMainWindow):
    def __init__(self, parent=None, image_path=""):
        super().__init__(parent)  # 首先调用基类初始化
        self.wallpaper_path = image_path  # 存储图片路径
        self.setup_window()
        # 不在初始化时调用set_wallpaper，等待窗口显示后再设置
        
    def setup_window(self):
        self.setWindowTitle("Wallpaper")
        # 设置全屏无标题栏窗口
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.X11BypassWindowManagerHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_X11DoNotAcceptFocus, True)  # 确保窗口不接受焦点
        self.showFullScreen()
        # 确保壁纸窗口在其他窗口之下
        self.lower()
    
    def set_wallpaper(self, image_path):
        self.wallpaper_path = image_path
        palette = QPalette()
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            # 调整图片大小以适应窗口 - 现在self.size()会返回正确的尺寸
            scaled_pixmap = pixmap.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            palette.setBrush(QPalette.Window, scaled_pixmap)
            self.setPalette(palette)
        else:
            # 如果图片加载失败，使用默认背景色
            self.setStyleSheet("background-color: #36393F;")
    
    def resizeEvent(self, event):
        self.set_wallpaper(self.wallpaper_path)
        super().resizeEvent(event)

    def closeEvent(self, event):
        pass

    def mousePressEvent(self, event):
        # 重写鼠标点击事件，防止窗口被带到前台
        event.ignore()  # 忽略点击事件，不响应点击操作

    def mouseMoveEvent(self, event):
        # 重写鼠标移动事件，防止窗口被带到前台
        event.ignore()  # 忽略移动事件，不响应鼠标移动操作

    def mouseReleaseEvent(self, event):
        # 重写鼠标释放事件，防止窗口被带到前台
        event.ignore()  # 忽略释放事件，不响应鼠标释放操作

    def showEvent(self, event):
        # 窗口显示时设置壁纸，确保此时self.size()返回正确的尺寸
        if self.wallpaper_path:
            self.set_wallpaper(self.wallpaper_path)
        super().showEvent(event)