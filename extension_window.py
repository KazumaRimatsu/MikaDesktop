import os
import ctypes
from ctypes import wintypes
# 删除不再需要的win32con导入
# 删除不再需要的win32gui导入
from PySide6.QtCore import Qt, QPoint, QTimer, QSize
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QApplication, QPushButton
from PySide6.QtGui import QIcon, QPixmap, QCursor
# 删除托盘图标相关导入
from custom_ui import ContextPopup
# 删除不再需要的ProcessManager导入
# 删除不再需要的win32process导入
import win32api
import win32con
import win32gui


class ExtensionWindow(QMainWindow):
    """拓展窗口类，与主程序坞样式和高度一致"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 设置窗口标志和属性，与主Dock窗口保持完全一致
        self.setWindowFlags(
            Qt.FramelessWindowHint | 
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        # 移除WA_AlwaysStackOnTop，确保与主窗口层级一致
        self.setAttribute(Qt.WA_AlwaysStackOnTop, False)
        # 添加WA_ShowWithoutActivating，确保显示时不影响主窗口
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        
        # 创建中央窗口部件
        central_widget = QWidget()
        central_widget.setStyleSheet("""
            QWidget {
                background-color: #ECECEC;
                border-radius: 18px;
            }
        """)
        self.setCentralWidget(central_widget)
        
        # 创建主布局，使用QVBoxLayout实现垂直居中
        self.extension_layout = QVBoxLayout(central_widget)
        # 调整边距以确保圆角效果正确显示
        self.extension_layout.setContentsMargins(5, 5, 5, 5)
        self.extension_layout.setSpacing(5)
        
        # 创建顶部工具栏，包含键盘图标
        self.toolbar_layout = QHBoxLayout()
        self.toolbar_layout.setContentsMargins(5, 5, 5, 5)
        
        # 创建键盘图标按钮
        self.keyboard_button = QPushButton()
        self.keyboard_button.setFixedSize(60, 60)
        self.keyboard_button.setIcon(QIcon(os.path.join(os.path.dirname(os.path.abspath(__file__)),"keyboard.png")))
        self.keyboard_button.setIconSize(QSize(48, 48))
        self.keyboard_button.setContextMenuPolicy(Qt.CustomContextMenu)
        self.keyboard_button.customContextMenuRequested.connect(self.show_keyboard_menu)
        self.keyboard_button.clicked.connect(self.show_keyboard_menu)

        # 将键盘按钮添加到工具栏
        self.toolbar_layout.addWidget(self.keyboard_button)
        self.toolbar_layout.addStretch()

        self.separator = QWidget()
        self.separator.setFixedWidth(2)  # 设置分隔符宽度为2像素
        self.separator.setStyleSheet("""
            QWidget {
                background-color: #CCCCCC;  /* 设置分隔符颜色 */
                border-radius: 1px;
            }
        """)
        self.toolbar_layout.addWidget(self.separator)
        
        # 将工具栏添加到主布局
        self.extension_layout.addLayout(self.toolbar_layout)
        
        # 设置样式，与主Dock窗口完全一致
        self.setStyleSheet("""
            QPushButton {
                    border: 2px solid transparent;
                    border-radius: 16px;
                    background-color: #ECECEC;
                }
                QPushButton:hover {
                    border: 2px solid #4a86e8;
                    background-color: rgba(200, 200, 200, 100);
                }
        """)
        
        # 初始化窗口几何
        self.extension_width = 300  # 扩展窗口宽度
        self.min_gap = 20  # 最小水平间距
    
    def initialize_position(self, main_x, main_y, main_width, main_height):
        """初始化拓展窗口的位置和大小，使其位于主窗口右侧"""
        # 计算拓展窗口的初始位置和大小
        extension_height = main_height  # 与主窗口高度完全一致
        
        # 计算位置：主窗口右侧，保持min_gap像素的水平距离
        extension_x = main_x + main_width + self.min_gap
        extension_y = main_y  # 与主窗口垂直对齐
        
        # 确保窗口在屏幕范围内
        screen_geometry = QApplication.primaryScreen().geometry()
        if extension_x + self.extension_width > screen_geometry.width():
            # 如果超出屏幕，则向左移动主窗口以保留 min_gap（主窗口不小于0）
            overflow = (extension_x + self.extension_width) - screen_geometry.width()
            new_main_x = max(0, main_x - overflow)
            # 重新计算拓展窗口位置
            main_x = new_main_x
            extension_x = main_x + main_width + self.min_gap
            # 兜底，确保不超出屏幕
            if extension_x + self.extension_width > screen_geometry.width():
                extension_x = screen_geometry.width() - self.extension_width - 10
        
        # 设置拓展窗口的初始位置和大小
        self.setGeometry(extension_x, extension_y, self.extension_width, extension_height)
        
        # 确保窗口层级与主窗口一致
        if self.parent():
            try:
                # 将拓展窗口设置与主窗口相同的层级
                main_hwnd = int(self.parent().winId())
                ext_hwnd = int(self.winId())
                # 使用HWND_NOTOPMOST确保窗口层级一致
                win32gui.SetWindowPos(
                    ext_hwnd,
                    win32con.HWND_NOTOPMOST,
                    0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                )
            except Exception as e:
                print(f"设置窗口层级时出错: {e}")
    
    def update_position(self, main_x, main_y, main_width, main_height):
        """更新拓展窗口位置，使其位于主程序坞右侧，高度与主窗口一致"""
        # 设置拓展窗口尺寸：固定宽度，高度与主窗口完全一致
        extension_height = main_height  # 与主窗口高度完全一致
        
        # 计算位置：主窗口右侧，保持 min_gap 的水平距离
        extension_x = main_x + main_width + self.min_gap
        extension_y = main_y  # 与主窗口垂直对齐
        
        # 确保窗口在屏幕范围内，若超出则向左移动主窗口以维持间距
        screen_geometry = QApplication.primaryScreen().geometry()
        if extension_x + self.extension_width > screen_geometry.width():
            overflow = (extension_x + self.extension_width) - screen_geometry.width()
            new_main_x = max(0, main_x - overflow)
            main_x = new_main_x
            extension_x = main_x + main_width + self.min_gap
            # 兜底
            if extension_x + self.extension_width > screen_geometry.width():
                extension_x = screen_geometry.width() - self.extension_width - 10
        
        # 设置拓展窗口几何
        self.setGeometry(extension_x, extension_y, self.extension_width, extension_height)
        
        # 确保窗口层级与主窗口一致
        if self.parent():
            try:
                main_hwnd = int(self.parent().winId())
                ext_hwnd = int(self.winId())
                # 使用HWND_NOTOPMOST确保窗口层级一致
                win32gui.SetWindowPos(
                    ext_hwnd,
                    win32con.HWND_NOTOPMOST,
                    0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                )
            except Exception as e:
                print(f"设置窗口层级时出错: {e}")
    
    def update_position_with_center_calculation(self, x, y, window_width, window_height):
        """使用与主窗口相同的居中计算方式更新拓展窗口位置"""
        # 计算拓展窗口的位置：主窗口右侧，保持间距
        extension_spacing = max(20, 80)  # 保证至少为 min_gap
        extension_x = x + window_width + extension_spacing
        extension_y = y  # 与主窗口垂直对齐
        
        # 确保窗口在屏幕范围内
        screen_geometry = QApplication.primaryScreen().geometry()
        
        # 如果超出屏幕右侧，尝试向左移动主窗口以保留 min_gap
        overflow = (extension_x + self.extension_width) - screen_geometry.width()
        if overflow > 0:
            # 向左移动主窗口，保证不小于0
            new_x = max(0, x - overflow)
            # 更新拓展窗口X
            extension_x = new_x + window_width + extension_spacing
            # 返回新的主窗口X坐标供主窗口更新使用
            return new_x
        
        # 确保拓展窗口在屏幕范围内（兜底）
        if extension_x + self.extension_width > screen_geometry.width():
            extension_x = screen_geometry.width() - self.extension_width - 10
        
        # 设置拓展窗口位置
        self.setGeometry(extension_x, extension_y, self.extension_width, window_height)
        
        # 确保窗口层级与主窗口一致
        if self.parent():
            try:
                main_hwnd = int(self.parent().winId())
                ext_hwnd = int(self.winId())
                # 使用HWND_NOTOPMOST确保窗口层级一致
                win32gui.SetWindowPos(
                    ext_hwnd,
                    win32con.HWND_NOTOPMOST,
                    0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                )
            except Exception as e:
                print(f"设置窗口层级时出错: {e}")
        
        # 返回原始主窗口X坐标（不需要调整）
        return x
    
    def adjust_window_height(self):
        """不再调整窗口高度，保持与主窗口一致的高度"""
        # 不再自动调整窗口高度，保持与主窗口一致的高度
        pass
    
    # 删除与托盘图标相关的方法
    
    # 删除show_tray_icon_context_menu方法
    
    # 删除refresh_tray_icons方法
    
    def show_keyboard_menu(self, pos):
        """显示键盘图标的右键菜单，使用ContextPopup以统一风格"""
        # 创建动作列表
        actions = [
            ("切换输入法", self.switch_input_method, True)
        ]
        
        # 创建并显示自定义弹窗，使用键盘按钮作为锚点
        popup = ContextPopup(actions, parent=None)
        popup.show_at_position(pos, self.keyboard_button)
    
    def switch_input_method(self):
        """切换输入法"""
        try:
            print("切换输入法")
            
            # 显示输入法切换提示
            self.show_ime_notification()
            
            # 使用系统级API发送输入法切换消息
            # 获取当前活动窗口句柄
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            
            if hwnd:
                # 方法1: 使用PostMessageW发送WM_INPUTLANGCHANGEREQUEST消息
                # WM_INPUTLANGCHANGEREQUEST = 0x0050
                result = user32.PostMessageW(hwnd, 0x0050, 1, 0)
                if result == 0:
                    print(f"PostMessageW失败，尝试备用方法")
                    
                    # 方法2: 使用SendInput模拟按键（Win+Space）
                    import win32con
                    win32api.keybd_event(win32con.VK_LWIN, 0, 0, 0)
                    win32api.keybd_event(0x20, 0, 0, 0)  # 空格键
                    win32api.keybd_event(0x20, 0, win32con.KEYEVENTF_KEYUP, 0)
                    win32api.keybd_event(win32con.VK_LWIN, 0, win32con.KEYEVENTF_KEYUP, 0)
                else:
                    print(f"PostMessageW成功发送")
            else:
                print(f"无法获取活动窗口句柄，使用备用方法")
                
                # 备用方法: 使用SendInput模拟按键（Win+Space）
                import win32con
                win32api.keybd_event(win32con.VK_LWIN, 0, 0, 0)
                win32api.keybd_event(0x20, 0, 0, 0)  # 空格键
                win32api.keybd_event(0x20, 0, win32con.KEYEVENTF_KEYUP, 0)
                win32api.keybd_event(win32con.VK_LWIN, 0, win32con.KEYEVENTF_KEYUP, 0)
            
        except Exception as e:
            print(f"切换输入法时出错: {e}")
    
    def show_ime_notification(self):
        """显示输入法切换提示"""
        try:
            self.keyboard_button.setStyleSheet("""
                QPushButton {
                    background-color: #5d4ae8;
                }
            """)
            QTimer.singleShot(1000, lambda: self.keyboard_button.setStyleSheet('QPushButton {background-color: #ECECEC;}'))
        except Exception as e:
            print(f"显示输入法切换提示时出错: {e}")