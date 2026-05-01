from ctypes import windll
import os
import win32con
import win32gui
import win32print

HDC = win32gui.GetDC(0)
SCREEN_RECT = (0, 0, windll.user32.GetSystemMetrics(0), windll.user32.GetSystemMetrics(1))
REAL_SCREEN_RECT = (0, 0, win32print.GetDeviceCaps(HDC, win32con.DESKTOPHORZRES), win32print.GetDeviceCaps(HDC, win32con.DESKTOPVERTRES))
REAL_SCREEN_WIDTH = win32print.GetDeviceCaps(HDC, win32con.DESKTOPHORZRES)
REAL_SCREEN_HEIGHT = win32print.GetDeviceCaps(HDC, win32con.DESKTOPVERTRES)
SCREEN_WIDTH = REAL_SCREEN_RECT[2]
SCREEN_HEIGHT = REAL_SCREEN_RECT[3]



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

def get_user32():
    return windll.user32

def get_shell32():
    return windll.shell32

def get_hwnd(title: str):
    return win32gui.FindWindow(title, None)

def get_window_rect(hwnd: int):
    return win32gui.GetWindowRect(hwnd)

def hide_window(hwnd: int):
    get_user32().ShowWindow(hwnd, win32con.SW_HIDE)

def show_window(hwnd: int):
    get_user32().ShowWindow(hwnd, win32con.SW_SHOW)

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
    return get_user32().MessageBoxW(0, text, title, buttons)
