from ctypes import windll, Structure, wintypes, sizeof, byref, c_longlong
import win32con
import win32gui
import win32print

# LRESULT 在部分 Python 版本的 ctypes.wintypes 中缺失，手动定义（64位有符号整数）
if not hasattr(wintypes, 'LRESULT'):
    wintypes.LRESULT = c_longlong

MB_OK = win32con.MB_OKCANCEL
MB_OKCANCEL = win32con.MB_OKCANCEL
MB_YESNO = win32con.MB_YESNO
MB_YESNOCANCEL = win32con.MB_YESNOCANCEL
MB_HELP = win32con.MB_HELP
MB_RETRYCANCEL = win32con.MB_RETRYCANCEL
MB_ICONWARNING = win32con.MB_ICONWARNING
MB_ICONINFORMATION = win32con.MB_ICONINFORMATION
MB_ICONASTERISK = win32con.MB_ICONASTERISK
MB_ICONQUESTION = win32con.MB_ICONQUESTION
MB_ICONSTOP = win32con.MB_ICONSTOP

IDYES = win32con.IDYES
IDNO = win32con.IDNO
IDRETRY = win32con.IDRETRY
IDCANCEL = win32con.IDCANCEL

_user32 = windll.user32

# ========== DPI 感知（进程生命周期内只需设置一次） ==========
_user32.SetProcessDPIAware()

# ========== 屏幕尺寸缓存 ==========
# 主显示器物理分辨率（GetDeviceCaps 获取真实像素，不受 DPI 缩放影响）
_hdc = win32gui.GetDC(0)
REAL_SCREEN_WIDTH = win32print.GetDeviceCaps(_hdc, win32con.DESKTOPHORZRES)
REAL_SCREEN_HEIGHT = win32print.GetDeviceCaps(_hdc, win32con.DESKTOPVERTRES)
win32gui.ReleaseDC(0, _hdc)

# 逻辑分辨率（受 DPI 缩放影响）
LOGICAL_SCREEN_WIDTH = _user32.GetSystemMetrics(0)   # SM_CXSCREEN
LOGICAL_SCREEN_HEIGHT = _user32.GetSystemMetrics(1)   # SM_CYSCREEN

# 主显示器工作区矩形（排除任务栏），屏幕绝对坐标，模块加载时缓存
_primary_hmon = _user32.MonitorFromPoint(wintypes.POINT(0, 0), 2)  # MONITOR_DEFAULTTONEAREST

class _MONITORINFO(Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]

_mi = _MONITORINFO()
_mi.cbSize = sizeof(_MONITORINFO)
_user32.GetMonitorInfoW(_primary_hmon, byref(_mi))
PRIMARY_WORK_LEFT = _mi.rcWork.left
PRIMARY_WORK_TOP = _mi.rcWork.top
PRIMARY_WORK_RIGHT = _mi.rcWork.right
PRIMARY_WORK_BOTTOM = _mi.rcWork.bottom
del _mi, _primary_hmon

HWND_TRAY = win32gui.FindWindow("Shell_TrayWnd", None)


def get_window_rect(hwnd: int):
    return win32gui.GetWindowRect(hwnd)

def hide_window(hwnd: int):
    _user32.ShowWindow(hwnd, win32con.SW_HIDE)

def show_window(hwnd: int):
    _user32.ShowWindow(hwnd, win32con.SW_SHOW)

def set_window_topmost(hwnd: int):
    """将窗口设为 TOPMOST（HWND_TOPMOST）"""
    _user32.SetWindowPos(
        hwnd, win32con.HWND_TOPMOST,
        0, 0, 0, 0,
        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
    )

def messagebox(title: str, text: str, buttons: int = MB_OK) -> int:
    """
    显示消息框
    Args:
        title (str): 标题
        text (str): 文本
        buttons (int, optional): 按钮. 默认为MB_OK.可选值:[MB_OK,MB_OKCANCEL,MB_YESNO,MB_YESNOCANCEL,MB_HELP,MB_RETRYCANCEL,MB_ICONWARNING,MB_ICONINFORMATION,MB_ICONASTERISK,MB_ICONQUESTION,MB_ICONSTOP]
    Returns:
        int: 按钮索引
       """
    return _user32.MessageBoxW(0, text, title, buttons)


# ========== AppBar（屏幕保留区域管理） ==========
# 使用 Windows AppBar API 管理工作区，比 SystemParametersInfo 更可靠
# 参考：https://learn.microsoft.com/en-us/windows/win32/shell/appbar

from ctypes import wintypes as _wt
import ctypes

_shell32 = windll.shell32

# kernel32：GetModuleHandleW 必须设置 64 位返回类型，否则句柄被截断
_kernel32 = windll.kernel32
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE
_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

# AppBar 常量
_ABM_NEW = 0x00000000
_ABM_REMOVE = 0x00000001
_ABM_SETPOS = 0x00000003
_ABE_BOTTOM = 3
_WM_APP = 0x8000


class _APPBARDATA(Structure):
    _fields_ = [
        ("cbSize", _wt.UINT),
        ("hWnd", _wt.HWND),
        ("uCallbackMessage", _wt.UINT),
        ("uEdge", _wt.UINT),
        ("rc", wintypes.RECT),
        ("lParam", _wt.LPARAM),
    ]


