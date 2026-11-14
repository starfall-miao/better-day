"""
更好的一天 —— 服务层（纯逻辑，无 Qt 依赖，可单独测试）

负责：
- 中央气象台（nmc.cn）天气（实况 + 7 日预报 + 空气质量 + 24 小时温度走势，无需 API Key）
- 城市名 → 站点代码（打包内置 cities.json，支持「广东深圳」「北京市朝阳区」等写法）
- 农历 / 黄历 / 节日 / 节气（lunar-python），含最近节日 / 节气查找
- 每日一言（hitokoto）
- 整周课程表结构整理（尊重单双周 / 指定周 / 调课覆盖）
- 月历生成

本模块只做纯计算，不碰 Qt，方便在后台线程里调用，也方便单独跑单元测试：
    python -m unittest discover -s tests
"""

import calendar as _calendar
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from lunar_python import Solar
from lunar_python.util import HolidayUtil


WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
WEEKDAY_SHORT = ["一", "二", "三", "四", "五", "六", "日"]

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

# 中央气象台用 9999 表示无效值；接口偶尔也会直接返回 "-" 之类的占位符
_INVALID_NUMBERS = 9000.0
_INVALID_TEXTS = {"", "-", "--", "—", "null", "None", "none", "9999", "9999.0"}

# 中央气象台天气现象图标编号 → emoji（文字缺失时兜底）
_IMG_EMOJI = {
    "0": "☀️",
    "1": "⛅",
    "2": "☁️",
    "3": "🌦️",
    "4": "⛈️",
    "5": "⛈️",
    "6": "🌨️",
    "7": "🌧️",
    "8": "🌧️",
    "9": "🌧️",
    "10": "⛈️",
    "11": "⛈️",
    "12": "⛈️",
    "13": "🌨️",
    "14": "❄️",
    "15": "❄️",
    "16": "❄️",
    "17": "❄️",
    "18": "🌫️",
    "19": "🌧️",
    "20": "🌪️",
    "29": "🌫️",
    "30": "🌪️",
    "31": "🌪️",
    "53": "🌫️",
}

# 省级行政区后缀（按长度降序剥离，避免「广西壮族自治区」被截坏）
_PROVINCE_SUFFIXES = (
    "维吾尔自治区",
    "壮族自治区",
    "回族自治区",
    "特别行政区",
    "自治区",
    "省",
    "市",
)

# 城市名的行政后缀（用户常写「海淀区」「朝阳县」）
_CITY_SUFFIXES = (
    "特别行政区",
    "自治区",
    "自治州",
    "地区",
    "新区",
    "市",
    "区",
    "县",
    "盟",
    "旗",
)


# --------------------------------------------------------------------------
# 小工具
# --------------------------------------------------------------------------
def clean_text(value):
    """清洗接口里的无效文本占位符。"""
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text in _INVALID_TEXTS else text


