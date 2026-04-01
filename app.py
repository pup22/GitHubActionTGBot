import os
import requests
from dotenv import load_dotenv
import openmeteo_requests
import requests_cache
import pandas as pd
from retry_requests import retry
from datetime import datetime, timezone, timedelta

load_dotenv()
LATITUDE = os.getenv('LATITUDE')
LONGITUDE = os.getenv('LONGITUDE')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

def get_usd_rate():
    """Получает актуальный курс доллара от НБУ"""
    try:
        url = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=USD&json"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if data:
            return data[0]['rate']
    except Exception as e:
        print(f"Ошибка при получении курса валют: {e}")
    return None

def get_weather():
    # Setup the Open-Meteo API client with cache and retry on error
    cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
    retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
    openmeteo = openmeteo_requests.Client(session = retry_session)

    # Make sure all required weather variables are listed here
    # The order of variables in hourly or daily is important to assign them correctly below
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
      "latitude": LATITUDE,
      "longitude": LONGITUDE,
      "daily": ["sunrise", "sunset"],
      "current": ["temperature_2m", "relative_humidity_2m", "wind_speed_10m", "wind_direction_10m"],
      "timezone": "Europe/Kiev",
      "forecast_days": 1,
    }
    responses = openmeteo.weather_api(url, params = params)

    # Process first location. Add a for-loop for multiple locations or weather models
    response = responses[0]
    offset = response.UtcOffsetSeconds()
    tz_kiev = timezone(timedelta(seconds=offset))

    print(f"Coordinates: {response.Latitude()}°N {response.Longitude()}°E")
    print(f"Elevation: {response.Elevation()} m asl")
    print(f"Timezone: {response.Timezone()}{response.TimezoneAbbreviation()}")
    print(f"Timezone difference to GMT+0: {response.UtcOffsetSeconds()}s")

    # Process current data. The order of variables needs to be the same as requested.
    current = response.Current()
    current_temperature_2m = current.Variables(0).Value()
    current_relative_humidity_2m = current.Variables(1).Value()
    current_wind_speed_10m = current.Variables(2).Value()
    current_wind_direction_10m = current.Variables(3).Value()

    print(f"\nCurrent time: {current.Time()}")
    print(f"Current temperature_2m: {current_temperature_2m}")
    print(f"Current relative_humidity_2m: {current_relative_humidity_2m}")
    print(f"Current wind_speed_10m: {current_wind_speed_10m}")
    print(f"Current wind_direction_10m: {current_wind_direction_10m}")

    # Process daily data. The order of variables needs to be the same as requested.
    daily = response.Daily()
    daily_sunrise = daily.Variables(0).ValuesInt64AsNumpy()
    daily_sunset = daily.Variables(1).ValuesInt64AsNumpy()

    daily_data = {"date": pd.date_range(
      start = pd.to_datetime(daily.Time() + response.UtcOffsetSeconds(), unit = "s", utc = True),
      end =  pd.to_datetime(daily.TimeEnd() + response.UtcOffsetSeconds(), unit = "s", utc = True),
      freq = pd.Timedelta(seconds = daily.Interval()),
      inclusive = "left"
    )}

    daily_data["sunrise"] = daily_sunrise
    daily_data["sunset"] = daily_sunset

    daily_dataframe = pd.DataFrame(data = daily_data)
    print("\nDaily data\n", daily_dataframe)

    # Получаем курс доллара
    usd_rate = get_usd_rate()

    # Вспомогательная функция для форматирования времени из Unix Timestamp
    def format_unix_time(timestamp):
            # Создаем время в UTC и принудительно переводим в нужный часовой пояс
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(tz_kiev).strftime('%H:%M')

    # Формируем текст сообщения 🌍
    message = (
        f"<b>Погода в Одессе</b>\n"
        # f"<i>Координаты: {response.Latitude():.2f}°N, {response.Longitude():.2f}°E</i>\n\n"
        f"🌡 {current_temperature_2m:.1f}°C 💧 {current_relative_humidity_2m}%\n"
        f"💨 <b>Ветер:</b> {current_wind_speed_10m:.1f} км/ч, {current_wind_direction_10m:.0f}°\n"
        f"🌅 <b>Восход:</b> {format_unix_time(daily_sunrise[0])} 🌇 <b>Закат:</b> {format_unix_time(daily_sunset[0])}\n"
        # f"🕒 <i>Данные на: {format_unix_time(current.Time())}</i>\n"
        f"💵 <b>Курс НБУ USD:</b> {usd_rate:.2f} грн\n" if usd_rate else ""
    ).strip()

    print(f"Погода\n\n{message}")
    return message

def send_message(message):
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'

    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML',
        'disable_notification': True
    }
    res = requests.post(url, json=payload) 
    
    # ЕСЛИ ОШИБКА — ПЕЧАТАЕМ ТОЧНЫЙ ОТВЕТ ОТ ТЕЛЕГРАМ
    if not res.ok:
        print(f"\n--- ОШИБКА ОТ TELEGRAM ---")
        print(f"Отправленный chat_id: '{TELEGRAM_CHAT_ID}'")
        print(f"Ответ API: {res.text}\n--------------------------\n")
        
    res.raise_for_status()

    return res.json()


if __name__ == '__main__':
    weather = get_weather()
    send_message(weather)
