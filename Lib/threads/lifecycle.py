"""
简化的线程生命周期管理标准接口
提供线程创建、启动、暂停、恢复、终止和资源回收的规范协议
移除健康检查、事件回调等高级功能以解决程序无响应问题
"""

import threading
import time
import enum
from abc import abstractmethod
from PySide6.QtCore import QObject
from typing import Optional, Dict, Any, Callable, List, Union
from dataclasses import dataclass, field
from datetime import datetime

from .. import log_maker

log = log_maker.logger()


class ThreadState(enum.Enum):
    """线程状态枚举"""
    IDLE = "idle"           # 空闲，未初始化
    INITIALIZING = "initializing"  # 初始化中
    RUNNING = "running"     # 运行中
    PAUSED = "paused"       # 已暂停
    STOPPING = "stopping"   # 停止中
    STOPPED = "stopped"     # 已停止
    ERROR = "error"         # 错误状态


class ThreadError(Exception):
    """线程错误基类"""
    
    def __init__(self, thread_name: str, message: str, original_error: Optional[Exception] = None):
        self.thread_name = thread_name
        self.message = message
        self.original_error = original_error
        self.timestamp = datetime.now()
        super().__init__(f"[{thread_name}] {message}")


class ThreadInitializationError(ThreadError):
    """线程初始化错误"""
    pass


class ThreadStartError(ThreadError):
    """线程启动错误"""
    pass


class ThreadStopError(ThreadError):
    """线程停止错误"""
    pass


class ThreadPauseError(ThreadError):
    """线程暂停错误"""
    pass


class ThreadResumeError(ThreadError):
    """线程恢复错误"""
    pass


@dataclass
class ThreadConfig:
    """简化的线程配置"""
    name: str
    daemon: bool = True
    priority: int = 5  # 线程优先级：0（最低）到10（最高），5为正常优先级
    auto_start: bool = False


