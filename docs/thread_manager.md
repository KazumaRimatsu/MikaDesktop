# 线程管理器使用指南

## 概述

线程管理器提供了线程创建、启动、暂停、恢复、停止和销毁的完整管理功能，并支持线程优先级和状态跟踪。

## 核心组件

### 1. ThreadState（线程状态枚举）

线程管理器定义了7种线程状态：

- **CREATED**: 已创建但未启动
- **RUNNING**: 运行中
- **PAUSED**: 已暂停
- **STOPPING**: 停止中
- **STOPPED**: 已停止
- **ERROR**: 错误状态
- **COMPLETED**: 已完成

### 2. ThreadPriority（线程优先级）

- **LOW** (-1): 低优先级
- **NORMAL** (0): 普通优先级
- **HIGH** (1): 高优先级

### 3. ThreadInfo（线程信息类）

存储线程的详细信息：

- `id`: 线程唯一标识符（UUID）
- `name`: 线程名称
- `level`: 优先级级别
- `state`: 当前状态
- `created_time`: 创建时间
- `worker`: QThread工作线程对象
- `start_time`: 启动时间（可选）
- `end_time`: 结束时间（可选）
- `error`: 错误信息（可选）

### 4. ThreadManager（线程管理器类）

主管理类，继承自QObject，提供完整的线程管理功能。

## 快速开始

### 安装与导入

```python
from Lib.threads.manager import ThreadManager, ThreadPriority, ThreadState
from PySide6.QtCore import QThread
```

### 基本使用

```python
# 创建线程管理器（默认最大16个线程）
manager = ThreadManager(max_threads=16)

# 创建自定义工作线程
class MyWorker(QThread):
    def run(self):
        # 线程执行逻辑
        for i in range(10):
            print(f"Working... {i}")
            self.msleep(1000)

# 创建并注册线程
worker = MyWorker()
thread_id = manager.create(
    name="MyWorkerThread",
    level=ThreadPriority.NORMAL,
    start_when_create=True,
    worker=worker
)

# 获取线程信息
thread_info = manager.get_thread_info(thread_id)
print(f"Thread ID: {thread_info.id}")
print(f"Thread Name: {thread_info.name}")
print(f"Thread State: {thread_info.state}")

# 等待线程完成
import time
time.sleep(5)

# 停止线程
manager.stop(thread_id, wait=True, timeout=5000)

# 销毁线程
manager.destroy(thread_id)
```

## API参考

### ThreadManager类方法

#### 构造函数

```python
def __init__(self, max_threads: int = 16):
    """
    初始化线程管理器
    
    参数:
        max_threads: 最大线程数限制，默认16
    """
```

#### 线程管理方法

##### create - 创建并注册线程

```python
def create(self, name: str, level: int = ThreadPriority.NORMAL, 
           start_when_create: bool = False, worker: QThread = None) -> str:
    """
    创建并注册线程
    
    参数:
        name: 线程名称
        level: 优先级级别（ThreadPriority.LOW/NORMAL/HIGH）
        start_when_create: 是否在创建后立即启动
        worker: QThread工作线程对象
    
    返回:
        thread_id: 线程唯一标识符
    
    异常:
        ValueError: 参数无效
        RuntimeError: 达到最大线程数限制
    """
```

##### run - 启动线程

```python
def run(self, thread_id: str) -> bool:
    """
    启动线程
    
    参数:
        thread_id: 线程ID
    
    返回:
        bool: 是否成功启动
    """
```

##### stop - 停止线程

```python
def stop(self, thread_id: str, wait: bool = True, timeout: int = 5000) -> bool:
    """
    停止线程
    
    参数:
        thread_id: 线程ID
        wait: 是否等待线程结束
        timeout: 等待超时时间（毫秒）
    
    返回:
        bool: 是否成功停止
    """
```

##### pause - 暂停线程

```python
def pause(self, thread_id: str) -> bool:
    """
    暂停线程（如果线程支持暂停功能）
    
    注意: 需要线程对象实现pause()方法
    
    参数:
        thread_id: 线程ID
    
    返回:
        bool: 是否成功暂停
    """
```

##### resume - 恢复线程

```python
def resume(self, thread_id: str) -> bool:
    """
    恢复暂停的线程
    
    注意: 需要线程对象实现resume()方法
    
    参数:
        thread_id: 线程ID
    
    返回:
        bool: 是否成功恢复
    """
```

##### destroy - 销毁线程

```python
def destroy(self, thread_id: str) -> bool:
    """
    销毁线程
    
    参数:
        thread_id: 线程ID
    
    返回:
        bool: 是否成功销毁
    """
```

##### stop\_all - 停止所有线程

```python
def stop_all(self) -> None:
    """
    停止所有线程（不等待）
    """
```

#### 查询方法

##### get\_thread\_info - 获取线程信息

```python
def get_thread_info(self, thread_id: str) -> Optional[ThreadInfo]:
    """
    获取线程信息
    
    参数:
        thread_id: 线程ID
    
    返回:
        ThreadInfo: 线程信息对象，如果不存在则返回None
    """
```

##### get\_all\_threads - 获取所有线程信息

```python
def get_all_threads(self) -> List[ThreadInfo]:
    """
    获取所有线程信息
    
    返回:
        List[ThreadInfo]: 所有线程信息列表
    """
```

##### get\_threads\_by\_state - 按状态筛选线程

```python
def get_threads_by_state(self, state: str) -> List[ThreadInfo]:
    """
    按状态筛选线程
    
    参数:
        state: 线程状态（ThreadState枚举值）
    
    返回:
        List[ThreadInfo]: 符合状态的线程信息列表
    """
```