def to_number(value, invalid=_INVALID_NUMBERS):
    """把接口里的数值转成 float；9999 之类的哨兵值返回 None。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number >= invalid:  # NaN 也丢掉
        return None
    return number


def _round(value, digits=0):
    """四舍五入；digits=0 时返回 int，避免 QML 里显示成 "13.0"。"""
    if value is None:
        return None
    rounded = round(value, digits)
    return int(rounded) if digits == 0 else rounded


def _short_hm(value):
    """把 "2026-11-14 06:57" / "06:57" 统一成 "06:57"。"""
    text = clean_text(value)
    if not text:
        return ""
    if " " in text:
        text = text.split(" ", 1)[1]
    return text[:5]


def weather_emoji(text, img=""):
    """把天气描述映射成 emoji（先按关键词匹配，再退回图标编号）。"""
    cleaned = clean_text(text)
    if not cleaned:
        return _IMG_EMOJI.get(clean_text(img), "🌡️")
    if "雷" in cleaned:
        return "⛈️"
    if "雪" in cleaned or "冰粒" in cleaned:
        return "❄️"
    if "雨" in cleaned:
        return "🌧️"
    if "雾" in cleaned or "霾" in cleaned:
        return "🌫️"
    if "沙" in cleaned or "尘" in cleaned or "飑" in cleaned:
        return "🌪️"
    if "阴" in cleaned:
        return "☁️"
    if "多云" in cleaned:
        return "⛅"
    if "晴" in cleaned:
        return "☀️"
    return "🌤️"


def http_get_json(url, timeout=10, referer=None, retries=1):
    """GET 一个 JSON 接口；网络抖动时重试一次。"""
    headers = {
        "User-Agent": "Mozilla/5.0 (ClassWidgets-BetterDay/1.1)",
        "Accept": "application/json, text/plain, */*",
    }
    if referer:
        headers["Referer"] = referer

    last_error = None
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            last_error = error
            if attempt >= retries:
                break
    raise last_error


# --------------------------------------------------------------------------
# 城市名 → 中央气象台站点代码（打包内置 cities.json）
# --------------------------------------------------------------------------
_cities_cache = None
_province_aliases_cache = None


def _load_cities():
    global _cities_cache
    if _cities_cache is not None:
        return _cities_cache
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cities.json")
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        _cities_cache = data if isinstance(data, dict) else {}
    except Exception:
        _cities_cache = {}
    return _cities_cache


def city_count():
    """内置城市表里的条目数（设置页用来展示数据规模）。"""
    return len(_load_cities())


def _province_aliases():
    """省级别名表：全称与简称 → 全称，例如 "广东" → "广东省"。"""
    global _province_aliases_cache
    if _province_aliases_cache is not None:
        return _province_aliases_cache

    aliases = {}
    for info in _load_cities().values():
        province = clean_text((info or {}).get("province"))
        if not province:
            continue
        aliases[province] = province
        for suffix in _PROVINCE_SUFFIXES:
            if province.endswith(suffix) and len(province) > len(suffix):
                aliases.setdefault(province[: -len(suffix)], province)
                break
    _province_aliases_cache = aliases
    return aliases


def _make_match(name, info):
    return {
        "name": name,
        "code": clean_text((info or {}).get("code")),
        "province": clean_text((info or {}).get("province")),
    }


def _strip_city_suffix(name):
    for suffix in _CITY_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return ""


def _find_candidates(name):
    """按「精确 → 去行政后缀 → 前缀」三级查找，返回候选列表（可能为空）。"""
    cities = _load_cities()
    if not name:
        return []

    if name in cities:
        return [_make_match(name, cities[name])]

    stripped = _strip_city_suffix(name)
    if stripped and stripped in cities:
        return [_make_match(stripped, cities[stripped])]

    # 前缀匹配：如「哈尔」→「哈尔滨」；命中多个时优先更短的键（更像城市而不是区县）
    prefix_hits = [
        (key, info)
        for key, info in cities.items()
        if key.startswith(name) or (stripped and key.startswith(stripped))
    ]
    prefix_hits.sort(key=lambda item: (len(item[0]), item[0]))
    return [_make_match(key, info) for key, info in prefix_hits]


def _split_province(query):
    """把「广东省深圳市」「北京朝阳」拆成 (省全称, 余下部分)。"""
    aliases = _province_aliases()
    for alias in sorted(aliases, key=len, reverse=True):
        if query.startswith(alias):
            return aliases[alias], query[len(alias):]
    return "", query


def resolve_city_verbose(name):
    """城市名 → 站点（带候选），供设置页做即时提示。

    返回:
        {
          "query": 原始输入, "ok": bool,
          "code": 站点代码, "name": 命中的城市名, "province": 省份,
          "message": 人类可读的说明,
          "alternatives": [{"name","province","code"}, ...],
        }
    """
    query = clean_text(name).replace("　", "").replace(" ", "")
    result = {
        "query": query,
        "ok": False,
        "code": "",
        "name": "",
        "province": "",
        "message": "",
        "alternatives": [],
    }
    if not query:
        result["message"] = "还没有填写城市"
        return result

    cities = _load_cities()

    # 1. 直接填站点代码（5 位字母，如 Wqsps）
    if len(query) == 5 and query.isascii() and query.isalpha():
        for key, info in cities.items():
            if clean_text((info or {}).get("code")) == query:
                match = _make_match(key, info)
                result.update(ok=True, code=match["code"], name=match["name"], province=match["province"])
                result["message"] = f"已匹配站点 {match['name']}（{match['province']}）"
                return result

    # 2. 省 / 直辖市前缀 + 城市名
    province_hint, rest = _split_province(query)
    candidates = []
    if province_hint:
        if rest:
            candidates = [
                match for match in _find_candidates(rest)
                if match["province"] == province_hint
            ]
        if not candidates:
            # 「北京」「上海」这类直辖市：省名本身就是城市名
            candidates = [
                match for match in _find_candidates(province_hint)
                if match["province"] == province_hint
            ]
    if not candidates:
        candidates = _find_candidates(query)

    if not candidates:
        result["message"] = f"找不到「{query}」这座城市，换个写法试试？"
        return result

    primary = candidates[0]
    alternatives = [
        item for item in candidates[1:6]
        if (item["name"], item["province"]) != (primary["name"], primary["province"])
    ]
    result.update(
        ok=True,
        code=primary["code"],
        name=primary["name"],
        province=primary["province"],
        alternatives=alternatives,
    )
    if primary["province"] and primary["province"] != primary["name"]:
        result["message"] = f"已匹配 {primary['province']}·{primary['name']}"
    else:
        result["message"] = f"已匹配 {primary['name']}"
    if alternatives:
        names = "、".join(
            f"{item['province']}·{item['name']}" if item["province"] != item["name"] else item["name"]
            for item in alternatives[:3]
        )
        result["message"] += f"（也可试试：{names}）"
    return result


def resolve_city(name):
    """城市名 → 站点信息 dict（code/name/province）；找不到返回 None。"""
    resolved = resolve_city_verbose(name)
    return resolved if resolved["ok"] else None


def search_cities(keyword, limit=8):
    """按关键字搜索城市，供设置页给出候选项。"""
    text = clean_text(keyword)
    if not text:
        return []
    hits = []
    for name, info in _load_cities().items():
        if text in name:
            match = _make_match(name, info)
            match["label"] = (
                f"{match['province']}·{match['name']}"
                if match["province"] and match["province"] != match["name"]
                else match["name"]
            )
            hits.append(match)
    hits.sort(key=lambda item: (len(item["name"]), item["name"]))
    return hits[: max(1, int(limit or 8))]


# --------------------------------------------------------------------------
# 天气（中央气象台 nmc.cn，无需 API Key）
# --------------------------------------------------------------------------
NMC_WEATHER_URL = "https://www.nmc.cn/rest/weather?stationid="


def fetch_weather(city, timeout=20):
    """从中央气象台拉取实况 + 7 日预报 + 空气质量。失败抛 ValueError。"""
    resolved = resolve_city(city)
    if not resolved:
        raise ValueError(f"找不到「{clean_text(city)}」这座城市，换个写法试试？")
    return fetch_weather_by_code(resolved["code"], timeout=timeout)


def fetch_weather_by_code(code, timeout=20):
    """按站点代码取天气原始数据。"""
    city_code = clean_text(code)
    if not city_code:
        raise ValueError("城市代码为空，请先在插件设置里填写城市")
    url = NMC_WEATHER_URL + urllib.parse.quote(city_code)
    data = http_get_json(url, timeout=timeout, referer="https://www.nmc.cn/")
    if not isinstance(data, dict):
        raise ValueError("天气接口返回格式不对，稍后再试试？")
    payload = data.get("data")
    if not payload or not payload.get("real"):
        raise ValueError(clean_text(data.get("msg")) or "没查到天气数据，稍后再试试？")
    return payload


def _warning_from(data):
    """解析中央气象台预警信息，没有预警返回 None。"""
    warn = (data.get("real") or {}).get("warn") or {}
    if not isinstance(warn, dict):
        return None
    alert = clean_text(warn.get("alert"))
    if not alert:
        return None
    province = clean_text(warn.get("province"))
    city = clean_text(warn.get("city"))
    signal_type = clean_text(warn.get("signaltype"))
    signal_level = clean_text(warn.get("signallevel"))
    title = "".join(
        part for part in (
            city or province,
            signal_type,
            signal_level,
        ) if part
    )
    return {
        "title": title or alert,
        "type": signal_type,
        "level": signal_level,
        "content": clean_text(warn.get("issuecontent")),
        "issueTime": clean_text(warn.get("issuetime")),
    }


def _forecast_detail(data):
    detail = (data.get("predict") or {}).get("detail") or []
    return [item for item in detail if isinstance(item, dict)]


def build_now_weather(data, now=None):
    """整理实况天气。data 为 nmc 接口的 data 字段。"""
    now = now or datetime.now()
    real = data.get("real") or {}
    weather = real.get("weather") or {}
    wind = real.get("wind") or {}
    air = data.get("air") or {}
    if not isinstance(air, dict):
        air = {}

    detail = _forecast_detail(data)
    today_day = ((detail[0].get("day") or {}).get("weather") or {}) if detail else {}
    today_night = ((detail[0].get("night") or {}).get("weather") or {}) if detail else {}

    day_text = clean_text(today_day.get("info"))
    night_text = clean_text(today_night.get("info"))
    # 实况的天气现象经常是 "-"，按当前时刻用预报的白天 / 夜间天气兜底
    text = clean_text(weather.get("info")) or day_text or night_text

    sunrise_sunset = real.get("sunriseSunset") or {}
    if not isinstance(sunrise_sunset, dict):
        sunrise_sunset = {}

    wind_direct = clean_text(wind.get("direct"))
    wind_power = clean_text(wind.get("power"))
    temp = to_number(weather.get("temperature"))
    feels = to_number(weather.get("feelst"))
    humidity = to_number(weather.get("humidity"))
    rain = to_number(weather.get("rain"), invalid=1000)
    aqi = to_number(air.get("aqi"))

    icon = clean_text(weather.get("img"))
    if not icon:
        icon = clean_text(today_day.get("img"))

    return {
        "temp": _round(temp),
        "feelsLike": _round(feels),
        "humidity": _round(humidity),
        "rain": _round(rain, 1),
        "tempDiff": _round(to_number(weather.get("temperatureDiff")), 1),
        "wind": " ".join(part for part in (wind_direct, wind_power) if part),
        "windDirect": wind_direct,
        "windPower": wind_power,
        "isDay": 6 <= now.hour < 18,
        "text": text,
        "nightText": night_text,
        "emoji": weather_emoji(text, icon),
        "aqi": _round(aqi),
        "aqiCategory": clean_text(air.get("text")),
        "sunrise": _short_hm(sunrise_sunset.get("sunrise")),
        "sunset": _short_hm(sunrise_sunset.get("sunset")),
        "warning": _warning_from(data),
        "reportTime": clean_text(real.get("publish_time")),
        "reportTimeShort": _short_hm(real.get("publish_time")),
    }


def build_daily_weather(data, limit=7):
    """整理 7 日预报，附带「今天 / 明天 / 后天」标签与日期简写。"""
    out = []
    detail = _forecast_detail(data)
    today = datetime.now().date()
    now_weather = build_now_weather(data)

    for index, item in enumerate(detail[:limit]):
        day = item.get("day") or {}
        night = item.get("night") or {}
        day_weather = day.get("weather") or {}
        night_weather = night.get("weather") or {}

        day_text = clean_text(day_weather.get("info"))
        night_text = clean_text(night_weather.get("info"))
        temp_max = to_number(day_weather.get("temperature"))
        temp_min = to_number(night_weather.get("temperature"))

        try:
            date_value = datetime.strptime(clean_text(item.get("date")), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            date_value = today + timedelta(days=index)

        text = day_text or night_text
        if index == 0:
            # 今天的白天字段偶尔已经失效，用实况补上
            text = day_text or now_weather.get("text") or night_text
            if temp_max is None:
                temp_max = now_weather.get("temp")

        label = ""
        if date_value == today:
            label = "今天"
        elif date_value == today + timedelta(days=1):
            label = "明天"
        elif date_value == today + timedelta(days=2):
            label = "后天"

        out.append(
            {
                "date": date_value.isoformat(),
                "dateShort": date_value.strftime("%m-%d"),
                "weekday": WEEKDAY_CN[date_value.weekday()],
                "weekdayShort": WEEKDAY_SHORT[date_value.weekday()],
                "label": label,
                "text": text,
                "nightText": night_text,
                "emoji": weather_emoji(text, day_weather.get("img")),
                "nightEmoji": weather_emoji(night_text, night_weather.get("img")),
                "tempMax": _round(temp_max),
                "tempMin": _round(temp_min),
                "wind": clean_text((day.get("wind") or {}).get("direct"))
                or clean_text((night.get("wind") or {}).get("direct")),
                "precipitation": _round(to_number(item.get("precipitation"), invalid=100), 1),
                "isToday": date_value == today,
            }
        )
    return out


def build_hourly_trend(data, limit=24):
    """把实况曲线（passedchart，过去逐小时）整理成按时间升序的温度走势。"""
    chart = data.get("passedchart") or []
    if not isinstance(chart, list):
        return {"points": [], "summary": {"min": None, "max": None, "last": None}}

    points = []
    for item in chart:
        if not isinstance(item, dict):
            continue
        temp = to_number(item.get("temperature"))
        if temp is None:
            continue
        stamp = clean_text(item.get("time"))
        points.append(
            {
                "time": stamp,
                "timeShort": _short_hm(stamp),
                "temp": _round(temp, 1),
                "rain": _round(to_number(item.get("rain1h"), invalid=100), 1),
                "humidity": _round(to_number(item.get("humidity"))),
                "windSpeed": _round(to_number(item.get("windSpeed")), 1),
            }
        )

    points.sort(key=lambda point: point["time"])
    points = points[-limit:]
    if not points:
        return {"points": [], "summary": {"min": None, "max": None, "last": None}}

    temps = [point["temp"] for point in points if point["temp"] is not None]
    low, high = min(temps), max(temps)
    span = (high - low) or 1.0
    for point in points:
        temp = point["temp"] if point["temp"] is not None else low
        point["ratio"] = round((temp - low) / span, 3)
    return {
        "points": points,
        "summary": {"min": low, "max": high, "last": points[-1]["temp"]},
    }


# --------------------------------------------------------------------------
# 黄历 / 节日 / 农历（lunar-python）
# --------------------------------------------------------------------------
def _collect_festivals(lunar, month, day):
    """合并农历节日与公历固定节日，去重并保持「农历优先」的顺序。"""
    names = []
    for name in (lunar.getFestivals() or []):
        cleaned = clean_text(name)
        if cleaned and cleaned not in names:
            names.append(cleaned)
    fixed = FIXED_FESTIVALS.get((month, day))
    if fixed and fixed not in names:
        names.append(fixed)
    return names


def build_almanac(now=None):
    """今日黄历：农历、干支、宜忌、冲煞、值星、节日与节气。"""
    now = now or datetime.now()
    solar = Solar.fromDate(now)
    lunar = solar.getLunar()

    holiday = HolidayUtil.getHoliday(now.year, now.month, now.day)
    festivals = _collect_festivals(lunar, now.month, now.day)

    jieqi = clean_text(lunar.getJieQi())
    next_jieqi = lunar.getNextJieQi()
    next_jieqi_name = next_jieqi.getName() if next_jieqi else ""
    next_jieqi_date = ""
    days_to_next = None
    if next_jieqi and next_jieqi.getSolar():
        try:
            next_jieqi_date = next_jieqi.getSolar().toYmd()
            days_to_next = (
                datetime.strptime(next_jieqi_date, "%Y-%m-%d").date() - now.date()
            ).days
        except (TypeError, ValueError):
            days_to_next = None

    lunar_month = lunar.getMonthInChinese()
    lunar_day = lunar.getDayInChinese()

    return {
        "solarDate": now.strftime("%Y-%m-%d"),
        "solarFull": f"{now.year}年{now.month}月{now.day}日",
        "weekday": WEEKDAY_CN[now.weekday()],
        "weekdayShort": WEEKDAY_SHORT[now.weekday()],
        "lunarYear": lunar.getYearInChinese(),
        "lunarMonth": lunar_month,
        "lunarDay": lunar_day,
        "lunarMonthDay": f"{lunar_month}月{lunar_day}",
        "lunarFull": f"{lunar.getYearInChinese()}年{lunar_month}月{lunar_day}",
        "ganzhiYear": lunar.getYearInGanZhi(),
        "ganzhiMonth": lunar.getMonthInGanZhi(),
        "ganzhiDay": lunar.getDayInGanZhi(),
        "shengxiao": lunar.getDayShengXiao(),
        "chong": clean_text(lunar.getDayChongDesc()),
        "sha": clean_text(lunar.getDaySha()),
        "xiu": clean_text(lunar.getXiu()),
        "zhixing": clean_text(lunar.getZhiXing()),
        "yi": [name for name in (lunar.getDayYi() or []) if clean_text(name)],
        "ji": [name for name in (lunar.getDayJi() or []) if clean_text(name)],
        "jieqi": jieqi,
        "hasJieQi": bool(jieqi),
        "festivals": festivals,
        "legalHoliday": holiday.getName() if holiday else "",
        "isWorkday": holiday.isWork() if holiday else None,
        "nextJieQi": next_jieqi_name,
        "nextJieQiDate": next_jieqi_date,
        "daysToNextJieQi": days_to_next,
    }


_festival_scan_cache = {}


def _upcoming_jieqi(now, count=4):
    """顺着 getNextJieQi() 往后取几个节气（不用逐天扫描，很快）。"""
    items = []
    today = now.date()
    cursor = Solar.fromDate(now).getLunar()
    for _ in range(max(1, count) * 2 + 1):
        next_jieqi = cursor.getNextJieQi()
        if not next_jieqi or not next_jieqi.getSolar():
            break
        solar = next_jieqi.getSolar()
        try:
            day_value = datetime.strptime(solar.toYmd(), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            break
        if day_value <= today:
            # 今天正好是节气：跳过它，从明天继续往后找
            tomorrow = today + timedelta(days=1)
            cursor = Solar.fromYmd(tomorrow.year, tomorrow.month, tomorrow.day).getLunar()
            continue
        items.append(
            {
                "name": next_jieqi.getName(),
                "date": day_value.isoformat(),
                "dateShort": day_value.strftime("%m-%d"),
                "weekday": WEEKDAY_CN[day_value.weekday()],
                "daysLeft": (day_value - today).days,
                "kind": "jieqi",
            }
        )
        cursor = Solar.fromYmd(day_value.year, day_value.month, day_value.day).getLunar()
        if len(items) >= count:
            break
    return items


def upcoming_festivals(now=None, horizon=45, limit=5):
    """未来一段时间里的节日 / 节气（含倒计时）。

    节气走「下一个节气」链式取值（很快），节日才逐天扫描；
    结果按日期缓存，建议只在后台线程里调用（首次约 0.2~0.6s）。
    """
    now = now or datetime.now()
    key = now.date().isoformat()
    cached = _festival_scan_cache.get(key)
    if cached is not None:
        return cached[:limit] if limit else cached

    wanted = max(1, int(limit or 5))
    today = now.date()
    festivals = []
    for offset in range(1, horizon + 1):
        day_value = today + timedelta(days=offset)
        lunar = Solar.fromYmd(day_value.year, day_value.month, day_value.day).getLunar()
        for name in _collect_festivals(lunar, day_value.month, day_value.day):
            festivals.append(
                {
                    "name": name,
                    "date": day_value.isoformat(),
                    "dateShort": day_value.strftime("%m-%d"),
                    "weekday": WEEKDAY_CN[day_value.weekday()],
                    "daysLeft": offset,
                    "kind": "festival",
                }
            )
        if len(festivals) >= wanted + 1:
            break

    found = _upcoming_jieqi(now, count=min(4, wanted + 1)) + festivals
    found.sort(key=lambda item: (item["date"], item["kind"] != "festival"))

    # 同名同日的条目只留一条
    deduped = []
    seen = set()
    for item in found:
        marker = (item["name"], item["date"])
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(item)

    _festival_scan_cache.clear()
    _festival_scan_cache[key] = deduped
    return deduped[:limit] if limit else deduped


def build_month_calendar(year, month):
    """生成某个月的日历数据（含农历、节日、节气、法定节假日）。

    性能：跳过昂贵的 getOtherFestivals()，整月约 0.1s，由后台线程预热。
    """
    days = []
    today = datetime.now().date()
    last_day = _calendar.monthrange(year, month)[1]
    for day in range(1, last_day + 1):
        solar = Solar.fromYmd(year, month, day)
        lunar = solar.getLunar()
        festivals = _collect_festivals(lunar, month, day)
        holiday = HolidayUtil.getHoliday(year, month, day)
        jieqi = clean_text(lunar.getJieQi())
        weekday = _calendar.weekday(year, month, day)  # 0=周一
        days.append(
            {
                "solarDay": day,
                "lunarDay": lunar.getDayInChinese(),
                "lunarMonth": lunar.getMonthInChinese(),
                "weekday": weekday,
                "isToday": (year, month, day) == (today.year, today.month, today.day),
                "isWeekend": weekday >= 5,
                "festival": festivals[0] if festivals else "",
                "hasFestival": bool(festivals),
                "jieqi": jieqi,
                "legalHoliday": holiday.getName() if holiday else "",
                "isHolidayRest": bool(holiday and not holiday.isWork()),
            }
        )
    return days


# --------------------------------------------------------------------------
# 每日一言（hitokoto）
# --------------------------------------------------------------------------
HITOKOTO_URL = "https://v1.hitokoto.cn/"


def fetch_quote(category="", timeout=10):
    """取一句一言；分类可以留空。分类不可用时自动退回默认分类。"""

    def _request(extra):
        payload = http_get_json(
            HITOKOTO_URL + "?encode=json" + extra,
            timeout=timeout,
            referer="https://hitokoto.cn/",
        )
        text = clean_text(payload.get("hitokoto"))
        if not text:
            raise ValueError("一言接口没有返回内容")
        return {
            "text": text,
            "from": clean_text(payload.get("from")) or clean_text(payload.get("from_who")),
            "fromWho": clean_text(payload.get("from_who")),
            "category": clean_text(payload.get("type")),
            "uuid": clean_text(payload.get("uuid")),
        }

    category = clean_text(category)
    if category:
        try:
            return _request("&c=" + urllib.parse.quote(category))
        except Exception:
            pass
    return _request("")


# --------------------------------------------------------------------------
# 整周课程表
# --------------------------------------------------------------------------
def _week_list(values):
    result = []
    for item in values:
        if isinstance(item, bool):
            continue
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        if number >= 1 and number not in result:
            result.append(number)
    result.sort()
    return result


def normalize_week_rule(value):
    """把课表里的 weeks 规则统一成 None / "all" / "odd" / "even" / int / list。

    与 Class Widgets 2 的语义一致：整数是 maxWeekCycle 内的轮换位置，
    列表是从开学日算起的绝对周，odd / even 也是绝对周的奇偶。
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 1 else None
    if isinstance(value, float):
        return int(value) if value.is_integer() and value >= 1 else None
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"all", "odd", "even"}:
            return text
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except ValueError:
                return None
            return _week_list(parsed) if isinstance(parsed, list) else None
        if "," in text:
            parts = [part.strip() for part in text.split(",")]
            weeks = _week_list(parts)
            return weeks if len(weeks) == len(parts) else None
        try:
            number = int(text)
        except ValueError:
            return None
        return number if number >= 1 else None
    if isinstance(value, (list, tuple)):
        return _week_list(value)
    return None


