import win32gui
import win32con


def goodbye():
   """
   设置任务栏自动隐藏或显示
   :param hide: True 表示隐藏，False 表示显示
   """
   # 获取任务栏窗口句柄
   hwnd = win32gui.FindWindow("Shell_TrayWnd", None)
   if hwnd:
       # 根据参数决定隐藏或显示任务栏
       win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
   else:
       raise Exception("无法找到任务栏窗口句柄！")
   
def hello():
   """
   设置任务栏自动隐藏或显示
   :param hide: True 表示隐藏，False 表示显示
   """
   # 获取任务栏窗口句柄
   hwnd = win32gui.FindWindow("Shell_TrayWnd", None)
   if hwnd:
       # 根据参数决定隐藏或显示任务栏
       win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
   else:
       raise Exception("无法找到任务栏窗口句柄！")