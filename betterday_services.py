"""
更好的一天 —— 服务层（纯逻辑，无 Qt 依赖，可单独测试）

负责：
- uapis.cn 天气（当前 / 24 小时 / 7 日预报 + 空气质量，无需 API Key）
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


WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def weather_emoji(text):
    """把 uapis.cn 返回的中文天气描述映射成 emoji（非固定枚举，做关键词匹配）。"""
    t = (text or "").strip()
    if not t:
        return "🌡️"
    if "雷" in t:
        return "⛈️"
    if "雪" in t:
        return "❄️"
    if "雨" in t:
        return "🌧️"
    if "雾" in t or "霾" in t:
        return "🌫️"
    if "沙" in t or "尘" in t:
        return "🌪️"
    if "阴" in t:
        return "☁️"
    if "多云" in t:
        return "⛅"
    if "晴" in t:
        return "☀️"
    return "🌤️"


def http_get_json(url, timeout=10):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ClassWidgets-BetterDay/1.0 (https://github.com/starfall-miao/better-day)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# --------------------------------------------------------------------------
# 天气（uapis.cn，无需 API Key）
# --------------------------------------------------------------------------
def fetch_weather(city, timeout=12):
    """从 uapis.cn 拉取实时天气 + 7 日预报 + 24 小时预报（一次请求）。

    失败会抛出异常（网络错误 / urllib 错误），由调用方兜底。
    """
    params = urllib.parse.urlencode(
        {
            "city": str(city).strip(),
            "extended": "true",
            "forecast": "true",
            "hourly": "true",
        }
    )
    return http_get_json("https://uapis.cn/api/v1/misc/weather?" + params, timeout=timeout)


def build_now_weather(data):
    text = data.get("weather") or ""
    temp = data.get("temperature")
    feels = data.get("feels_like")
    wind = " ".join(x for x in (data.get("wind_direction"), data.get("wind_power")) if x)
    return {
        "temp": round(temp) if isinstance(temp, (int, float)) else None,
        "feelsLike": round(feels) if isinstance(feels, (int, float)) else None,
        "humidity": data.get("humidity"),
        "wind": wind,
        "isDay": True,
        "text": text,
        "emoji": weather_emoji(text),
        "aqi": data.get("aqi"),
        "aqiCategory": data.get("aqi_category"),
        "reportTime": data.get("report_time") or "",
    }


def build_daily_weather(data):
    out = []
    for f in data.get("forecast") or []:
        text = f.get("weather_day") or f.get("weather") or ""
        out.append(
            {
                "date": f.get("date") or "",
                "weekday": f.get("week") or "",
                "text": text,
                "emoji": weather_emoji(text),
                "tempMax": round(f["temp_max"]) if isinstance(f.get("temp_max"), (int, float)) else None,
                "tempMin": round(f["temp_min"]) if isinstance(f.get("temp_min"), (int, float)) else None,
            }
        )
    return out


def build_hourly_weather(data, limit=24):
    out = []
    for h in data.get("hourly_forecast") or []:
        t = h.get("time") or ""
        hour = t
        # 兼容 "YYYY-MM-DD HH:MM:SS" 与 ISO8601（可能带时区）
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                hour = datetime.strptime(t[:19], fmt).strftime("%H:%M")
                break
            except (ValueError, TypeError):
                continue
        text = h.get("weather") or ""
        out.append(
            {
                "hour": hour,
                "temp": round(h["temperature"]) if isinstance(h.get("temperature"), (int, float)) else None,
                "text": text,
                "emoji": weather_emoji(text),
                "precip": h.get("precip"),
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
