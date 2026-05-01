import gc
import os
import sys
from typing import Dict, List, Any
import subprocess

import psutil
import win32con
import win32gui
import win32process
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QSize, QTimer, QRect, QEvent, QPoint
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QPushButton, QFileDialog, QVBoxLayout, QHBoxLayout,
                               QDialog, QLabel, QInputDialog, QPlainTextEdit)
# 添加获取任务栏固定程序所需的库
from win32com.shell import shell  # type: ignore
from core.custom_ui import IconHoverFilter, ContextPopup, ShutdownDialog
from core.process_manager import ProcessManager
import core.skills.sys32 as sys32
import core.log_maker as log_maker
import core.config_manager as Config
import core.notification_system as notification_system
import core.settings as settings

from core.threads import manager

VERSION = "0.0.0"

log = log_maker.logger()
#log.enable_debug()
log.disable_debug()


# 常量定义
class DockConstants:
    """Dock应用常量定义"""
    BUTTON_SIZE = 60
    ICON_SIZE = 48
    BORDER_RADIUS = 16
    WINDOW_BORDER_RADIUS = 18
    BUTTON_SPACING = 10
    WINDOW_MARGIN = 0
    SEPARATOR_WIDTH = 2
    PROCESS_CHECK_INTERVAL = 1400  # 进程检查间隔（毫秒）
    
    # 颜色常量
    COLOR_BACKGROUND = "#ECECEC"
    COLOR_HOVER = "#e9e1d4"
    COLOR_BORDER_ACTIVE = "#52d1ff"
    COLOR_BORDER_INACTIVE = "#555555"
    COLOR_BG_ACTIVE = "#008566"
    COLOR_BG_HOVER_ACTIVE = "#00e6eb"
    COLOR_BG_HOVER_INACTIVE = "#65E2D2"
    COLOR_SEPARATOR = "#888888"
    COLOR_WINDOW_BORDER = "#000000"
    COLOR_TOOLTIP= "#008566"
    
    # 样式表模板
    BUTTON_STYLE_RUNNING = f"""
        QPushButton {{
            border: 2px solid {COLOR_BORDER_ACTIVE};
            border-radius: {BORDER_RADIUS}px;
            background-color: {COLOR_BG_ACTIVE};
        }}
        QPushButton:hover {{
            border: 2px solid {COLOR_BORDER_ACTIVE};
            background-color: {COLOR_BG_HOVER_ACTIVE};
        }}
    """
    
    BUTTON_STYLE_INACTIVE = f"""
        QPushButton {{
            border: 2px solid {COLOR_BORDER_INACTIVE};
            border-radius: {BORDER_RADIUS}px;
            background-color: {COLOR_BACKGROUND};
        }}
        QPushButton:hover {{
            border: 2px solid {COLOR_BORDER_ACTIVE};
            background-color: {COLOR_BG_HOVER_INACTIVE};
        }}
    """
    
    CONTAINER_STYLE = f"""
        QWidget {{
            background-color: {COLOR_BACKGROUND};
            border-radius: {BORDER_RADIUS}px;
        }}
    """
    
    SEPARATOR_STYLE = f"""
        QWidget {{
            background-color: {COLOR_SEPARATOR};
            border-radius: 1px;
        }}
    """
    
    MAIN_WINDOW_STYLE = f"""
        QMainWindow {{
            background: {COLOR_BACKGROUND};
            border: 1px solid {COLOR_WINDOW_BORDER};
            border-radius: {WINDOW_BORDER_RADIUS}px;
        }}
        QPushButton {{
            border: none;
            border-radius: {BORDER_RADIUS}px;
            background-color: {COLOR_BACKGROUND};
        }}
        QPushButton:hover {{
            background-color: {COLOR_HOVER};
        }}
    """



class DockApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.settings_file = os.path.join(self.script_dir, "settings.json")
        
        # 应用数据存储
        self.running_apps: Dict[str, str] = {}
        self.app_buttons: Dict[str, QPushButton] = {}
        self.pinned_app_buttons: Dict[str, QPushButton] = {}
        self.running_app_buttons: Dict[str, QPushButton] = {}
        
        # 应用列表
        self.pinned_apps: List[Dict[str, Any]] = []
        self.apps: List[Dict[str, Any]] = []
        self.running_apps_list: List[Dict[str, Any]] = []
        
        # UI组件
        self.icon_hover_filter = IconHoverFilter(self)
        self.process_manager = ProcessManager()
        self.geometry_anim = None
        
        # 通知系统
        self.notification_manager = None
        self._is_hidden = False
        self.hwnd = None
        
        self.init_ui()
        self.load_settings()
        self.load_pinned_apps()
        self.update_app_buttons()
        self.setup_process_monitoring()
        # Position the window at center horizontally and 20 pixels from bottom
        self.update_window_position()
        
        # 使用统一的线程管理器启动所有后台服务
        self.thread_manager = manager.ThreadManager()
        
        # 创建并运行通知系统线程
        try:
            self.notification_manager = notification_system.NotificationManager(parent=self)
            notification_system_id = self.thread_manager.create(name = self.notification_manager.get_name(), start_when_create=True, worker=self.notification_manager)
            log.info(f"通知系统已开启，id为{notification_system_id}")
        except Exception as e:
            log.error(f"创建通知系统线程时出错: {e}")

        self.destroyed.connect(self.exit_app)



    def eventFilter(self, obj, event):
        """过滤键盘事件，屏蔽关闭窗口相关的快捷键"""
        if event.type() == QEvent.KeyPress:
            key = event.key()
            modifiers = event.modifiers()
            
            # 屏蔽常见关闭窗口快捷键组合
            blocked_shortcuts = [
                (Qt.ControlModifier, Qt.Key_Q),  # Ctrl+Q
                (Qt.ControlModifier, Qt.Key_W),  # Ctrl+W
                (Qt.AltModifier, Qt.Key_F4),     # Alt+F4
                (Qt.ControlModifier | Qt.ShiftModifier, Qt.Key_W),  # Ctrl+Shift+W
                (Qt.NoModifier, Qt.Key_Escape)   # Escape
            ]
            
            for mod, k in blocked_shortcuts:
                if modifiers == mod and key == k:
                    log.info(f"阻止快捷键: {modifiers.name() if modifiers else 'No Modifiers'}+{event.text() if event.text() else key}")
                    return True
        
        return super().eventFilter(obj, event)
    
    def create_app_button(self, app_data: Dict[str, Any], button_dict: Dict[str, QPushButton], 
                         layout: QHBoxLayout, is_running_app: bool = False) -> QPushButton:
        """创建统一的应用按钮"""
        app_name = app_data['name']
        
        # 确保图标存在
        icon_path = app_data.get('icon') or ''
        if not icon_path or not os.path.exists(icon_path):
            # 如果图标路径不存在或文件不存在，重新提取图标
            app_data['icon'] = self.process_manager.extract_icon(app_data.get('path', '')) or ''
            icon_path = app_data['icon']
        
        # 创建按钮
        button = QPushButton()
        button.setFixedSize(DockConstants.BUTTON_SIZE, DockConstants.BUTTON_SIZE)
        button.setMouseTracking(True)
        
        # 设置图标
        if icon_path and os.path.exists(icon_path):
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                button.setIcon(QIcon(pixmap))
                button.setIconSize(QSize(DockConstants.ICON_SIZE, DockConstants.ICON_SIZE))
        
        # 检查运行状态并设置样式
        if is_running_app:
            is_running = self.process_manager.is_process_running(app_data['path'])
        else:
            is_running = app_name in self.running_apps
        
        self.set_button_style(button, is_running)
        
        # 绑定点击事件
        button.clicked.connect(lambda checked, app=app_data: self.handle_app_click(app))
        
        # 绑定右键菜单
        button.setContextMenuPolicy(Qt.CustomContextMenu)
        button.customContextMenuRequested.connect(
            lambda pos, app=app_data, btn=button: self.show_app_context_menu(pos, app, btn)
        )
        
        # 设置工具提示
        button.setToolTip(app_name)
        
        # 安装悬浮事件过滤器
        button.setAttribute(Qt.WA_Hover, True)
        button.setMouseTracking(True)
        button.installEventFilter(self.icon_hover_filter)
        
        # 保存按钮引用
        button_dict[app_name] = button
        
        # 添加到布局
        layout.addWidget(button)
        
        return button

    def load_pinned_apps(self):
        """获取Windows任务栏上固定的应用程序"""
        try:
            pinned_apps = self.get_pinned_apps_from_taskbar()
            self.pinned_apps = pinned_apps
        except Exception as e:
            self.handle_error(f"获取固定应用时出错: {e}")
            self.pinned_apps = []
    
    def handle_error(self, message: str, show_dialog: bool = False):
        """统一错误处理"""
        log.error(message)
        if show_dialog:
            sys32.messagebox("错误", message, sys32.MB_ICONSTOP | sys32.MB_OKCANCEL)

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
            self.handle_error(f"获取任务栏固定应用失败: {e}")
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
            self.handle_error(f"解析快捷方式 {shortcut_path} 失败: {e}")
            return None

    def setup_process_monitoring(self):
        """设置定时器来监控进程状态"""
        self.process_timer = QTimer()
        self.process_timer.timeout.connect(self.check_running_processes)
        self.process_timer.start(DockConstants.PROCESS_CHECK_INTERVAL)

    def check_running_processes(self):
        """检查所有应用的运行状态 - 只考虑有窗口的应用"""
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
                    log.info(f"应用 {app_name} 状态更新: {'运行中' if is_running else '已关闭'}")
            
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

            # 根据当前运行的应用（仅限 dock栏中的应用）调整 dock栏的显示/隐藏，
            # 以避免遮挡全屏程序（例如全屏视频/浏览器）
            try:
                self.adjust_window_stacking()
            except Exception as e:
                log.error(f"调整窗口层级时出错: {e}")
            
        except Exception as e:
            log.error(f"检查运行进程时出错: {e}")

    def adjust_window_stacking(self):
        """根据 dock栏中的应用是否有全屏窗口灵活调整 dock栏的显示/隐藏（带动画）"""
        try:
            fullscreen_windows = self.process_manager.get_fullscreen_windows()
            log.debug(f"全屏窗口检测: 找到 {fullscreen_windows}")
            if len(fullscreen_windows) > 0:
                log.debug("检测到全屏窗口，隐藏dock栏")
                self.hide_dock()
            else:
                log.debug("未检测到全屏窗口，显示dock栏")
                self.show_dock()
            
        except Exception as e:
            log.error(f"adjust_window_stacking error: {e}")
    
    def hide_dock(self):
        """将 dock栏隐藏到屏幕下边缘（带动画）"""
        if self._is_hidden or self.hwnd is None:
            return
        try:
            sys32.hide_window(self.hwnd)
            self._is_hidden = True
            log.info("dock栏隐藏")
        except Exception as e:
            log.error(f"隐藏dock栏时出错: {e}")
        
    
    def show_dock(self):
        """将 dock栏从屏幕下边缘显示（带动画）"""
        if not self._is_hidden or self.hwnd is None:
            return
        try:
            sys32.show_window(self.hwnd)
            self._is_hidden = False
            log.info("dock栏显示")
        except Exception as e:
            log.error(f"显示dock栏时出错: {e}")


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
                sys32.messagebox("错误", f"无法启动应用: {str(e)}", sys32.MB_ICONSTOP | sys32.MB_OK)

    def get_app_button(self, app_name):
        """获取指定应用名称的按钮引用，适用于所有类型的应用"""
        if app_name in self.app_buttons:
            return self.app_buttons[app_name]
        elif app_name in self.pinned_app_buttons:
            return self.pinned_app_buttons[app_name]
        elif app_name in self.running_app_buttons:
            return self.running_app_buttons[app_name]
        return None

    def _extract_app_name(self, file_path: str) -> str:
        """从文件路径提取应用名（快捷方式和可执行文件统一处理）"""
        return os.path.splitext(os.path.basename(file_path))[0]

    def _generate_unique_app_name(self, base_name: str) -> str:
        """生成不与已有应用重名的唯一应用名，重名时添加 (1), (2)... 后缀"""
        name = base_name
        counter = 1
        while any(app['name'] == name for app in self.apps):
            name = f"{base_name} ({counter})"
            counter += 1
        return name

    def add_running_app_to_dock(self, app_data):
        """将运行中的应用添加到程序栏"""
        # 检查是否已存在相同路径的应用
        for app in self.apps:
            if app['path'] == app_data['path']:
                sys32.messagebox("提示", "该应用已存在", sys32.MB_ICONINFORMATION)
                return
        
        # 检查是否与固定应用重复
        for app in self.pinned_apps:
            if app['path'] == app_data['path']:
                sys32.messagebox("提示", "该应用已在固定列表中", sys32.MB_ICONINFORMATION)
                return
        
        # 从运行中应用列表中移除（避免重复）
        self.running_apps_list = [app for app in self.running_apps_list if app['path'] != app_data['path']]
        
        base_name = self._extract_app_name(app_data['path'])
        app_name = self._generate_unique_app_name(base_name)
        
        new_app = {
            'name': app_name,
            'path': app_data['path'],
            'icon': app_data['icon']
        }
        self.apps.append(new_app)
        
        self.save_settings()
        self.update_app_buttons()

    def activate_window(self, app_path):
        """激活已运行的应用窗口（取第一个可见窗口）"""
        visible_windows = self.process_manager.get_app_visible_windows(app_path)
        if visible_windows:
            hwnd, _ = visible_windows[0]
            self._bring_window_to_top(hwnd)
        else:
            log.warning(f"未找到应用 {app_path} 的可见窗口")

    def activate_specific_window(self, hwnd):
        """激活指定的窗口句柄"""
        self._bring_window_to_top(hwnd)

    def _bring_window_to_top(self, hwnd):
        """将指定窗口置顶并恢复（如果最小化）"""
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            log.info(f"窗口 {win32gui.GetWindowText(hwnd)} 已成功激活")
        except Exception as e:
            log.error(f"激活窗口时出错: {e}")

    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("301-02 Dock")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.ToolTip)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.installEventFilter(self)
        self.setStyleSheet(DockConstants.MAIN_WINDOW_STYLE)

        # 创建中央窗口部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 创建主布局
        self.main_layout = QVBoxLayout(central_widget)
        self.main_layout.setContentsMargins(15, 15, 15, 15)
        self.main_layout.setSpacing(5)

        # 创建内容布局
        self.content_layout = QHBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(DockConstants.BUTTON_SPACING)

        # 添加菜单按钮
        self.menu_button = self.create_special_button(
            os.path.join(self.script_dir, "res", "icon_start.png"),
            self.show_menu,
            right_click_handler=self.show_menu
        )
        self.content_layout.addWidget(self.menu_button)

        # 创建固定应用按钮容器
        self.pinned_app_container = QWidget()
        self.pinned_app_layout = QHBoxLayout(self.pinned_app_container)
        self.pinned_app_layout.setContentsMargins(0, 0, 0, 0)
        self.pinned_app_layout.setSpacing(10)  # 设置最小间距为10
        # 设置容器非透明样式
        self.pinned_app_container.setStyleSheet(DockConstants.CONTAINER_STYLE)
        
        # 创建分隔符
        self.separator = QWidget()
        self.separator.setFixedWidth(2)  # 设置分隔符宽度为2像素
        self.separator.setStyleSheet(DockConstants.SEPARATOR_STYLE)
        
        # 创建用户添加应用按钮容器
        self.app_container = QWidget()
        self.app_layout = QHBoxLayout(self.app_container)
        self.app_layout.setContentsMargins(0, 0, 0, 0)
        self.app_layout.setSpacing(10)  # 设置最小间距为10
        # 设置容器非透明样式
        self.app_container.setStyleSheet(DockConstants.CONTAINER_STYLE)

        # 创建运行中应用的分隔符
        self.running_separator = QWidget()
        self.running_separator.setFixedWidth(2)  # 设置分隔符宽度为2像素
        self.running_separator.setStyleSheet(DockConstants.SEPARATOR_STYLE)

        # 创建运行中应用按钮容器
        self.running_app_container = QWidget()
        self.running_app_layout = QHBoxLayout(self.running_app_container)
        self.running_app_layout.setContentsMargins(0, 0, 0, 0)
        self.running_app_layout.setSpacing(10)  # 设置最小间距为10
        # 设置容器非透明样式
        self.running_app_container.setStyleSheet(DockConstants.CONTAINER_STYLE)

        # 将容器添加到内容布局
        self.content_layout.addWidget(self.pinned_app_container)
        self.content_layout.addWidget(self.separator)
        self.content_layout.addWidget(self.app_container, 1)
        self.content_layout.addWidget(self.running_separator)
        self.content_layout.addWidget(self.running_app_container)

        # 添加设置按钮
        settings_layout = QHBoxLayout()
        settings_layout.addStretch()
        self.settings_button = self.create_special_button(
            os.path.join(self.script_dir, "res", "icon_settings.png"),
            self.open_settings
        )
        settings_layout.addWidget(self.settings_button)
        self.content_layout.addLayout(settings_layout)

        self.main_layout.addLayout(self.content_layout)
        self.init_tooltip()


    def update_window_position(self):
        """更新窗口位置 - 根据应用数量自动调整宽度（使用动画平滑过渡）"""
        # 使用可用几何（工作区）而不是整个屏幕几何
        available_geometry = QApplication.primaryScreen().availableGeometry()
        
        # 计算所需宽度：菜单按钮 + 固定应用按钮 + 分隔符 + 用户应用按钮 + 运行应用分隔符 + 运行应用按钮 + 设置按钮 + 间距
        pinned_button_count = len(self.pinned_apps)
        user_button_count = len(self.apps)
        running_button_count = len(self.running_apps_list)
        button_width = DockConstants.BUTTON_SIZE
        button_spacing = DockConstants.BUTTON_SPACING  # 按钮间间距
        separator_width = DockConstants.SEPARATOR_WIDTH  # 分隔符宽度
        margin = DockConstants.WINDOW_MARGIN  # 边距
        
        # 基础宽度：菜单按钮 + 设置按钮 + 边距
        base_width = DockConstants.BUTTON_SIZE + DockConstants.BUTTON_SIZE + (margin * 2)  # 菜单按钮 + 设置按钮 + 左右边距
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
        
        # 根据分隔符可见性计算实际宽度
        separator1_width = DockConstants.SEPARATOR_WIDTH if (hasattr(self, 'separator') and self.separator.isVisible()) else 0
        separator2_width = DockConstants.SEPARATOR_WIDTH if (hasattr(self, 'running_separator') and self.running_separator.isVisible()) else 0
        
        # 计算总宽度
        total_width = base_width + pinned_apps_width + separator1_width + user_apps_width + separator2_width + running_apps_width
        max_width = int(available_geometry.width() * 0.9)
        window_width = min(total_width, max_width)
        
        window_height = 80  # Dock窗口高度
        
        # 计算主窗口的起始X坐标，使整个系统（主窗口+拓展窗口）居中
        # 使用可用几何的宽度进行计算
        x = available_geometry.x() + (available_geometry.width() - window_width) // 2
        # 将窗口放置在可用几何的底部
        y = available_geometry.bottom() - window_height - DockConstants.WINDOW_MARGIN
        
        # 确保 x 不为负
        if x < 0:
            x = 0
        
        # 先设定主窗口目标矩形
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
            except Exception as e:
                log.debug(f"停止几何动画时出错: {e}")
        
        # 创建新动画并保存引用，避免被回收
        self.geometry_anim = QPropertyAnimation(self, b"geometry", self)
        self.geometry_anim.setDuration(220)  # 毫秒，短时平滑过渡
        self.geometry_anim.setStartValue(current_rect)
        self.geometry_anim.setEndValue(target_rect)
        self.geometry_anim.setEasingCurve(QEasingCurve.OutCubic)
        
        self.geometry_anim.start()
    

    
    def create_special_button(self, icon_path: str, click_handler, right_click_handler=None) -> QPushButton:
        """创建特殊按钮（菜单、设置等）"""
        button = QPushButton()
        button.setFixedSize(DockConstants.BUTTON_SIZE, DockConstants.BUTTON_SIZE)
        
        if os.path.exists(icon_path):
            button.setIcon(QIcon(icon_path))
            button.setIconSize(QSize(DockConstants.ICON_SIZE, DockConstants.ICON_SIZE))
        
        button.setStyleSheet(DockConstants.BUTTON_STYLE_INACTIVE)
        button.clicked.connect(click_handler)
        
        if right_click_handler:
            button.setContextMenuPolicy(Qt.CustomContextMenu)
            button.customContextMenuRequested.connect(right_click_handler)
        
        return button



    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(DockConstants.COLOR_BACKGROUND))
        painter.setPen(QPen(QColor(0, 0, 0, 30), 1))
        painter.drawRoundedRect(self.rect(), DockConstants.WINDOW_BORDER_RADIUS, DockConstants.WINDOW_BORDER_RADIUS)
    


    def add_application(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "选择应用程序", 
            "", 
            "可执行文件 (*.exe *.bat *.com);;所有文件 (*)"
        )
        
        if file_path:
            icon_path = self.process_manager.extract_icon(file_path)
            
            for app in self.apps:
                if app['path'] == file_path:
                    sys32.messagebox("提示", "该应用已存在", sys32.MB_ICONINFORMATION | sys32.MB_OK)
                    return
            
            for app in self.pinned_apps:
                if app['path'] == file_path:
                    sys32.messagebox("提示", "该应用已在固定列表中", sys32.MB_ICONINFORMATION | sys32.MB_OK)
                    return
            
            base_name = self._extract_app_name(file_path)
            app_name = self._generate_unique_app_name(base_name)
            
            self.apps.append({
                'name': app_name,
                'path': file_path,
                'icon': icon_path
            })
            
            self.save_settings()
            self.update_app_buttons()


    def init_tooltip(self):
        self.tooltip = QLabel("", None)
        self.tooltip.setObjectName("DockIconTooltip")
        flags = Qt.ToolTip | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint
        self.tooltip.setWindowFlags(flags)
        self.tooltip.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.tooltip.setStyleSheet(f"""
            QLabel#DockIconTooltip {{
                color: white;
                font-family: 'Microsoft YaHei UI';
                font-weight: Medium;
                font-size: 14px;
                background-color: {DockConstants.COLOR_TOOLTIP};
                border-radius: 5px;
                padding: 8px 16px;
            }}
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

    def clear_layout(self, layout: QHBoxLayout) -> None:
        """清空布局中的所有部件"""
        for i in reversed(range(layout.count())):
            widget = layout.itemAt(i).widget()
            if widget is not None:
                widget.setParent(None)
    
    def update_app_buttons(self):
        """更新所有应用按钮"""
        # 清空现有按钮
        self.clear_layout(self.pinned_app_layout)
        self.clear_layout(self.app_layout)
        self.clear_layout(self.running_app_layout)
        
        # 重置按钮字典
        self.pinned_app_buttons.clear()
        self.app_buttons.clear()
        self.running_app_buttons.clear()
        
        # 添加固定应用按钮
        for app in self.pinned_apps:
            self.create_app_button(app, self.pinned_app_buttons, self.pinned_app_layout)
        
        # 添加用户添加的应用按钮
        for app in self.apps:
            self.create_app_button(app, self.app_buttons, self.app_layout)
        
        # 添加运行中的应用按钮
        for app in self.running_apps_list:
            self.create_app_button(app, self.running_app_buttons, self.running_app_layout, is_running_app=True)
        
        # 更新所有容器的可见性
        pinned_apps_visible = len(self.pinned_apps) > 0
        user_apps_visible = len(self.apps) > 0
        running_apps_visible = len(self.running_apps_list) > 0
        
        self.pinned_app_container.setVisible(pinned_apps_visible)
        self.app_container.setVisible(user_apps_visible)
        self.running_app_container.setVisible(running_apps_visible)
        
        # 更新分隔符可见性（仅在相邻容器都可见时显示）
        self.separator.setVisible(pinned_apps_visible and user_apps_visible)
        self.running_separator.setVisible(user_apps_visible and running_apps_visible)
        
        # 更新窗口位置以反映宽度变化
        self.update_window_position()
        
    def set_button_style(self, button, is_running):
        """设置按钮样式，根据运行状态"""
        if is_running:
            button.setStyleSheet(DockConstants.BUTTON_STYLE_RUNNING)
        else:
            button.setStyleSheet(DockConstants.BUTTON_STYLE_INACTIVE)


    def launch_app(self, path):
        try:
            os.startfile(path)
        except Exception as e:
            sys32.messagebox("错误", f"无法启动应用: {str(e)}", sys32.MB_ICONSTOP | sys32.MB_OK)

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
        except Exception as e:
            log.debug(f"隐藏图标提示时出错: {e}")

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
                            log.info(f"已发送关闭命令到窗口: {window_title}")
                            return False  # 找到并处理了窗口，停止枚举
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    return True  # 继续枚举其他窗口

        try:
            win32gui.EnumWindows(enum_windows_proc, 0)
            # 延迟检查进程状态
            QTimer.singleShot(1000, self.check_running_processes)
        except Exception as e:
            log.error(f"关闭窗口时出错: {e}")

    def remove_app(self, app_data):
        reply = sys32.messagebox(
            "确认",
            f"确定要删除应用 '{app_data['name']}' 吗？",
            sys32.MB_YESNO | sys32.MB_ICONQUESTION
        )

        if reply == sys32.IDYES:
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
            new_name = self._generate_unique_app_name(new_name.strip())
            
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
            if os.path.exists(file_path):
                app_data['icon'] = file_path
                self.save_settings()
                self.update_app_buttons()
            else:
                sys32.messagebox("错误", "选择的图标文件不存在", sys32.MB_ICONWARNING | sys32.MB_OK)

    def open_settings(self):
        """打开设置对话框"""
        self.dialog = settings.SettingsUI(
            version=VERSION,
            config_path=self.settings_file,
            on_save_callback=self.on_settings_saved
        )
        self.dialog.show()

    def on_settings_saved(self, config_data):
        """设置保存后的回调"""
        dock_config = config_data.get('dock', {})
        except_list = dock_config.get('except_processes', [])
        if except_list and hasattr(self, 'process_manager') and self.process_manager:
            try:
                self.process_manager.set_except_processes(except_list)
            except Exception:
                pass

        debug_enabled = config_data.get('debug', False)
        if debug_enabled:
            log.enable_debug()
        else:
            log.disable_debug()

        log.info("设置已更新")

    def load_settings(self):
        try:
            settings = Config.load_config(self.settings_file)
            # 从 dock栏配置部分获取数据
            dock_config = settings.get('dock', {})
            self.apps = dock_config.get('apps', [])
            
            # 加载 ProcessManager 的排除进程设置（如存在）
            except_list = dock_config.get('except_processes', [])
            if except_list and hasattr(self, 'process_manager') and self.process_manager:
                try:
                    self.process_manager.set_except_processes(except_list)
                except Exception:
                    pass
            

            
            # 确保加载设置后更新应用按钮
            self.update_app_buttons()
            if dock_config.get('hide_taskbar', False):
                sys32.show_window(sys32.HWND_TRAY)
        except Exception as e:
            log.exception(f"加载配置文件 {self.settings_file} 时出错")
            self.apps = []  # 出错时使用默认设置
            self.update_app_buttons()

    def save_settings(self):
        try:
            config = Config.load_config(self.settings_file)
            config['dock']['apps'] = self.apps
            config['dock']['except_processes'] = getattr(self.process_manager, 'except_processes', [])
            Config.save_config(self.settings_file, config)
        except Exception as e:
            log.exception(f"保存配置文件 {self.settings_file} 时出错")

    def show_menu(self, pos):
        """显示菜单按钮的菜单"""
        # 构建动作列表
        actions = [
            ("命令提示符", self.open_terminal, True),
            ("命令提示符（管理员）", self.open_terminal_admin, True),
            ("任务管理器", self.open_task_manager, True),
            ("电源操作", self.show_shutdown_menu, True),
            ("添加应用到程序栏", self.add_application, True),
            ("退出", self.exit_app, True),
        ]
        
        # 创建并显示自定义弹窗，使用菜单按钮作为锚点
        popup = ContextPopup(actions, parent=None)
        popup.show_at_position(pos, self.sender())

    def open_terminal(self):
        """打开命令提示符"""
        try:
            os.startfile("cmd.exe")
        except Exception as e:
            self.handle_error(f"打开命令提示符失败: {e}")

    def open_terminal_admin(self):
        """打开管理员命令提示符"""
        try:
            subprocess.run(["powershell", "-Command", "Start-Process", "cmd.exe", "-Verb", "RunAs"])
        except Exception as e:
            self.handle_error(f"打开管理员命令提示符失败: {e}")

    def open_task_manager(self):
        """打开任务管理器"""
        try:
            os.startfile("taskmgr.exe")
        except Exception as e:
            self.handle_error(f"打开任务管理器失败: {e}")

    def show_shutdown_menu(self):
        """显示关机或注销对话框"""
        try:
            dialog = ShutdownDialog(self)
            if dialog.exec() == QDialog.Accepted:
                action = dialog.selected_action

                action_names = {
                    "logout": "注销",
                    "shutdown": "关机",
                    "restart": "重启",
                    "hibernate": "休眠"
                }

                reply = sys32.messagebox(
                    "确认操作",
                    f"确定要执行{action_names[action]}操作吗？\n\n请确保已保存所有工作！",
                    sys32.MB_YESNO | sys32.MB_ICONQUESTION,
                )

                if reply == sys32.IDYES:
                    if action == "logout":
                        subprocess.run(["shutdown.exe", "/l"])
                    elif action == "shutdown":
                        subprocess.run(["shutdown.exe", "/s", "/t", "0"])
                    elif action == "restart":
                        subprocess.run(["shutdown.exe", "/r", "/t", "0"])
                    elif action == "hibernate":
                        subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "Hibernate"])
        except Exception as e:
            self.handle_error(f"显示关机对话框失败: {e}")

    def exit_app(self):
        """清理资源并退出应用"""
        self.save_settings()
        gc.collect()
        try:

            # 使用统一的线程管理器停止所有后台服务
            if hasattr(self, 'thread_manager') and self.thread_manager:
                try:
                    self.thread_manager.stop_all()
                    log.info("所有后台服务已停止")
                except Exception as e:
                    log.error(f"停止后台服务时出错: {e}")
            
            # 停止进程监控定时器
            if hasattr(self, 'process_timer') and self.process_timer:
                self.process_timer.stop()
            
            # 停止全局快捷键管理器
            if hasattr(self, 'hotkey_manager') and self.hotkey_manager:
                self.hotkey_manager.stop()

            # 重启explorer.exe
            sys32.show_window(sys32.HWND_TRAY)
            
            log.info("应用程序已清理资源并退出")
            sys.exit(0)
            
        except Exception as e:
            log.error(f"退出应用时出错: {e}")
            # 重启explorer.exe
            sys32.show_window(sys32.HWND_TRAY)
            os._exit(0)

    def closeEvent(self, event):
        event.ignore()  # 忽略关闭事件，因为应用程序不应该真正退出

    def showEvent(self, event):
        super().showEvent(event)
        if self.hwnd is None:
            self.hwnd = int(self.winId())


def main():
    sys32.hide_window(sys32.HWND_TRAY)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 防止关闭主窗口时退出
    
    dock = DockApp()
    dock.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()