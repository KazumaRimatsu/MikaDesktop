import gc
import os
import sys
from typing import Dict, List, Any

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
from Lib.custom_ui import IconHoverFilter, ContextPopup, ShutdownDialog
from Lib.process_manager import ProcessManager
from Lib.win32_omessagebox import information, warning, critical, question, Yes, No
import Lib.goodbye_tray as goodbye_tray
import Lib.log_maker as log_maker
import Lib.config_manager as Config
from Lib.threads import manager

log = log_maker.logger()


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
    COLOR_HOVER = "#DADADA"
    COLOR_BORDER_ACTIVE = "#4a86e8"
    COLOR_BORDER_INACTIVE = "transparent"
    COLOR_BG_ACTIVE = "rgba(74, 134, 232, 100)"
    COLOR_BG_HOVER_ACTIVE = "rgba(58, 118, 216, 150)"
    COLOR_BG_HOVER_INACTIVE = "rgba(200, 200, 200, 100)"
    COLOR_SEPARATOR = "#CCCCCC"
    COLOR_WINDOW_BORDER = "rgba(0, 0, 0, 0.1)"
    
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
            background-color: {COLOR_BACKGROUND};
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
        self.accidental_touch_monitor = None
        self._target_rect = None
        self._is_hidden = False
        
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
            from Lib.features.notification_system import NotificationManager
            self.notification_manager = NotificationManager(parent=self)
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
            warning(self, "错误", message)

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

            # 根据当前运行的应用（仅限 Dock 中的应用）调整 Dock 的显示/隐藏，
            # 以避免遮挡全屏程序（例如全屏视频/浏览器）
            try:
                self.adjust_window_stacking()
            except Exception as e:
                log.error(f"调整窗口层级时出错: {e}")
            
        except Exception as e:
            log.error(f"检查运行进程时出错: {e}")

    def adjust_window_stacking(self):
        """根据 Dock 中的应用是否有全屏窗口灵活调整 Dock 的显示/隐藏（带动画）"""
        try:
            # 收集 Dock 中关注的应用路径（去重）
            all_paths = []
            for app in (self.pinned_apps + self.apps + self.running_apps_list):
                p = app.get('path') if isinstance(app, dict) else None
                if p:
                    all_paths.append(p)
            
            # 检查是否有任意应用处于全屏状态
            any_fullscreen = self.process_manager.any_apps_fullscreen(all_paths)
            
            if any_fullscreen and not self._is_hidden:
                # 有全屏应用且 Dock 未隐藏，执行隐藏动画
                self.hide_dock_with_animation()
            elif not any_fullscreen and self._is_hidden:
                # 没有全屏应用且 Dock 已隐藏，执行显示动画
                self.show_dock_with_animation()
                
        except Exception as e:
            log.error(f"adjust_window_stacking error: {e}")
    
    def hide_dock_with_animation(self):
        """将 Dock 隐藏到屏幕下边缘（带动画）"""
        if self._is_hidden:
            return
        
        # 获取屏幕可用几何
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        
        # 计算隐藏位置：移动到屏幕下边缘之下
        current_rect = self.geometry()
        target_rect = QRect(
            current_rect.x(),
            screen_geometry.bottom() + 10,  # 完全移出屏幕
            current_rect.width(),
            current_rect.height()
        )
        
        # 停止现有动画
        if self.geometry_anim is not None and isinstance(self.geometry_anim, QPropertyAnimation):
            try:
                self.geometry_anim.stop()
            except:
                pass
        
        # 创建动画
        self.geometry_anim = QPropertyAnimation(self, b"geometry", self)
        self.geometry_anim.setDuration(300)  # 毫秒
        self.geometry_anim.setStartValue(current_rect)
        self.geometry_anim.setEndValue(target_rect)
        self.geometry_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.geometry_anim.finished.connect(lambda: self.set_is_hidden(True))
        self.geometry_anim.start()
    
    def show_dock_with_animation(self):
        """将 Dock 从屏幕下边缘显示（带动画）"""
        if not self._is_hidden:
            return
        
        # 获取屏幕可用几何并计算目标位置
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        
        # 计算目标位置（原始位置）
        if self._target_rect is not None:
            target_rect = self._target_rect
        else:
            # 使用当前窗口位置作为目标（实际上应该调用 update_window_position 计算）
            # 临时计算：居中底部
            window_height = 80
            window_width = self.width()
            x = (screen_geometry.width() - window_width) // 2
            y = screen_geometry.bottom() - window_height - DockConstants.WINDOW_MARGIN
            target_rect = QRect(x, y, window_width, window_height)
        self._target_rect = target_rect
        
        # 当前隐藏位置（屏幕下边缘之下）
        current_rect = self.geometry()
        
        # 停止现有动画
        if self.geometry_anim is not None and isinstance(self.geometry_anim, QPropertyAnimation):
            try:
                self.geometry_anim.stop()
            except:
                pass
        
        # 创建动画
        # 确保只有垂直移动：使用当前水平位置，目标垂直位置
        target_rect = QRect(current_rect.x(), target_rect.y(), target_rect.width(), target_rect.height())
        self.geometry_anim = QPropertyAnimation(self, b"geometry", self)
        self.geometry_anim.setDuration(300)  # 毫秒
        self.geometry_anim.setStartValue(current_rect)
        self.geometry_anim.setEndValue(target_rect)
        self.geometry_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.geometry_anim.finished.connect(lambda: self.set_is_hidden(False))
        self.geometry_anim.start()
    
    def set_is_hidden(self, hidden):
        """设置隐藏状态并更新标志"""
        self._is_hidden = hidden
        if not hidden:
            # 显示后确保窗口在最顶层
            dock_hwnd = int(self.winId())
            try:
                win32gui.SetWindowPos(
                    dock_hwnd,
                    win32con.HWND_TOPMOST,
                    0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                )
            except Exception as e:
                log.error(f"设置窗口顶层时出错: {e}")

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
                critical(self, "错误", f"无法启动应用: {str(e)}")

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
                information(self, "提示", "该应用已存在")
                return
        
        # 检查是否与固定应用重复
        for app in self.pinned_apps:
            if app['path'] == app_data['path']:
                information(self, "提示", "该应用已在固定列表中")
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
                        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
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
                log.info(f"窗口 {title} 已成功激活")
            except Exception as e:
                log.error(f"激活窗口时出错: {e}")
        else:
            log.warning(f"未找到应用 {app_path} 的可见窗口")

    def activate_specific_window(self, hwnd):
        """激活指定的窗口句柄"""
        try:
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
            
            # 确保Dock窗口保持在顶层
            dock_hwnd = int(self.winId())  # 确保转换为int类型
            win32gui.SetWindowPos(
                dock_hwnd, 
                win32con.HWND_TOPMOST,  # 修改：改为TOPMOST确保始终在最顶层
                0, 0, 0, 0, 
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
            )
            log.info(f"窗口 {win32gui.GetWindowText(hwnd)} 已成功激活，Dock保持在顶层")
        except Exception as e:
            log.error(f"激活窗口时出错: {e}")

    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("Dock")
        # 移除WindowStaysOnTopHint，使用ToolTip标志避免任务栏显示
        # 使用Tool标志可以让窗口在某些情况下不被视为常规窗口
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.ToolTip)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # 移除WA_AlwaysStackOnTop属性，避免始终在最顶层
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
            self.show_menu
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
        screen = QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        available_geometry = screen.availableGeometry()
        
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
            except:
                pass
        
        # 创建新动画并保存引用，避免被回收
        self.geometry_anim = QPropertyAnimation(self, b"geometry", self)
        self.geometry_anim.setDuration(220)  # 毫秒，短时平滑过渡
        self.geometry_anim.setStartValue(current_rect)
        self.geometry_anim.setEndValue(target_rect)
        self.geometry_anim.setEasingCurve(QEasingCurve.OutCubic)
        
        self.geometry_anim.start()
    

    
    def create_special_button(self, icon_path: str, click_handler) -> QPushButton:
        """创建特殊按钮（菜单、设置等）"""
        button = QPushButton()
        button.setFixedSize(DockConstants.BUTTON_SIZE, DockConstants.BUTTON_SIZE)
        
        if os.path.exists(icon_path):
            button.setIcon(QIcon(icon_path))
            button.setIconSize(QSize(DockConstants.ICON_SIZE, DockConstants.ICON_SIZE))
        
        button.setStyleSheet(DockConstants.BUTTON_STYLE_INACTIVE)
        button.clicked.connect(click_handler)
        
        # 如果是菜单按钮，添加右键菜单支持
        if click_handler == self.show_menu:
            button.setContextMenuPolicy(Qt.CustomContextMenu)
            button.customContextMenuRequested.connect(self.show_menu)
        
        return button



    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#ECECEC"))
        painter.setPen(QPen(QColor(0, 0, 0, 30), 1))
        painter.drawRoundedRect(self.rect(), 15, 15)
    
    def resizeEvent(self, event):
        """窗口大小变化事件"""
        super().resizeEvent(event)
    
    def moveEvent(self, event):
        """窗口移动事件"""
        super().moveEvent(event)

    def add_application(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "选择应用程序", 
            "", 
            "可执行文件 (*.exe *.bat *.com);;所有文件 (*)"
        )
        
        if file_path:
            # 提取图标（使用 ProcessManager）
            icon_path = self.process_manager.extract_icon(file_path)
            
            # 检查是否已存在相同路径的应用
            for app in self.apps:
                if app['path'] == file_path:
                    information(self, "提示", "该应用已存在")
                    return
            
            # 检查是否与固定应用重复
            for app in self.pinned_apps:
                if app['path'] == file_path:
                    information(self, "提示", "该应用已在固定列表中")
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
            log.error(f"提取图标时出错: {e}")
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
            critical(self, "错误", f"无法启动应用: {str(e)}")

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
        reply = question(
            self, 
            "确认", 
            f"确定要删除应用 '{app_data['name']}' 吗？", 
            Yes | No
        )
        
        if reply == Yes:
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
            if os.path.exists(file_path):
                app_data['icon'] = file_path
                self.save_settings()
                self.update_app_buttons()
            else:
                warning(self, "错误", "选择的图标文件不存在")

    def open_settings(self):
        """打开设置对话框"""
        dialog = SettingsDialog(self)
        if dialog.exec():
            pass

    def load_settings(self):
        try:
            settings = Config.load_config(self.settings_file)
            # 从 dock 配置部分获取数据
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
        except Exception as e:
            log.exception(f"加载配置文件 {self.settings_file} 时出错")
            self.apps = []  # 出错时使用默认设置
            self.update_app_buttons()

    def save_settings(self):
        try:
            settings = {
                'dock': {
                    'apps': self.apps,
                    # 将 ProcessManager 的排除列表保存到配置
                    'except_processes': getattr(self.process_manager, 'except_processes', [])
                }
            }
            
            success = Config.save_config(self.settings_file, settings)
            if not success:
                log.error(f"保存配置文件到 {self.settings_file} 失败")
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
            import subprocess
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
                if action == "logout":
                    os.system("shutdown /l")
                elif action == "shutdown":
                    os.system("shutdown /s /t 0")
                elif action == "restart":
                    os.system("shutdown /r /t 0")
                elif action == "hibernate":
                    os.system("rundll32.exe powrprof.dll,SetSuspendState Hibernate")
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
            goodbye_tray.hello()
            
            log.info("应用程序已清理资源并退出")
            sys.exit(0)
            
        except Exception as e:
            log.error(f"退出应用时出错: {e}")
            # 重启explorer.exe
            goodbye_tray.hello()
            os._exit(0)

    def closeEvent(self, event):
        event.ignore()  # 忽略关闭事件，因为应用程序不应该真正退出


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent  # 保存父窗口引用
        self.setWindowTitle("设置")
        self.setFixedSize(480, 420)  # 略微增大窗口以容纳编辑区
        # 启用透明背景以支持模糊效果
        self.setAttribute(Qt.WA_TranslucentBackground)

        layout = QVBoxLayout()



        # 分隔说明
        layout.addSpacing(8)
        excl_label = QLabel("进程排除列表（每行一个，若只写名称将自动补 .exe）：")
        excl_label.setAlignment(Qt.AlignLeft)
        layout.addWidget(excl_label)
        # 编辑区域：每行一个进程名
        self.except_edit = QPlainTextEdit()
        self.except_edit.setPlaceholderText("例如：\npython.exe\nexplorer.exe\nshellexperiencehost")
        self.except_edit.setFixedHeight(120)
        # 初始化内容（从 ProcessManager 读取当前列表）
        try:
            current = getattr(self.parent.process_manager, 'except_processes', [])
            if current:
                self.except_edit.setPlainText("\n".join(current))
        except Exception:
            pass
        layout.addWidget(self.except_edit)

        # 保存按钮
        save_button = QPushButton("确定")
        save_button.clicked.connect(self.accept)
        layout.addWidget(save_button)

        self.setLayout(layout)

        # 添加独立的样式表
        self.setStyleSheet("""
            QDialog {
                background-color: #f0f0f0;
                border-radius: 16px;
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



    def accept(self):
        """重写accept方法以保存设置"""
        # 应用并保存排除进程列表
        try:
            text = self.except_edit.toPlainText()
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            if hasattr(self.parent, 'process_manager') and self.parent.process_manager:
                self.parent.process_manager.set_except_processes(lines)
        except Exception as e:
            log.error(f"应用排除列表时出错: {e}")
        # 保存设置到父窗口的配置文件
        self.parent.save_settings()
        super().accept()

    def save_settings(self):
        """保存设置"""


def main():
    goodbye_tray.goodbye()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 防止关闭主窗口时退出
    
    dock = DockApp()
    dock.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()