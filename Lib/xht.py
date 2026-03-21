import sys
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QHBoxLayout, QMessageBox
from PySide6.QtGui import Qt, QColor, QPainter, QBrush, QIcon
from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QPoint, QTimer, QTime, Property
import os, subprocess, threading
import platform

import Lib.APIs as API
import Lib.config_manager as Config
import Lib.log_maker as log_maker

import pygetwindow as gw

#测试用
#import random




class xht(QWidget):
    def __init__(self, config_path, logger:log_maker.logger=log_maker.logger()):        
        super().__init__()
        global log
        log=logger
        log.info(f"""运行平台：{platform.system()}
        OS版本：{platform.release()}
        Python版本：{platform.python_version()}
        PID：{os.getpid()}""")
        #先决条件
        sys.excepthook = self.handle_exception
        self.weather_api = API.WeatherAPI()
        self.background_color = QColor(0, 0, 0)
        self.config = Config.load_config(config_path)

        #布局
        self.global_layout = None # 全局布局

        #动画
        self.size_animation = QPropertyAnimation(self, b"size")  # 初始化尺寸动画
        self.size_animation.setDuration(180)
        self.show_animation = QPropertyAnimation(self, b"pos")   # 初始化显示动画
        self.hide_animation = QPropertyAnimation(self, b"pos")   # 初始化隐藏动画
        self.is_hiding = False  # 动画状态

        # 新增初始化位置动画
        self.position_animation = QPropertyAnimation(self, b"pos")  # 初始化位置动画
        
        # 身位相关
        self.edge_height = self.config.get("edge_height")  # 边缘
        self.horizontal_edge_margin = self.config.get("horizontal_edge_margin")  # 水平方向边距
        self.is_hidden = False  # 是否隐藏
        self.auto_hide = False # 自动隐藏
        self.windowpos = self.config.get("windowpos")  # 窗口位置
        self.drag_threshold = self.config.get("drag_threshold")  # 拖动触发阈值
        self.window_start_pos = None

        #其他
        self.fullscreen_apps = self.config.get("auto_hide_apps")  # 全屏检测关键词列表
        self.initUI()
    def quit_app(self):
        log.info("程序退出")
        try:
            self.close()
        except Exception as e:
            log.error(f"终止进程失败: {e}")

    def initUI(self):
        log.info("程序正在启动")
        self.setMinimumSize(180, 48)
        self.setMaximumSize(900, 600)
        screen = self.get_current_screen().availableGeometry()

        if self.windowpos == "L":
            initial_x = screen.x() - self.minimumWidth()
        elif self.windowpos == "R":
            initial_x = screen.x() + screen.width()
        else:
            initial_x = screen.x() + (screen.width() - self.minimumWidth()) // 2

        self.setGeometry(initial_x, self.edge_height, self.minimumWidth(), self.minimumHeight())

        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle('XHT')

        self.original_ui()
        threading.Thread(target=self.update_weather).start()
        self.reg_timers()

    def showEvent(self, event):
        super().showEvent(event)
        self.update_position()
        
        screen = self.get_current_screen().availableGeometry()
        current_pos = self.pos()
        
        if self.windowpos == "L":
            initial_pos = QPoint(screen.x() - self.width(), current_pos.y())
        elif self.windowpos == "R":
            initial_pos = QPoint(screen.x() + screen.width(), current_pos.y())
        else:  
            initial_pos = QPoint(current_pos.x(), screen.y() - self.height())
        
        self.position_animation.setDuration(250)
        self.position_animation.setStartValue(initial_pos)
        self.position_animation.setEndValue(current_pos)
        self.position_animation.setEasingCurve(QEasingCurve.OutQuad)
        self.position_animation.start()

    def getBackgroundColor(self):
        return self.background_color

    def setBackgroundColor(self, color):
        self.background_color = color
        self.update()

    backgroundColor = Property(QColor, getBackgroundColor, setBackgroundColor)

    def handle_exception(self, exc_type, exc_value, traceback):
        error_msg = f"{exc_type.__name__}: {exc_value}"
        log.critical(f"严重错误: {error_msg}", exc_info=True)
        
        QTimer.singleShot(0, lambda: self.show_error_window(error_msg))
        
    def show_error_window(self, msg):
        QMessageBox.critical(self,"严重错误",  msg)
        self.quit_app()
    def reg_timers(self):
        self.ortime_timer = QTimer(self)
        self.ortime_timer.timeout.connect(self.update_time)
        self.ortime_timer.start(1500)

        self.check_wea = QTimer(self)
        self.check_wea.timeout.connect(self.update_weather)
        self.check_wea.start(720000)

        self.fullscreen_check_timer = QTimer(self)
        self.fullscreen_check_timer.timeout.connect(self.fcd)
        self.fullscreen_check_timer.start(2000)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(self.background_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 24, 24)

    def update_time(self):
            self.current_time = QTime.currentTime().toString("hh:mm")
            self.time_label.setText(self.current_time)
            #self.time_label.setText(str(random.randint(781391,1145141919810)))
            self.set_size()

    def update_weather(self):
            weather = self.weather_api.GetWeather()
            if not weather == 900:
                self.weather_label.setStyleSheet("color: white;  font-size: 16px;font-weight: bold;")
                self.weather_label.setText(f" {weather.get('weather')} {str(weather['temperature'])}{weather['unit']} ")
                log.info(f"{weather['region']}的天气数据更新成功")
            else:
                self.weather_label.setStyleSheet("color: red;  font-size: 16px;font-weight: bold;")
                self.weather_label.setText(f" 天气获取失败 ")
                log.error(f"天气获取失败")

    def get_current_screen(self):
        """获取窗口所在屏幕"""
        pos = self.pos()
        for screen in QApplication.screens():
            if screen.availableGeometry().contains(pos):
                return screen
        return QApplication.primaryScreen()  # 默认使用主屏

    def update_position(self):
        # 获取当前所在屏幕的可用区域
        screen = self.get_current_screen().availableGeometry()
        if self.windowpos == "L":
            target_x = screen.x() + self.horizontal_edge_margin  # 使用统一的水平边距
        elif self.windowpos == "R":
            target_x = screen.x() + (screen.width() - self.width()) - self.horizontal_edge_margin  # 右侧边距
        else:
            target_x = screen.x() + (screen.width() - self.width()) // 2
        current_y = self.y()
        current_pos = self.pos()
        target_pos = QPoint(target_x, current_y)

        if self.position_animation.state() == QPropertyAnimation.Running:
            self.position_animation.stop()

        self.position_animation.setDuration(250)
        self.position_animation.setStartValue(current_pos)
        self.position_animation.setEndValue(target_pos)
        self.position_animation.setEasingCurve(QEasingCurve.OutQuad)
        self.position_animation.start()

    def set_size(self):
        self.layout().activate()
        self.updateGeometry()
        
        content_size = self.layout().sizeHint().expandedTo(self.minimumSize())
        content_size = content_size.boundedTo(self.maximumSize())
        
        if self.size() == content_size:
            return
        
        if self.size_animation.state() == QPropertyAnimation.Running:
            self.size_animation.stop()
        
        self.size_animation.setStartValue(self.size())
        self.size_animation.setEndValue(content_size)
        
        def on_finish():
            self.resize(content_size)
            self.update_position()
        
        self.size_animation.finished.connect(on_finish)
        self.size_animation.start()

    def original_ui(self):
        self.time_label = QLabel(self)
        self.time_label.setStyleSheet("color: white; font-size: 16px;font-weight: bold;")
        self.time_label.setText(QTime.currentTime().toString("hh:mm"))
        self.weather_label = QLabel(self)
        self.weather_label.setStyleSheet("color: white; font-size: 16px;font-weight: bold;")
        self.weather_label.setText("获取信息中 ")
        self.weather_label.installEventFilter(self)
        
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.weather_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.global_layout = QHBoxLayout()
        self.global_layout.addWidget(self.time_label)
        self.global_layout.addWidget(self.weather_label)

        self.setLayout(self.global_layout)
        self.set_size()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_pos = event.globalPos()
            self.window_start_pos = self.pos()
            self.is_dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            if self.drag_start_pos is not None:
                delta = event.globalPos() - self.drag_start_pos
                if not self.is_dragging and (abs(delta.x()) > self.drag_threshold or abs(delta.y()) > self.drag_threshold):
                    self.is_dragging = True
                if self.is_dragging:
                    new_x = self.window_start_pos.x() + delta.x()
                    self.move(new_x, self.window_start_pos.y()) 
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle()
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_dragging:
            screen = self.get_current_screen().availableGeometry()
            screen_width = screen.width()
            window_center = self.pos().x() + self.width() / 2

            # 根据窗口中心相对于屏幕宽度的比例划分区域
            if window_center < screen.x() + screen_width * 0.30:
                self.windowpos = "L"  
            elif window_center > screen.x() + screen_width * 0.70:
                self.windowpos = "R"  
            else:
                self.windowpos = "M"  

            self.update_position()
        self.drag_start_pos = None
        self.is_dragging = False
        super().mouseReleaseEvent(event)

    def show_with_animation(self):
        log.info("事件：显示")
        if self.is_hiding or not self.is_hidden:
            return

        self.is_hiding = True
        current_pos = self.pos()
        # 获取当前屏幕信息
        current_screen = self.get_current_screen()
        screen = current_screen.availableGeometry()
        screen_width = screen.width()  # 使用当前屏幕宽度

        # 确定 Y 坐标：优先使用 window_start_pos，否则使用当前 Y
        window_y = current_pos.y()
        if self.window_start_pos is not None:
            window_y = self.window_start_pos.y()

        if self.windowpos == "L":
            # 从左侧隐藏位置开始，移动到正常位置
            initial_pos = QPoint(screen.x() - self.width() + self.edge_height, current_pos.y())
            target_pos = QPoint(screen.x() + self.horizontal_edge_margin, window_y)
        elif self.windowpos == "R":
            screen_width = screen.width()
            screen_width_minus_margin = screen.x() + screen_width - self.width() - self.horizontal_edge_margin
            # 从右侧隐藏位置开始，移动到正常位置
            initial_pos = QPoint(screen.x() + screen_width - self.edge_height, current_pos.y())
            target_pos = QPoint(screen_width_minus_margin, window_y)
        else:
            # 垂直方向处理保持不变
            initial_pos = QPoint(current_pos.x(), screen.y() - self.height())
            target_pos = QPoint(current_pos.x(), screen.y() + self.edge_height)

        if not self.show_animation:
            self.show_animation = QPropertyAnimation(self, b"pos", self)
        self.show_animation.setDuration(250)
        self.show_animation.setStartValue(initial_pos)
        self.show_animation.setEndValue(target_pos)
        self.show_animation.setEasingCurve(QEasingCurve.OutQuad)

        def on_finished():
            self.is_hiding = False
            self.is_hidden = False

        self.show_animation.finished.connect(on_finished)
        self.show_animation.start()

    def hide_with_animation(self):
        log.info("事件：隐藏")
        if self.is_hiding:
            return
        
        self.is_hiding = True
        current_pos = self.pos()
        screen = self.get_current_screen().availableGeometry()
        
        if self.windowpos in ["L", "R"]:
            if self.windowpos == "L":
                # 保留edge_height宽度可见
                target_x = screen.x() - (self.width() - self.edge_height)
            else:
                # 保留edge_height宽度可见
                target_x = screen.x() + screen.width() - self.edge_height
                
            target_pos = QPoint(target_x, current_pos.y())
        else:
            # 垂直方向保持原逻辑
            target_y = current_pos.y() - (self.height() - self.edge_height)
            target_pos = QPoint(current_pos.x(), target_y)
        
        if not self.hide_animation:
            self.hide_animation = QPropertyAnimation(self, b"pos", self)
        self.hide_animation.setDuration(250)
        self.hide_animation.setStartValue(current_pos)
        self.hide_animation.setEndValue(target_pos)
        self.hide_animation.setEasingCurve(QEasingCurve.OutQuad)
        
        def on_finished():
            self.is_hiding = False
            self.is_hidden = True
            
        self.hide_animation.finished.connect(on_finished)
        self.hide_animation.start()

    def toggle(self):
        if self.is_hidden:
            self.show_with_animation()
        else:
            self.hide_with_animation()

    def closeEvent(self, event):
        event.ignore()  # 忽略关闭事件

    def fcd(self):
        try:
            active_window = gw.getActiveWindow()
            if not active_window:
                return
            try:
                self.title = active_window.title
            except AttributeError:
                self.title = ""
        except Exception as e:
            log.warning(f"窗口检测异常: {str(e)}")


    def refresh(self, config_path):
        """刷新窗口"""
        self.config = Config.load_config(config_path)
        self.edge_height = self.config.get("edge_height")  # 边缘
        self.horizontal_edge_margin = self.config.get("horizontal_edge_margin")  # 水平方向边距
        self.windowpos = self.config.get("windowpos")  # 窗口位置
        self.drag_threshold = self.config.get("drag_threshold")  # 拖动触发阈值
        self.fullscreen_apps = self.config.get("auto_hide_apps")
        self.update_position()
        self.set_size()
        self.update_time()
        self.update_weather()
