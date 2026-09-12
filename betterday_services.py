"""
更好的一天 —— 服务层（纯逻辑，无 Qt 依赖，可单独测试）

负责：
- Open-Meteo 天气（无需 API Key）
- 城市地理编码
- 农历 / 黄历 / 节日 / 节气（lunar-python）
- 每日一言（hitokoto）
- 整周课程表结构整理
- 月历生成
"""

import calendar as _calendar
import json
import urllib.parse
import urllib.request
from datetime import datetime

from lunar_python import Solar
from lunar_python.util import HolidayUtil


# --------------------------------------------------------------------------
# WMO 天气代码 → (中文描述, 表情符号)
# --------------------------------------------------------------------------
WMO_CODE_MAP = {
    0: ("晴", "☀️"),
    1: ("大致晴朗", "🌤️"),
    2: ("多云", "⛅"),
    3: ("阴", "☁️"),
    45: ("雾", "🌫️"),
    48: ("雾凇", "🌫️"),
    51: ("小毛毛雨", "🌦️"),
    53: ("毛毛雨", "🌦️"),
    55: ("大毛毛雨", "🌧️"),
    56: ("冻毛毛雨", "🌧️"),
    57: ("强冻毛毛雨", "🌧️"),
    61: ("小雨", "🌧️"),
    63: ("中雨", "🌧️"),
    65: ("大雨", "🌧️"),
    66: ("冻雨", "🌧️"),
    67: ("强冻雨", "🌧️"),
    71: ("小雪", "🌨️"),
    73: ("中雪", "🌨️"),
    75: ("大雪", "❄️"),
    77: ("雪粒", "🌨️"),
    80: ("小阵雨", "🌦️"),
    81: ("阵雨", "🌧️"),
    82: ("强阵雨", "⛈️"),
    85: ("小阵雪", "🌨️"),
    86: ("大阵雪", "❄️"),
    95: ("雷阵雨", "⛈️"),
    96: ("雷阵雨伴冰雹", "⛈️"),
    99: ("强雷暴伴冰雹", "⛈️"),
}

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def wmo(code):
    """根据 WMO 天气代码返回 (中文, emoji)。"""
    return WMO_CODE_MAP.get(code, ("未知", "🌡️"))


def http_get_json(url, timeout=10):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ClassWidgets-BetterDay/1.0 (https://github.com/starfall-miao/better-day)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# --------------------------------------------------------------------------
# 天气（Open-Meteo，无需 API Key）
# --------------------------------------------------------------------------
def geocode(city):
    """城市名 → {name, lat, lon, timezone}；失败返回 None。"""
    if not city or not str(city).strip():
        return None
    url = (
        "https://geocoding-api.open-meteo.com/v1/search?name="
        + urllib.parse.quote(str(city).strip())
        + "&count=1&language=zh&format=json"
    )
    data = http_get_json(url)
    results = data.get("results") or []
    if not results:
        return None
    r = results[0]
    return {
        "name": r.get("name") or str(city),
        "lat": r.get("latitude"),
        "lon": r.get("longitude"),
        "timezone": r.get("timezone") or "auto",
    }


def fetch_weather_raw(lat, lon, timezone="auto", forecast_days=7):
    params = urllib.parse.urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,is_day",
            "hourly": "temperature_2m,weather_code,precipitation_probability",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": timezone,
            "forecast_days": forecast_days,
        }
    )
    return http_get_json("https://api.open-meteo.com/v1/forecast?" + params)


def build_now_weather(data):
    cur = data.get("current") or {}
    text, emoji = wmo(cur.get("weather_code"))
    temp = cur.get("temperature_2m")
    feels = cur.get("apparent_temperature")
    return {
        "temp": round(temp) if temp is not None else None,
        "feelsLike": round(feels) if feels is not None else None,
        "humidity": cur.get("relative_humidity_2m"),
        "wind": round(cur.get("wind_speed_10m"), 1) if cur.get("wind_speed_10m") is not None else None,
        "isDay": bool(cur.get("is_day", 1)),
        "text": text,
        "emoji": emoji,
    }


def build_daily_weather(data):
    daily = data.get("daily") or {}
    times = daily.get("time") or []
    codes = daily.get("weather_code") or []
    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []
    out = []
    for i, t in enumerate(times):
        code = codes[i] if i < len(codes) else 0
        text, emoji = wmo(code)
        try:
            dt = datetime.strptime(t, "%Y-%m-%d")
            weekday = WEEKDAY_CN[dt.weekday()]
        except (ValueError, TypeError):
            weekday = ""
        out.append(
            {
                "date": t,
                "weekday": weekday,
                "text": text,
                "emoji": emoji,
                "tempMax": round(tmax[i]) if i < len(tmax) and tmax[i] is not None else None,
                "tempMin": round(tmin[i]) if i < len(tmin) and tmin[i] is not None else None,
            }
        )
    return out


def build_hourly_weather(data, limit=24):
    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    temps = hourly.get("temperature_2m") or []
    codes = hourly.get("weather_code") or []
    pops = hourly.get("precipitation_probability") or []

    # Open-Meteo 默认会返回 forecast_days 天内的全部小时数据，这里只取
    # 「从当前整点开始的接下来 24 小时」。
    now_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
    out = []
    for i, t in enumerate(times):
        try:
            dt = datetime.fromisoformat(t)
            hour = f"{dt.hour:02d}:00"
        except (ValueError, TypeError):
            dt = None
            hour = t

        if dt is not None and dt < now_hour:
            continue

        code = codes[i] if i < len(codes) else 0
        text, emoji = wmo(code)
        out.append(
            {
                "hour": hour,
                "temp": round(temps[i]) if i < len(temps) and temps[i] is not None else None,
                "text": text,
                "emoji": emoji,
                "precip": pops[i] if i < len(pops) and pops[i] is not None else None,
            }
        )
        if len(out) >= limit:
            break
    return out


