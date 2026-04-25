from loguru import logger as log
import datetime



class logger:
    _initialized = False
    
    def __init__(self):
        if not logger._initialized:
            # 只添加文件处理器，loguru默认已经有stderr处理器了
            log.add(f"log/{datetime.datetime.now().strftime('%Y-%m-%d')}.log")
            logger._initialized = True
    
    def enable_debug(self):
        self.is_debug = True

    def disable_debug(self):
        self.is_debug = False

    def debug(self, msg, **kwargs):
        if self.is_debug:
            log.opt(depth=1).debug(msg, **kwargs)
    def info(self, msg, **kwargs):
        log.opt(depth=1).info(msg, **kwargs)
    def warning(self, msg, **kwargs):
        log.opt(depth=1).warning(msg, **kwargs)
    def error(self, msg, **kwargs):
        log.opt(depth=1).error(msg, **kwargs)
    def critical(self, msg, **kwargs):
        log.opt(depth=1).critical(msg, **kwargs)