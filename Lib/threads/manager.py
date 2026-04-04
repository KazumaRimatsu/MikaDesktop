"""
简化的线程管理器
提供线程创建、启动、暂停、恢复、终止和资源回收功能
移除健康检查、自动重启等高级生命周期管理功能以解决程序无响应问题
"""

import threading
from typing import Dict, Optional

from .. import log_maker
from .lifecycle import ThreadBase, ThreadState

log = log_maker.logger()


class ThreadManager:
    """简化的线程管理器"""
    
    def __init__(self):
        self._threads: Dict[str, ThreadBase] = {}
        self._lock = threading.RLock()
        self._running = False  # 管理器是否正在运行（有线程在运行）
    
    def register_thread(self, thread: ThreadBase) -> bool:
        """注册线程到管理器
        
        Args:
            thread: 要注册的线程实例
            
        Returns:
            bool: 注册是否成功
        """
        with self._lock:
            thread_name = thread.get_name()
            
            if thread_name in self._threads:
                log.warning(f"线程 '{thread_name}' 已注册，跳过重复注册")
                return False
            
            self._threads[thread_name] = thread
            log.info(f"线程 '{thread_name}' 已注册到管理器")
            return True
    
    def unregister_thread(self, thread_name: str) -> bool:
        """从管理器注销线程
        
        Args:
            thread_name: 线程名称
            
        Returns:
            bool: 注销是否成功
        """
        with self._lock:
            if thread_name not in self._threads:
                log.warning(f"线程 '{thread_name}' 未注册，无法注销")
                return False
            
            thread = self._threads[thread_name]
            
            # 停止线程（如果正在运行）
            if thread.get_state() in [ThreadState.RUNNING, ThreadState.PAUSED]:
                log.info(f"停止已注册的线程 '{thread_name}'")
                thread.stop(timeout=3.0)
            
            del self._threads[thread_name]
            log.info(f"线程 '{thread_name}' 已从管理器注销")
            return True
    
    def start_all(self) -> bool:
        """启动所有已注册的线程
        
        Returns:
            bool: 是否所有线程都启动成功
        """
        with self._lock:
            if self._running:
                log.warning("线程管理器已在运行")
                return False
            
            success = True
            started_count = 0
            
            for thread_name, thread in self._threads.items():
                try:
                    if thread.start():
                        started_count += 1
                        log.info(f"线程 '{thread_name}' 启动成功")
                    else:
                        log.error(f"线程 '{thread_name}' 启动失败")
                        success = False
                except Exception as e:
                    log.error(f"启动线程 '{thread_name}' 时发生异常: {e}")
                    success = False
            
            if started_count > 0:
                self._running = True
                log.info(f"线程管理器已启动，共启动 {started_count}/{len(self._threads)} 个线程")
            else:
                log.warning("没有线程成功启动")
            
            return success
    
    def stop_all(self, timeout: float = 5.0) -> bool:
        """停止所有已注册的线程
        
        Args:
            timeout: 等待线程停止的超时时间（秒）
            
        Returns:
            bool: 是否所有线程都停止成功
        """
        with self._lock:
            if not self._running:
                log.info("线程管理器未运行")
                return True
            
            success = True
            stopped_count = 0
            
            for thread_name, thread in self._threads.items():
                try:
                    if thread.stop(timeout=timeout):
                        stopped_count += 1
                        log.info(f"线程 '{thread_name}' 停止成功")
                    else:
                        log.error(f"线程 '{thread_name}' 停止失败")
                        success = False
                except Exception as e:
                    log.error(f"停止线程 '{thread_name}' 时发生异常: {e}")
                    success = False
            
            self._running = False
            log.info(f"线程管理器已停止，共停止 {stopped_count}/{len(self._threads)} 个线程")
            return success
    
    def pause_all(self) -> bool:
        """暂停所有正在运行的线程
        
        Returns:
            bool: 是否所有线程都暂停成功
        """
        with self._lock:
            success = True
            paused_count = 0
            
            for thread_name, thread in self._threads.items():
                if thread.get_state() == ThreadState.RUNNING:
                    try:
                        if thread.pause():
                            paused_count += 1
                            log.info(f"线程 '{thread_name}' 暂停成功")
                        else:
                            log.error(f"线程 '{thread_name}' 暂停失败")
                            success = False
                    except Exception as e:
                        log.error(f"暂停线程 '{thread_name}' 时发生异常: {e}")
                        success = False
            
            log.info(f"已暂停 {paused_count} 个线程")
            return success
    
    def resume_all(self) -> bool:
        """恢复所有已暂停的线程
        
        Returns:
            bool: 是否所有线程都恢复成功
        """
        with self._lock:
            success = True
            resumed_count = 0
            
            for thread_name, thread in self._threads.items():
                if thread.get_state() == ThreadState.PAUSED:
                    try:
                        if thread.resume():
                            resumed_count += 1
                            log.info(f"线程 '{thread_name}' 恢复成功")
                        else:
                            log.error(f"线程 '{thread_name}' 恢复失败")
                            success = False
                    except Exception as e:
                        log.error(f"恢复线程 '{thread_name}' 时发生异常: {e}")
                        success = False
            
            log.info(f"已恢复 {resumed_count} 个线程")
            return success
    
    def start_thread(self, thread_name: str) -> bool:
        """启动指定线程
        
        Args:
            thread_name: 线程名称
            
        Returns:
            bool: 启动是否成功
        """
        with self._lock:
            if thread_name not in self._threads:
                log.error(f"线程 '{thread_name}' 未注册")
                return False
            
            thread = self._threads[thread_name]
            
            try:
                if thread.start():
                    self._running = True
                    log.info(f"线程 '{thread_name}' 启动成功")
                    return True
                else:
                    log.error(f"线程 '{thread_name}' 启动失败")
                    return False
            except Exception as e:
                log.error(f"启动线程 '{thread_name}' 时发生异常: {e}")
                return False
    
    def stop_thread(self, thread_name: str, timeout: float = 5.0) -> bool:
        """停止指定线程
        
        Args:
            thread_name: 线程名称
            timeout: 等待超时时间（秒）
            
        Returns:
            bool: 停止是否成功
        """
        with self._lock:
            if thread_name not in self._threads:
                log.error(f"线程 '{thread_name}' 未注册")
                return False
            
            thread = self._threads[thread_name]
            
            try:
                if thread.stop(timeout=timeout):
                    # 检查是否还有线程在运行
                    self._update_running_state()
                    log.info(f"线程 '{thread_name}' 停止成功")
                    return True
                else:
                    log.error(f"线程 '{thread_name}' 停止失败")
                    return False
            except Exception as e:
                log.error(f"停止线程 '{thread_name}' 时发生异常: {e}")
                return False
    
    def pause_thread(self, thread_name: str) -> bool:
        """暂停指定线程
        
        Args:
            thread_name: 线程名称
            
        Returns:
            bool: 暂停是否成功
        """
        with self._lock:
            if thread_name not in self._threads:
                log.error(f"线程 '{thread_name}' 未注册")
                return False
            
            thread = self._threads[thread_name]
            
            try:
                if thread.pause():
                    log.info(f"线程 '{thread_name}' 暂停成功")
                    return True
                else:
                    log.error(f"线程 '{thread_name}' 暂停失败")
                    return False
            except Exception as e:
                log.error(f"暂停线程 '{thread_name}' 时发生异常: {e}")
                return False
    
    def resume_thread(self, thread_name: str) -> bool:
        """恢复指定线程
        
        Args:
            thread_name: 线程名称
            
        Returns:
            bool: 恢复是否成功
        """
        with self._lock:
            if thread_name not in self._threads:
                log.error(f"线程 '{thread_name}' 未注册")
                return False
            
            thread = self._threads[thread_name]
            
            try:
                if thread.resume():
                    log.info(f"线程 '{thread_name}' 恢复成功")
                    return True
                else:
                    log.error(f"线程 '{thread_name}' 恢复失败")
                    return False
            except Exception as e:
                log.error(f"恢复线程 '{thread_name}' 时发生异常: {e}")
                return False
    
    def get_thread(self, thread_name: str) -> Optional[ThreadBase]:
        """获取指定线程实例
        
        Args:
            thread_name: 线程名称
            
        Returns:
            ThreadBase: 线程实例，如果未找到则返回None
        """
        with self._lock:
            return self._threads.get(thread_name)
    
    def get_thread_state(self, thread_name: str) -> Optional[ThreadState]:
        """获取指定线程状态
        
        Args:
            thread_name: 线程名称
            
        Returns:
            ThreadState: 线程状态，如果未找到则返回None
        """
        with self._lock:
            if thread_name not in self._threads:
                return None
            
            return self._threads[thread_name].get_state()
    
    def get_all_threads(self) -> Dict[str, ThreadBase]:
        """获取所有已注册的线程
        
        Returns:
            Dict[str, ThreadBase]: 线程名称到线程实例的映射
        """
        with self._lock:
            return self._threads.copy()
    
    def is_running(self) -> bool:
        """检查线程管理器是否正在运行"""
        with self._lock:
            return self._running
    
    def _update_running_state(self):
        """更新运行状态（内部方法）"""
        with self._lock:
            self._running = any(
                thread.get_state() in [ThreadState.RUNNING, ThreadState.PAUSED]
                for thread in self._threads.values()
            )
    
    def __enter__(self):
        """上下文管理器入口"""
        self.start_all()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.stop_all()


# 全局线程管理器实例
_global_thread_manager: Optional[ThreadManager] = None


def get_global_thread_manager() -> ThreadManager:
    """获取全局线程管理器实例（单例）"""
    global _global_thread_manager
    
    if _global_thread_manager is None:
        _global_thread_manager = ThreadManager()
    
    return _global_thread_manager


def create_thread_manager() -> ThreadManager:
    """创建新的线程管理器实例"""
    return ThreadManager()