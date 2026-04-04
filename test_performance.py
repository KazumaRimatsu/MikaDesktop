import requests
import Lib.APIs as APIs

api = APIs.WeatherAPI()
#print(api.GetLocation())
print(api.GetWeather(latitude=30.5233, longitude=120.4727, weather_time_day=-2, weather_time_param="weather_code", current=False))
