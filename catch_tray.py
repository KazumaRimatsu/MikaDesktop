import os
import ctypes
from typing import Optional, List, Dict, Union
from dataclasses import dataclass
from enum import IntEnum, IntFlag
import warnings

# 类型提示
try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal

# 可选依赖
try:
    import win32gui
    import win32ui
    import win32con
    import win32api
    import win32process
    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False
    warnings.warn("pywin32 未安装，部分功能可能受限")

try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    warnings.warn("Pillow 未安装，无法处理图像")


# ====================== 常量定义 ======================

class IconSize(IntEnum):
    """图标尺寸枚举"""
    SMALL = 16
    MEDIUM = 32
    LARGE = 48
    EXTRALARGE = 128
    JUMBO = 256
    THUMBNAIL = 96  # 缩略图尺寸


class IconType(IntFlag):
    """图标类型标志"""
    EXECUTABLE = 1      # 可执行文件
    DOCUMENT = 2        # 文档文件
    FOLDER = 4          # 文件夹
    SHORTCUT = 8        # 快捷方式
    UWP = 16            # UWP应用
    SYSTEM = 32         # 系统图标
    TRAY = 64           # 托盘图标


class IconFormat(IntEnum):
    """图标输出格式"""
    PNG = 1
    ICO = 2
    BMP = 3
    JPEG = 4


@dataclass
class IconInfo:
    """图标信息容器"""
    path: str                    # 图标源路径
    index: int                   # 图标索引
    width: int                   # 宽度
    height: int                  # 高度
    bits_per_pixel: int          # 位深度
    format: str                  # 原始格式
    size_bytes: int              # 数据大小
    process_id: Optional[int] = None  # 关联进程ID
    window_title: Optional[str] = None  # 窗口标题
    tooltip: Optional[str] = None  # 工具提示


@dataclass
class ExtractedIcon:
    """提取的图标数据"""
    image: Optional['Image.Image']   # PIL图像对象
    raw_data: bytes                  # 原始字节数据
    info: IconInfo                   # 图标信息
    success: bool                    # 提取是否成功
    error: Optional[str] = None      # 错误信息


# ====================== Windows API 常量 ======================

# 添加Windows API常量
NIM_ADD = 0x00000001
NIM_MODIFY = 0x00000002
NIM_DELETE = 0x00000003
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_STATE = 0x00000008
NIF_INFO = 0x00000010
NIF_GUID = 0x00000020


# ====================== Windows API 结构体定义 ======================

class NOTIFYICONDATA(ctypes.Structure):
    """Windows通知图标数据结构"""
    _fields_ = [
        ('cbSize', ctypes.c_uint32),
        ('hWnd', ctypes.c_void_p),
        ('uID', ctypes.c_uint32),
        ('uFlags', ctypes.c_uint32),
        ('uCallbackMessage', ctypes.c_uint32),
        ('hIcon', ctypes.c_void_p),
        ('szTip', ctypes.c_wchar * 128),
        ('dwState', ctypes.c_uint32),
        ('dwStateMask', ctypes.c_uint32),
        ('szInfo', ctypes.c_wchar * 256),
        ('uTimeoutOrVersion', ctypes.c_uint32),
        ('szInfoTitle', ctypes.c_wchar * 64),
        ('dwInfoFlags', ctypes.c_uint32),
        ('guidItem', ctypes.c_byte * 16),
        ('hBalloonIcon', ctypes.c_void_p)
    ]


# ====================== 托盘图标提取器 ======================

