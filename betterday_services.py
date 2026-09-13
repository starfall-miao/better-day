"""
更好的一天 —— 服务层（纯逻辑，无 Qt 依赖，可单独测试）

负责：
- 中央气象台（nmc.cn）天气（实况 + 7 日预报 + 空气质量，无需 API Key）
- 城市名 → 站点代码（打包内置 cities.json）
- 农历 / 黄历 / 节日 / 节气（lunar-python）
- 每日一言（hitokoto）
- 整周课程表结构整理（表格形式）
- 月历生成
"""

import calendar as _calendar
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime

from lunar_python import Solar
from lunar_python.util import HolidayUtil


WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# 固定公历日期的节日 / 纪念日（lunar-python 不覆盖的公历节日）
FIXED_FESTIVALS = {
    (1, 1): "元旦",
    (2, 14): "情人节",
    (3, 8): "妇女节",
    (3, 12): "植树节",
    (4, 1): "愚人节",
    (5, 1): "劳动节",
    (5, 4): "青年节",
    (6, 1): "儿童节",
    (7, 1): "建党节",
    (8, 1): "建军节",
    (9, 10): "教师节",
    (10, 1): "国庆节",
    (12, 24): "平安夜",
    (12, 25): "圣诞节",
}


def weather_emoji(text):
    """把中文天气描述映射成 emoji（非固定枚举，做关键词匹配）。"""
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