def cycle_week_for(absolute_week, max_week_cycle):
    """绝对周 → 在 maxWeekCycle 内的轮换位置（1 起）。"""
    cycle = max(1, int(max_week_cycle or 1))
    if absolute_week >= 1:
        return ((absolute_week - 1) % cycle) + 1
    return (absolute_week % cycle) + 1


def week_rule_matches(rule, absolute_week, max_week_cycle=1):
    """规则是否包含某个绝对周；无规则视为「每周都上」。"""
    normalized = normalize_week_rule(rule)
    if normalized is None or normalized == "all":
        return True
    if normalized == "odd":
        return absolute_week % 2 == 1
    if normalized == "even":
        return absolute_week % 2 == 0
    if isinstance(normalized, int):
        return cycle_week_for(absolute_week, max_week_cycle) == normalized
    if isinstance(normalized, list):
        return absolute_week in normalized
    return False


def _week_dates(schedule_meta, absolute_week):
    """按开学日推出某一周的 7 个日期（周一为首）。"""
    start_text = clean_text((schedule_meta or {}).get("startDate"))
    try:
        start = datetime.strptime(start_text, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        start = None

    if start is not None and absolute_week and absolute_week >= 1:
        week_start = start + timedelta(days=(absolute_week - 1) * 7)
    elif start is not None:
        week_start = start
    else:
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())
    week_start -= timedelta(days=week_start.weekday())
    return {index + 1: week_start + timedelta(days=index) for index in range(7)}


