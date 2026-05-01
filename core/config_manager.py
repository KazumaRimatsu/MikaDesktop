import json
import os
from . import log_maker

log = log_maker.logger()

DEFAULT_CONFIG = {
  "dock":{
    "apps": [],
    "except_processes": [
      "shellexperiencehost.exe",
      "applicationframehost.exe",
      "startmenuexperiencehost.exe",
      "widgets.exe",
      "widgetservice.exe",
      "python.exe",
      "wetype_server.exe",
      "wetype_service.exe",
      "wetype_renderer.exe",
      "systemsettings.exe",
      "textinputhost.exe"
    ]
  },
  "notify": {
    "default_timeout": 0
  },
  "debug": False
}

def check(config_path):
    config_file = os.path.join(config_path, "settings.json")
    if not os.path.exists(config_path):
        os.makedirs(config_path)
    if not os.path.exists(config_file):
        with open(config_file, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        log.warning("配置文件不存在，已创建默认配置文件")
        return
    else:
        return    

def load_config(file_path):
    """加载配置文件"""
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 确保所有必要的键都存在
            for key, default_value in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = default_value
            
            return config
        else:
            log.warning(f"Dock配置文件 {file_path} 不存在，将使用默认配置")
            return DEFAULT_CONFIG.copy()
    except Exception as e:
        log.error(f"加载Dock配置文件 {file_path} 失败: {e}")
        return DEFAULT_CONFIG.copy()

def save_config(file_path, config):
    """保存配置文件"""
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # 合并默认值以确保完整性
        merged_config = DEFAULT_CONFIG.copy()
        merged_config.update(config)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(merged_config, f, ensure_ascii=False, indent=2)
        
        log.info(f"Dock配置已成功保存到 {file_path}")
        return True
    except Exception as e:
        log.error(f"保存Dock配置文件 {file_path} 失败: {e}")
        return False