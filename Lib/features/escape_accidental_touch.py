import ctypes
from pynput import mouse
import time
import threading
import requests
from typing import Optional
from ..threads.lifecycle import ThreadBase, ThreadConfig, ThreadState, ThreadError


class DeviceData:
    def __init__(self):
        user32 = ctypes.windll.user32
        self.screen_width = user32.GetSystemMetrics(0)
        self.redline_x = [self.screen_width * 0.05, self.screen_width * 0.95]


class Monitor(ThreadBase):
    def __init__(self, device_data: DeviceData, max_data_count: int = 1024, config: Optional[ThreadConfig] = None):
        # 创建简化配置（如果未提供）
        if config is None:
            config = ThreadConfig(
                name="AccidentalTouchMonitor",
                daemon=True,
                auto_start=False
            )
        
        # 初始化基类
        super().__init__(config)
        
        # 原有成员初始化
        self.stop_thread = False
        self.max_data_count = max_data_count
        self.device_data = device_data
        self.accidental_count = 0
        self.total_clicks = 0
        self.cache_data = []
        self.clicks_doubted = []
        
        # 子线程引用
        self.listener: Optional[mouse.Listener] = None
        self.warning_thread: Optional[threading.Thread] = None
    
    def initialize(self) -> bool:
        """初始化误触检测资源"""
        try:
            print(f"初始化误触检测: {self.get_name()}")
            
            # 创建鼠标监听器
            self.listener = mouse.Listener(on_click=self.record)
            
            # 创建警告线程
            self.warning_thread = threading.Thread(
                target=self.send_warning,
                name=f"{self.get_name()}_WarningThread",
                daemon=True
            )
            
            print(f"误触检测初始化完成: {self.get_name()}")
            return True
            
        except Exception as e:
            error = ThreadError(
                self.get_name(),
                f"误触检测初始化失败: {str(e)}",
                e if isinstance(e, Exception) else None
            )
            self._handle_error(error)
            return False
    
    def run(self):
        """误触检测主循环"""
        print(f"误触检测开始运行: {self.get_name()}")
        
        try:
            # 启动鼠标监听器
            if self.listener:
                self.listener.start()
                print(f"鼠标监听器已启动: {self.get_name()}")
            
            # 启动警告线程
            if self.warning_thread:
                self.warning_thread.start()
                print(f"警告线程已启动: {self.get_name()}")
            
            # 主循环：等待停止事件
            while not self._should_stop():
                # 检查是否暂停
                if not self._wait_if_paused():
                    break
                
                # 短暂睡眠以避免忙等待
                time.sleep(1.0)
            
            print(f"误触检测运行结束: {self.get_name()}")
            
        except Exception as e:
            error = ThreadError(
                self.get_name(),
                f"误触检测运行时发生未捕获异常: {str(e)}",
                e if isinstance(e, Exception) else None
            )
            self._handle_error(error)
            raise
    
    def cleanup(self):
        """清理误触检测资源"""
        try:
            print(f"清理误触检测资源: {self.get_name()}")
            
            # 设置停止标志
            self.stop_thread = True
            
            # 停止鼠标监听器
            if self.listener:
                self.listener.stop()
                self.listener = None
            
            # 等待警告线程结束
            if self.warning_thread and self.warning_thread.is_alive():
                self.warning_thread.join(timeout=5.0)
                if self.warning_thread.is_alive():
                    print(f"警告线程在5秒内未停止: {self.get_name()}")
                self.warning_thread = None
            
            # 清理数据
            self.cache_data.clear()
            self.clicks_doubted.clear()
            
            print(f"误触检测资源清理完成: {self.get_name()}")
            
        except Exception as e:
            error = ThreadError(
                self.get_name(),
                f"清理误触检测资源时发生错误: {str(e)}",
                e if isinstance(e, Exception) else None
            )
            self._handle_error(error)
    
    def send_warning(self):
        """发送误触警告（在独立线程中运行）"""
        self.stop_thread = False
        warning_count = 0
        
        while not self.stop_thread and not self._should_stop():
            try:
                # 检查是否暂停
                if self.is_paused():
                    time.sleep(1.0)
                    continue
                
                if self.accidental_count > 15:
                    # 发送警告通知
                    try:
                        requests.post("http://127.0.0.2:8848/notify", json={
                            "title": "误触警告",
                            "context": "屏幕可能存在误触，请清理屏幕边缘的红外发射器。若问题持续存在，请与老师联系",
                            "level": "warn",
                            "type": "default",
                            "timelimit": 5
                        })
                        warning_count += 1
                        print(f"已发送误触警告 (总数: {warning_count})")
                    except Exception as e:
                        print(f"发送警告通知失败: {e}")
                    
                    self.accidental_count = 0
                    time.sleep(10)
                else:
                    time.sleep(10)
                    continue
            except Exception as e:
                print(f"警告线程错误: {e}")
                time.sleep(10)
    
    def compare_data(self):
        if len(self.cache_data) >= 3:
            last_index = len(self.cache_data) - 1
            third_last_index = len(self.cache_data) - 3
            
            if self.cache_data[last_index]["x"] < self.device_data.redline_x[0] or self.cache_data[last_index]["x"] > self.device_data.redline_x[1]:
                if abs(self.cache_data[third_last_index]["x"] - self.cache_data[last_index]["x"]) < 8 and abs(self.cache_data[third_last_index]["y"] - self.cache_data[last_index]["y"]) < 8:
                    self.clicks_doubted.append(time.time())
                    if len(self.clicks_doubted) > 2:
                        if self.clicks_doubted[-1] - self.clicks_doubted[-2] < 0.25:
                            self.accidental_count += 1
                            print(f"accidental_count: {self.accidental_count}")
    
    def record(self, x, y, pressed):
        if pressed:
            self.total_clicks += 1
            #print(self.total_clicks)
            if len(self.cache_data) >= self.max_data_count:
                self.cache_data = self.cache_data[1:]
            self.cache_data.append({"x": x, "y": y, "time": time.time()})
            self.compare_data()
    

    
    # 保持向后兼容的方法
    def start(self):
        """启动误触检测（兼容旧接口）"""
        return super().start()
    
    def stop(self, timeout: float = 5.0):
        """停止误触检测（兼容旧接口）"""
        return super().stop(timeout=timeout)

def start(max_data_count=1024, stop_thread=False):
    detector = DeviceData()
    monitor = Monitor(detector, max_data_count)
    
    if stop_thread:
        # 如果设置了stop_thread参数，直接停止并返回
        monitor.stop()
        return monitor
    
    try:
        # 启动误触检测（非阻塞）
        if monitor.start():
            print(f"误触检测已启动: {monitor.get_name()}")
            # 返回Monitor实例以便后续控制
            return monitor
        else:
            print(f"误触检测启动失败: {monitor.get_name()}")
            return None
    except Exception as e:
        print(f"启动误触检测时发生异常: {e}")
        raise e


if __name__ == '__main__':
    start(stop_thread=True)