def _schedule_payload(schedule):
    """把 ScheduleData 或普通 dict 统一成 dict。"""
    if not schedule:
        return {}
    try:
        data = schedule.model_dump()
    except AttributeError:
        data = schedule
    return data if isinstance(data, dict) else {}


def _override_priority(override, weeks, day_of_week, max_week_cycle):
    """调课覆盖的优先级：指定周 > 单双周 / 轮换 > 不限制；不适用返回 None。"""
    days = override.get("dayOfWeek") or []
    if days and day_of_week not in days:
        return None
    rule = normalize_week_rule(override.get("weeks"))
    if rule is None:
        return 1
    if not week_rule_matches(rule, weeks, max_week_cycle):
        return None
    if rule == "all":
        return 1
    if isinstance(rule, list):
        return 3
    return 2


def _resolve_entry(entry, weeks, day_of_week, overrides, max_week_cycle):
    """对单个课程应用调课覆盖（字段级覆盖，最具体的生效）。"""
    data = dict(entry)
    applicable = []
    for override in overrides:
        if clean_text(override.get("entryId")) != clean_text(entry.get("id")):
            continue
        priority = _override_priority(override, weeks, day_of_week, max_week_cycle)
        if priority is not None:
            applicable.append((priority, override))

    subject_overridden = False
    title_overridden = False
    for _, override in sorted(applicable, key=lambda item: item[0]):
        if clean_text(override.get("subjectId")):
            data["subjectId"] = override.get("subjectId")
            subject_overridden = True
        if clean_text(override.get("title")):
            data["title"] = override.get("title")
            title_overridden = True
        if clean_text(override.get("startTime")):
            data["startTime"] = override.get("startTime")
        if clean_text(override.get("endTime")):
            data["endTime"] = override.get("endTime")
    if subject_overridden and not title_overridden:
        data["title"] = None
    return data


