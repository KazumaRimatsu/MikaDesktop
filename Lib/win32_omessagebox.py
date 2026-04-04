"""
Windows原生消息框工具模块
"""

import ctypes
from ctypes import wintypes
from typing import Optional, Literal

# Windows消息框常量
MB_OK = 0x00000000
MB_OKCANCEL = 0x00000001
MB_ABORTRETRYIGNORE = 0x00000002
MB_YESNOCANCEL = 0x00000003
MB_YESNO = 0x00000004
MB_RETRYCANCEL = 0x00000005
MB_CANCELTRYCONTINUE = 0x00000006

# 图标类型
MB_ICONERROR = 0x00000010
MB_ICONQUESTION = 0x00000020
MB_ICONWARNING = 0x00000030
MB_ICONINFORMATION = 0x00000040

# 默认按钮
MB_DEFBUTTON1 = 0x00000000
MB_DEFBUTTON2 = 0x00000100
MB_DEFBUTTON3 = 0x00000200
MB_DEFBUTTON4 = 0x00000300

# 模态
MB_APPLMODAL = 0x00000000
MB_SYSTEMMODAL = 0x00001000
MB_TASKMODAL = 0x00002000

# 返回结果
IDOK = 1
IDCANCEL = 2
IDABORT = 3
IDRETRY = 4
IDIGNORE = 5
IDYES = 6
IDNO = 7
IDCLOSE = 8
IDHELP = 9
IDTRYAGAIN = 10
IDCONTINUE = 11

# 加载user32.dll
user32 = ctypes.windll.user32
MessageBoxW = user32.MessageBoxW
MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]
MessageBoxW.restype = wintypes.INT

def show_messagebox(
    title: str,
    text: str,
    style: int = MB_OK | MB_ICONINFORMATION,
    hwnd: Optional[int] = None
) -> int:
    """
    显示Windows原生消息框
    
    Args:
        title: 消息框标题
        text: 消息框内容
        style: 消息框样式（按钮+图标+默认按钮等）
        hwnd: 父窗口句柄，None表示无父窗口
    
    Returns:
        用户点击的按钮ID
    """
    return MessageBoxW(hwnd, text, title, style)

def show_info(title: str, text: str, hwnd: Optional[int] = None) -> int:
    """
    显示信息提示框（确定按钮）
    
    Args:
        title: 标题
        text: 内容
        hwnd: 父窗口句柄
    
    Returns:
        IDOK (1)
    """
    return show_messagebox(title, text, MB_OK | MB_ICONINFORMATION, hwnd)

def show_warning(title: str, text: str, hwnd: Optional[int] = None) -> int:
    """
    显示警告框（确定按钮）
    
    Args:
        title: 标题
        text: 内容
        hwnd: 父窗口句柄
    
    Returns:
        IDOK (1)
    """
    return show_messagebox(title, text, MB_OK | MB_ICONWARNING, hwnd)

def show_error(title: str, text: str, hwnd: Optional[int] = None) -> int:
    """
    显示错误框（确定按钮）
    
    Args:
        title: 标题
        text: 内容
        hwnd: 父窗口句柄
    
    Returns:
        IDOK (1)
    """
    return show_messagebox(title, text, MB_OK | MB_ICONERROR, hwnd)

def show_question(
    title: str, 
    text: str, 
    buttons: Literal["yesno", "yesnocancel", "okcancel"] = "yesno",
    default_button: Literal[1, 2, 3] = 1,
    hwnd: Optional[int] = None
) -> int:
    """
    显示询问框
    
    Args:
        title: 标题
        text: 内容
        buttons: 按钮类型
            "yesno": 是/否
            "yesnocancel": 是/否/取消
            "okcancel": 确定/取消
        default_button: 默认按钮（1, 2, 3）
        hwnd: 父窗口句柄
    
    Returns:
        用户点击的按钮ID
    """
    # 设置按钮类型
    if buttons == "yesno":
        button_style = MB_YESNO
    elif buttons == "yesnocancel":
        button_style = MB_YESNOCANCEL
    elif buttons == "okcancel":
        button_style = MB_OKCANCEL
    else:
        button_style = MB_YESNO
    
    # 设置默认按钮
    if default_button == 1:
        default_style = MB_DEFBUTTON1
    elif default_button == 2:
        default_style = MB_DEFBUTTON2
    elif default_button == 3:
        default_style = MB_DEFBUTTON3
    else:
        default_style = MB_DEFBUTTON1
    
    style = button_style | MB_ICONQUESTION | default_style
    return show_messagebox(title, text, style, hwnd)

def show_critical(title: str, text: str, hwnd: Optional[int] = None) -> int:
    """
    显示严重错误框（确定按钮）
    
    Args:
        title: 标题
        text: 内容
        hwnd: 父窗口句柄
    
    Returns:
        IDOK (1)
    """
    return show_messagebox(title, text, MB_OK | MB_ICONERROR, hwnd)

def get_hwnd_from_qwidget(qwidget) -> Optional[int]:
    """
    从QWidget获取Windows窗口句柄
    
    Args:
        qwidget: PySide6 QWidget对象
    
    Returns:
        Windows窗口句柄，如果无法获取则返回None
    """
    try:
        # 尝试获取QWidget的winId()，转换为整数句柄
        if hasattr(qwidget, 'winId'):
            win_id = qwidget.winId()
            if win_id:
                return int(win_id)
    except:
        pass
    return None

# 兼容性函数，模拟QMessageBox的接口
def information(parent, title: str, text: str) -> int:
    """信息提示框（兼容QMessageBox.information）"""
    hwnd = get_hwnd_from_qwidget(parent) if parent else None
    return show_info(title, text, hwnd)

def warning(parent, title: str, text: str) -> int:
    """警告框（兼容QMessageBox.warning）"""
    hwnd = get_hwnd_from_qwidget(parent) if parent else None
    return show_warning(title, text, hwnd)

def critical(parent, title: str, text: str) -> int:
    """错误框（兼容QMessageBox.critical）"""
    hwnd = get_hwnd_from_qwidget(parent) if parent else None
    return show_error(title, text, hwnd)

def question(parent, title: str, text: str, buttons: int = MB_YESNO, default_button: int = 0) -> int:
    """
    询问框（兼容QMessageBox.question）
    
    Args:
        parent: 父窗口
        title: 标题
        text: 内容
        buttons: 按钮组合（使用MB_YESNO等常量）
        default_button: 默认按钮（0=第一个，1=第二个，2=第三个）
    
    Returns:
        用户点击的按钮ID
    """
    hwnd = get_hwnd_from_qwidget(parent) if parent else None
    
    # 转换按钮类型
    if buttons == (MB_YESNO | MB_ICONQUESTION):
        button_type = "yesno"
    elif buttons == (MB_YESNOCANCEL | MB_ICONQUESTION):
        button_type = "yesnocancel"
    elif buttons == (MB_OKCANCEL | MB_ICONQUESTION):
        button_type = "okcancel"
    else:
        button_type = "yesno"
    
    return show_question(title, text, button_type, default_button + 1, hwnd)

# QMessageBox按钮常量兼容
Yes = IDYES
No = IDNO
Ok = IDOK
Cancel = IDCANCEL