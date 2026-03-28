import ctypes
from pynput import mouse
import time
import threading
import requests



class DeviceData:
    def __init__(self):

        user32 = ctypes.windll.user32
        self.screen_width = user32.GetSystemMetrics(0)

        self.redline_x = [self.screen_width * 0.05, self.screen_width * 0.95]

class Monitor:
    def __init__(self, device_data: DeviceData, max_data_count: int = 1024):
        self.stop_thread = False
        self.max_data_count = max_data_count
        self.device_data = device_data
        self.accidental_count = 0
        self.total_clicks = 0
        self.cache_data = []
        self.clicks_doubted = []

    def send_warning(self):
        self.stop_thread = False
        while not self.stop_thread:
            try:
                if self.accidental_count > 15:
                    #print("accidental_count >= 15")
                    requests.get("http://127.0.0.2:8848/notify?title=误触警告&context=屏幕可能存在误触，请清理屏幕边缘的红外发射器。若问题持续存在，请与老师联系&level=warn&type=default&timelimit=5")
                    self.accidental_count = 0
                    time.sleep(10)
                else:
                    time.sleep(10)
                    continue
            except Exception as e:
                print(e)
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
    
    def start(self):
        self.listener = mouse.Listener(on_click=self.record)
        self.listener.start()
        
        self.if_need_warning = threading.Thread(target=self.send_warning)
        self.if_need_warning.start()
        
        self.listener.join()
        self.if_need_warning.join()

    def stop(self):
        self.stop_thread = True

        if self.listener:
            self.listener.stop()

        if self.if_need_warning:
            self.if_need_warning.join()
    
def start(max_data_count=1024, stop_thread=False):
    detector = DeviceData()
    monitor = Monitor(detector, max_data_count)
    if stop_thread:
        monitor.stop()

    try:
        monitor.start()
    except Exception as e:
        raise e


if __name__ == '__main__':
    start(stop_thread=True)