class TrayIconExtractor:
    """
    Windows任务栏托盘图标提取器
    
    特性:
    - 支持提取任务栏托盘区的所有图标
    - 支持获取图标相关的进程信息
    - 支持提取工具提示文本
    - 支持多种尺寸和格式输出
    """
    
    def __init__(self):
        """初始化托盘图标提取器"""
        self._missing_dependencies = []
        if not PYWIN32_AVAILABLE:
            self._missing_dependencies.append("pywin32")
        if not PILLOW_AVAILABLE:
            self._missing_dependencies.append("Pillow")
        if self._missing_dependencies:
            self._dep_error = f"缺失依赖: {', '.join(self._missing_dependencies)}"
        else:
            self._dep_error = None
    
    def _check_deps(self):
        if getattr(self, '_dep_error', None):
            return False, self._dep_error
        return True, None
    
    def get_tray_icons(self, size: Union[int, IconSize] = IconSize.MEDIUM) -> List[ExtractedIcon]:
        """
        获取任务栏托盘区的所有图标
        
        Args:
            size: 图标尺寸，支持整数或IconSize枚举
            
        Returns:
            List[ExtractedIcon]: 托盘图标列表
        """
        if isinstance(size, IconSize):
            size = size.value
        
        tray_icons = []
        
        # 方法1: 使用改进的窗口枚举方法（更精确）
        tray_icons.extend(self._get_tray_icons_improved(size))
        
        # 方法2: 使用传统的窗口枚举方法（备用）
        if len(tray_icons) == 0:
            tray_icons.extend(self._get_tray_icons_by_window_enum(size))
        
        # 方法3: 使用Windows API直接获取（最后的备用方法）
        if len(tray_icons) == 0:
            tray_icons.extend(self._get_tray_icons_via_api(size))
        
        # 去重：基于进程ID和窗口标题
        unique_icons = []
        seen_keys = set()
        
        for icon in tray_icons:
            if icon.success:
                # 创建唯一键，基于进程ID和窗口标题
                key = f"{icon.info.process_id}_{icon.info.window_title}_{icon.info.tooltip}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    unique_icons.append(icon)
        
        return unique_icons
    
    def _get_son_windows(self, hwnd):
        """获取指定窗口的所有子窗口句柄"""
        hwnd_child_list = []
        
        def enum_child_callback(hwnd_child, param):
            hwnd_child_list.append(hwnd_child)
            return True
            
        win32gui.EnumChildWindows(hwnd, enum_child_callback, None)
        return hwnd_child_list
    
    def _get_classname(self, hwnd):
        """获取窗口类名"""
        try:
            class_name = win32gui.GetClassName(hwnd)
            return class_name
        except:
            return ""
    
    def _get_tray_icons_improved(self, size: int) -> List[ExtractedIcon]:
        """使用改进的方法获取托盘图标（基于2文件中的思路）"""
        tray_icons = []
        
        try:
            # 获取任务栏窗口
            tray_hwnd = win32gui.FindWindow("Shell_TrayWnd", None)
            if not tray_hwnd:
                return tray_icons
            
            # 获取任务栏的所有子窗口
            hwnd_child_list = self._get_son_windows(tray_hwnd)
            
            # 找到托盘通知区域及其后续窗口
            tuopan_hwd_list = []
            flag = False
            
            for child_hwnd in hwnd_child_list:
                class_name = self._get_classname(child_hwnd)
                
                # 找到TrayNotifyWnd后开始收集
                if class_name == 'TrayNotifyWnd':
                    flag = True
                
                # 收集托盘相关的窗口
                if flag:
                    tuopan_hwd_list.append(child_hwnd)
            
            # 从收集到的托盘窗口中提取图标
            for notify_hwnd in tuopan_hwd_list:
                # 只处理可能包含图标的窗口类型
                class_name = self._get_classname(notify_hwnd)
                if class_name in ['TrayNotifyWnd', 'ToolbarWindow32', 'SysPager']:
                    tray_icons.extend(self._extract_icons_from_notify_window_improved(notify_hwnd, size))
            
            # 查找溢出通知区域（Windows 10/11）
            overflow_hwnd = win32gui.FindWindow("NotifyIconOverflowWindow", None)
            if overflow_hwnd:
                tray_icons.extend(self._extract_icons_from_notify_window_improved(overflow_hwnd, size))
                
        except Exception as e:
            print(f"改进方法获取托盘图标失败: {e}")
        
        return tray_icons
    
    def _extract_icons_from_notify_window_improved(self, hwnd, size: int) -> List[ExtractedIcon]:
        """从通知窗口提取图标（改进版，更精确的过滤）"""
        icons = []
        
        def enum_child_proc(child_hwnd, param):
            try:
                class_name = win32gui.GetClassName(child_hwnd)
                
                # 只处理特定类型的控件
                if class_name in ["ToolbarWindow32", "Button", "Static", "SysImageView32"]:
                    # 获取窗口矩形，过滤掉不可见或尺寸异常的窗口
                    rect = win32gui.GetWindowRect(child_hwnd)
                    if not rect:
                        return True  # 跳过无效窗口
                        
                    width = rect[2] - rect[0]
                    height = rect[3] - rect[1]
                    
                    # 更严格的尺寸过滤：托盘图标通常为16x16到32x32像素
                    if width < 12 or height < 12 or width > 40 or height > 40:
                        return True  # 跳过尺寸不符的窗口
                    
                    # 检查窗口是否可见
                    if not win32gui.IsWindowVisible(child_hwnd):
                        return True  # 跳过隐藏窗口
                    
                    # 获取窗口文本（可能是工具提示）
                    window_text = win32gui.GetWindowText(child_hwnd)
                    
                    # 获取进程ID
                    try:
                        _, pid = win32process.GetWindowThreadProcessId(child_hwnd)
                    except:
                        pid = None
                    
                    # 尝试获取图标句柄
                    hicon = None
                    
                    # 方法1: WM_GETICON消息
                    try:
                        hicon = win32gui.SendMessage(child_hwnd, win32con.WM_GETICON, win32con.ICON_SMALL, 0)
                        if not hicon:
                            hicon = win32gui.SendMessage(child_hwnd, win32con.WM_GETICON, win32con.ICON_BIG, 0)
                        if not hicon:
                            hicon = win32gui.SendMessage(child_hwnd, win32con.WM_GETICON, 0, 0)
                    except:
                        pass
                    
                    # 方法2: 获取窗口的图标资源
                    if not hicon:
                        try:
                            hicon = win32gui.GetClassLong(child_hwnd, win32con.GCL_HICONSM)
                            if not hicon:
                                hicon = win32gui.GetClassLong(child_hwnd, win32con.GCL_HICON)
                        except:
                            pass
                    
                    # 方法3: 尝试通过进程获取可执行文件图标
                    if not hicon and pid:
                        try:
                            process_handle = win32api.OpenProcess(
                                win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, 
                                False, pid
                            )
                            exe_path = win32process.GetModuleFileNameEx(process_handle, 0)
                            win32api.CloseHandle(process_handle)
                            
                            # 从可执行文件提取图标
                            if os.path.exists(exe_path):
                                large, small = win32gui.ExtractIconEx(exe_path, 0, 1)
                                if large:
                                    hicon = large[0]
                                    win32gui.DestroyIcon(small[0] if small else 0)
                                elif small:
                                    hicon = small[0]
                        except:
                            pass
                    
                    if hicon:
                        try:
                            # 转换为PIL图像
                            image = self._hicon_to_pil(hicon, size)
                            
                            # 创建图标信息
                            icon_info = IconInfo(
                                path=f"TrayIcon_PID_{pid}" if not pid else f"PID_{pid}",
                                index=0,
                                width=size,
                                height=size,
                                bits_per_pixel=32,
                                format='ICO',
                                size_bytes=len(self._pil_to_bytes(image, 'PNG')),
                                process_id=pid,
                                window_title=window_text,
                                tooltip=window_text
                            )
                            
                            tray_icon = ExtractedIcon(
                                image=image,
                                raw_data=self._pil_to_bytes(image, 'PNG'),
                                info=icon_info,
                                success=True
                            )
                            param.append(tray_icon)
                            
                            # 清理图标句柄
                            try:
                                win32gui.DestroyIcon(hicon)
                            except:
                                pass
                                
                        except Exception as e:
                            print(f"转换托盘图标失败: {e}")
            except Exception as e:
                print(f"处理托盘子窗口失败: {e}")
            
            return True
        
        win32gui.EnumChildWindows(hwnd, enum_child_proc, icons)
        return icons
    
    def _get_tray_icons_by_window_enum(self, size: int) -> List[ExtractedIcon]:
        """通过窗口枚举获取托盘图标（传统方法）"""
        tray_icons = []
        
        try:
            # 查找Shell_TrayWnd窗口
            tray_hwnd = win32gui.FindWindow("Shell_TrayWnd", None)
            if not tray_hwnd:
                return tray_icons
            
            # 查找通知区域 - 尝试多种可能的窗口类名
            notify_hwnds = []
            
            # 标准通知区域
            notify_hwnd = win32gui.FindWindowEx(tray_hwnd, 0, "TrayNotifyWnd", None)
            if notify_hwnd:
                notify_hwnds.append(notify_hwnd)
            
            # SysPager窗口（Windows 10/11）
            syspager_hwnd = win32gui.FindWindowEx(tray_hwnd, 0, "SysPager", None)
            if syspager_hwnd:
                # 查找嵌套的TrayNotifyWnd
                nested_notify = win32gui.FindWindowEx(syspager_hwnd, 0, "TrayNotifyWnd", None)
                if nested_notify:
                    notify_hwnds.append(nested_notify)
            
            # 直接查找ToolbarWindow32
            toolbar_hwnd = win32gui.FindWindowEx(tray_hwnd, 0, "ToolbarWindow32", None)
            if toolbar_hwnd:
                notify_hwnds.append(toolbar_hwnd)
            
            # 如果没有找到任何通知窗口，尝试枚举所有子窗口
            if not notify_hwnds:
                def find_notify_windows(hwnd, param):
                    class_name = win32gui.GetClassName(hwnd)
                    if class_name in ['TrayNotifyWnd', 'ToolbarWindow32', 'SysPager']:
                        param.append(hwnd)
                    return True
                
                win32gui.EnumChildWindows(tray_hwnd, find_notify_windows, notify_hwnds)
            
            # 遍历所有找到的通知窗口
            for notify_hwnd in notify_hwnds:
                tray_icons.extend(self._extract_icons_from_notify_window(notify_hwnd, size))
            
            # 查找溢出通知区域（Windows 10/11）
            overflow_hwnd = win32gui.FindWindow("NotifyIconOverflowWindow", None)
            if overflow_hwnd:
                tray_icons.extend(self._extract_icons_from_notify_window(overflow_hwnd, size))
            
        except Exception as e:
            print(f"窗口枚举方法失败: {e}")
        
        return tray_icons
    
    def _is_descendant(self, root_hwnd, hwnd) -> bool:
        """判断 hwnd 是否为 root_hwnd 的后代（严格向上遍历父链）"""
        try:
            current = hwnd
            while current:
                parent = win32gui.GetParent(current)
                if parent == 0:
                    # 如果没有父窗口且不是根，则停止
                    return False
                if parent == root_hwnd:
                    return True
                current = parent
            return False
        except Exception:
            return False

    def _rect_intersects(self, r1, r2) -> bool:
        """判断两个矩形（left, top, right, bottom）是否有交集"""
        if not r1 or not r2:
            return False
        return not (r2[0] >= r1[2] or r2[2] <= r1[0] or r2[1] >= r1[3] or r2[3] <= r1[1])

    def _extract_icons_from_notify_window(self, hwnd, size: int) -> List[ExtractedIcon]:
        """从通知窗口提取图标（更严格的过滤）"""
        icons = []

        # 获取通知区域父窗口矩形，用于后续过滤
        try:
            parent_rect = win32gui.GetWindowRect(hwnd)
        except Exception:
            parent_rect = None

        def enum_child_proc(child_hwnd, param):
            try:
                class_name = win32gui.GetClassName(child_hwnd)

                # 对于 ToolbarWindow32，使用精确枚举方式
                if class_name == "ToolbarWindow32":
                    items = self._enum_toolbar_buttons_and_capture(child_hwnd, size, parent_rect=parent_rect)
                    for it in items:
                        param.append(it)
                    return True

                # 只处理最可能包含托盘图标的控件
                if class_name not in ["ToolbarWindow32", "Button", "Static", "SysImageView32", "SysPager", "TrayNotifyWnd"]:
                    return True

                # 过滤不可见或无效大小的项
                if not win32gui.IsWindowVisible(child_hwnd):
                    return True

                # 获取项矩形并确保位于notify区域内（允许少量溢出）
                try:
                    item_rect = win32gui.GetWindowRect(child_hwnd)
                except Exception:
                    item_rect = None

                if parent_rect and item_rect:
                    # 如果子项与父区域完全不相交，跳过（避免捕捉到其他面板上的按钮）
                    if not self._rect_intersects(parent_rect, item_rect):
                        return True

                    width = item_rect[2] - item_rect[0]
                    height = item_rect[3] - item_rect[1]
                    # 托盘图标通常在此范围内，超出则跳过
                    if width < 8 or height < 8 or width > 64 or height > 64:
                        return True

                # 获取窗口文本（可能为空）
                window_text = win32gui.GetWindowText(child_hwnd)

                # 获取进程ID（安全捕获）
                try:
                    _, pid = win32process.GetWindowThreadProcessId(child_hwnd)
                except Exception:
                    pid = None

                # 尝试获取图标句柄：有限且有优先级的多种方式
                hicon = None
                # 优先使用 WM_GETICON（目标控件可能是 toolbar item）
                try:
                    hicon = win32gui.SendMessage(child_hwnd, win32con.WM_GETICON, win32con.ICON_SMALL, 0)
                    if not hicon:
                        hicon = win32gui.SendMessage(child_hwnd, win32con.WM_GETICON, win32con.ICON_BIG, 0)
                except Exception:
                    hicon = None

                # 再尝试类图标
                if not hicon:
                    try:
                        hicon = win32gui.GetClassLong(child_hwnd, win32con.GCL_HICONSM)
                        if not hicon:
                            hicon = win32gui.GetClassLong(child_hwnd, win32con.GCL_HICON)
                    except Exception:
                        hicon = None

                # 最后尝试从进程 exe 提取（仅在有 pid 且 exe 存在时）
                if not hicon and pid:
                    try:
                        process_handle = win32api.OpenProcess(
                            win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
                            False, pid
                        )
                        exe_path = win32process.GetModuleFileNameEx(process_handle, 0)
                        win32api.CloseHandle(process_handle)
                        if exe_path and os.path.exists(exe_path):
                            large, small = win32gui.ExtractIconEx(exe_path, 0, 1)
                            if large:
                                hicon = large[0]
                                # 清理可能的 small 图标句柄
                                try:
                                    if small and small[0]:
                                        win32gui.DestroyIcon(small[0])
                                except Exception:
                                    pass
                            elif small:
                                hicon = small[0]
                    except Exception:
                        hicon = None

                # 如果获得图标句柄，才进一步转换与保存
                if hicon:
                    try:
                        image = self._hicon_to_pil(hicon, size)
                        raw = self._pil_to_bytes(image, 'PNG')
                        icon_info = IconInfo(
                            path=f"PID_{pid}" if pid else "Unknown",
                            index=0,
                            width=size,
                            height=size,
                            bits_per_pixel=32,
                            format='ICO',
                            size_bytes=len(raw),
                            process_id=pid,
                            window_title=window_text,
                            tooltip=window_text
                        )
                        tray_icon = ExtractedIcon(image=image, raw_data=raw, info=icon_info, success=True)
                        param.append(tray_icon)
                        # 尝试销毁图标句柄（若来源可销毁）
                        try:
                            win32gui.DestroyIcon(hicon)
                        except Exception:
                            pass
                    except Exception as e:
                        print(f"转换托盘图标失败: {e}")

            except Exception as e:
                print(f"处理托盘子窗口失败: {e}")

            return True

        # 仅枚举 notify 窗口的直接子项（减少误判）
        try:
            win32gui.EnumChildWindows(hwnd, enum_child_proc, icons)
        except Exception as e:
            print(f"枚举通知窗口子项失败: {e}")

        return icons

    def _get_tray_icons_via_api(self, size: int) -> List[ExtractedIcon]:
        """通过Windows API获取托盘图标（改进版）"""
        icons = []
        
        try:
            # 使用ctypes直接调用Windows API
            user32 = ctypes.windll.user32
            shell32 = ctypes.windll.shell32
            
            # 尝试获取任务栏窗口
            taskbar_hwnd = user32.FindWindowW("Shell_TrayWnd", None)
            if taskbar_hwnd:
                # 获取任务栏矩形
                rect = ctypes.wintypes.RECT()
                user32.GetWindowRect(taskbar_hwnd, ctypes.byref(rect))
                
                # 尝试查找通知区域
                def enum_notify_windows(hwnd, lparam):
                    class_name = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(hwnd, class_name, 256)
                    
                    if "TrayNotifyWnd" in class_name.value or "ToolbarWindow32" in class_name.value:
                        # 获取窗口进程ID
                        pid = ctypes.c_ulong()
                        tid = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                        
                        # 尝试获取图标
                        try:
                            hicon = user32.SendMessageW(hwnd, win32con.WM_GETICON, win32con.ICON_SMALL, 0)
                            if not hicon:
                                hicon = user32.SendMessageW(hwnd, win32con.WM_GETICON, win32con.ICON_BIG, 0)
                            
                            if hicon:
                                # 使用pywin32处理图标
                                image = self._hicon_to_pil(hicon, size)
                                
                                # 获取窗口标题
                                title_length = user32.GetWindowTextLengthW(hwnd)
                                title = ctypes.create_unicode_buffer(title_length + 1)
                                user32.GetWindowTextW(hwnd, title, title_length + 1)
                                
                                icon_info = IconInfo(
                                    path=f"API_TrayIcon_PID_{pid.value}",
                                    index=0,
                                    width=size,
                                    height=size,
                                    bits_per_pixel=32,
                                    format='ICO',
                                    size_bytes=len(self._pil_to_bytes(image, 'PNG')),
                                    process_id=pid.value,
                                    window_title=title.value,
                                    tooltip=title.value
                                )
                                
                                tray_icon = ExtractedIcon(
                                    image=image,
                                    raw_data=self._pil_to_bytes(image, 'PNG'),
                                    info=icon_info,
                                    success=True
                                )
                                icons.append(tray_icon)
                        except Exception as e:
                            print(f"API方法处理图标失败: {e}")
                    
                    return True
                
                # 枚举任务栏子窗口
                enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                user32.EnumChildWindows(taskbar_hwnd, enum_proc(enum_notify_windows), 0)
                
        except Exception as e:
            print(f"Windows API方法失败: {e}")
        
        return icons
    
    def _get_tray_icons_by_process_enum(self, size: int) -> List[ExtractedIcon]:
        """通过进程枚举获取托盘图标（备用方法）"""
        icons = []
        
        try:
            # 获取所有进程
            import psutil
            processes = []
            
            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    processes.append(proc)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # 检查每个进程是否有托盘图标
            for proc in processes:
                try:
                    pid = proc.info['pid']
                    exe_path = proc.info['exe']
                    
                    if exe_path and os.path.exists(exe_path):
                        # 检查进程是否有可见窗口
                        def enum_process_windows(hwnd, param):
                            _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
                            if window_pid == pid and win32gui.IsWindowVisible(hwnd):
                                class_name = win32gui.GetClassName(hwnd)
                                # 检查是否是系统托盘相关的窗口
                                if class_name in ["Shell_TrayWnd", "TrayNotifyWnd", "ToolbarWindow32"]:
                                    return False  # 停止枚举，这个进程可能有托盘图标
                            return True
                        
                        has_tray_window = True
                        try:
                            win32gui.EnumWindows(enum_process_windows, None)
                        except Exception:
                            has_tray_window = False
                        
                        if has_tray_window:
                            # 尝试从可执行文件提取图标
                            try:
                                large, small = win32gui.ExtractIconEx(exe_path, 0, 1)
                                hicon = None
                                if large:
                                    hicon = large[0]
                                    if small:
                                        win32gui.DestroyIcon(small[0])
                                elif small:
                                    hicon = small[0]
                                
                                if hicon:
                                    image = self._hicon_to_pil(hicon, size)
                                    
                                    icon_info = IconInfo(
                                        path=exe_path,
                                        index=0,
                                        width=size,
                                        height=size,
                                        bits_per_pixel=32,
                                        format='ICO',
                                        size_bytes=len(self._pil_to_bytes(image, 'PNG')),
                                        process_id=pid,
                                        window_title=proc.info['name'],
                                        tooltip=proc.info['name']
                                    )
                                    
                                    tray_icon = ExtractedIcon(
                                        image=image,
                                        raw_data=self._pil_to_bytes(image, 'PNG'),
                                        info=icon_info,
                                        success=True
                                    )
                                    icons.append(tray_icon)
                                    
                                    win32gui.DestroyIcon(hicon)
                            except Exception as e:
                                print(f"从进程 {proc.info['name']} 提取图标失败: {e}")
                                
                except Exception as e:
                    print(f"处理进程 {proc.info['name'] if 'name' in proc.info else 'unknown'} 失败: {e}")
                    
        except ImportError:
            print("psutil 未安装，跳过进程枚举方法")
        except Exception as e:
            print(f"进程枚举方法失败: {e}")
        
        return icons
    
    def _hicon_to_pil(self, hicon, size: int) -> 'Image.Image':
        """将图标句柄转换为PIL图像（改进版）"""
        ok, err = self._check_deps()
        if not ok:
            raise RuntimeError(err)
        
        try:
            # 创建内存DC
            hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
            hbmp = win32ui.CreateBitmap()
            hbmp.CreateCompatibleBitmap(hdc, size, size)
            hdc = hdc.CreateCompatibleDC()
            hdc.SelectObject(hbmp)
            
            # 绘制图标
            hdc.FillSolidRect((0, 0, size, size), 0xFFFFFF)  # 白色背景
            win32gui.DrawIconEx(
                hdc.GetHandleOutput(), 
                0, 0, hicon, 
                size, size, 
                0, None, 
                win32con.DI_NORMAL
            )
            
            # 转换为PIL Image
            bmpinfo = hbmp.GetInfo()
            bmpstr = hbmp.GetBitmapBits(True)
            
            image = Image.frombuffer(
                'RGB',
                (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                bmpstr, 'raw', 'BGRX', 0, 1
            )
            
            return image
            
        except Exception as e:
            # 备用方法：直接使用PIL创建图像
            print(f"标准图标转换失败，使用备用方法: {e}")
            try:
                # 创建一个简单的占位图像
                from PIL import ImageDraw
                image = Image.new('RGB', (size, size), color='gray')
                draw = ImageDraw.Draw(image)
                draw.text((10, 10), "Icon", fill='white')
                return image
            except:
                # 最后的手段：返回一个最小图像
                return Image.new('RGB', (size, size), color='red')
    
    def _pil_to_bytes(self, image: 'Image.Image', format: str = 'PNG') -> bytes:
        """将PIL图像转换为字节数据"""
        import io
        buffer = io.BytesIO()
        image.save(buffer, format=format)
        return buffer.getvalue()
    
    # 新增：捕获窗口指定矩形为PIL图像
    def _capture_window_rect(self, hwnd, rect, size: int):
        """使用 BitBlt 捕获窗口 rect 区域并返回 PIL.Image，按 size 缩放"""
        try:
            # rect: (left, top, right, bottom)
            left, top, right, bottom = rect
            width = right - left
            height = bottom - top
            if width <= 0 or height <= 0:
                return None

            # 获取窗口DC并创建兼容DC/位图
            hwnd_dc = win32gui.GetWindowDC(hwnd)
            src_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            mem_dc = src_dc.CreateCompatibleDC()
            bmp = win32ui.CreateBitmap()
            bmp.CreateCompatibleBitmap(src_dc, width, height)
            mem_dc.SelectObject(bmp)
            # 从窗口拷贝区域
            mem_dc.BitBlt((0, 0), (width, height), src_dc, (left - win32gui.GetWindowRect(hwnd)[0], top - win32gui.GetWindowRect(hwnd)[1]), win32con.SRCCOPY)

            # 转换为PIL Image
            bmpinfo = bmp.GetInfo()
            bmpstr = bmp.GetBitmapBits(True)
            image = Image.frombuffer('RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRX', 0, 1)
            # 缩放到目标尺寸
            if size and (image.width != size or image.height != size):
                image = image.resize((size, size), Image.LANCZOS)

            # 释放GDI对象
            try:
                mem_dc.DeleteDC()
                src_dc.DeleteDC()
                win32gui.ReleaseDC(hwnd, hwnd_dc)
                win32gui.DeleteObject(bmp.GetHandle())
            except Exception:
                pass

            return image
        except Exception:
            return None

    # 新增：精确枚举 Toolbar 按钮并返回提取结果列表
    def _enum_toolbar_buttons_and_capture(self, toolbar_hwnd, size: int, parent_rect=None) -> List[ExtractedIcon]:
        """使用 TB_BUTTONCOUNT + TB_GETITEMRECT 精确枚举 Toolbar 的按钮并截图"""
        icons = []
        try:
            user32 = ctypes.windll.user32
            WM_USER = 0x0400
            TB_BUTTONCOUNT = WM_USER + 24
            TB_GETITEMRECT = WM_USER + 29

            count = user32.SendMessageW(int(toolbar_hwnd), TB_BUTTONCOUNT, 0, 0)
            if count <= 0:
                return icons

            for idx in range(count):
                # 准备RECT
                rect = ctypes.wintypes.RECT()
                res = user32.SendMessageW(int(toolbar_hwnd), TB_GETITEMRECT, idx, ctypes.byref(rect))
                if not res:
                    continue
                item_rect = (rect.left, rect.top, rect.right, rect.bottom)
                # 将 item_rect 转换为屏幕坐标（GetWindowRect 基点）
                try:
                    tleft, ttop, tright, tbottom = win32gui.GetWindowRect(toolbar_hwnd)
                    screen_rect = (item_rect[0] + tleft, item_rect[1] + ttop, item_rect[2] + tleft, item_rect[3] + ttop)
                except Exception:
                    screen_rect = item_rect

                # 过滤尺寸与父区域不相交项
                width = screen_rect[2] - screen_rect[0]
                height = screen_rect[3] - screen_rect[1]
                if width < 8 or height < 8 or width > 128 or height > 128:
                    continue
                if parent_rect:
                    # 仅在父区域内的按钮才认为是托盘图标
                    if not (not (screen_rect[0] >= parent_rect[2] or screen_rect[2] <= parent_rect[0] or screen_rect[1] >= parent_rect[3] or screen_rect[3] <= parent_rect[1])):
                        pass  # 有交集则继续
                    # 若完全不相交，跳过
                    else:
                        continue

                # 捕获该按钮区域图像
                img = self._capture_window_rect(toolbar_hwnd, screen_rect, size)
                if img is None:
                    continue

                raw = self._pil_to_bytes(img, 'PNG')
                # 尝试获取 toolbar 所在进程 id（通常是 explorer）
                try:
                    _, pid = win32process.GetWindowThreadProcessId(toolbar_hwnd)
                except Exception:
                    pid = None

                icon_info = IconInfo(
                    path=f"Toolbar_{toolbar_hwnd}_btn_{idx}",
                    index=idx,
                    width=size,
                    height=size,
                    bits_per_pixel=32,
                    format='PNG',
                    size_bytes=len(raw),
                    process_id=pid,
                    window_title=None,
                    tooltip=None
                )
                icons.append(ExtractedIcon(image=img, raw_data=raw, info=icon_info, success=True))

        except Exception as e:
            print(f"精确枚举 Toolbar 按钮失败: {e}")

        return icons

def get_all_tray_icons(size: Union[int, IconSize] = IconSize.MEDIUM) -> List[ExtractedIcon]:
    """
    便捷函数：获取所有托盘图标
    
    Args:
        size: 图标尺寸
        
    Returns:
        List[ExtractedIcon]: 托盘图标列表
    """
    extractor = TrayIconExtractor()
    return extractor.get_tray_icons(size)


def main():
    """示例用法（改进版）"""
    if not PYWIN32_AVAILABLE or not PILLOW_AVAILABLE:
        print("错误: 缺少必要的依赖库 (pywin32, Pillow)")
        return
    
    print("正在获取任务栏托盘图标...")
    print("=" * 50)
    
    extractor = TrayIconExtractor()
    
    # 尝试不同尺寸获取更多图标
    sizes_to_try = [IconSize.SMALL, IconSize.MEDIUM, IconSize.LARGE]
    all_icons = []
    
    for size in sizes_to_try:
        print(f"尝试使用尺寸 {size.value}x{size.value}...")
        tray_icons = extractor.get_tray_icons(size)
        
        # 去重：基于进程ID和窗口标题
        for icon in tray_icons:
            if icon.success:
                key = f"{icon.info.process_id}_{icon.info.window_title}"
                if not any(key == f"{i.info.process_id}_{i.info.window_title}" for i in all_icons):
                    all_icons.append(icon)
    
    print(f"总共找到 {len(all_icons)} 个独特的托盘图标:")
    print("=" * 50)
    
    # 创建输出目录
    output_dir = "tray_icons_output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    for i, icon in enumerate(all_icons):
        if icon.success:
            print(f"图标 {i+1}:")
            print(f"  路径: {icon.info.path}")
            print(f"  进程ID: {icon.info.process_id}")
            print(f"  窗口标题: {icon.info.window_title or '无标题'}")
            print(f"  工具提示: {icon.info.tooltip or '无提示'}")
            print(f"  尺寸: {icon.info.width}x{icon.info.height}")
            print(f"  大小: {icon.info.size_bytes} 字节")
            
            # 保存图标到文件
            try:
                filename = f"tray_icon_{i+1}_pid{icon.info.process_id}.png"
                save_path = os.path.join(output_dir, filename)
                icon.image.save(save_path)
                print(f"  已保存到: {save_path}")
            except Exception as e:
                print(f"  保存失败: {e}")
            print("-" * 30)
        else:
            print(f"图标 {i+1}: 提取失败 - {icon.error}")
            print("-" * 30)
    
    if not all_icons:
        print("未找到任何托盘图标")
        print("尝试以下解决方案:")
        print("1. 确保pywin32和Pillow已正确安装")
        print("2. 以管理员权限运行程序")
        print("3. 检查Windows版本是否支持")
    
    # 显示统计信息
    print("\n统计信息:")
    print(f"成功提取的图标: {sum(1 for icon in all_icons if icon.success)}")
    print(f"失败的图标: {sum(1 for icon in all_icons if not icon.success)}")
    print(f"输出目录: {os.path.abspath(output_dir)}")


if __name__ == "__main__":
    main()