# WNDCLASSEXW 在 Python 3.13 中被移除，手动定义
class _WNDCLASSEXW(Structure):
    _fields_ = [
        ("cbSize", _wt.UINT),
        ("style", _wt.UINT),
        ("lpfnWndProc", ctypes.WINFUNCTYPE(wintypes.LRESULT, _wt.HWND, _wt.UINT, _wt.WPARAM, _wt.LPARAM)),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", _wt.HMODULE),
        ("hIcon", _wt.HANDLE),
        ("hCursor", _wt.HANDLE),
        ("hbrBackground", _wt.HANDLE),
        ("lpszMenuName", _wt.LPCWSTR),
        ("lpszClassName", _wt.LPCWSTR),
        ("hIconSm", _wt.HANDLE),
    ]


# WndProc 回调类型（WINFUNCTYPE = Windows 调用约定，64位系统必需）
_WNDPROC = ctypes.WINFUNCTYPE(
    wintypes.LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)

# 给 DefWindowProcW 设置正确的参数类型，避免 64 位参数溢出导致崩溃
_user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.DefWindowProcW.restype = wintypes.LRESULT

# 窗口创建/注册函数设置 64 位安全签名
_user32.RegisterClassExW.argtypes = [ctypes.c_void_p]
_user32.RegisterClassExW.restype = wintypes.ATOM
_user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HANDLE, wintypes.HINSTANCE, ctypes.c_void_p,
]
_user32.CreateWindowExW.restype = wintypes.HWND

# AppBar 宿主窗口句柄和注册状态
_appbar_hwnd = None
_appbar_registered = False
_appbar_wndproc_ref = None  # 防止回调被 GC 回收


def _appbar_wndproc(hwnd, msg, wparam, lparam):
    """AppBar 宿主窗口回调。"""
    try:
        return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)
    except Exception:
        return 0


# AppBar 宿主窗口类名（模块级常量，确保字符串生命周期有效）
_APPBAR_CLASS_NAME = "DockAppBarHostClass"
_APPBAR_WINDOW_NAME = "DockAppBarHost"


def _create_appbar_host_window():
    """创建隐藏的 AppBar 宿主窗口。"""
    global _appbar_hwnd, _appbar_wndproc_ref

    _appbar_wndproc_ref = _WNDPROC(_appbar_wndproc)

    wc = _WNDCLASSEXW()
    wc.cbSize = sizeof(_WNDCLASSEXW)
    wc.lpfnWndProc = _appbar_wndproc_ref
    wc.hInstance = _kernel32.GetModuleHandleW(None)
    wc.lpszClassName = _APPBAR_CLASS_NAME

    atom = _user32.RegisterClassExW(byref(wc))
    if not atom:
        raise RuntimeError(f"AppBar 窗口类注册失败 error={ctypes.get_last_error()}")

    _appbar_hwnd = _user32.CreateWindowExW(
        0, _APPBAR_CLASS_NAME, _APPBAR_WINDOW_NAME,
        0, 0, 0, 0, 0, 0, 0, wc.hInstance, 0
    )
    if not _appbar_hwnd:
        raise RuntimeError(f"AppBar 宿主窗口创建失败 error={ctypes.get_last_error()}")
    return _appbar_hwnd


def set_appbar_bottom(dock_top: int):
    """将程序栏注册为底部 AppBar，系统自动调整工作区。

    注册后，最大化窗口会停在 AppBar 上方，退出时自动恢复。
    请求的 rc.top 即新的工作区底部（dock 栏顶端）。

    Args:
        dock_top: dock 栏顶端的 Y 坐标（屏幕像素，即新工作区底部）
    """
    global _appbar_registered

    hwnd = _create_appbar_host_window()

    abd = _APPBARDATA()
    abd.cbSize = sizeof(_APPBARDATA)
    abd.hWnd = hwnd
    abd.uCallbackMessage = _WM_APP
    abd.uEdge = _ABE_BOTTOM
    abd.rc.left = 0
    abd.rc.top = dock_top
    abd.rc.right = REAL_SCREEN_WIDTH
    abd.rc.bottom = REAL_SCREEN_HEIGHT

    # 注册 AppBar
    ret_new = _shell32.SHAppBarMessage(_ABM_NEW, byref(abd))
    _appbar_registered = True

    # 设置位置（系统会据此调整工作区）
    ret_pos = _shell32.SHAppBarMessage(_ABM_SETPOS, byref(abd))
    print(f"[AppBar] 注册完成 hwnd=0x{hwnd:X} NEW={ret_new} SETPOS={ret_pos} "
          f"rc=({abd.rc.left},{abd.rc.top},{abd.rc.right},{abd.rc.bottom})")


def remove_appbar():
    """注销 AppBar，恢复原始工作区。"""
    global _appbar_registered, _appbar_hwnd
    hwnd = _appbar_hwnd
    if hwnd:
        abd = _APPBARDATA()
        abd.cbSize = sizeof(_APPBARDATA)
        abd.hWnd = hwnd
        ret = _shell32.SHAppBarMessage(_ABM_REMOVE, byref(abd))
        print(f"[AppBar] 注销 hwnd=0x{hwnd:X} REMOVE={ret}")
        _user32.DestroyWindow(hwnd)
        _appbar_hwnd = None
    _appbar_registered = False