##### get\_active\_count - 获取活跃线程数量

```python
def get_active_count(self) -> int:
    """
    获取活跃线程数量（RUNNING状态的线程）
    
    返回:
        int: 活跃线程数量
    """
```

##### get\_total\_count - 获取总线程数量

```python
def get_total_count(self) -> int:
    """
    获取总线程数量
    
    返回:
        int: 总线程数量
    """
```

### 信号（Signals）

线程管理器提供以下信号，用于监听线程状态变化：

```python
# 线程启动信号
thread_started = Signal(str, str)  # (thread_id, thread_name)

# 线程停止信号
thread_stopped = Signal(str, str)  # (thread_id, thread_name)

# 线程错误信号
thread_error = Signal(str, str, str)  # (thread_id, thread_name, error_message)

# 线程状态变化信号
thread_state_changed = Signal(str, str, str)  # (thread_id, old_state, new_state)
```

#### 信号使用示例

```python
# 连接信号
manager.thread_started.connect(lambda tid, name: print(f"Thread {name} ({tid}) started"))
manager.thread_stopped.connect(lambda tid, name: print(f"Thread {name} ({tid}) stopped"))
manager.thread_error.connect(lambda tid, name, error: print(f"Thread {name} ({tid}) error: {error}"))
manager.thread_state_changed.connect(lambda tid, old, new: print(f"Thread {tid} state changed: {old} -> {new}"))
```

## 高级用法

### 1. 创建支持暂停/恢复的线程

```python
class PausableWorker(QThread):
    def __init__(self):
        super().__init__()
        self._paused = False
        self._pause_lock = threading.Lock()
    
    def pause(self):
        """暂停线程"""
        with self._pause_lock:
            self._paused = True
    
    def resume(self):
        """恢复线程"""
        with self._pause_lock:
            self._paused = False
    
    def is_paused(self):
        """检查是否暂停"""
        with self._pause_lock:
            return self._paused
    
    def run(self):
        while not self.isInterruptionRequested():
            # 检查是否暂停
            if self.is_paused():
                self.msleep(100)  # 暂停时短暂休眠
                continue
            
            # 执行工作
            print("Working...")
            self.msleep(1000)

# 使用支持暂停的线程
worker = PausableWorker()
thread_id = manager.create(name="PausableWorker", worker=worker)
manager.run(thread_id)

# 暂停线程
manager.pause(thread_id)

# 恢复线程
manager.resume(thread_id)
```

### 2. 批量管理线程

```python
# 批量创建线程
thread_ids = []
for i in range(5):
    worker = MyWorker()
    thread_id = manager.create(name=f"Worker-{i}", worker=worker)
    thread_ids.append(thread_id)

# 批量启动线程
for thread_id in thread_ids:
    manager.run(thread_id)

# 批量停止线程
for thread_id in thread_ids:
    manager.stop(thread_id)

# 批量销毁线程
for thread_id in thread_ids:
    manager.destroy(thread_id)
```

### 3. 监控线程状态

```python
# 定期检查线程状态
import time

def monitor_threads(manager):
    while True:
        active_count = manager.get_active_count()
        total_count = manager.get_total_count()
        
        print(f"Active threads: {active_count}/{total_count}")
        
        # 获取所有线程状态
        threads = manager.get_all_threads()
        for thread in threads:
            print(f"  - {thread.name}: {thread.state}")
        
        time.sleep(2)

# 在单独的线程中运行监控
monitor_thread = threading.Thread(target=monitor_threads, args=(manager,))
monitor_thread.start()
```

## 最佳实践

### 1. 线程命名规范

- 使用有意义的线程名称，便于调试和监控
- 建议格式：`功能模块_具体任务`，如 `Notification_Server`、`AccidentalTouch_Monitor`

### 2. 错误处理

- 始终检查线程管理方法的返回值
- 监听`thread_error`信号处理异常情况
- 在关键操作中添加异常处理

### 3. 资源管理

- 及时销毁不再需要的线程
- 避免创建过多线程，合理设置`max_threads`参数
- 使用`stop_all()`在程序退出时清理所有线程

### 4. 线程安全

- 线程管理器内部使用`threading.RLock`确保线程安全
- 在多线程环境中访问管理器时，注意同步问题

## 故障排除

### 常见问题

1. **线程无法启动**
   - 检查线程是否已处于运行状态
   - 验证worker参数是否为有效的QThread对象
   - 检查是否达到最大线程数限制
2. **暂停/恢复功能无效**
   - 确保线程对象实现了`pause()`和`resume()`方法
   - 检查线程状态是否为RUNNING或PAUSED
3. **线程管理器信号未触发**
   - 确认信号连接正确
   - 检查Qt事件循环是否正常运行
4. **内存泄漏**
   - 使用`destroy()`方法及时销毁线程
   - 避免创建大量短期线程

### 调试技巧

```python
# 启用详细日志
import logging
logging.basicConfig(level=logging.DEBUG)

# 打印线程管理器状态
def print_manager_status(manager):
    print(f"Total threads: {manager.get_total_count()}")
    print(f"Active threads: {manager.get_active_count()}")
    
    threads = manager.get_all_threads()
    for thread in threads:
        print(f"  {thread.name} ({thread.id}): {thread.state}")
```

## 性能考虑

1. **线程数量限制**：默认最大16个线程，可根据系统资源调整
2. **内存使用**：每个线程对象占用一定内存，避免创建过多线程
3. **CPU占用**：线程管理器本身开销很小，主要开销来自工作线程
4. **同步开销**：使用锁保护内部数据结构，确保线程安全

