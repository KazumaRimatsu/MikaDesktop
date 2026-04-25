import requests
import time
import json
from datetime import datetime, timedelta

class WeatherAPI():
    """天气API封装类，提供地理位置获取和天气查询功能"""
    def __init__(self):
        """初始化天气API，设置天气状态映射和请求头"""
        self.weather_status =[
            {"code": 0,"wea": "晴"},
            {"code": 1,"wea": "晴"},
            {"code": 2,"wea": "多云"},
            {"code": 3,"wea": "阴"},
            {"code": 45,"wea": "雾"},
            {"code": 48,"wea": "霜雾"},
            {"code": 51,"wea": "毛毛雨"},
            {"code": 53,"wea": "毛毛雨"},
            {"code": 55,"wea": "毛毛雨"},
            {"code": 56,"wea": "冻雨"},
            {"code": 57,"wea": "冻雨"},
            {"code": 61,"wea": "小雨"},
            {"code": 63,"wea": "中雨"},
            {"code": 65,"wea": "大雨"},
            {"code": 66,"wea": "冻雨"},
            {"code": 67,"wea": "冻雨"},
            {"code": 71,"wea": "小雪"},
            {"code": 73,"wea": "中雪"},
            {"code": 75,"wea": "大雪"},
            {"code": 77,"wea": "雪粒"},
            {"code": 80,"wea": "阵雨"},
            {"code": 81,"wea": "阵雨"},
            {"code": 82,"wea": "阵雨"},
            {"code": 85,"wea": "阵雪"},
            {"code": 86,"wea": "阵雪"},
            {"code": 95,"wea": "雷暴"},
            {"code": 96,"wea": "冰雹"},
            {"code": 99,"wea": "冰雹"},
  ]
        self.headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0"
        }
        # 创建天气代码映射字典，提高查找效率
        self.weather_status_map = {item["code"]: item["wea"] for item in self.weather_status}

    def GetLocation(self):
        """获取当前IP的地理位置信息"""
        apis = [
            {"url": "https://api.ip.sb/geoip", "timeout": 5},
            {"url": "https://ipwhois.app/json/?format=json", "timeout": 5}
        ]
        
        for api_info in apis:
            try:
                resp = requests.get(api_info["url"], headers=self.headers, timeout=api_info["timeout"])
                resp.raise_for_status()
                ctb = resp.json()
                
                # 验证响应数据
                if "latitude" in ctb and "longitude" in ctb and "city" in ctb:
                    return {
                        "latitude": ctb["latitude"],
                        "longitude": ctb["longitude"],
                        "region": ctb["city"]
                    }
                else:
                    continue  # 尝试下一个API
                    
            except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError) as e:
                continue  # 尝试下一个API
        
        # 所有API都失败
        return {"error": True, "message": "All location APIs failed"}
        
    def GetWeather(self, timeout=6, 
                   latitude=None, longitude=None,
                   current=True, current_param:str="temperature_2m,weather_code",
                   weather_time_day = 0, weather_time_param:str="weather_code"):
        """
        获取天气信息
        
        Args:
            timeout: 请求超时时间（秒）
            latitude: 纬度，范围-90到90
            longitude: 经度，范围-180到180
            current: 是否获取当前天气
            current_param: 当前天气参数，逗号分隔
            weather_time_day: 天气预报天数，0表示不获取预报，正数表示未来天数，负数表示过去天数
            weather_time_param: 天气预报参数，逗号分隔
        
        Returns:
            dict: 成功返回天气信息字典，失败返回错误字典
        """
        try:
            # 参数验证
            if latitude is None or longitude is None:
                return {"error": True, "message": "Latitude and longitude must be provided"}
            if not (-90 <= latitude <= 90):
                return {"error": True, "message": "Latitude must be between -90 and 90"}
            if not (-180 <= longitude <= 180):
                return {"error": True, "message": "Longitude must be between -180 and 180"}
            
            current_part = f"&current={current_param}" if current else ""
            time_part = f"&time={weather_time_param}" if weather_time_day != 0 else ""

            # 处理日期范围
            today = datetime.now().date()
            weather_current_time = today.strftime("%Y-%m-%d")
            
            if weather_time_day != 0:
                if weather_time_day > 0:    
                    end_date = today + timedelta(days=weather_time_day)
                    weather_end_time = end_date.strftime("%Y-%m-%d")
                    weather_time_part = f"&start_date={weather_current_time}&end_date={weather_end_time}&daily={weather_time_param}"
                elif weather_time_day < 0:
                    start_date = today + timedelta(days=weather_time_day)
                    weather_start_time = start_date.strftime("%Y-%m-%d")
                    weather_time_part = f"&start_date={weather_start_time}&end_date={weather_current_time}&daily={weather_time_param}"
            else:
                weather_time_part = ""

            url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}{current_part}{time_part}{weather_time_part}"
            print(url)
            try:
                resp = requests.get(url, headers=self.headers, timeout=timeout)
                resp.raise_for_status()
                data = resp.json()
                
                return data
                
            except requests.exceptions.RequestException as req_err:
                return {"error": True, "message": f"Request failed: {str(req_err)}"}
            except json.JSONDecodeError as json_err:
                return {"error": True, "message": f"Invalid JSON response: {str(json_err)}"}
            except KeyError as key_err:
                return {"error": True, "message": f"Missing expected data key: {str(key_err)}"}
        except Exception as e:
            return {"error": True, "message": f"Unexpected error: {str(e)}"}

    def GetWeatherStatus(self, code: int) -> str:
        """根据天气代码获取天气描述"""
        return self.weather_status_map.get(code, "未知")