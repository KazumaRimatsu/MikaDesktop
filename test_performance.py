#!/usr/bin/env python3
"""测试线程管理器性能，验证修复忙等待问题后的CPU占用"""

import sys
import os
import time
import threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from Lib.threads.manager import ThreadManager
from Lib.threads.lifecycle import ThreadBase, ThreadConfig

class CountingThread(ThreadBase):
    """计数线程，用于测试CPU占用"""
    
    def __init__(self, name="CountingThread"):
        config = ThreadConfig(name=name, daemon=True)
        super().__init__(config)
        self.iteration_count = 0
        self.start_time = None
        self.end_time = None
    
    def initialize(self) -> bool:
        return True
    
    def run(self):
        self.start_time = time.time()
        while not self._should_stop():
            if not self._wait_if_paused():
                break
            self.iteration_count += 1
            time.sleep(1.0)  # 模拟工作，每秒一次
        self.end_time = time.time()
    
    def cleanup(self):
        pass

class BusyThread(ThreadBase):
    """模拟忙等待的线程（错误实现）"""
    
    def __init__(self, name="BusyThread"):
        config = ThreadConfig(name=name, daemon=True)
        super().__init__(config)
        self.iteration_count = 0
        self.start_time = None
        self.end_time = None
    
    def initialize(self) -> bool:
        return True
    
    def run(self):
        self.start_time = time.time()
        while not self._should_stop():
            if not self._wait_if_paused():
                break
            self.iteration_count += 1
            # 错误：没有休眠，会导致忙等待
            # time.sleep(0)  # 没有休眠
            pass  # 故意不休眠，模拟错误实现
        self.end_time = time.time()
    
    def cleanup(self):
        pass

def test_no_busy_wait():
    """测试线程是否避免了忙等待"""
    print("=== 测试忙等待修复 ===")
    
    manager = ThreadManager()
    
    # 创建正常线程
    normal_thread = CountingThread("NormalThread")
    manager.register_thread(normal_thread)
    
    # 启动线程
    assert manager.start_thread("NormalThread") == True
    
    # 运行2秒
    time.sleep(2.0)
    
    # 停止线程
    assert manager.stop_thread("NormalThread") == True
    
    # 检查迭代次数：应该有大约2次迭代（每秒1次）
    iteration_count = normal_thread.iteration_count
    print(f"正常线程迭代次数: {iteration_count}")
    
    # 应该大约2次，不超过5次（允许一些误差）
    assert iteration_count <= 5, f"正常线程迭代次数过多: {iteration_count}，可能存在忙等待"
    assert iteration_count >= 1, f"正常线程迭代次数过少: {iteration_count}"
    
    print(f"正常线程测试通过: {iteration_count} 次迭代")
    
    # 注销线程
    manager.unregister_thread("NormalThread")
    
    # 测试忙等待线程（错误实现）
    print("\n=== 测试忙等待检测 ===")
    busy_thread = BusyThread("BusyThread")
    manager.register_thread(busy_thread)
    
    # 启动线程
    assert manager.start_thread("BusyThread") == True
    
    # 运行0.5秒（忙等待线程会进行大量迭代）
    time.sleep(0.5)
    
    # 停止线程
    assert manager.stop_thread("BusyThread") == True
    
    # 检查迭代次数：忙等待线程会有非常高的迭代次数
    iteration_count = busy_thread.iteration_count
    print(f"忙等待线程迭代次数: {iteration_count}")
    
    # 忙等待线程的迭代次数会非常高（可能数万或更多）
    # 我们只是记录，不断言，因为这是错误实现的示例
    if iteration_count > 10000:
        print("检测到忙等待行为（预期中）")
    
    # 注销线程
    manager.unregister_thread("BusyThread")
    
    print("忙等待测试完成")

def test_existing_threads():
    """测试现有线程实现"""
    print("\n=== 测试现有线程实现 ===")
    
    # 导入现有线程
    from Lib.features.escape_accidental_touch import DeviceData, Monitor
    from Lib.features.notification_system import NotificationManager
    
    # 测试误触检测线程
    device_data = DeviceData()
    monitor = Monitor(device_data)
    
    # 创建管理器
    manager = ThreadManager()
    assert manager.register_thread(monitor) == True
    
    # 启动线程
    print("启动误触检测线程...")
    assert manager.start_thread("AccidentalTouchMonitor") == True
    
    # 运行1秒
    time.sleep(1.0)
    
    # 停止线程
    print("停止误触检测线程...")
    assert manager.stop_thread("AccidentalTouchMonitor", timeout=3.0) == True
    
    # 注销线程
    manager.unregister_thread("AccidentalTouchMonitor")
    
    print("现有线程测试通过")

def test_multiple_threads():
    """测试多个线程同时运行"""
    print("\n=== 测试多个线程 ===")
    
    manager = ThreadManager()
    threads = []
    
    # 创建5个线程
    for i in range(5):
        thread = CountingThread(f"Thread-{i}")
        threads.append(thread)
        assert manager.register_thread(thread) == True
    
    # 启动所有线程
    print("启动所有线程...")
    assert manager.start_all() == True
    
    # 运行3秒
    time.sleep(3.0)
    
    # 暂停所有线程
    print("暂停所有线程...")
    assert manager.pause_all() == True
    
    # 等待1秒
    time.sleep(1.0)
    
    # 恢复所有线程
    print("恢复所有线程...")
    assert manager.resume_all() == True
    
    # 再运行2秒
    time.sleep(2.0)
    
    # 停止所有线程
    print("停止所有线程...")
    assert manager.stop_all() == True
    
    # 检查迭代次数
    total_iterations = sum(t.iteration_count for t in threads)
    print(f"总迭代次数: {total_iterations}")
    
    # 每个线程应该大约有5次迭代（3+2秒运行，暂停期间没有迭代）
    # 5个线程 * 5次 = 25次，允许一些误差
    assert total_iterations <= 35, f"总迭代次数过多: {total_iterations}"
    assert total_iterations >= 15, f"总迭代次数过少: {total_iterations}"
    
    print(f"多个线程测试通过: {total_iterations} 次总迭代")

if __name__ == "__main__":
    try:
        test_no_busy_wait()
        test_existing_threads()
        test_multiple_threads()
        print("\n所有性能测试通过！")
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)