class ThreadBase(QObject):
    """线程抽象基类，所有线程实现必须继承此类"""
    
    def __init__(self, config: ThreadConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self._state = ThreadState.IDLE
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # 初始为未暂停状态
        self._last_error: Optional[ThreadError] = None
        self._start_time: Optional[datetime] = None
        self._stop_time: Optional[datetime] = None
    
    def initialize(self) -> bool:
        """初始化线程资源
        
        Returns:
            bool: 初始化是否成功
        """
        raise NotImplementedError("子类必须实现 initialize 方法")
    
    @abstractmethod
    def run(self):
        """线程主循环（子类实现具体的线程逻辑）"""
        pass
    
    @abstractmethod
    def cleanup(self):
        """清理线程资源"""
        pass
    
    def start(self) -> bool:
        """启动线程
        
        Returns:
            bool: 启动是否成功
        """
        with self._lock:
            if self._state not in [ThreadState.IDLE, ThreadState.STOPPED]:
                log.warning(f"线程 {self.config.name} 当前状态为 {self._state.value}，无法启动")
                return False
            
            try:
                # 状态设置为初始化中
                self._set_state(ThreadState.INITIALIZING)
                
                # 初始化资源
                if not self.initialize():
                    raise ThreadInitializationError(
                        self.config.name, 
                        "线程初始化失败"
                    )
                
                # 创建并启动线程
                self._stop_event.clear()
                self._pause_event.set()  # 确保未暂停
                self._thread = threading.Thread(
                    target=self._thread_wrapper,
                    name=self.config.name,
                    daemon=self.config.daemon
                )
                self._thread.start()
                
                # 更新状态和启动时间
                self._set_state(ThreadState.RUNNING)
                self._start_time = datetime.now()
                self._stop_time = None
                self._last_error = None
                
                log.info(f"线程 {self.config.name} 已启动")
                return True
                
            except Exception as e:
                error = ThreadStartError(
                    self.config.name,
                    f"启动线程失败: {str(e)}",
                    e if isinstance(e, Exception) else None
                )
                self._handle_error(error)
                self._set_state(ThreadState.ERROR)
                return False
    
    def pause(self) -> bool:
        """暂停线程
        
        Returns:
            bool: 暂停是否成功
        """
        with self._lock:
            if self._state != ThreadState.RUNNING:
                log.warning(f"线程 {self.config.name} 当前状态为 {self._state.value}，无法暂停")
                return False
            
            try:
                self._pause_event.clear()
                self._set_state(ThreadState.PAUSED)
                log.info(f"线程 {self.config.name} 已暂停")
                return True
                
            except Exception as e:
                error = ThreadPauseError(
                    self.config.name,
                    f"暂停线程失败: {str(e)}",
                    e if isinstance(e, Exception) else None
                )
                self._handle_error(error)
                return False
    
    def resume(self) -> bool:
        """恢复线程
        
        Returns:
            bool: 恢复是否成功
        """
        with self._lock:
            if self._state != ThreadState.PAUSED:
                log.warning(f"线程 {self.config.name} 当前状态为 {self._state.value}，无法恢复")
                return False
            
            try:
                self._pause_event.set()
                self._set_state(ThreadState.RUNNING)
                log.info(f"线程 {self.config.name} 已恢复")
                return True
                
            except Exception as e:
                error = ThreadResumeError(
                    self.config.name,
                    f"恢复线程失败: {str(e)}",
                    e if isinstance(e, Exception) else None
                )
                self._handle_error(error)
                return False
    
    def stop(self, timeout: float = 5.0) -> bool:
        """停止线程
        
        Args:
            timeout: 等待线程停止的超时时间（秒）
            
        Returns:
            bool: 停止是否成功
        """
        with self._lock:
            if self._state in [ThreadState.IDLE, ThreadState.STOPPED]:
                log.info(f"线程 {self.config.name} 已处于停止状态")
                return True
            
            if self._state == ThreadState.STOPPING:
                log.warning(f"线程 {self.config.name} 正在停止中")
                return False
            
            try:
                # 设置停止状态
                self._set_state(ThreadState.STOPPING)
                self._stop_event.set()
                self._pause_event.set()  # 确保线程可以退出
                
                # 等待线程结束
                if self._thread and self._thread.is_alive():
                    self._thread.join(timeout=timeout)
                    
                    if self._thread.is_alive():
                        log.warning(f"线程 {self.config.name} 在 {timeout} 秒内未停止")
                        # 继续尝试清理
                
                # 清理资源
                self.cleanup()
                
                # 更新状态
                self._set_state(ThreadState.STOPPED)
                self._stop_time = datetime.now()
                
                log.info(f"线程 {self.config.name} 已停止")
                return True
                
            except Exception as e:
                error = ThreadStopError(
                    self.config.name,
                    f"停止线程失败: {str(e)}",
                    e if isinstance(e, Exception) else None
                )
                self._handle_error(error)
                return False
    
    def get_state(self) -> ThreadState:
        """获取当前线程状态"""
        with self._lock:
            return self._state
    
    def get_name(self) -> str:
        """获取线程名称"""
        return self.config.name
    
    def get_uptime(self) -> Optional[float]:
        """获取线程运行时间（秒）"""
        with self._lock:
            if self._start_time:
                if self._stop_time:
                    return (self._stop_time - self._start_time).total_seconds()
                else:
                    return (datetime.now() - self._start_time).total_seconds()
            return None
    
    def get_last_error(self) -> Optional[ThreadError]:
        """获取最后发生的错误"""
        with self._lock:
            return self._last_error
    
    def is_alive(self) -> bool:
        """检查线程是否存活"""
        with self._lock:
            return self._thread is not None and self._thread.is_alive()
    
    def is_paused(self) -> bool:
        """检查线程是否暂停"""
        with self._lock:
            return self._state == ThreadState.PAUSED
    
    # 向后兼容的方法（空实现）
    def add_state_changed_callback(self, callback):
        """添加状态变化回调（向后兼容，空实现）"""
        log.warning("add_state_changed_callback 已废弃，调用被忽略")
    
    def add_error_callback(self, callback):
        """添加错误回调（向后兼容，空实现）"""
        log.warning("add_error_callback 已废弃，调用被忽略")
    
    def add_event_callback(self, callback):
        """添加事件回调（向后兼容，空实现）"""
        log.warning("add_event_callback 已废弃，调用被忽略")
    
    def send_message(self, message: Any) -> bool:
        """发送消息到线程（向后兼容，空实现）"""
        log.debug(f"线程 {self.config.name} 收到消息（已废弃）: {message}")
        return True
    
    def _update_metric(self, key: str, value: Any):
        """更新指标（向后兼容，空实现）"""
        # 不再存储指标，仅记录调试信息
        log.debug(f"线程 {self.config.name} 指标更新（已废弃）: {key} = {value}")
    
    # 保护方法，供子类使用
    
    def _thread_wrapper(self):
        """线程包装器，处理异常和状态管理"""
        try:
            # 等待暂停事件（如果暂停则阻塞）
            self._pause_event.wait()
            
            # 调用子类的run方法
            self.run()
            
            # 运行完成，更新状态
            with self._lock:
                if self._state == ThreadState.STOPPING:
                    self._set_state(ThreadState.STOPPED)
                else:
                    self._set_state(ThreadState.STOPPED)
                    log.info(f"线程 {self.config.name} 运行完成")
                    
        except Exception as e:
            error = ThreadError(
                self.config.name,
                f"线程运行时发生未捕获异常: {str(e)}",
                e if isinstance(e, Exception) else None
            )
            self._handle_error(error)
            self._set_state(ThreadState.ERROR)
    
    def _set_state(self, new_state: ThreadState):
        """设置线程状态"""
        with self._lock:
            old_state = self._state
            self._state = new_state
            
            # 记录状态变化
            log.debug(f"线程 {self.config.name} 状态变化: {old_state.value} -> {new_state.value}")
    
    def _handle_error(self, error: ThreadError):
        """处理错误"""
        with self._lock:
            self._last_error = error
            
            # 记录错误
            log.error(f"线程 {self.config.name} 发生错误: {error.message}")
            if error.original_error:
                log.error(f"原始错误: {error.original_error}")
    
    def _should_stop(self) -> bool:
        """检查是否应该停止"""
        return self._stop_event.is_set()
    
    def _wait_if_paused(self, timeout: Optional[float] = None) -> bool:
        """如果线程暂停则等待
        
        Args:
            timeout: 等待超时时间（秒），None表示无限等待
            
        Returns:
            bool: 是否应该继续运行（False表示应该停止）
        """
        if self._should_stop():
            return False
        
        if not self._pause_event.is_set():
            # 线程暂停，等待恢复或停止
            if timeout is None:
                while not self._pause_event.is_set() and not self._should_stop():
                    # 使用事件等待更高效
                    self._pause_event.wait(timeout=0.1)
            else:
                end_time = time.time() + timeout
                while not self._pause_event.is_set() and not self._should_stop() and time.time() < end_time:
                    # 计算剩余时间
                    remaining = end_time - time.time()
                    if remaining <= 0:
                        break
                    # 使用事件等待更高效，最多等待0.1秒或剩余时间
                    self._pause_event.wait(timeout=min(0.1, remaining))
        
        return not self._should_stop()


class SimpleThread(ThreadBase):
    """简单线程实现示例，用于演示和测试"""
    
    def __init__(self, config: ThreadConfig, work_interval: float = 1.0):
        super().__init__(config)
        self.work_interval = work_interval
        self.counter = 0
    
    def initialize(self) -> bool:
        log.info(f"简单线程 {self.config.name} 初始化")
        return True
    
    def run(self):
        log.info(f"简单线程 {self.config.name} 开始运行")
        
        while not self._should_stop():
            # 检查是否暂停
            if not self._wait_if_paused():
                break
            
            # 执行工作
            self.counter += 1
            log.debug(f"简单线程 {self.config.name} 工作计数: {self.counter}")
            
            # 模拟工作
            time.sleep(self.work_interval)
        
        log.info(f"简单线程 {self.config.name} 运行结束")
    
    def cleanup(self):
        log.info(f"简单线程 {self.config.name} 清理资源")