def http_get_json(url, timeout=10, referer=None):
    headers = {"User-Agent": "Mozilla/5.0 (ClassWidgets-BetterDay/1.0)"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# --------------------------------------------------------------------------
# 城市名 → 中央气象台站点代码（打包内置 cities.json）
# --------------------------------------------------------------------------
_cities_cache = None


def _load_cities():
    global _cities_cache
    if _cities_cache is not None:
        return _cities_cache
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cities.json")
        with open(path, encoding="utf-8") as f:
            _cities_cache = json.load(f)
    except Exception:
        _cities_cache = {}
    return _cities_cache


def resolve_city(name):
    """城市名 → 站点代码；找不到返回 None。支持「上海」「上海市」等写法。"""
    name = (name or "").strip()
    if not name:
        return None
    cities = _load_cities()

    # 去掉「市/省/自治区」等后缀再匹配（如「北京市」→「北京」）
    for suf in ("特别行政区", "自治区", "自治州", "地区", "市", "省"):
        if name.endswith(suf) and len(name) > len(suf):
            base = name[: -len(suf)]
            if base in cities:
                return cities[base]["code"]

    if name in cities:
        return cities[name]["code"]

    # 前缀匹配：如「哈尔」→「哈尔滨」
    for k, v in cities.items():
        if k.startswith(name):
            return v["code"]
    return None


# --------------------------------------------------------------------------
# 天气（中央气象台 nmc.cn，无需 API Key）
# --------------------------------------------------------------------------
def fetch_weather(city, timeout=20):
    """从中央气象台拉取实况 + 7 日预报 + 空气质量。失败抛异常。"""
    code = resolve_city(city)
    if not code:
        raise ValueError(f"找不到「{city}」这座城市，换个写法试试？")
    url = "https://www.nmc.cn/rest/weather?stationid=" + urllib.parse.quote(code)
    data = http_get_json(url, timeout=timeout, referer="https://www.nmc.cn/")
    payload = data.get("data")
    if not payload or not payload.get("real"):
        raise ValueError(f"没查到「{city}」的天气数据")
    return payload


def _to_number(v):
    try:
        f = float(v)
        return None if f > 9000 else f  # 中央气象台用 9999 表示无效值
    except (TypeError, ValueError):
        return None


def _clean(text):
    text = (text or "").strip()
    return "" if text in ("9999", "null", "9999.0") else text


def build_now_weather(data):
    real = data.get("real") or {}
    weather = real.get("weather") or {}
    wind = real.get("wind") or {}
    text = _clean(weather.get("info"))
    temp = _to_number(weather.get("temperature"))
    feels = _to_number(weather.get("feelst"))
    humidity = _to_number(weather.get("humidity"))
    wind_text = " ".join(x for x in (_clean(wind.get("direct")), _clean(wind.get("power"))) if x)
    air = data.get("air") or {}
    return {
        "temp": round(temp) if temp is not None else None,
        "feelsLike": round(feels) if feels is not None else None,
        "humidity": round(humidity) if humidity is not None else None,
        "wind": wind_text,
        "isDay": True,
        "text": text,
        "emoji": weather_emoji(text),
        "aqi": round(_to_number(air.get("aqi"))) if _to_number(air.get("aqi")) is not None else None,
        "aqiCategory": _clean(air.get("text")),
        "reportTime": _clean(real.get("publish_time")),
    }


def build_daily_weather(data):
    out = []
    predict = data.get("predict") or {}
    for i, f in enumerate(predict.get("detail") or []):
        day = f.get("day") or {}
        night = f.get("night") or {}
        day_text = _clean(day.get("weather", {}).get("info"))
        night_text = _clean(night.get("weather", {}).get("info"))
        # 今天（i==0）的白天字段通常为 9999（已到晚上），用夜间/实况替代
        text = day_text or night_text or ""
        temp_max = _to_number(day.get("weather", {}).get("temperature"))
        temp_min = _to_number(night.get("weather", {}).get("temperature"))
        if i == 0:
            now = build_now_weather(data)
            text = now["text"] or night_text
            if temp_max is None:
                temp_max = now["temp"]
        try:
            dt = datetime.strptime(f.get("date", ""), "%Y-%m-%d")
            weekday = WEEKDAY_CN[dt.weekday()]
        except (ValueError, TypeError):
            weekday = ""
        out.append(
            {
                "date": f.get("date") or "",
                "weekday": weekday,
                "text": text,
                "nightText": night_text,
                "emoji": weather_emoji(text),
                "tempMax": round(temp_max) if temp_max is not None else None,
                "tempMin": round(temp_min) if temp_min is not None else None,
                "wind": _clean((day.get("wind") or {}).get("direct")) or _clean((night.get("wind") or {}).get("direct")),
                "precipitation": _to_number(f.get("precipitation")),
            }
        )
    return out


def build_hourly_weather(data, limit=24):
    # 中央气象台不提供未来逐小时预报，返回空列表（由前端隐藏该区块）
    return []


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
    fixed = FIXED_FESTIVALS.get((now.month, now.day))
    if fixed:
        festivals.append(fixed)

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
    """生成某个月的日历数据（含农历、节日、节气）。

    性能优化：用 Solar.fromYmd 直接构造、跳过昂贵的 getOtherFestivals()，
    整月计算从 ~1.3s 降到 ~0.05s。
    """
    days = []
    today = datetime.now().date()
    last_day = _calendar.monthrange(year, month)[1]
    for day in range(1, last_day + 1):
        solar = Solar.fromYmd(year, month, day)
        lunar = solar.getLunar()
        fests = [f for f in (lunar.getFestivals() or []) if f]
        fixed = FIXED_FESTIVALS.get((month, day))
        if fixed:
            fests.append(fixed)
        holiday = HolidayUtil.getHoliday(year, month, day)
        days.append(
            {
                "solarDay": day,
                "lunarDay": lunar.getDayInChinese(),
                "lunarMonth": lunar.getMonthInChinese(),
                "weekday": _calendar.weekday(year, month, day),  # 0=周一
                "isToday": (year, month, day) == (today.year, today.month, today.day),
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
    """把 ScheduleData 整理成「整周课程表格」结构。

    返回:
      {
        "periods": [{"start": "08:00", "end": "08:45", "label": "08:00-08:45"}, ...],
        "days": [{"day": 1, "dayName": "周一", "cells": [entry_or_None, ...]}, ...]
      }
    cells[i] 与 periods[i] 一一对应；无课为 None。
    """
    days_out = [{"day": d, "dayName": WEEKDAY_CN[d - 1], "cells": []} for d in range(1, 8)]
    empty = {"periods": [], "days": days_out}

    if not schedule:
        return empty
    try:
        data = schedule.model_dump()
    except AttributeError:
        data = schedule
    if not isinstance(data, dict):
        return empty

    subjects = {s.get("id"): s for s in (data.get("subjects") or []) if s.get("id")}

    # 按星期几聚合条目（dayOfWeek 为 1~7，1=周一）
    by_day = {d: [] for d in range(1, 8)}
    for day in data.get("days") or []:
        for dow in day.get("dayOfWeek") or []:
            if dow in by_day:
                by_day[dow].extend(day.get("entries") or [])

    # 汇总所有出现过的节次（startTime~endTime），按开始时间排序
    period_keys = set()
    for d in range(1, 8):
        for e in by_day[d]:
            period_keys.add((str(e.get("startTime") or ""), str(e.get("endTime") or "")))
    periods = [
        {
            "start": k[0],
            "end": k[1],
            "label": (k[0] + "-" + k[1]) if k[0] else "",
        }
        for k in sorted(period_keys, key=lambda x: x[0])
    ]

    def build_entry(e):
        subj = subjects.get(e.get("subjectId")) or {}
        return {
            "type": e.get("type") or "",
            "startTime": e.get("startTime") or "",
            "endTime": e.get("endTime") or "",
            "title": e.get("title") or subj.get("simplifiedName") or subj.get("name") or "",
            "teacher": subj.get("teacher") or "",
            "location": subj.get("location") or "",
            "color": subj.get("color") or "",
        }

    for item in days_out:
        d = item["day"]
        m = {}
        for e in by_day[d]:
            key = (str(e.get("startTime") or ""), str(e.get("endTime") or ""))
            m[key] = build_entry(e)
        item["cells"] = [m.get((p["start"], p["end"])) for p in periods]

    return {"periods": periods, "days": days_out}
