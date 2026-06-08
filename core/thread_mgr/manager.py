from PySide6.QtCore import QThread, QObject, Signal
import uuid
import threading
from typing import Dict, List, Optional, Callable
from datetime import datetime

class ThreadState:
    """线程状态枚举"""
    CREATED = "created"     # 已注册
    RUNNING = "running"     # 运行中
    PAUSED = "paused"       # 已暂停
    STOPPING = "stopping"   # 停止中
    STOPPED = "stopped"     # 已停止
    ERROR = "error"         # 错误状态
    COMPLETED = "completed" # 已完成

class ThreadPriority:
    """线程优先级"""
    LOW = -1    # 低优先级
    NORMAL = 0  # 普通优先级
    HIGH = 1    # 高优先级

class ThreadInfo:
    """线程信息类"""
    def __init__(self, id: str, name: str, level: int, state: str, 
                 created_time: datetime, worker: QThread):
        self.id = id
        self.name = name
        self.level = level
        self.state = state
        self.created_time = created_time
        self.worker = worker
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.error: Optional[str] = None

class ThreadManager(QObject):
    """改进的线程管理器"""
    
    # 信号定义
    thread_started = Signal(str, str)  # (thread_id, thread_name)
    thread_stopped = Signal(str, str)  # (thread_id, thread_name)
    thread_error = Signal(str, str, str)  # (thread_id, thread_name, error_message)
    thread_state_changed = Signal(str, str, str)  # (thread_id, old_state, new_state)
    
    def __init__(self, max_threads: int = 16):
        super().__init__()
        self.max_threads = max_threads
        self.threads: Dict[str, ThreadInfo] = {}
        self._lock = threading.RLock()
        self._active_count = 0
    
    def create(self, name: str, level: int = ThreadPriority.NORMAL, 
               start_when_create: bool = False, worker: QThread = None) -> str:
        """创建并注册线程"""
        if level not in [ThreadPriority.LOW, ThreadPriority.NORMAL, ThreadPriority.HIGH]:
            raise ValueError("level must be in [-1, 0, 1]")
        if worker is None:
            raise ValueError("worker must be provided")
        
        with self._lock:
            # 检查线程数量限制
            if len(self.threads) >= self.max_threads:
                raise RuntimeError(f"已达到最大线程数限制: {self.max_threads}")
            
            thread_id = str(uuid.uuid4())
            created_time = datetime.now()
            
            thread_info = ThreadInfo(
                id=thread_id,
                name=name,
                level=level,
                state=ThreadState.CREATED,
                created_time=created_time,
                worker=worker
            )
            
            self.threads[thread_id] = thread_info
            
            # 连接线程信号
            worker.finished.connect(lambda: self._on_thread_finished(thread_id))
            if hasattr(worker, 'errorOccurred'):
                worker.errorOccurred.connect(lambda error: self._on_thread_error(thread_id, error))
            
            if start_when_create:
                self.run(thread_id)
            
            return thread_id
    
    def run(self, thread_id: str) -> bool:
        """启动线程"""
        with self._lock:
            if thread_id not in self.threads:
                return False
            
            thread_info = self.threads[thread_id]
            
            if thread_info.state not in [ThreadState.CREATED, ThreadState.STOPPED, ThreadState.PAUSED]:
                return False
            
            try:
                old_state = thread_info.state
                thread_info.state = ThreadState.RUNNING
                thread_info.start_time = datetime.now()
                thread_info.end_time = None
                thread_info.error = None
                
                thread_info.worker.start()
                self._active_count += 1
                
                self.thread_state_changed.emit(thread_id, old_state, ThreadState.RUNNING)
                self.thread_started.emit(thread_id, thread_info.name)
                
                return True
            except Exception as e:
                thread_info.state = ThreadState.ERROR
                thread_info.error = str(e)
                self.thread_error.emit(thread_id, thread_info.name, str(e))
                return False
    
    def stop(self, thread_id: str, wait: bool = True, timeout: int = 5000) -> bool:
        """停止线程"""
        with self._lock:
            if thread_id not in self.threads:
                return False
            
            thread_info = self.threads[thread_id]
            
            if thread_info.state not in [ThreadState.RUNNING, ThreadState.PAUSED]:
                return False
            
            try:
                old_state = thread_info.state
                thread_info.state = ThreadState.STOPPING
                
                thread_info.worker.quit()
                
                if wait:
                    if not thread_info.worker.wait(timeout):
                        thread_info.worker.terminate()
                
                thread_info.state = ThreadState.STOPPED
                thread_info.end_time = datetime.now()
                self._active_count -= 1
                
                self.thread_state_changed.emit(thread_id, old_state, ThreadState.STOPPED)
                self.thread_stopped.emit(thread_id, thread_info.name)
                
                return True
            except Exception as e:
                thread_info.state = ThreadState.ERROR
                thread_info.error = str(e)
                self.thread_error.emit(thread_id, thread_info.name, str(e))
                return False
    
    def pause(self, thread_id: str) -> bool:
        """暂停线程（如果线程支持暂停功能）"""
        with self._lock:
            if thread_id not in self.threads:
                return False
            
            thread_info = self.threads[thread_id]
            
            if thread_info.state != ThreadState.RUNNING:
                return False
            
            # 这里需要线程对象实现暂停功能
            if hasattr(thread_info.worker, 'pause'):
                try:
                    old_state = thread_info.state
                    thread_info.worker.pause()
                    thread_info.state = ThreadState.PAUSED
                    
                    self.thread_state_changed.emit(thread_id, old_state, ThreadState.PAUSED)
                    return True
                except Exception as e:
                    thread_info.state = ThreadState.ERROR
                    thread_info.error = str(e)
                    self.thread_error.emit(thread_id, thread_info.name, str(e))
                    return False
            return False
    
    def resume(self, thread_id: str) -> bool:
        """恢复暂停的线程"""
        with self._lock:
            if thread_id not in self.threads:
                return False
            
            thread_info = self.threads[thread_id]
            
            if thread_info.state != ThreadState.PAUSED:
                return False
            
            if hasattr(thread_info.worker, 'resume'):
                try:
                    old_state = thread_info.state
                    thread_info.worker.resume()
                    thread_info.state = ThreadState.RUNNING
                    
                    self.thread_state_changed.emit(thread_id, old_state, ThreadState.RUNNING)
                    return True
                except Exception as e:
                    thread_info.state = ThreadState.ERROR
                    thread_info.error = str(e)
                    self.thread_error.emit(thread_id, thread_info.name, str(e))
                    return False
            return False
    
    def destroy(self, thread_id: str) -> bool:
        """销毁线程"""
        with self._lock:
            if thread_id not in self.threads:
                return False
            
            thread_info = self.threads[thread_id]
            
            # 先停止线程
            if thread_info.state in [ThreadState.RUNNING, ThreadState.PAUSED]:
                self.stop(thread_id, wait=True)
            
            try:
                thread_info.worker.deleteLater()
                del self.threads[thread_id]
                return True
            except Exception as e:
                return False
    
    def stop_all(self) -> None:
        """停止所有线程"""
        with self._lock:
            for thread_id in list(self.threads.keys()):
                self.stop(thread_id, wait=False)
    
    def get_thread_info(self, thread_id: str) -> Optional[ThreadInfo]:
        """获取线程信息"""
        with self._lock:
            return self.threads.get(thread_id)
    
    def get_all_threads(self) -> List[ThreadInfo]:
        """获取所有线程信息"""
        with self._lock:
            return list(self.threads.values())
    
    def get_threads_by_state(self, state: str) -> List[ThreadInfo]:
        """按状态筛选线程"""
        with self._lock:
            return [info for info in self.threads.values() if info.state == state]
    
    def get_active_count(self) -> int:
        """获取活跃线程数量"""
        with self._lock:
            return self._active_count
    
    def get_total_count(self) -> int:
        """获取总线程数量"""
        with self._lock:
            return len(self.threads)
    
    def _on_thread_finished(self, thread_id: str) -> None:
        """线程完成回调"""
        with self._lock:
            if thread_id in self.threads:
                thread_info = self.threads[thread_id]
                old_state = thread_info.state
                
                if thread_info.state == ThreadState.RUNNING:
                    thread_info.state = ThreadState.COMPLETED
                    thread_info.end_time = datetime.now()
                    self._active_count -= 1
                    
                    self.thread_state_changed.emit(thread_id, old_state, ThreadState.COMPLETED)
                    self.thread_stopped.emit(thread_id, thread_info.name)
    
    def _on_thread_error(self, thread_id: str, error: str) -> None:
        """线程错误回调"""
        with self._lock:
            if thread_id in self.threads:
                thread_info = self.threads[thread_id]
                old_state = thread_info.state
                
                thread_info.state = ThreadState.ERROR
                thread_info.error = error
                thread_info.end_time = datetime.now()
                self._active_count -= 1
                
                self.thread_state_changed.emit(thread_id, old_state, ThreadState.ERROR)
                self.thread_error.emit(thread_id, thread_info.name, error)