def build_week_schedule(schedule, week=0, day_of_week=0, max_week_cycle=1):
    """把课表整理成「整周课程表格」。

    返回:
      {
        "periods": [{"start": "08:00", "end": "08:45", "label": "08:00-08:45"}, ...],
        "days": [{"day": 1, "dayName": "周一", "date": "2026-09-01",
                  "dateShort": "09-01", "isToday": bool, "cells": [...]}, ...],
        "weekNumber": 绝对周, "weekOfCycle": 轮换位置, "maxWeekCycle": N,
        "todayDay": 今天星期几, "hasData": bool, "startDate": "2026-09-01",
      }
    cells[i] 与 periods[i] 一一对应；无课为 None。
    """
    data = _schedule_payload(schedule)
    meta = data.get("meta") or {}
    max_cycle = int(_safe_float(meta.get("maxWeekCycle"), 1) or 1)
    if max_week_cycle and int(max_week_cycle) > 0:
        max_cycle = int(max_week_cycle)
    absolute_week = int(week or 0)
    today_day = int(day_of_week or 0) or datetime.now().isoweekday()

    result = {
        "periods": [],
        "days": [
            {
                "day": index,
                "dayName": WEEKDAY_CN[index - 1],
                "dayShort": WEEKDAY_SHORT[index - 1],
                "date": "",
                "dateShort": "",
                "isToday": index == today_day,
                "cells": [],
            }
            for index in range(1, 8)
        ],
        "weekNumber": absolute_week,
        "weekOfCycle": cycle_week_for(absolute_week, max_cycle) if absolute_week >= 1 else 0,
        "maxWeekCycle": max_cycle,
        "todayDay": today_day,
        "hasData": False,
        "startDate": clean_text(meta.get("startDate")),
    }
    if not data:
        return result

    subjects = {
        subject.get("id"): subject
        for subject in (data.get("subjects") or [])
        if isinstance(subject, dict) and subject.get("id")
    }
    timelines = [item for item in (data.get("days") or []) if isinstance(item, dict)]
    overrides = [item for item in (data.get("overrides") or []) if isinstance(item, dict)]
    week_dates = _week_dates(meta, absolute_week)

    def build_entry(raw, day_index):
        merged = _resolve_entry(raw, absolute_week, day_index, overrides, max_cycle)
        subject = subjects.get(merged.get("subjectId")) or {}
        title = (
            clean_text(merged.get("title"))
            or clean_text(subject.get("simplifiedName"))
            or clean_text(subject.get("name"))
        )
        return {
            "id": clean_text(merged.get("id")),
            "type": clean_text(merged.get("type")) or "class",
            "startTime": clean_text(merged.get("startTime")),
            "endTime": clean_text(merged.get("endTime")),
            "title": title,
            "teacher": clean_text(subject.get("teacher")),
            "location": clean_text(subject.get("location")),
            "color": clean_text(subject.get("color")),
        }

    columns = {}
    for day_index in range(1, 8):
        date_text = week_dates[day_index].isoformat() if week_dates else ""
        matched = []
        for timeline in timelines:
            timeline_date = clean_text(timeline.get("date"))
            if timeline_date:
                # 按日期指定的时间线只在对应那天生效
                if timeline_date == date_text:
                    matched.append(((4, 0, 0, ()), timeline))
                continue
            days = timeline.get("dayOfWeek") or []
            if days and day_index not in days:
                continue
            rule = normalize_week_rule(timeline.get("weeks"))
            if absolute_week >= 1 and rule is not None and not week_rule_matches(rule, absolute_week, max_cycle):
                continue
            day_priority = (7 - len(days)) if days else 0
            weekday_order = tuple(sorted(days))
            if isinstance(rule, list):
                week_priority = 3
            elif rule is None or rule == "all":
                week_priority = 1
            else:
                week_priority = 2
            matched.append(((0, day_priority, week_priority, weekday_order), timeline))

        # 越具体的时间线越晚合并，从而覆盖更宽泛的时间线
        merged = {}
        for _, timeline in sorted(matched, key=lambda item: item[0]):
            for raw_entry in (timeline.get("entries") or []):
                if not isinstance(raw_entry, dict):
                    continue
                entry_type = clean_text(raw_entry.get("type"))
                if entry_type not in ("", "class", "activity"):
                    continue
                slot = (
                    clean_text(raw_entry.get("startTime")),
                    clean_text(raw_entry.get("endTime")),
                )
                merged[slot] = raw_entry
        columns[day_index] = [
            build_entry(raw, day_index)
            for raw in sorted(merged.values(), key=lambda item: clean_text(item.get("startTime")))
        ]

    period_keys = {
        (entry["startTime"], entry["endTime"])
        for entries in columns.values()
        for entry in entries
        if entry["startTime"]
    }
    periods = [
        {"start": start, "end": end, "label": f"{start}-{end}" if start else ""}
        for start, end in sorted(period_keys)
    ]

    days_out = []
    for day_index in range(1, 8):
        entries_by_slot = {
            (entry["startTime"], entry["endTime"]): entry
            for entry in columns.get(day_index, [])
        }
        day_value = week_dates.get(day_index)
        days_out.append(
            {
                "day": day_index,
                "dayName": WEEKDAY_CN[day_index - 1],
                "dayShort": WEEKDAY_SHORT[day_index - 1],
                "date": day_value.isoformat() if day_value else "",
                "dateShort": day_value.strftime("%m-%d") if day_value else "",
                "isToday": day_index == today_day,
                "cells": [
                    entries_by_slot.get((period["start"], period["end"]))
                    for period in periods
                ],
            }
        )

    result.update(periods=periods, days=days_out, hasData=bool(periods))
    return result


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def pick_today_course(week_schedule, day_of_week=0, now=None):
    """从整周课表里挑出「今天正在上 / 下一节」的课程，供小卡片轮换。"""
    now = now or datetime.now()
    day_index = int(day_of_week or 0) or now.isoweekday()
    schedule = week_schedule if isinstance(week_schedule, dict) else {}
    column = next(
        (item for item in (schedule.get("days") or []) if item.get("day") == day_index),
        None,
    )

    result = {
        "state": "none",
        "title": "",
        "subtitle": "今天没有课啦",
        "startTime": "",
        "endTime": "",
        "teacher": "",
        "location": "",
        "color": "",
        "minutesLeft": None,
    }
    if not column or not schedule.get("hasData"):
        result["subtitle"] = "还没有课表数据"
        return result

    entries = [entry for entry in (column.get("cells") or []) if entry]
    if not entries:
        result["subtitle"] = "今天没有课啦"
        return result

    current_clock = now.strftime("%H:%M")
    current = None
    upcoming = None
    for entry in entries:
        start = entry.get("startTime") or ""
        end = entry.get("endTime") or ""
        if start and end and start <= current_clock < end:
            current = entry
            break
        if start and start > current_clock and upcoming is None:
            upcoming = entry

    chosen = current or upcoming or entries[-1]
    result.update(
        title=chosen.get("title") or "",
        startTime=chosen.get("startTime") or "",
        endTime=chosen.get("endTime") or "",
        teacher=chosen.get("teacher") or "",
        location=chosen.get("location") or "",
        color=chosen.get("color") or "",
    )

    def minutes_until(clock):
        try:
            hour, minute = (int(part) for part in str(clock).split(":")[:2])
        except (TypeError, ValueError):
            return None
        return hour * 60 + minute - (now.hour * 60 + now.minute)

    if current:
        result["state"] = "class"
        left = minutes_until(current.get("endTime"))
        result["minutesLeft"] = left
        result["subtitle"] = (
            f"还有 {left} 分钟下课" if left is not None and left >= 0 else "正在上课"
        )
    elif upcoming:
        result["state"] = "upcoming"
        left = minutes_until(upcoming.get("startTime"))
        result["minutesLeft"] = left
        result["subtitle"] = (
            f"{left} 分钟后开始" if left is not None and left >= 0 else "马上开始"
        )
    else:
        result["state"] = "after"
        result["subtitle"] = "今天的课都上完啦"
    return result
