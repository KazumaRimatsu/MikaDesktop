from ctypes import windll
import win32con
import win32gui
import win32print

_user32 = windll.user32

_hdc = win32gui.GetDC(0)
REAL_SCREEN_WIDTH = win32print.GetDeviceCaps(_hdc, win32con.DESKTOPHORZRES)
REAL_SCREEN_HEIGHT = win32print.GetDeviceCaps(_hdc, win32con.DESKTOPVERTRES)
win32gui.ReleaseDC(0, _hdc)



HWND_TRAY = win32gui.FindWindow("Shell_TrayWnd", None)

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

def get_window_rect(hwnd: int):
    return win32gui.GetWindowRect(hwnd)

def hide_window(hwnd: int):
    _user32.ShowWindow(hwnd, win32con.SW_HIDE)

def show_window(hwnd: int):
    _user32.ShowWindow(hwnd, win32con.SW_SHOW)

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
