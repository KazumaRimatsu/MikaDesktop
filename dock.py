import sys
import os
import json
import tempfile
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QPushButton, QMenu, QFileDialog, QVBoxLayout, QHBoxLayout, 
                               QMessageBox, QDialog, QLabel, QInputDialog)
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QCursor, QAction, QPalette
from PySide6.QtCore import Qt, QSize, QTimer
from PIL import Image
from MakeAppIcon import compose_on_template
import win32con
import win32gui
import psutil  # 添加进程监控库
import win32process  # 新增导入


class WallpaperWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_window()
        self.wallpaper_path = ""
        self.load_wallpaper()
        
    def setup_window(self):
        # 设置全屏无标题栏窗口
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.X11BypassWindowManagerHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.showFullScreen()
        # 确保壁纸窗口在其他窗口之下
        self.lower()
        
    def load_wallpaper(self):
        settings_file = os.path.abspath("apps.json")
        if os.path.exists(settings_file):
            with open(settings_file, 'r', encoding='utf-8') as f:
                try:
                    settings = json.load(f)
                    self.wallpaper_path = settings.get('wallpaper', "")
                except json.JSONDecodeError:
                    self.wallpaper_path = ""
        
        if self.wallpaper_path and os.path.exists(self.wallpaper_path):
            self.set_wallpaper(self.wallpaper_path)
        else:
            # 默认使用纯色背景
            self.setStyleSheet("background-color: #36393F;")
    
    def set_wallpaper(self, image_path):
        self.wallpaper_path = image_path
        palette = QPalette()
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            # 调整图片大小以适应窗口
            scaled_pixmap = pixmap.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            palette.setBrush(QPalette.Window, scaled_pixmap)
            self.setPalette(palette)
        else:
            # 如果图片加载失败，使用默认背景色
            self.setStyleSheet("background-color: #36393F;")
    
    def resizeEvent(self, event):
        # 窗口大小改变时重新设置壁纸
        if self.wallpaper_path and os.path.exists(self.wallpaper_path):
            self.set_wallpaper(self.wallpaper_path)
        super().resizeEvent(event)

    def closeEvent(self, event):
        pass

class DockApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.apps = []
        self.settings_file = os.path.abspath("apps.json")  # 仅存储应用列表
        self.config_file = os.path.abspath("settings.json")  # 存储其他设置
        self.wallpaper_window = None  # 添加壁纸窗口引用
        self.wallpaper_path = ""  # 添加壁纸路径属性
        self.running_apps = {}  # 记录正在运行的应用
        self.app_buttons = {}  # 存储按钮引用，用于更新样式
        self.init_ui()
        self.create_tray_icon()
        self.load_settings()  # 在初始化后加载设置
        self.update_app_buttons()
        self.create_wallpaper_window()  # 创建壁纸窗口
        self.setup_process_monitoring()  # 设置进程监控

    def setup_process_monitoring(self):
        """设置定时器来监控进程状态"""
        self.process_timer = QTimer()
        self.process_timer.timeout.connect(self.check_running_processes)
        self.process_timer.start(2000)  # 每2秒检查一次

    def is_process_running(self, app_path):
        """检查指定路径的应用是否正在运行 - 改进版本"""
        try:
            # 规范化路径以进行比较
            normalized_app_path = os.path.abspath(app_path).lower()
            app_filename = os.path.basename(app_path).lower()
            
            for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
                try:
                    # 检查进程名是否匹配
                    proc_name = proc.info['name'].lower()
                    if proc_name == app_filename:
                        # 优先检查可执行文件路径
                        proc_exe = proc.info.get('exe')
                        if proc_exe:
                            normalized_proc_exe = os.path.abspath(proc_exe).lower()
                            if normalized_proc_exe == normalized_app_path:
                                return True
                        
                        # 备选方案：检查命令行参数
                        cmdline = proc.info.get('cmdline')
                        if cmdline:
                            # 将命令行参数合并为字符串进行比较
                            cmdline_str = ' '.join(cmdline).lower()
                            if normalized_app_path in cmdline_str:
                                return True
                            
                            # 检查命令行中是否包含应用文件名
                            if app_filename in cmdline_str:
                                # 进一步验证路径相似性
                                for arg in cmdline:
                                    if app_filename in arg.lower():
                                        arg_path = os.path.abspath(arg).lower()
                                        if normalized_app_path in arg_path or arg_path in normalized_app_path:
                                            return True
                    
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            return False
        except Exception as e:
            print(f"检查进程时出错: {e}")
            return False

    def check_running_processes(self):
        """检查所有应用的运行状态 - 改进版本"""
        try:
            # 创建当前运行应用的快照
            current_running = {}
            
            for app in self.apps:
                app_name = app['name']
                app_path = app['path']
                
                # 检查进程状态
                is_running = self.is_process_running(app_path)
                if is_running:
                    current_running[app_name] = app_path
            
            # 找出状态发生变化的应用
            apps_to_update = set()
            
            # 检查新启动的应用
            for app_name in current_running:
                if app_name not in self.running_apps:
                    apps_to_update.add(app_name)
            
            # 检查已关闭的应用
            for app_name in self.running_apps:
                if app_name not in current_running:
                    apps_to_update.add(app_name)
            
            # 更新需要变化的应用按钮
            for app_name in apps_to_update:
                if app_name in self.app_buttons:
                    button = self.app_buttons[app_name]
                    is_running = app_name in current_running
                    self.set_button_style(button, is_running)
                    print(f"应用 {app_name} 状态更新: {'运行中' if is_running else '已关闭'}")
            
            # 更新运行应用记录
            self.running_apps = current_running
            
        except Exception as e:
            print(f"检查运行进程时出错: {e}")

    def handle_app_click(self, app_data):
        """处理应用按钮点击事件 - 添加状态立即更新"""
        app_name = app_data['name']
        app_path = app_data['path']
        
        # 检查应用是否正在运行
        if app_name in self.running_apps:
            # 如果正在运行，激活窗口
            self.activate_window(app_path)
        else:
            # 如果未运行，启动应用
            try:
                # 启动前立即更新状态（避免启动延迟导致的显示问题）
                self.running_apps[app_name] = app_path
                if app_name in self.app_buttons:
                    button = self.app_buttons[app_name]
                    self.set_button_style(button, True)
                
                # 启动应用
                self.launch_app(app_path)
                
                # 延迟检查一次确保状态正确
                QTimer.singleShot(1000, self.check_running_processes)
                
            except Exception as e:
                # 如果启动失败，回滚状态
                if app_name in self.running_apps:
                    del self.running_apps[app_name]
                if app_name in self.app_buttons:
                    button = self.app_buttons[app_name]
                    self.set_button_style(button, False)
                QMessageBox.critical(self, "错误", f"无法启动应用: {str(e)}")

    def activate_window(self, app_path):
        """激活已运行的应用窗口"""
        app_filename = os.path.basename(app_path)
        
        def enum_windows_proc(hwnd, param):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd) != '':
                try:
                    # 使用 win32process 替代 win32gui
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    proc = psutil.Process(pid)
                    if proc.name().lower() == app_filename.lower():
                        if win32gui.IsIconic(hwnd):  # 如果窗口最小化，则恢复
                            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                            win32gui.SetWindowPos(
                                hwnd, 
                                win32con.HWND_TOP, 
                                0, 0, 0, 0, 
                                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                            )
                        else:
                            win32gui.SetWindowPos(
                                hwnd, 
                                win32con.HWND_TOP, 
                                0, 0, 0, 0, 
                                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                            )
                        dock_hwnd = self.winId()
                        if isinstance(dock_hwnd, int):
                            win32gui.SetWindowPos(
                                dock_hwnd, 
                                win32con.HWND_TOPMOST, 
                                0, 0, 0, 0, 
                                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                            )
                        print(f"窗口 {win32gui.GetWindowText(hwnd)} 已成功激活")
                        return False
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            return True

        try:
            win32gui.EnumWindows(enum_windows_proc, 0)
        except Exception as e:
            print(f"枚举窗口时出错: {e}")

    def init_ui(self):
        self.setWindowTitle("应用栏")
        # 修改窗口标志，使用Qt.Tool标志防止被其他窗口遮挡
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 创建中央窗口部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 创建主布局 - 根据窗口位置调整方向
        self.main_layout = QVBoxLayout(central_widget)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(5)

        # 创建一个布局来容纳菜单按钮、应用按钮容器和设置按钮
        self.content_layout = QHBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(10)

        # 添加菜单按钮
        self.menu_button = QPushButton()
        self.menu_button.setFixedSize(60, 60)
        self.menu_button.setIcon(QIcon("more.png"))
        self.menu_button.setIconSize(QSize(48, 48))
        self.menu_button.setStyleSheet("""
            QPushButton {
                border: 2px solid transparent;
                border-radius: 10px;
                background-color: #ECECEC;
            }
            QPushButton:hover {
                background-color: #DADADA;
            }
        """)
        self.menu_button.clicked.connect(self.show_menu)
        self.content_layout.addWidget(self.menu_button)

        # 创建应用按钮容器
        self.app_container = QWidget()
        self.app_layout = QHBoxLayout(self.app_container)
        self.app_layout.setContentsMargins(0, 0, 0, 0)
        self.app_layout.setSpacing(10)  # 设置最小间距为10
        # 设置容器非透明样式
        self.app_container.setStyleSheet("""
            QWidget {
                background-color: #ECECEC;
                border-radius: 10px;
            }
        """)

        # 移除滚动区域，直接将应用按钮容器添加到主布局中
        self.content_layout.addWidget(self.app_container, 1)

        # 添加设置按钮到独立布局中，并右对齐
        settings_layout = QHBoxLayout()
        settings_layout.addStretch()  # 添加伸缩项以右对齐
        self.settings_button = QPushButton()
        self.settings_button.setFixedSize(60, 60)
        self.settings_button.setIcon(QIcon("settings.png"))
        self.settings_button.setIconSize(QSize(48, 48))
        self.settings_button.setStyleSheet("""
            QPushButton {
                border: 2px solid transparent;
                border-radius: 10px;
                background-color: #ECECEC;
            }
            QPushButton:hover {
                background-color: #DADADA;
            }
        """)
        self.settings_button.clicked.connect(self.open_settings)
        settings_layout.addWidget(self.settings_button)
        self.content_layout.addLayout(settings_layout)

        self.main_layout.addLayout(self.content_layout)

        # 设置窗口大小和位置
        self.update_window_position()

        # 设置样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #ECECEC;
                border-radius: 15px;
                border: 1px solid rgba(0, 0, 0, 0.1);
            }
            QPushButton {
                border: none;
                border-radius: 10px;
                background-color: #ECECEC;
            }
            QPushButton:hover {
                background-color: #DADADA;
            }
        """)

    def update_window_position(self):
        """更新窗口位置 - 根据应用数量自动调整宽度"""
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        
        # 计算所需宽度：菜单按钮 + 应用按钮 + 设置按钮 + 间距
        button_count = len(self.apps)
        button_width = 60  # 每个按钮宽度
        button_spacing = 10  # 按钮间间距
        margin = 10  # 边距
        
        # 基础宽度：菜单按钮 + 设置按钮 + 固定边距
        base_width = 60 + 60 + (margin * 2)  # 菜单按钮 + 设置按钮 + 左右边距
        # 应用按钮总宽度：按钮数量 * 按钮宽度 + 间距
        apps_width = button_count * button_width
        if button_count > 0:
            apps_width += (button_count - 1) * button_spacing  # 按钮间间距
        
        # 总宽度，限制最大值为屏幕宽度的90%
        calculated_width = base_width + apps_width
        max_width = int(screen_geometry.width() * 0.9)
        window_width = min(calculated_width, max_width)
        
        window_height = 80
        
        # 居中定位
        x = (screen_geometry.width() - window_width) // 2
        y = screen_geometry.height() - window_height - 10
        
        self.resize(window_width, window_height)
        self.move(x, y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#ECECEC"))
        painter.setPen(QPen(QColor(0, 0, 0, 30), 1))
        painter.drawRoundedRect(self.rect(), 15, 15)

    def create_tray_icon(self):
        # 移除托盘图标功能
        pass

    def add_application(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "选择应用程序", 
            "", 
            "可执行文件 (*.exe);;所有文件 (*)"
        )
        
        if file_path:
            # 提取图标
            icon_path = self.extract_icon(file_path)
            
            # 检查是否已存在相同路径的应用
            for app in self.apps:
                if app['path'] == file_path:
                    QMessageBox.information(self, "提示", "该应用已存在")
                    return
            
            # 获取默认应用名（文件名，不带扩展名）
            default_app_name = os.path.splitext(os.path.basename(file_path))[0]
            
            # 弹出对话框让用户输入应用名
            app_name, ok = QInputDialog.getText(
                self, 
                "输入应用名", 
                "请输入应用名称:", 
                text=default_app_name
            )
            
            # 如果用户取消或输入为空，则使用默认名称
            if not ok or not app_name.strip():
                app_name = default_app_name
            
            # 检查是否有重复的应用名，如果有则添加后缀
            counter = 1
            original_app_name = app_name
            while any(app['name'] == app_name for app in self.apps):
                app_name = f"{original_app_name} ({counter})"
                counter += 1
            
            # 添加应用到列表
            self.apps.append({
                'name': app_name,
                'path': file_path,
                'icon': icon_path
            })
            
            # 保存设置
            self.save_settings()
            
            # 更新界面
            self.update_app_buttons()

    def extract_icon(self, exe_path):
        try:
            # 尝试使用新的图标提取器
            from CatchIco import WindowsIconExtractor, extract_icon as extract_icon_func
            
            # 创建AppData\Local\AppIcon缓存目录
            appdata_local = os.getenv('LOCALAPPDATA')
            cache_dir = os.path.join(appdata_local, 'AppIcon')
            os.makedirs(cache_dir, exist_ok=True)
            
            # 使用缓存目录
            icon_path = os.path.join(cache_dir, f"{os.path.splitext(os.path.basename(exe_path))[0]}.png")
            
            # 使用新的图标提取器
            extractor = WindowsIconExtractor()
            extracted_icon = extractor.extract_file_icon(exe_path, size=64)
            
            if extracted_icon.success and extracted_icon.image:
                # 保存原始图标到临时文件
                temp_icon_path = os.path.join(cache_dir, f"temp_{os.path.basename(icon_path)}")
                extracted_icon.image.save(temp_icon_path)
                
                # 使用 MakeAppIcon 处理图标
                with open(temp_icon_path, "rb") as f:
                    processed_icon_data = compose_on_template(f.read())
                
                # 保存处理后的图标
                with open(icon_path, "wb") as f:
                    f.write(processed_icon_data)
                
                # 删除临时文件
                if os.path.exists(temp_icon_path):
                    os.remove(temp_icon_path)
                
                return icon_path
            else:
                print(f"提取图标失败: {extracted_icon.error}")
        except ImportError:
            print("未找到CatchIco模块")
        except Exception as e:
            print(f"使用图标提取器出错: {e}")

    def update_app_buttons(self):
        # 清空现有按钮
        for i in reversed(range(self.app_layout.count())):
            widget = self.app_layout.itemAt(i).widget()
            if widget is not None:
                widget.setParent(None)
        
        # 重置按钮字典
        self.app_buttons = {}
        
        # 添加应用按钮
        for app in self.apps:
            button = QPushButton()
            button.setFixedSize(60, 60)
            
            # 设置图标
            if app['icon'] and os.path.exists(app['icon']):
                pixmap = QPixmap(app['icon'])
                if not pixmap.isNull():
                    button.setIcon(QIcon(pixmap))
                    button.setIconSize(QSize(48, 48))
            
            # 检查应用是否正在运行
            is_running = app['name'] in self.running_apps
            
            # 设置按钮样式
            self.set_button_style(button, is_running)
            
            # 绑定点击事件 - 如果应用正在运行则激活窗口，否则启动应用
            button.clicked.connect(lambda checked, app_data=app: self.handle_app_click(app_data))
            
            # 绑定右键菜单
            button.setContextMenuPolicy(Qt.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda pos, app_data=app: self.show_app_context_menu(pos, app_data)
            )
            
            # 添加工具提示显示应用名
            button.setToolTip(app['name'])
            
            # 保存按钮引用
            self.app_buttons[app['name']] = button
            
            self.app_layout.addWidget(button)
        
        # 移除应用布局末尾的伸缩项，避免挤压右侧图标
        # 原代码: self.app_layout.addStretch()
        
        # 更新窗口尺寸以适应按钮数量
        self.update_window_position()

    def set_button_style(self, button, is_running):
        """设置按钮样式，根据运行状态"""
        if is_running:
            # 应用运行时显示蓝色边框
            button.setStyleSheet("""
                QPushButton {
                    border: 2px solid #4a86e8;
                    border-radius: 10px;
                    background-color: rgba(74, 134, 232, 100);
                }
                QPushButton:hover {
                    border: 2px solid #4a86e8;
                    background-color: rgba(58, 118, 216, 150);
                }
            """)
        else:
            # 应用未运行时的样式
            button.setStyleSheet("""
                QPushButton {
                    border: 2px solid transparent;
                    border-radius: 10px;
                    background-color: #ECECEC;
                }
                QPushButton:hover {
                    border: 2px solid #4a86e8;
                    background-color: rgba(200, 200, 200, 100);
                }
            """)

    def update_app_button_styles(self):
        """更新所有应用按钮的样式"""
        for app in self.apps:
            app_name = app['name']
            if app_name in self.app_buttons:
                button = self.app_buttons[app_name]
                is_running = app_name in self.running_apps
                self.set_button_style(button, is_running)

    def launch_app(self, path):
        try:
            os.startfile(path)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法启动应用: {str(e)}")

    def show_app_context_menu(self, pos, app_data):
        # 获取触发事件的按钮
        sender = self.sender()
        menu = QMenu()
        
        # 删除应用
        delete_action = QAction("删除应用", self)
        delete_action.triggered.connect(lambda: self.remove_app(app_data))
        menu.addAction(delete_action)
        
        # 修改应用名
        rename_action = QAction("修改应用名", self)
        rename_action.triggered.connect(lambda: self.rename_app(app_data))
        menu.addAction(rename_action)
        
        # 更改图标
        change_icon_action = QAction("更改图标", self)
        change_icon_action.triggered.connect(lambda: self.change_app_icon(app_data))
        menu.addAction(change_icon_action)
        
        # 使用事件位置计算全局位置，而不是通过sender
        if sender:
            menu.exec_(sender.mapToGlobal(pos))
        else:
            # 如果sender为None，则使用鼠标当前位置
            menu.exec_(QCursor.pos())

    def remove_app(self, app_data):
        reply = QMessageBox.question(
            self, 
            "确认", 
            f"确定要删除应用 '{app_data['name']}' 吗？", 
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.apps.remove(app_data)
            # 如果应用正在运行，从运行列表中移除
            if app_data['name'] in self.running_apps:
                del self.running_apps[app_data['name']]
            self.save_settings()
            self.update_app_buttons()

    def rename_app(self, app_data):
        """修改应用名称"""
        current_name = app_data['name']
        new_name, ok = QInputDialog.getText(
            self, 
            "修改应用名", 
            "请输入新的应用名称:", 
            text=current_name
        )
        
        if ok and new_name.strip():
            # 检查是否有重复的应用名，如果有则添加后缀
            counter = 1
            original_new_name = new_name
            while any(app['name'] == new_name for app in self.apps):
                new_name = f"{original_new_name} ({counter})"
                counter += 1
            
            # 更新应用名称
            app_data['name'] = new_name
            
            # 更新按钮引用
            if current_name in self.app_buttons:
                button = self.app_buttons[current_name]
                del self.app_buttons[current_name]
                self.app_buttons[new_name] = button
            
            self.save_settings()
            self.update_app_buttons()

    def change_app_icon(self, app_data):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "选择图标文件", 
            "", 
            "图标文件 (*.ico *.png *.jpg *.bmp);;所有文件 (*)"
        )
        
        if file_path:
            app_data['icon'] = file_path
            self.save_settings()
            self.update_app_buttons()

    def open_settings(self):
        """打开设置对话框"""
        dialog = SettingsDialog(self)
        if dialog.exec_():
            # 由于移除了位置设置，这里不需要更新窗口位置
            pass

    def create_wallpaper_window(self):
        """创建壁纸窗口，层级设置为最底层"""
        self.wallpaper_window = WallpaperWindow()
        # 修改窗口标志，使用正确的Qt标志使窗口在最底层
        self.wallpaper_window.setWindowFlags(Qt.FramelessWindowHint | Qt.X11BypassWindowManagerHint)
        # 使用Windows API设置窗口层级到桌面壁纸层
        import ctypes
        from ctypes import wintypes
        
        # 获取窗口句柄
        hwnd = self.wallpaper_window.winId()
        if isinstance(hwnd, int):
            # 设置窗口层级为最低
            win32gui.SetWindowPos(hwnd, win32con.HWND_BOTTOM, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
        
        self.wallpaper_window.show()
        # 确保Dock窗口在壁纸之上
        dock_hwnd = self.winId()
        if isinstance(dock_hwnd, int):
            win32gui.SetWindowPos(dock_hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
        self.raise_()
        self.show()

    def save_settings(self):
        settings = {
            'apps': self.apps,
            'wallpaper': getattr(self, 'wallpaper_path', '')  # 保存壁纸路径
        }
        
        with open(self.settings_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

    def load_settings(self):
        if os.path.exists(self.settings_file):
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                self.apps = settings.get('apps', [])
                # 添加壁纸路径的加载
                wallpaper_path = settings.get('wallpaper', '')
                if wallpaper_path:
                    self.wallpaper_path = wallpaper_path  # 将壁纸路径保存到实例变量
                # 如果壁纸窗口存在，加载壁纸设置
                if self.wallpaper_window:
                    if wallpaper_path and os.path.exists(wallpaper_path):
                        self.wallpaper_window.set_wallpaper(wallpaper_path)
                    else:
                        # 如果没有壁纸路径或路径不存在，使用默认背景
                        self.wallpaper_window.setStyleSheet("background-color: #36393F;")
        else:
            self.apps = []
        
        # 确保加载设置后更新应用按钮
        self.update_app_buttons()

    def show_menu(self):
        """显示菜单"""
        menu = QMenu()
        
        # 添加应用
        add_app_action = QAction("添加应用", self)
        add_app_action.triggered.connect(self.add_application)
        menu.addAction(add_app_action)
        
        # 退出应用
        exit_action = QAction("退出程序", self)
        exit_action.triggered.connect(self.exit_app)
        menu.addAction(exit_action)
        
        # 重启应用
        restart_action = QAction("重启程序", self)
        restart_action.triggered.connect(self.restart_app)
        menu.addAction(restart_action)
        
        # 显示菜单
        menu.exec_(QCursor.pos())

    def restart_app(self):
        """重启应用程序"""
        os.system("taskkill /f /im explorer.exe")
        os.execl(sys.executable, sys.executable, *sys.argv)

    def exit_app(self):
        os.popen("explorer")
        QApplication.quit()

    def closeEvent(self, event):
        pass

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent  # 保存父窗口引用
        self.setWindowTitle("设置")
        self.setFixedSize(400, 400)  # 增加窗口高度以容纳新设置
        
        layout = QVBoxLayout()
        
        # 说明文本
        info_label = QLabel("壁纸设置：")
        info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(info_label)
        
        # 壁纸设置按钮
        self.wallpaper_button = QPushButton("选择壁纸")
        self.wallpaper_button.clicked.connect(self.select_wallpaper)
        layout.addWidget(self.wallpaper_button)
        
        # 显示当前壁纸路径
        self.current_wallpaper_label = QLabel("当前壁纸: 未设置")
        layout.addWidget(self.current_wallpaper_label)
        self.update_wallpaper_label()
        
        # 重置壁纸按钮
        self.reset_wallpaper_button = QPushButton("重置壁纸")
        self.reset_wallpaper_button.clicked.connect(self.reset_wallpaper)
        layout.addWidget(self.reset_wallpaper_button)
        
        # 保存按钮
        save_button = QPushButton("确定")
        save_button.clicked.connect(self.accept)
        layout.addWidget(save_button)
        
        self.setLayout(layout)
        
        # 添加独立的样式表
        self.setStyleSheet("""
            QDialog {
                background-color: #f0f0f0;
                border-radius: 10px;
            }
            QLabel {
                font-size: 14px;
                color: #333;
                padding: 5px;
            }
            QComboBox {
                padding: 5px;
                border: 1px solid #ccc;
                border-radius: 5px;
                min-height: 30px;
            }
            QComboBox:focus {
                border: 2px solid #4a86e8;
            }
            QPushButton {
                background-color: #4a86e8;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                font-size: 14px;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #3a76d8;
            }
            QPushButton:pressed {
                background-color: #2a66c8;
            }
        """)
    
    def select_wallpaper(self):
        """选择壁纸图片"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "选择壁纸图片", 
            "", 
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif);;所有文件 (*)"
        )
        
        if file_path:
            self.parent.wallpaper_path = file_path  # 保存到父窗口
            # 同时更新父窗口的壁纸路径
            self.parent.wallpaper_path = file_path
            self.update_wallpaper_label()
            # 更新壁纸窗口
            if self.parent.wallpaper_window:
                self.parent.wallpaper_window.set_wallpaper(file_path)
    
    def update_wallpaper_label(self):
        """更新壁纸路径显示"""
        if hasattr(self.parent, 'wallpaper_path') and self.parent.wallpaper_path:
            self.current_wallpaper_label.setText(f"当前壁纸: {os.path.basename(self.parent.wallpaper_path)}")
        else:
            self.current_wallpaper_label.setText("当前壁纸: 未设置")
    
    def reset_wallpaper(self):
        """重置壁纸为默认背景"""
        self.parent.wallpaper_path = ""  # 清除壁纸路径
        self.update_wallpaper_label()
        # 重置壁纸窗口为默认背景
        if self.parent.wallpaper_window:
            self.parent.wallpaper_window.setStyleSheet("background-color: #36393F;")
    
    def accept(self):
        """重写accept方法以保存设置"""
        # 保存壁纸设置到父窗口的配置文件
        if hasattr(self.parent, 'wallpaper_path'):
            self.parent.save_settings()
        super().accept()
    
    def save_settings(self):
        """保存设置"""
        


def main():
    os.system("taskkill /f /im explorer.exe")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 防止关闭主窗口时退出应用
    
    dock = DockApp()
    dock.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()