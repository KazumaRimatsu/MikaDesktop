import json
import os
import sys

import psutil  # 添加进程监控库
import win32con
import win32gui
import win32process  # 新增导入
from PySide6.QtCore import Qt, QSize, QTimer, QRect, QPropertyAnimation, QEasingCurve, QEvent, QPoint
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QCursor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QPushButton, QFileDialog, QVBoxLayout, QHBoxLayout,
                               QMessageBox, QDialog, QLabel, QInputDialog)
# 添加获取任务栏固定程序所需的库
from win32com.shell import shell  # type: ignore

from CustomUI import IconHoverFilter, ContextPopup
from ProcessManager import ProcessManager  # 导入新的进程管理器
# from MakeAppIcon import compose_on_template  # removed duplicate processing, use ProcessManager's extractor
from Wallpaper import WallpaperWindow


class DockApp(QMainWindow):
    def __init__(self):
        super().__init__()
        # 获取当前脚本所在目录
        global script_dir
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.settings_file = os.path.join(script_dir, "apps.json")  # 仅存储应用列表
        self.config_file = os.path.join(script_dir, "settings.json")  # 存储其他设置
        self.wallpaper_window = None  # 添加壁纸窗口引用
        self.wallpaper_path = ""  # 添加壁纸路径属性
        self.running_apps = {}  # 记录正在运行的应用
        self.app_buttons = {}  # 存储按钮引用，用于更新样式
        self.pinned_app_buttons = {}  # 存储固定应用按钮引用
        self.running_app_buttons = {}  # 存储运行中应用按钮引用
        self.icon_hover_filter = IconHoverFilter(self)
        # 新增：用于保存几何动画引用，防止被回收
        self.geometry_anim = None
        # 初始化新的进程管理器
        self.process_manager = ProcessManager()
        
        # 在初始化UI前，先初始化应用列表（修复AttributeError问题）
        self.pinned_apps = []  # 初始化固定应用列表
        self.apps = []  # 初始化用户添加的应用列表
        self.running_apps_list = []  # 初始化运行中应用列表
        
        self.init_ui()
        self.create_tray_icon()
        self.load_settings()  # 在初始化后加载设置
        self.load_pinned_apps()  # 加载任务栏固定的应用
        self.update_app_buttons()
        self.create_wallpaper_window()  # 创建壁纸窗口
        self.setup_process_monitoring()  # 设置进程监控
        
        # 添加应用程序退出事件处理器
        self.destroyed.connect(self.exit_app)

    def eventFilter(self, obj, event):
        """
        过滤键盘事件，屏蔽关闭窗口相关的快捷键
        """
        if event.type() == QEvent.KeyPress:
            key = event.key()
            modifiers = event.modifiers()
            
            # 屏蔽常见地关闭窗口快捷键组合
            if (
                (modifiers == Qt.ControlModifier and key == Qt.Key_Q) or  # Ctrl+Q
                (modifiers == Qt.ControlModifier and key == Qt.Key_W) or  # Ctrl+W
                (modifiers == Qt.AltModifier and key == Qt.Key_F4) or     # Alt+F4
                (modifiers == Qt.ControlModifier and modifiers == Qt.ShiftModifier and key == Qt.Key_W) or  # Ctrl+Shift+W
                (key == Qt.Key_Escape)  # Escape
            ):
                print(f"阻止快捷键: {modifiers.name() if modifiers else 'No Modifiers'}+{event.text() if event.text() else key}")
                return True  # 表示事件已被处理，不再传递
        
        # 其他事件按正常流程处理
        return super().eventFilter(obj, event)

    def load_pinned_apps(self):
        """获取Windows任务栏上固定的应用程序"""
        try:
            # 方法1: 从任务栏固定的应用路径获取
            pinned_apps = self.get_pinned_apps_from_taskbar()
            self.pinned_apps = pinned_apps
        except Exception as e:
            print(f"获取固定应用时出错: {e}")
            self.pinned_apps = []

    def get_pinned_apps_from_taskbar(self):
        """从任务栏固定的应用程序路径获取应用"""
        pinned_apps = []
        try:
            # Windows 10/11 任务栏固定应用的位置
            appdata = os.getenv('APPDATA')
            pinned_dir = os.path.join(appdata, 'Microsoft', 'Internet Explorer', 'Quick Launch', 'User Pinned', 'TaskBar')
            
            if os.path.exists(pinned_dir):
                for item in os.listdir(pinned_dir):
                    if item.endswith('.lnk'):
                        shortcut_path = os.path.join(pinned_dir, item)
                        app_info = self.get_app_info_from_shortcut(shortcut_path)
                        if app_info:
                            # 检查是否已存在，避免重复
                            if not any(app['name'] == app_info['name'] for app in pinned_apps):
                                pinned_apps.append(app_info)
        
        except Exception as e:
            print(f"获取任务栏固定应用失败: {e}")
            # 如果无法获取固定应用，则返回空列表
            return []
            
        return pinned_apps

    def get_app_info_from_shortcut(self, shortcut_path):
        """从快捷方式获取应用信息"""
        try:
            import pythoncom
            
            # 使用shell接口获取快捷方式信息
            shortcut = pythoncom.CoCreateInstance(
                shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink
            )
            persist_file = shortcut.QueryInterface(pythoncom.IID_IPersistFile)
            persist_file.Load(shortcut_path)
            
            # 获取目标路径
            target_path = shortcut.GetPath(shell.SLGP_RAWPATH)[0]
            if not target_path or not os.path.exists(target_path):
                return None
                
            # 获取应用名称（从快捷方式名称或可执行文件名）
            app_name = os.path.splitext(os.path.basename(shortcut_path))[0]
            if not app_name:
                app_name = os.path.splitext(os.path.basename(target_path))[0]
                
            # 获取图标路径（如果存在）
            icon_path, icon_index = shortcut.GetIconLocation()
            if not icon_path or not os.path.exists(icon_path):
                icon_path = None
                
            # 提取图标（使用 ProcessManager 提供的统一接口）
            if not icon_path:
                icon_path = self.process_manager.extract_icon(target_path)
            else:
                # 如果快捷方式指定了图标，但路径不存在，尝试从目标提取
                if not os.path.exists(icon_path):
                    icon_path = self.process_manager.extract_icon(target_path)
            
            return {
                'name': app_name,
                'path': target_path,
                'icon': icon_path,
                'is_pinned': True  # 标记为固定应用
            }
        except Exception as e:
            print(f"解析快捷方式 {shortcut_path} 失败: {e}")
            return None

    def setup_process_monitoring(self):
        """设置定时器来监控进程状态"""
        self.process_timer = QTimer()
        self.process_timer.timeout.connect(self.check_running_processes)
        self.process_timer.start(1100)

    def check_running_processes(self):
        """检查所有应用的运行状态 - 改进版本，只考虑有窗口的应用"""
        try:
            # 创建当前运行应用的快照
            current_running = {}
            
            # 检查固定应用
            for app in self.pinned_apps:
                app_name = app['name']
                app_path = app['path']
                
                # 使用进程管理器检查进程状态（仅当有可见窗口时）
                is_running = self.process_manager.is_process_running(app_path)
                if is_running:
                    current_running[app_name] = app_path
        
            # 检查用户添加的应用
            for app in self.apps:
                app_name = app['name']
                app_path = app['path']
                
                # 使用进程管理器检查进程状态（仅当有可见窗口时）
                is_running = self.process_manager.is_process_running(app_path)
                if is_running:
                    current_running[app_name] = app_path
        
            # 检查系统中所有正在运行的进程，找出未添加但运行的应用
            # 使用进程管理器获取所有正在运行的进程
            all_apps_paths = [app['path'] for app in self.pinned_apps + self.apps]
            running_processes = self.process_manager.get_running_processes(all_apps_paths)
            
            # 更新运行中应用列表
            self.running_apps_list = list(running_processes.values())
            
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
            
            # 更新所有类型的应用按钮
            for app_name in apps_to_update:
                button = self.get_app_button(app_name)
                if button:
                    is_running = app_name in current_running
                    self.set_button_style(button, is_running)
                    print(f"应用 {app_name} 状态更新: {'运行中' if is_running else '已关闭'}")
            
            # 更新运行中应用按钮
            for app_info in self.running_apps_list:
                app_name = app_info['name']
                if app_name in self.running_app_buttons:
                    button = self.running_app_buttons[app_name]
                    is_running = self.process_manager.is_process_running(app_info['path'])
                    self.set_button_style(button, is_running)
            
            # 更新运行应用记录
            self.running_apps = current_running
            
            # 更新界面
            self.update_app_buttons()

            # 根据当前运行的应用（仅限 Dock 中的应用）调整 Dock 的层级，
            # 以避免遮挡全屏程序（例如全屏视频/浏览器）
            try:
                self.adjust_window_stacking()
            except Exception as e:
                print(f"调整窗口层级时出错: {e}")
            
        except Exception as e:
            print(f"检查运行进程时出错: {e}")

    def adjust_window_stacking(self):
        """根据 Dock 中的应用是否有全屏窗口灵活调整 Dock 的层级"""
        try:
            # 收集 Dock 中关注的应用路径（去重）
            all_paths = []
            for app in (self.pinned_apps + self.apps + self.running_apps_list):
                p = app.get('path') if isinstance(app, dict) else None
                if p:
                    all_paths.append(p)
            # 如果其中任意应用处于全屏状态，则将 Dock 设为非顶层，避免遮挡
            if self.process_manager.any_apps_fullscreen(all_paths):
                dock_hwnd = int(self.winId())
                win32gui.SetWindowPos(
                    dock_hwnd,
                    win32con.HWND_NOTOPMOST,
                    0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                )
            else:
                dock_hwnd = int(self.winId())
                win32gui.SetWindowPos(
                    dock_hwnd,
                    win32con.HWND_TOPMOST,
                    0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                )
        except Exception as e:
            print(f"adjust_window_stacking error: {e}")

    def handle_app_click(self, app_data):
        """处理应用按钮点击事件 - 添加状态立即更新"""
        app_name = app_data['name']
        app_path = app_data['path']
        
        # 使用进程管理器检查应用是否正在运行
        if app_name in self.running_apps or self.process_manager.is_process_running(app_path):
            # 如果正在运行，激活窗口
            self.activate_window(app_path)
        else:
            # 如果未运行，启动应用
            try:
                # 启动前立即更新状态（避免启动延迟导致的显示问题）
                self.running_apps[app_name] = app_path
                button = self.get_app_button(app_name)
                if button:
                    self.set_button_style(button, True)
                
                # 启动应用
                self.launch_app(app_path)
                
                # 延迟检查一次确保状态正确
                QTimer.singleShot(1000, self.check_running_processes)
                
            except Exception as e:
                # 如果启动失败，回滚状态
                if app_name in self.running_apps:
                    del self.running_apps[app_name]
                button = self.get_app_button(app_name)
                if button:
                    self.set_button_style(button, False)
                QMessageBox.critical(self, "错误", f"无法启动应用: {str(e)}")

    def get_app_button(self, app_name):
        """获取指定应用名称的按钮引用，适用于所有类型的应用"""
        if app_name in self.app_buttons:
            return self.app_buttons[app_name]
        elif app_name in self.pinned_app_buttons:
            return self.pinned_app_buttons[app_name]
        elif app_name in self.running_app_buttons:
            return self.running_app_buttons[app_name]
        return None

    def add_running_app_to_dock(self, app_data):
        """将运行中的应用添加到程序栏"""
        # 检查是否已存在相同路径的应用
        for app in self.apps:
            if app['path'] == app_data['path']:
                QMessageBox.information(self, "提示", "该应用已存在")
                return
        
        # 检查是否与固定应用重复
        for app in self.pinned_apps:
            if app['path'] == app_data['path']:
                QMessageBox.information(self, "提示", "该应用已在固定列表中")
                return
        
        # 检查是否与运行中应用重复（避免重复添加）
        for app in self.running_apps_list:
            if app['path'] == app_data['path']:
                # 从运行中应用列表中移除，因为它将被添加到用户应用列表
                self.running_apps_list.remove(app)
                break
        
        # 自动从文件路径获取应用名（快捷方式则获取快捷方式名称）
        file_path = app_data['path']
        if file_path.endswith('.lnk'):
            # 如果是快捷方式，尝试获取快捷方式的实际名称
            app_name = os.path.splitext(os.path.basename(file_path))[0]
        else:
            # 如果是可执行文件，使用文件名作为应用名
            app_name = os.path.splitext(os.path.basename(file_path))[0]
        
        # 检查是否有重复的应用名，如果有则添加后缀
        counter = 1
        original_app_name = app_name
        while any(app['name'] == app_name for app in self.apps):
            app_name = f"{original_app_name} ({counter})"
            counter += 1
        
        # 添加应用到用户应用列表
        new_app = {
            'name': app_name,
            'path': app_data['path'],
            'icon': app_data['icon']
        }
        self.apps.append(new_app)
        
        # 保存设置
        self.save_settings()
        
        # 更新界面
        self.update_app_buttons()

    def get_app_visible_windows(self, app_path):
        """获取应用的所有可见窗口，使用进程管理器的方法"""
        return self.process_manager.get_app_visible_windows(app_path)

    def activate_window(self, app_path):
        """激活已运行的应用窗口"""
        # 获取应用的所有可见窗口
        visible_windows = self.process_manager.get_app_visible_windows(app_path)
        
        if visible_windows:
            # 如果有多个窗口，激活第一个窗口
            hwnd, title = visible_windows[0]
            try:
                if win32gui.IsIconic(hwnd):  # 如果窗口最小化，则恢复
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.SetWindowPos(
                        hwnd, 
                        win32con.HWND_TOP, 
                        0, 0, 0, 0, 
                        win32con.SW_NOMOVE | win32con.SWP_NOSIZE
                    )
                else:
                    win32gui.SetWindowPos(
                        hwnd, 
                        win32con.HWND_TOP, 
                        0, 0, 0, 0, 
                        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                    )
                
                # 确保Dock窗口保持在顶层
                dock_hwnd = int(self.winId())  # 确保转换为int类型
                win32gui.SetWindowPos(
                    dock_hwnd, 
                    win32con.HWND_TOPMOST,  # 修改：改为TOPMOST确保始终在最顶层
                    0, 0, 0, 0, 
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                )
                print(f"窗口 {title} 已成功激活，Dock保持在顶层")
            except Exception as e:
                print(f"激活窗口时出错: {e}")
        else:
            print(f"未找到应用 {app_path} 的可见窗口")

    def activate_specific_window(self, hwnd):
        """激活指定的窗口句柄"""
        try:
            if win32gui.IsIconic(hwnd):  # 如果窗口最小化，则恢复
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetWindowPos(
                    hwnd, 
                    win32con.HWND_TOP, 
                    0, 0, 0, 0, 
                    win32con.SW_NOMOVE | win32con.SWP_NOSIZE
                )
            else:
                win32gui.SetWindowPos(
                    hwnd, 
                    win32con.HWND_TOP, 
                    0, 0, 0, 0, 
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                )
            
            # 确保Dock窗口保持在顶层
            dock_hwnd = int(self.winId())  # 确保转换为int类型
            win32gui.SetWindowPos(
                dock_hwnd, 
                win32con.HWND_TOPMOST,  # 修改：改为TOPMOST确保始终在最顶层
                0, 0, 0, 0, 
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
            )
            print(f"窗口 {win32gui.GetWindowText(hwnd)} 已成功激活，Dock保持在顶层")
        except Exception as e:
            print(f"激活窗口时出错: {e}")

    def init_ui(self):
        self.setWindowTitle("Dock")
        # 修改窗口标志，使用Qt.Tool标志防止被其他窗口遮挡
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        #self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_AlwaysStackOnTop)  # 确保始终在顶层

        # 安装事件过滤器，屏蔽关闭快捷键
        self.installEventFilter(self)

        # 创建中央窗口部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 创建主布局 - 根据窗口位置调整方向
        self.main_layout = QVBoxLayout(central_widget)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(5)

        # 创建一个布局来容纳菜单按钮、固定应用按钮容器、应用按钮容器和设置按钮
        self.content_layout = QHBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(10)

        # 添加菜单按钮
        self.menu_button = QPushButton()
        self.menu_button.setFixedSize(60, 60)
        self.menu_button.setIcon(QIcon(os.path.join(script_dir,"more.png")))
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

        # 创建固定应用按钮容器
        self.pinned_app_container = QWidget()
        self.pinned_app_layout = QHBoxLayout(self.pinned_app_container)
        self.pinned_app_layout.setContentsMargins(0, 0, 0, 0)
        self.pinned_app_layout.setSpacing(10)  # 设置最小间距为10
        # 设置容器非透明样式
        self.pinned_app_container.setStyleSheet("""
            QWidget {
                background-color: #ECECEC;
                border-radius: 10px;
            }
        """)
        # 初始隐藏固定应用容器，直到有固定应用时才显示
        self.pinned_app_container.setVisible(len(self.pinned_apps) > 0)

        # 创建分隔符
        self.separator = QWidget()
        self.separator.setFixedWidth(2)  # 设置分隔符宽度为2像素
        self.separator.setStyleSheet("""
            QWidget {
                background-color: #CCCCCC;  /* 设置分隔符颜色 */
                border-radius: 1px;
            }
        """)
        
        # 创建用户添加应用按钮容器
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

        # 创建运行中应用的分隔符
        self.running_separator = QWidget()
        self.running_separator.setFixedWidth(2)  # 设置分隔符宽度为2像素
        self.running_separator.setStyleSheet("""
            QWidget {
                background-color: #CCCCCC;  /* 设置分隔符颜色 */
                border-radius: 1px;
            }
        """)

        # 创建运行中应用按钮容器
        self.running_app_container = QWidget()
        self.running_app_layout = QHBoxLayout(self.running_app_container)
        self.running_app_layout.setContentsMargins(0, 0, 0, 0)
        self.running_app_layout.setSpacing(10)  # 设置最小间距为10
        # 设置容器非透明样式
        self.running_app_container.setStyleSheet("""
            QWidget {
                background-color: #ECECEC;
                border-radius: 10px;
            }
        """)

        # 将固定应用容器、分隔符和用户应用容器添加到内容布局中
        self.content_layout.addWidget(self.pinned_app_container)
        self.content_layout.addWidget(self.separator)  # 添加分隔符
        self.content_layout.addWidget(self.app_container, 1)  # 用户应用容器可扩展
        self.content_layout.addWidget(self.running_separator)  # 添加运行应用分隔符
        self.content_layout.addWidget(self.running_app_container)  # 运行中应用容器

        # 添加设置按钮到独立布局中，并右对齐
        settings_layout = QHBoxLayout()
        settings_layout.addStretch()  # 添加伸缩项以右对齐
        self.settings_button = QPushButton()
        self.settings_button.setFixedSize(60, 60)
        self.settings_button.setIcon(QIcon(os.path.join(script_dir,"settings.png")))
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
        # 初始化图标悬浮提示（必须在 UI 创建后调用）
        self.init_tooltip()

    def update_window_position(self):
        """更新窗口位置 - 根据应用数量自动调整宽度（使用动画平滑过渡）"""
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        
        # 计算所需宽度：菜单按钮 + 固定应用按钮 + 分隔符 + 用户应用按钮 + 运行应用分隔符 + 运行应用按钮 + 设置按钮 + 间距
        pinned_button_count = len(self.pinned_apps)
        user_button_count = len(self.apps)
        running_button_count = len(self.running_apps_list)
        button_width = 60  # 每个按钮宽度
        button_spacing = 10  # 按钮间间距
        separator_width = 2  # 分隔符宽度
        margin = 10  # 边距
        
        # 基础宽度：菜单按钮 + 设置按钮 + 边距
        base_width = 60 + 60 + (margin * 2)  # 菜单按钮 + 设置按钮 + 左右边距
        # 固定应用按钮总宽度：按钮数量 * 按钮宽度 + 间距
        pinned_apps_width = pinned_button_count * button_width
        if pinned_button_count > 0:
            pinned_apps_width += (pinned_button_count - 1) * button_spacing  # 按钮间间距
        # 用户应用按钮总宽度：按钮数量 * 按钮宽度 + 间距
        user_apps_width = user_button_count * button_width
        if user_button_count > 0:
            user_apps_width += (user_button_count - 1) * button_spacing  # 按钮间间距
        # 运行中应用按钮总宽度：按钮数量 * 按钮宽度 + 间距
        running_apps_width = running_button_count * button_width
        if running_button_count > 0:
            running_apps_width += (running_button_count - 1) * button_spacing  # 按钮间间距
        
        # 加上两个分隔符宽度
        total_width = base_width + pinned_apps_width + separator_width + user_apps_width + separator_width + running_apps_width
        max_width = int(screen_geometry.width() * 0.9)
        window_width = min(total_width, max_width)
        
        window_height = 80
        
        # 居中定位
        x = (screen_geometry.width() - window_width) // 2
        y = screen_geometry.height() - window_height - 10
        
        target_rect = QRect(x, y, window_width, window_height)
        
        # 如果窗口尚未显示，直接设置几何（避免首次不可见时的动画问题）
        if not self.isVisible():
            self.setGeometry(target_rect)
            return
        
        # 如果当前几何与目标相同，不重复动画
        current_rect = self.geometry()
        if current_rect == target_rect:
            return
        
        # 停止并丢弃已有动画（如果存在）
        if self.geometry_anim is not None and isinstance(self.geometry_anim, QPropertyAnimation):
            try:
                self.geometry_anim.stop()
            except:
                pass
        
        # 创建新动画并保存引用，避免被回收
        self.geometry_anim = QPropertyAnimation(self, b"geometry", self)
        self.geometry_anim.setDuration(220)  # 毫秒，短时平滑过渡
        self.geometry_anim.setStartValue(current_rect)
        self.geometry_anim.setEndValue(target_rect)
        self.geometry_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.geometry_anim.start()

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
            "所有文件 (*)"
        )
        
        if file_path:
            # 提取图标（使用 ProcessManager）
            icon_path = self.process_manager.extract_icon(file_path)
            
            # 检查是否已存在相同路径的应用
            for app in self.apps:
                if app['path'] == file_path:
                    QMessageBox.information(self, "提示", "该应用已存在")
                    return
            
            # 检查是否与固定应用重复
            for app in self.pinned_apps:
                if app['path'] == file_path:
                    QMessageBox.information(self, "提示", "该应用已在固定列表中")
                    return
            
            # 自动从文件路径获取应用名（快捷方式则获取快捷方式名称）
            if file_path.endswith('.lnk'):
                # 如果是快捷方式，尝试获取快捷方式的实际名称
                app_name = os.path.splitext(os.path.basename(file_path))[0]
            else:
                # 如果是可执行文件，使用文件名作为应用名
                app_name = os.path.splitext(os.path.basename(file_path))[0]
            
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
            return self.process_manager.extract_icon(exe_path)
        except Exception as e:
            print(f"提取图标时出错: {e}")
            return None

    def init_tooltip(self):
        from PySide6.QtWidgets import QLabel
        # 使用顶层无父窗口的 QLabel 作为 tooltip，避免构造参数差异导致异常
        self.tooltip = QLabel("", None)
        self.tooltip.setObjectName("DockIconTooltip")
        flags = Qt.ToolTip | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint
        self.tooltip.setWindowFlags(flags)
        self.tooltip.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.tooltip.setStyleSheet("""
            QLabel#DockIconTooltip {
                color: white;
                font-size: 12px;
                background-color: #4a86e8;
                border-radius: 5px;
                padding: 8px 16px;
            }
        """)
        self.tooltip.hide()

    def show_icon_tooltip(self, button, text):
        if not text:
            return
        self.tooltip.setText(text)
        self.tooltip.adjustSize()
        self.update_icon_tooltip_position(button)
        self.tooltip.show()

    def hide_icon_tooltip(self):
        if hasattr(self, 'tooltip') and self.tooltip.isVisible():
            self.tooltip.hide()

    def update_icon_tooltip_position(self, button):
        # 将 tooltip 居中放在图标上方，距离 8 像素
        if not hasattr(self, 'tooltip') or not button:
            return
        global_center = button.mapToGlobal(QPoint(button.width()//2, 0))
        tw = self.tooltip.width()
        th = self.tooltip.height()
        x = global_center.x() - tw//2
        y = global_center.y() - th - 8
        # 防止超出屏幕左/右边界（基本处理）
        screen_rect = QApplication.primaryScreen().availableGeometry()
        if x < screen_rect.left():
            x = screen_rect.left() + 4
        if x + tw > screen_rect.right():
            x = screen_rect.right() - tw - 4
        self.tooltip.move(x, y)

    def update_app_buttons(self):
        # 清空现有固定应用按钮
        for i in reversed(range(self.pinned_app_layout.count())):
            widget = self.pinned_app_layout.itemAt(i).widget()
            if widget is not None:
                widget.setParent(None)
        
        # 清空现有用户应用按钮
        for i in reversed(range(self.app_layout.count())):
            widget = self.app_layout.itemAt(i).widget()
            if widget is not None:
                widget.setParent(None)
        
        # 清空现有运行中应用按钮
        for i in reversed(range(self.running_app_layout.count())):
            widget = self.running_app_layout.itemAt(i).widget()
            if widget is not None:
                widget.setParent(None)
        
        # 重置按钮字典
        self.pinned_app_buttons = {}
        self.app_buttons = {}
        self.running_app_buttons = {}
        
        # 添加固定应用按钮
        for app in self.pinned_apps:
            # Ensure 'icon' key exists
            if 'icon' not in app:
                app['icon'] = self.process_manager.extract_icon(app.get('path', '')) or ''
            
            button = QPushButton()
            button.setFixedSize(60, 60)
            # 启用鼠标追踪以确保 MouseMove 可用
            button.setMouseTracking(True)
            
            # 设置图标（安全访问）
            icon_path = app.get('icon') or ''
            if icon_path and os.path.exists(icon_path):
                pixmap = QPixmap(icon_path)
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
            # 显式传入触发的 button，避免 lambda 包装导致无法正确获取 sender
            button.customContextMenuRequested.connect(
                lambda pos, app_data=app, btn=button: self.show_app_context_menu(pos, app_data, btn)
            )
            
            # 添加工具提示显示应用名
            button.setToolTip(app['name'])
            
            # 安装悬浮事件过滤器以显示自定义 tooltip
            button.setAttribute(Qt.WA_Hover, True)
            button.setMouseTracking(True)
            button.installEventFilter(self.icon_hover_filter)
            
            # 保存按钮引用
            self.pinned_app_buttons[app['name']] = button
            
            self.pinned_app_layout.addWidget(button)
        
        # 显示固定应用容器（如果有固定应用）
        self.pinned_app_container.setVisible(len(self.pinned_apps) > 0)
        
        # 添加用户添加的应用按钮
        for app in self.apps:
            # Ensure 'icon' key exists
            if 'icon' not in app:
                app['icon'] = self.process_manager.extract_icon(app.get('path', '')) or ''
            
            button = QPushButton()
            button.setFixedSize(60, 60)
            button.setMouseTracking(True)
            
            # 设置图标（安全访问）
            icon_path = app.get('icon') or ''
            if icon_path and os.path.exists(icon_path):
                pixmap = QPixmap(icon_path)
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
                lambda pos, app_data=app, btn=button: self.show_app_context_menu(pos, app_data, btn)
            )
            
            # 添加工具提示显示应用名
            button.setToolTip(app['name'])
            
            # 安装悬浮事件过滤器以显示自定义 tooltip
            button.setAttribute(Qt.WA_Hover, True)
            button.setMouseTracking(True)
            button.installEventFilter(self.icon_hover_filter)
            
            # 保存按钮引用
            self.app_buttons[app['name']] = button
            
            self.app_layout.addWidget(button)
        
        # 添加运行中的应用按钮（未添加到用户列表的）
        for app in self.running_apps_list:
            # Ensure 'icon' key exists
            if 'icon' not in app:
                app['icon'] = self.process_manager.extract_icon(app.get('path', '')) or ''
            
            button = QPushButton()
            button.setFixedSize(60, 60)
            button.setMouseTracking(True)
            
            # 设置图标（安全访问）
            icon_path = app.get('icon') or ''
            if icon_path and os.path.exists(icon_path):
                pixmap = QPixmap(icon_path)
                if not pixmap.isNull():
                    button.setIcon(QIcon(pixmap))
                    button.setIconSize(QSize(48, 48))
            
            # 检查应用是否正在运行（使用 ProcessManager）
            is_running = self.process_manager.is_process_running(app['path'])
            
            # 设置按钮样式
            self.set_button_style(button, is_running)
            
            # 绑定点击事件 - 激活窗口或启动应用
            button.clicked.connect(lambda checked, app_data=app: self.handle_app_click(app_data))
            
            # 绑定右键菜单
            button.setContextMenuPolicy(Qt.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda pos, app_data=app, btn=button: self.show_app_context_menu(pos, app_data, btn)
            )
            
            # 添加工具提示显示应用名
            button.setToolTip(app['name'])
            
            # 安装悬浮事件过滤器以显示自定义 tooltip
            button.setAttribute(Qt.WA_Hover, True)
            button.setMouseTracking(True)
            button.installEventFilter(self.icon_hover_filter)
            
            # 保存按钮引用
            self.running_app_buttons[app['name']] = button
            
            self.running_app_layout.addWidget(button)
        
        # 显示运行中应用容器（如果有运行中应用）
        self.running_app_container.setVisible(len(self.running_apps_list) > 0)
        
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
        # 统一处理所有类型的应用
        all_apps_with_containers = [
            (self.pinned_apps, self.pinned_app_buttons),
            (self.apps, self.app_buttons),
            (self.running_apps_list, self.running_app_buttons)
        ]
        
        for app_list, button_dict in all_apps_with_containers:
            for app in app_list:
                app_name = app['name']
                if app_name in button_dict:
                    button = button_dict[app_name]
                    # 根据应用类型检查运行状态
                    if app_list == self.running_apps_list:
                        # 对于运行中应用，检查实际进程状态
                        is_running = self.process_manager.is_process_running(app['path'])
                    else:
                        # 对于其他应用，检查是否在运行列表中
                        is_running = app_name in self.running_apps
                    self.set_button_style(button, is_running)

    def launch_app(self, path):
        try:
            os.startfile(path)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法启动应用: {str(e)}")

    def terminate_app_process(self, app_data):
        """终止应用进程"""
        # 使用进程管理器终止应用
        self.process_manager.terminate_app_process(app_data['path'])
        
        # 延迟检查进程状态
        QTimer.singleShot(1000, self.check_running_processes)

    def show_app_context_menu(self, pos, app_data, sender=None):
        # sender 必须显式传入（来自 lambda），用于精确计算图标全局矩形
        try:
            self.hide_icon_tooltip()
        except:
            pass

        # 构建动作列表
        actions = []
        is_running_app = any(app['path'] == app_data['path'] for app in self.running_apps_list)
        try:
            is_running = self.process_manager.is_process_running(app_data.get('path', ''))
        except Exception:
            is_running = False
        visible_windows = self.process_manager.get_app_visible_windows(app_data.get('path', ''))
        if is_running:
            if visible_windows:
                for hwnd, title in visible_windows:
                    label = f"{title[:40]}{'...' if len(title) > 40 else ''}"
                    callback = lambda h=hwnd: self.activate_specific_window(h)
                    actions.append((label, callback, True))
            else:
                actions.append(("没有可用窗口", None, False))
        if is_running_app:
            actions.append(("添加到程序栏", lambda: self.add_running_app_to_dock(app_data), True))
            actions.append((app_data['name'], lambda: self.handle_app_click(app_data), True))
        elif not app_data.get('is_pinned', False):
            actions.append(("删除应用", lambda: (self.remove_app(app_data)), True))
            actions.append(("修改应用名", lambda: (self.rename_app(app_data)), True))
            actions.append(("更改图标", lambda: (self.change_app_icon(app_data)), True))
        else:
            actions.append((app_data['name'], lambda: self.launch_app(app_data['path']), True))
        if is_running:
            if visible_windows:
                actions.append(("关闭窗口", lambda: self.close_app_window(app_data), True))
            actions.append(("关闭应用", lambda: self.terminate_app_process(app_data), True))

        # 创建并显示自定义弹窗，使用传入的 sender 作为锚点（始终居中在图标上方）
        popup = ContextPopup(actions, parent=None)
        popup.show_at_position(pos, sender)

    def close_app_window(self, app_data):
        """关闭应用窗口"""
        app_path = app_data['path']
        app_filename = os.path.basename(app_path)
        
        def enum_windows_proc(hwnd, param):
            if win32gui.IsWindowVisible(hwnd):
                try:
                    # 获取窗口的进程ID
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    proc = psutil.Process(pid)
                    
                    # 检查进程名称是否匹配
                    if proc.name().lower() == app_filename.lower():
                        # 检查窗口标题是否为空（避免关闭系统窗口）
                        window_title = win32gui.GetWindowText(hwnd)
                        if window_title.strip() != '':
                            # 尝试优雅地关闭窗口
                            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                            print(f"已发送关闭命令到窗口: {window_title}")
                            return False  # 找到并处理了窗口，停止枚举
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    return True  # 继续枚举其他窗口

        try:
            win32gui.EnumWindows(enum_windows_proc, 0)
            # 延迟检查进程状态
            QTimer.singleShot(1000, self.check_running_processes)
        except Exception as e:
            print(f"关闭窗口时出错: {e}")

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
            "输入应用名称:", 
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
        if dialog.exec():
            # 由于移除了位置设置，这里不需要更新窗口位置
            pass

    def create_wallpaper_window(self):
        """创建壁纸窗口，层级设置为最底层"""
        self.wallpaper_window = WallpaperWindow(image_path=self.wallpaper_path)
        # 安装事件过滤器到壁纸窗口，屏蔽关闭快捷键
        if self.wallpaper_window:
            self.wallpaper_window.installEventFilter(self.wallpaper_window)
            # 显示壁纸窗口并置于底层
            self.wallpaper_window.show()
            # 调整层级关系，确保壁纸在最底层
            self.wallpaper_window.lower()
        print(self.wallpaper_path)

    def load_settings(self):
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    self.apps = settings.get('apps', [])
                    # 添加壁纸路径的加载
                    wallpaper_path = settings.get('wallpaper', '')
                    if wallpaper_path:
                        # 确保壁纸路径是绝对路径
                        if not os.path.isabs(wallpaper_path):
                            wallpaper_path = os.path.join(os.path.dirname(self.settings_file), wallpaper_path)
                        self.wallpaper_path = wallpaper_path  # 将壁纸路径保存到实例变量
                    # 如果壁纸窗口存在，加载壁纸设置
                    if self.wallpaper_window:
                        if wallpaper_path and os.path.exists(wallpaper_path):
                            self.wallpaper_window.set_wallpaper(wallpaper_path)
                        else:
                            if wallpaper_path:
                                print(f"警告: 壁纸文件 {wallpaper_path} 不存在")
                            # 如果没有壁纸路径或路径不存在，使用默认背景
                            self.wallpaper_window.setStyleSheet("background-color: #36393F;")
            else:
                self.apps = []
                print(f"配置文件 {self.settings_file} 不存在，将使用默认设置")
            
            # 确保加载设置后更新应用按钮
            self.update_app_buttons()
        except Exception as e:
            print(f"加载配置文件 {self.settings_file} 时出错: {e}")
            import traceback
            traceback.print_exc()
            self.apps = []  # 出错时使用默认设置
            self.wallpaper_path = ""
            if self.wallpaper_window:
                self.wallpaper_window.setStyleSheet("background-color: #36393F;")
            self.update_app_buttons()

    def save_settings(self):
        try:
            settings = {
                'apps': self.apps,
                'wallpaper': getattr(self, 'wallpaper_path', '')  # 保存壁纸路径
            }
            
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            print(f"配置已成功保存到 {self.settings_file}")
        except Exception as e:
            print(f"保存配置文件 {self.settings_file} 时出错: {e}")
            import traceback
            traceback.print_exc()

    def show_menu(self):
        """显示菜单"""
        # 构建动作列表
        actions = [
            ("添加应用到程序栏", self.add_application, True),
            ("退出", self.exit_app, True),
        ]
        
        # 创建并显示自定义弹窗
        popup = ContextPopup(actions, parent=None)
        popup.show_at_position(QCursor.pos(), None)

    def exit_app(self):
        # 重启explorer.exe
        os.popen("explorer")
        sys.exit(0)

    def closeEvent(self, event):
        event.ignore()  # 忽略关闭事件，因为应用程序不应该真正退出


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
            # 确保保存绝对路径
            absolute_path = os.path.abspath(file_path)
            self.parent.wallpaper_path = absolute_path  # 保存到父窗口
            self.update_wallpaper_label()
            # 更新壁纸窗口
            if self.parent.wallpaper_window:
                self.parent.wallpaper_window.set_wallpaper(absolute_path)

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
    app.setQuitOnLastWindowClosed(False)  # 防止关闭主窗口时退出
    
    dock = DockApp()
    dock.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()