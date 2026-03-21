from loguru import logger as log
import datetime



class logger:
    _initialized = False
    
    def __init__(self):
        if not logger._initialized:
            # 只添加文件处理器，loguru默认已经有stderr处理器了
            log.add(f"log/{datetime.datetime.now().strftime('%Y-%m-%d')}.log")
            logger._initialized = True

    def debug(self, msg, **kwargs):
        log.debug(msg, **kwargs)
    def info(self, msg, **kwargs):
        log.info(msg, **kwargs)
    def warning(self, msg, **kwargs):
        log.warning(msg, **kwargs)
    def error(self, msg, **kwargs):
        log.error(msg, **kwargs)
    def critical(self, msg, **kwargs):
        log.critical(msg, **kwargs)