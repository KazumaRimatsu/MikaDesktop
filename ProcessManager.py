import psutil
import win32gui
import win32process
import win32con
import win32api
import os
import sys

import MakeAppIcon
import hashlib


class ProcessManager:
    def __init__(self):
        self.except_processes = [
            'shellexperiencehost.exe',
            'applicationframehost.exe',
            'startmenuexperiencehost.exe',
            'widgets.exe',
            'widgetservice.exe',
            'python.exe'
        ]
        # lazy extractor instance (复用 CatchIco 提取器，避免频繁创建)
        self._extractor = None
        try:
            from CatchIco import WindowsIconExtractor
            # 不立即实例化过重资源，延迟在需要时创建
            self._extractor_class = WindowsIconExtractor
        except Exception:
            self._extractor_class = None

    def _norm_path(self, p):
        try:
            return os.path.abspath(p).lower()
        except Exception:
            return str(p).lower()

    def set_except_processes(self, proc_list):
        """
        更新排除进程列表（用户可通过设置界面调用）。
        规范化为小写、去重、每项尽量带 .exe（若用户只写了进程名则自动补 .exe）。
        """
        try:
            if not proc_list:
                return
            normalized = []
            for s in proc_list:
                if not s:
                    continue
                if not isinstance(s, str):
                    s = str(s)
                s = s.strip().lower()
                if not s:
                    continue
                # 若用户只写了名称（例如 "python"），自动补 .exe；若已有扩展名则保留
                if '.' not in s:
                    s = s + '.exe'
                if s not in normalized:
                    normalized.append(s)
            if normalized:
                self.except_processes = normalized
        except Exception as e:
            print(f"设置排除进程列表时出错: {e}")
            # 保持原始列表不变
            pass

    def _get_extractor(self):
        if self._extractor is None and self._extractor_class:
            try:
                self._extractor = self._extractor_class()
            except Exception as e:
                self._extractor = None
        return self._extractor

    def is_process_running(self, app_path):
        """检查指定路径的应用是否正在运行 - 仅当有可见窗口时"""
        try:
            normalized_app = self._norm_path(app_path)
             # 遍历所有窗口，查找与应用路径匹配的窗口
            def enum_windows_proc(hwnd, param):
                if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd) != '':
                    try:
                        # 获取窗口的进程ID
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        proc = psutil.Process(pid)
                         
                         # 获取进程的可执行文件路径
                        proc_path = proc.exe().lower()
                        normalized_app_path = os.path.abspath(app_path).lower()
                                        # 比较路径是否匹配
                        if os.path.abspath(proc_path).lower() == normalized_app_path:
                            proc_path = proc.exe()
                        if proc_path and self._norm_path(proc_path) == normalized_app:
                             # 检查是否为系统服务或程序本身
                             
                             # 检查是否为系统服务
                            process_name = proc.name().lower()
                            if process_name in self.except_processes:
                                 return True  # 继续遍历，但不添加到结果中
                            
                             # 检查是否为程序本身
                            current_process_name = os.path.basename(sys.executable).lower()
                            if process_name == current_process_name.lower():
                                return True  # 继续遍历，但不添加到结果中
                            
                            # 窗口存在且可见，且不是系统服务或程序本身，说明应用正在运行
                            param.append(hwnd)  # 添加窗口句柄而不是布尔值
                            return False  # 停止遍历
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass
                    except Exception as e:
                        print(f"检查窗口 {hwnd} 时出错: {e}")
                return True  # 继续遍历
            
            result = []
            win32gui.EnumWindows(enum_windows_proc, result)
            
            # 只有当找到对应窗口时才认为应用正在运行
            return len(result) > 0
        except Exception as e:
            print(f"检查窗口时出错: {e}")
            return False

    def get_running_processes(self, known_apps_paths):
        """获取系统中所有正在运行的进程，找出未添加但运行的应用"""
        running_processes = {}
        try:
            # 先一次性枚举所有可见窗口，建立 pid -> visible-window-info 映射（提升性能，避免每个进程都调用 EnumWindows）
            pid_windows = {}
            def _collect_windows(hwnd, param):
                try:
                    if win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd):
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        title = win32gui.GetWindowText(hwnd)
                        if title and title.strip():
                            pid_windows.setdefault(pid, []).append((hwnd, title, win32gui.GetClassName(hwnd)))
                except Exception:
                    pass
                return True
            try:
                win32gui.EnumWindows(_collect_windows, None)
            except Exception:
                pass

            # 现在遍历进程并快速判断
            for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
                try:
                    process_info = proc.info
                    exe_path = process_info.get('exe')
                    if not exe_path or not os.path.exists(exe_path):
                        continue

                    pid = process_info.get('pid')
                    windows = pid_windows.get(pid)
                    if not windows:
                        continue  # 没有可见窗口，跳过

                    # 过滤特殊类名与系统进程
                    valid_window_found = False
                    for hwnd, title, cls in windows:
                        if cls in ["MSCTFIME UI", "IAIMETIPWndClass", "TIPBand", "Candidate"]:
                            continue
                        valid_window_found = True
                        break
                    if not valid_window_found:
                        continue

                    app_name = process_info.get('name', '').replace('.exe', '')
                    # 检查是否已知（固定或用户添加）
                    is_known_app = any(self._norm_path(p) == self._norm_path(exe_path) for p in known_apps_paths)
                    if is_known_app:
                        continue

                    if exe_path not in running_processes:
                        # 使用图标提取函数获取图标（可能为 None）
                        icon_path = None
                        try:
                            icon_path = self.extract_icon(exe_path) or ''
                        except Exception:
                            icon_path = ''
                        running_processes[exe_path] = {
                            'name': app_name,
                            'path': exe_path,
                            'icon': icon_path
                        }

                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
                except Exception as e:
                    print(f"处理进程 {process_info.get('name', 'Unknown')} 时出错: {e}")
                    continue
        except Exception as e:
            print(f"获取运行进程时出错: {e}")
        
        return running_processes

    def get_app_visible_windows(self, app_path):
        """获取应用的所有可见窗口"""
        try:
            app_filename = os.path.basename(app_path).lower()
            
            visible_windows = []
            
            def enum_windows_proc(hwnd, param):
                if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd) != '':
                    try:
                        # 获取窗口的进程ID
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        proc = psutil.Process(pid)
                        
                        # 获取进程的可执行文件路径
                        proc_path = proc.exe().lower()
                        normalized_app_path = os.path.abspath(app_path).lower()
                        
                        # 比较路径是否匹配
                        if os.path.abspath(proc_path).lower() == normalized_app_path:
                            # 检查是否为系统服务或程序本身
                            process_name = proc.name().lower()
                            
                            # 检查是否为系统服务
                            if process_name in self.except_processes:
                                return True  # 继续遍历，但不添加到结果中
                            
                            # 检查是否为程序本身
                            current_process_name = os.path.basename(sys.executable).lower()
                            if process_name == current_process_name.lower():
                                return True  # 继续遍历，但不添加到结果中
                            
                            # 获取窗口标题
                            window_title = win32gui.GetWindowText(hwnd)
                            
                            # 窗口存在且可见，添加到结果列表
                            param.append((hwnd, window_title))
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass
                    except Exception as e:
                        print(f"检查窗口 {hwnd} 时出错: {e}")
                return True  # 继续遍历
            
            win32gui.EnumWindows(enum_windows_proc, visible_windows)
            
            return visible_windows
        except Exception as e:
            print(f"检查窗口时出错: {e}")
            return []

    def close_app_window(self, app_path):
        """关闭应用窗口"""
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
                    pass
            return True  # 继续枚举其他窗口

        try:
            win32gui.EnumWindows(enum_windows_proc, 0)
        except Exception as e:
            print(f"关闭窗口时出错: {e}")

    def terminate_app_process(self, app_path):
        """终止应用进程"""
        app_filename = os.path.basename(app_path)
        
        try:
            # 遍历所有进程，找到匹配的应用进程并终止
            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    process_info = proc.info
                    if process_info['exe'] and os.path.abspath(process_info['exe']) == os.path.abspath(app_path):
                        # 检查是否为系统服务
                        process_name = process_info['name'].lower()
                        if process_name in self.except_processes:
                            continue  # 跳过系统服务
                        
                        # 检查是否为程序本身
                        current_process_name = os.path.basename(sys.executable).lower()
                        if process_name == current_process_name:
                            continue  # 跳过程序自身
                        
                        # 终止进程
                        proc.terminate()
                        print(f"已终止进程: {process_info['name']} (PID: {proc.pid})")
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
                except Exception as e:
                    print(f"终止进程 {proc.name()} 时出错: {e}")
                    continue
        except Exception as e:
            print(f"终止应用进程时出错: {e}")
            
    def extract_icon(self, exe_path):
        """提取图标，使用CatchIco.py中的功能并通过 MakeAppIcon.compose_on_template 生成统一风格图标"""
        try:
            # 使用包含路径哈希的缓存名，避免不同路径同名冲突
            cache_dir = os.path.join(os.getenv('LOCALAPPDATA') or os.path.expanduser("~"), 'AppIcon')
            os.makedirs(cache_dir, exist_ok=True)
            name = os.path.splitext(os.path.basename(exe_path))[0]
            md5 = hashlib.md5((os.path.abspath(exe_path)).encode('utf-8')).hexdigest()[:8]
            icon_path = os.path.join(cache_dir, f"{name}_{md5}.png")
            if os.path.exists(icon_path):
                return icon_path
            extractor = self._get_extractor()
            if not extractor:
                return None

            extracted_icon = extractor.extract_file_icon(exe_path, size=64)
            if extracted_icon.success and extracted_icon.image:
                try:
                    # 优先使用合成库生成统一风格图标
                    try:
                        composed_bytes = MakeAppIcon.compose_on_template(extracted_icon.image)
                        with open(icon_path, "wb") as f:
                            f.write(composed_bytes)
                        return icon_path
                    except Exception:
                        # 合成失败则回退为直接保存提取到的图像
                        extracted_icon.image.save(icon_path)
                        return icon_path
                except Exception as e:
                    print(f"保存/合成图标时出错: {e}")
                    return None
            else:
                return None
        except Exception as e:
            print(f"使用图标提取器出错: {e}")
            return None

    def is_window_fullscreen(self, hwnd) -> bool:
        """判断给定窗口句柄是否覆盖其所在显示器的工作区（近似全屏）"""
        try:
            if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
                return False
            # 获取窗口矩形
            rect = win32gui.GetWindowRect(hwnd)  # (left, top, right, bottom)
            # 获取窗口所在显示器
            try:
                monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONULL)
                if not monitor:
                    monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTOPRIMARY)
                mon_info = win32api.GetMonitorInfo(monitor)
                mon_rect = mon_info.get('Monitor')  # (left, top, right, bottom)
            except Exception:
                # 退回到主屏幕分辨率
                mon_rect = (0, 0, win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1))
            # 将矩形转换为整型并比较
            win_rect = tuple(int(x) for x in rect)
            mon_rect = tuple(int(x) for x in mon_rect)
            # 若窗口矩形覆盖或等于显示器矩形，视为全屏（允许微小偏差）
            # 使用容差2像素以容忍边框差异
            tol = 2
            return (abs(win_rect[0] - mon_rect[0]) <= tol and
                    abs(win_rect[1] - mon_rect[1]) <= tol and
                    abs(win_rect[2] - mon_rect[2]) <= tol and
                    abs(win_rect[3] - mon_rect[3]) <= tol)
        except Exception as e:
            # 出错时保守返回 False
            return False

    def is_app_fullscreen(self, app_path) -> bool:
        """判断指定应用（路径）是否有任意可见窗口处于全屏"""
        try:
            visible = self.get_app_visible_windows(app_path)
            for hwnd, _ in visible:
                if self.is_window_fullscreen(hwnd):
                    return True
        except Exception:
            pass
        return False

    def any_apps_fullscreen(self, app_paths) -> bool:
        """
        对传入的应用路径列表逐个判断，若任意应用有全屏窗口则返回 True。
        该方法复用 get_app_visible_windows，避免重复枚举进程窗口。
        """
        try:
            # 去重并快速返回
            seen = set()
            for p in app_paths:
                if not p:
                    continue
                np = os.path.abspath(p).lower()
                if np in seen:
                    continue
                seen.add(np)
                if self.is_app_fullscreen(p):
                    return True
        except Exception:
            pass
        return False