# --------------------------------------------------------------------------
# 黄历 / 节日 / 农历（lunar-python）
# --------------------------------------------------------------------------
def build_almanac(now=None):
    now = now or datetime.now()
    solar = Solar.fromDate(now)
    lunar = solar.getLunar()

    holiday = HolidayUtil.getHoliday(now.year, now.month, now.day)
    festivals = [f for f in (lunar.getFestivals() or []) if f]
    festivals += [f for f in (lunar.getOtherFestivals() or []) if f]

    jieqi = lunar.getJieQi() or ""
    next_jieqi = lunar.getNextJieQi()
    next_jieqi_name = next_jieqi.getName() if next_jieqi else ""
    next_jieqi_date = ""
    days_to_next = None
    if next_jieqi and next_jieqi.getSolar():
        try:
            next_jieqi_date = next_jieqi.getSolar().toYmd()
            d1 = datetime.strptime(next_jieqi_date, "%Y-%m-%d").date()
            days_to_next = (d1 - now.date()).days
        except (ValueError, TypeError):
            days_to_next = None

    return {
        "lunarYear": lunar.getYearInChinese(),
        "lunarMonth": lunar.getMonthInChinese(),
        "lunarDay": lunar.getDayInChinese(),
        "lunarFull": f"{lunar.getYearInChinese()}年{lunar.getMonthInChinese()}月{lunar.getDayInChinese()}",
        "ganzhiYear": lunar.getYearInGanZhi(),
        "ganzhiDay": lunar.getDayInGanZhi(),
        "shengxiao": lunar.getDayShengXiao(),
        "chong": lunar.getDayChongDesc(),
        "yi": list(lunar.getDayYi() or []),
        "ji": list(lunar.getDayJi() or []),
        "jieqi": jieqi,
        "festivals": festivals,
        "legalHoliday": holiday.getName() if holiday else "",
        "isWorkday": holiday.isWork() if holiday else None,
        "nextJieQi": next_jieqi_name,
        "nextJieQiDate": next_jieqi_date,
        "daysToNextJieQi": days_to_next,
    }


def build_month_calendar(year, month):
    """生成某个月的日历数据（含农历、节日、节气）。"""
    days = []
    today = datetime.now().date()
    last_day = _calendar.monthrange(year, month)[1]
    for day in range(1, last_day + 1):
        d = datetime(year, month, day)
        solar = Solar.fromDate(d)
        lunar = solar.getLunar()
        fests = [f for f in (lunar.getFestivals() or []) if f]
        fests += [f for f in (lunar.getOtherFestivals() or []) if f]
        holiday = HolidayUtil.getHoliday(year, month, day)
        days.append(
            {
                "solarDay": day,
                "lunarDay": lunar.getDayInChinese(),
                "lunarMonth": lunar.getMonthInChinese(),
                "weekday": d.weekday(),  # 0=周一
                "isToday": d.date() == today,
                "festival": fests[0] if fests else "",
                "jieqi": lunar.getJieQi() or "",
                "legalHoliday": holiday.getName() if holiday else "",
            }
        )
    return days


# --------------------------------------------------------------------------
# 每日一言（hitokoto）
# --------------------------------------------------------------------------
def fetch_quote():
    data = http_get_json("https://v1.hitokoto.cn/?encode=json")
    return {
        "text": data.get("hitokoto") or "",
        "from": (data.get("from") or "").strip() or (data.get("from_who") or "").strip(),
    }


# --------------------------------------------------------------------------
# 整周课程表
# --------------------------------------------------------------------------
def build_week_schedule(schedule):
    """把 ScheduleData（pydantic 或 dict）整理成 7 天结构。

    返回: [{"day": 1, "dayName": "周一", "entries": [...]}, ...]（day 1=周一）
    """
    week = [{"day": d, "dayName": WEEKDAY_CN[d - 1], "entries": []} for d in range(1, 8)]
    if not schedule:
        return week

    try:
        data = schedule.model_dump()
    except AttributeError:
        data = schedule

    if not isinstance(data, dict):
        return week

    subjects = {s.get("id"): s for s in (data.get("subjects") or []) if s.get("id")}

    # 按星期几聚合条目（dayOfWeek 为 1~7，1=周一）
    by_day = {d: [] for d in range(1, 8)}
    for day in data.get("days") or []:
        for dow in day.get("dayOfWeek") or []:
            if dow in by_day:
                by_day[dow].extend(day.get("entries") or [])

    for item in week:
        entries = sorted(by_day.get(item["day"], []), key=lambda e: str(e.get("startTime") or ""))
        out = []
        for e in entries:
            subj = subjects.get(e.get("subjectId")) or {}
            out.append(
                {
                    "type": e.get("type") or "",
                    "startTime": e.get("startTime") or "",
                    "endTime": e.get("endTime") or "",
                    "title": e.get("title") or subj.get("simplifiedName") or subj.get("name") or "",
                    "teacher": subj.get("teacher") or "",
                    "location": subj.get("location") or "",
                    "color": subj.get("color") or "",
                }
            )
        item["entries"] = out

    return week
