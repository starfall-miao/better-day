"""更好的一天 —— 服务层单元测试。

只测纯逻辑，不访问网络：天气接口的响应结构在下面用固定样例代替。
运行：
    python -m unittest discover -s tests -v
"""

import json
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import betterday_services as svc  # noqa: E402


# 中央气象台 /rest/weather 的真实响应（截取关键字段）
WEATHER_FIXTURE = {
    "real": {
        "station": {"code": "Wqsps", "province": "北京市", "city": "北京"},
        "publish_time": "2026-11-14 12:45",
        "weather": {
            "temperature": 12.4,
            "temperatureDiff": -1.5,
            "humidity": 55.0,
            "rain": 0.0,
            "info": "-",  # 实况天气现象常常是无效占位符
            "img": "9999",
            "feelst": 11.8,
        },
        "wind": {"direct": "东北风", "power": "微风", "speed": 0.5},
        "sunriseSunset": {"sunrise": "2026-11-14 06:57", "sunset": "2026-11-14 16:59"},
        "warn": {"alert": "9999", "city": "9999", "issuecontent": "9999"},
    },
    "predict": {
        "detail": [
            {
                "date": "2026-11-14",
                "day": {"weather": {"info": "晴", "img": "0", "temperature": "13"}},
                "night": {"weather": {"info": "雾", "img": "18", "temperature": "3"}},
                "precipitation": 0.0,
            },
            {
                "date": "2026-11-15",
                "day": {"weather": {"info": "多云", "img": "1", "temperature": "12"}},
                "night": {"weather": {"info": "小雨", "img": "7", "temperature": "3"}},
                "precipitation": 0.6,
            },
        ]
    },
    "air": {"aqi": 139, "text": "轻度污染"},
    "passedchart": [
        {"time": "2026-11-14 12:00", "temperature": 11.5, "rain1h": 0.0, "humidity": 58.0},
        {"time": "2026-11-14 10:00", "temperature": 8.2, "rain1h": 0.0, "humidity": 68.0},
        {"time": "2026-11-14 11:00", "temperature": 9.8, "rain1h": 0.0, "humidity": 61.0},
    ],
}


def make_schedule():
    """构造一份课表：单双周 + 指定周 + 调课覆盖都覆盖到。"""
    return {
        "meta": {"id": "s1", "version": 1, "maxWeekCycle": 2, "startDate": "2026-09-01"},
        "subjects": [
            {"id": "sub-yuwen", "name": "语文", "simplifiedName": "语文", "teacher": "王老师", "color": "#FFB3C1"},
            {"id": "sub-shuxue", "name": "数学", "simplifiedName": "数学", "teacher": "李老师", "color": "#A0C4FF"},
        ],
        "days": [
            {
                "id": "t1",
                "dayOfWeek": [1, 3],
                "weeks": "all",
                "entries": [
                    {"id": "e1", "type": "class", "startTime": "08:00", "endTime": "08:45", "subjectId": "sub-yuwen"},
                    {"id": "e2", "type": "class", "startTime": "09:00", "endTime": "09:45", "subjectId": "sub-shuxue"},
                ],
            },
            {
                "id": "t2",
                "dayOfWeek": [5],
                "weeks": "odd",
                "entries": [
                    {"id": "e3", "type": "class", "startTime": "08:00", "endTime": "08:45", "subjectId": "sub-shuxue"},
                ],
            },
            {
                "id": "t3",
                "dayOfWeek": [1],
                "weeks": [4],
                "entries": [
                    {"id": "e4", "type": "class", "startTime": "10:00", "endTime": "10:45", "subjectId": "sub-yuwen"},
                ],
            },
        ],
        "overrides": [
            {
                "id": "o1",
                "entryId": "e1",
                "dayOfWeek": [1],
                "weeks": "all",
                "subjectId": "sub-shuxue",
            }
        ],
    }


class CleanTextTest(unittest.TestCase):
    def test_placeholders_become_empty(self):
        for value in (None, "", "-", "--", "9999", "9999.0", "null"):
            self.assertEqual(svc.clean_text(value), "")
        self.assertEqual(svc.clean_text(" 晴 "), "晴")

    def test_to_number_drops_sentinel(self):
        self.assertIsNone(svc.to_number("9999"))
        self.assertIsNone(svc.to_number("abc"))
        self.assertEqual(svc.to_number("12.5"), 12.5)
        self.assertEqual(svc.to_number("-3"), -3.0)

    def test_round_returns_int(self):
        self.assertEqual(svc._round(12.6), 13)
        self.assertIsInstance(svc._round(12.6), int)
        self.assertEqual(svc._round(12.55, 1), 12.6)


class EmojiTest(unittest.TestCase):
    def test_keyword_priority(self):
        self.assertEqual(svc.weather_emoji("雷阵雨"), "⛈️")
        self.assertEqual(svc.weather_emoji("小雪"), "❄️")
        self.assertEqual(svc.weather_emoji("中雨"), "🌧️")
        self.assertEqual(svc.weather_emoji("霾"), "🌫️")
        self.assertEqual(svc.weather_emoji("沙尘暴"), "🌪️")
        self.assertEqual(svc.weather_emoji("阴"), "☁️")
        self.assertEqual(svc.weather_emoji("多云"), "⛅")
        self.assertEqual(svc.weather_emoji("晴"), "☀️")

    def test_falls_back_to_icon_code(self):
        self.assertEqual(svc.weather_emoji("-", "18"), "🌫️")
        self.assertEqual(svc.weather_emoji("", ""), "🌡️")


class CityResolveTest(unittest.TestCase):
    def test_exact_and_suffix(self):
        self.assertEqual(svc.resolve_city("北京")["code"], svc.resolve_city("北京市")["code"])
        self.assertEqual(svc.resolve_city("海淀区")["name"], "海淀")

    def test_province_prefix(self):
        resolved = svc.resolve_city("广东省深圳市")
        self.assertEqual(resolved["province"], "广东省")
        self.assertEqual(resolved["name"], "深圳")
        self.assertEqual(svc.resolve_city("广东深圳")["code"], resolved["code"])

    def test_station_code(self):
        code = svc.resolve_city("北京")["code"]
        self.assertEqual(svc.resolve_city(code)["name"], "北京")

    def test_unknown_city(self):
        self.assertIsNone(svc.resolve_city("火星基地"))
        self.assertFalse(svc.resolve_city_verbose("火星基地")["ok"])
        self.assertIn("找不到", svc.resolve_city_verbose("火星基地")["message"])

    def test_empty_query(self):
        self.assertIsNone(svc.resolve_city("   "))

    def test_search_prefix(self):
        hits = svc.search_cities("哈尔", limit=3)
        self.assertTrue(hits)
        self.assertTrue(hits[0]["name"].startswith("哈尔"))


class WeatherBuildTest(unittest.TestCase):
    def test_now_weather_falls_back_to_forecast_text(self):
        now = svc.build_now_weather(WEATHER_FIXTURE, now=datetime(2026, 11, 14, 12, 0))
        # 实况的 info 是 "-"，应当用预报里的「晴」兜底
        self.assertEqual(now["text"], "晴")
        self.assertEqual(now["emoji"], "☀️")
        self.assertEqual(now["temp"], 12)
        self.assertEqual(now["aqi"], 139)
        self.assertEqual(now["sunrise"], "06:57")
        self.assertEqual(now["sunset"], "16:59")
        self.assertIsNone(now["warning"])
        self.assertEqual(now["reportTimeShort"], "12:45")

    def test_daily_weather_labels(self):
        days = svc.build_daily_weather(WEATHER_FIXTURE, now=datetime(2026, 11, 14, 12, 0))
        self.assertEqual(len(days), 2)
        self.assertEqual(days[0]["weekday"], "周六")
        self.assertEqual(days[0]["dateShort"], "11-14")
        self.assertTrue(days[0]["isToday"])
        self.assertEqual(days[1]["nightText"], "小雨")
        self.assertEqual(days[1]["precipitation"], 0.6)

    def test_hourly_trend_sorted_and_ratios(self):
        trend = svc.build_hourly_trend(WEATHER_FIXTURE)
        times = [point["time"] for point in trend["points"]]
        self.assertEqual(times, sorted(times))
        self.assertEqual(trend["summary"]["min"], 8.2)
        self.assertEqual(trend["summary"]["max"], 11.5)
        self.assertEqual(trend["summary"]["last"], 11.5)
        self.assertEqual(trend["points"][0]["ratio"], 0.0)
        self.assertEqual(trend["points"][-1]["ratio"], 1.0)

    def test_hourly_trend_empty(self):
        trend = svc.build_hourly_trend({})
        self.assertEqual(trend["points"], [])

    def test_warning_parsed(self):
        data = json.loads(json.dumps(WEATHER_FIXTURE))
        data["real"]["warn"] = {
            "alert": "1",
            "province": "北京市",
            "city": "海淀区",
            "signaltype": "大风",
            "signallevel": "蓝色预警",
            "issuecontent": "预计未来 24 小时有大风",
            "issuetime": "2026-11-14 10:00",
        }
        warning = svc.build_now_weather(data)["warning"]
        self.assertEqual(warning["title"], "海淀区大风蓝色预警")
        self.assertIn("大风", warning["type"])


class AlmanacTest(unittest.TestCase):
    def test_fields_present(self):
        almanac = svc.build_almanac(datetime(2026, 11, 14, 12, 0))
        self.assertEqual(almanac["weekday"], "周六")
        self.assertEqual(almanac["lunarMonthDay"], "十月初六")
        self.assertTrue(almanac["ganzhiDay"])
        self.assertIsInstance(almanac["yi"], list)
        self.assertIsInstance(almanac["ji"], list)
        self.assertEqual(almanac["nextJieQi"], "小雪")
        self.assertEqual(almanac["daysToNextJieQi"], 8)
        self.assertEqual(almanac["chong"], "(丙戌)狗")

    def test_festival_merge_dedupes(self):
        # 10 月 1 日：农历节日 + 公历国庆节，不应重复
        almanac = svc.build_almanac(datetime(2026, 10, 1, 12, 0))
        self.assertIn("国庆节", almanac["festivals"])
        self.assertEqual(len(almanac["festivals"]), len(set(almanac["festivals"])))

    def test_upcoming_festivals_shape(self):
        found = svc.upcoming_festivals(datetime(2026, 11, 14, 12, 0), limit=5)
        self.assertTrue(found)
        self.assertTrue(all(item["daysLeft"] > 0 for item in found))
        self.assertTrue(all(item["kind"] in ("festival", "jieqi") for item in found))
        dates = [item["date"] for item in found]
        self.assertEqual(dates, sorted(dates))

    def test_month_calendar(self):
        days = svc.build_month_calendar(2026, 11)
        self.assertEqual(len(days), 30)
        self.assertEqual(days[0]["weekday"], 6)  # 2026-11-01 是周日
        self.assertTrue(any(day["jieqi"] for day in days))


class WeekRuleTest(unittest.TestCase):
    def test_none_means_every_week(self):
        self.assertTrue(svc.week_rule_matches(None, 3))
        self.assertTrue(svc.week_rule_matches("all", 3))

    def test_parity_uses_absolute_week(self):
        self.assertTrue(svc.week_rule_matches("odd", 5, 2))
        self.assertFalse(svc.week_rule_matches("odd", 6, 2))
        self.assertTrue(svc.week_rule_matches("even", 6, 2))

    def test_cycle_position(self):
        # maxWeekCycle=3：绝对周 4 → 轮换第 1 周
        self.assertTrue(svc.week_rule_matches(1, 4, 3))
        self.assertFalse(svc.week_rule_matches(2, 4, 3))

    def test_specific_week_list(self):
        self.assertTrue(svc.week_rule_matches([3, 4], 4, 2))
        self.assertFalse(svc.week_rule_matches([3, 4], 5, 2))
        self.assertFalse(svc.week_rule_matches([], 5, 2))

    def test_string_forms_from_qml(self):
        self.assertEqual(svc.normalize_week_rule("1,4"), [1, 4])
        self.assertEqual(svc.normalize_week_rule("[2,3]"), [2, 3])
        self.assertEqual(svc.normalize_week_rule("odd"), "odd")
        self.assertEqual(svc.normalize_week_rule(3), 3)
        self.assertIsNone(svc.normalize_week_rule("0"))
        self.assertIsNone(svc.normalize_week_rule(True))


class WeekScheduleTest(unittest.TestCase):
    def test_odd_week_has_friday_class(self):
        # 开学 2026-09-01（周二）→ 第 1 周只有 9/1~9/6；第 1 周是奇数周
        schedule = svc.build_week_schedule(make_schedule(), week=1, day_of_week=1, max_week_cycle=2)
        self.assertTrue(schedule["hasData"])
        friday = schedule["days"][4]
        self.assertTrue(any(cell for cell in friday["cells"]))

    def test_even_week_drops_odd_only_class(self):
        schedule = svc.build_week_schedule(make_schedule(), week=2, day_of_week=1, max_week_cycle=2)
        friday = schedule["days"][4]
        self.assertFalse(any(cell for cell in friday["cells"]))
        self.assertEqual(schedule["weekOfCycle"], 2)

    def test_specific_week_only(self):
        week4 = svc.build_week_schedule(make_schedule(), week=4, day_of_week=1, max_week_cycle=2)
        period_starts = [period["start"] for period in week4["periods"]]
        self.assertIn("10:00", period_starts)
        week3 = svc.build_week_schedule(make_schedule(), week=3, day_of_week=1, max_week_cycle=2)
        self.assertNotIn("10:00", [period["start"] for period in week3["periods"]])

    def test_override_replaces_subject(self):
        schedule = svc.build_week_schedule(make_schedule(), week=1, day_of_week=1, max_week_cycle=2)
        monday = schedule["days"][0]
        first = monday["cells"][0]
        # e1 原本是语文，被 override 改成数学
        self.assertEqual(first["title"], "数学")
        self.assertEqual(first["teacher"], "李老师")

    def test_cells_line_up_with_periods(self):
        schedule = svc.build_week_schedule(make_schedule(), week=1, day_of_week=1, max_week_cycle=2)
        for day in schedule["days"]:
            self.assertEqual(len(day["cells"]), len(schedule["periods"]))
        monday_cells = schedule["days"][0]["cells"]
        self.assertEqual(monday_cells[0]["startTime"], schedule["periods"][0]["start"])

    def test_no_schedule(self):
        schedule = svc.build_week_schedule(None, week=1)
        self.assertFalse(schedule["hasData"])
        self.assertEqual(schedule["periods"], [])
        self.assertEqual(len(schedule["days"]), 7)

    def test_week_dates_from_start_date(self):
        schedule = svc.build_week_schedule(make_schedule(), week=2, day_of_week=3, max_week_cycle=2)
        # 第 2 周的周一应当是 9/7
        self.assertEqual(schedule["days"][0]["date"], "2026-09-07")
        self.assertEqual(schedule["days"][0]["dateShort"], "09-07")

    def test_today_flag(self):
        schedule = svc.build_week_schedule(make_schedule(), week=1, day_of_week=3, max_week_cycle=2)
        self.assertTrue(schedule["days"][2]["isToday"])
        self.assertEqual(sum(1 for day in schedule["days"] if day["isToday"]), 1)


class TodayCourseTest(unittest.TestCase):
    def setUp(self):
        self.schedule = svc.build_week_schedule(
            make_schedule(), week=1, day_of_week=1, max_week_cycle=2
        )

    def test_current_class(self):
        course = svc.pick_today_course(
            self.schedule, day_of_week=1, now=datetime(2026, 9, 2, 8, 10)
        )
        self.assertEqual(course["state"], "class")
        self.assertEqual(course["title"], "数学")  # 被 override 覆盖过
        self.assertEqual(course["minutesLeft"], 35)

    def test_upcoming_class(self):
        course = svc.pick_today_course(
            self.schedule, day_of_week=1, now=datetime(2026, 9, 2, 8, 50)
        )
        self.assertEqual(course["state"], "upcoming")
        self.assertEqual(course["title"], "数学")

    def test_after_school(self):
        course = svc.pick_today_course(
            self.schedule, day_of_week=1, now=datetime(2026, 9, 2, 20, 0)
        )
        self.assertEqual(course["state"], "after")

    def test_day_without_class(self):
        course = svc.pick_today_course(
            self.schedule, day_of_week=2, now=datetime(2026, 9, 3, 9, 0)
        )
        self.assertEqual(course["state"], "none")

    def test_empty_schedule(self):
        course = svc.pick_today_course({}, day_of_week=1)
        self.assertEqual(course["subtitle"], "还没有课表数据")


if __name__ == "__main__":
    unittest.main()


class DutyTest(unittest.TestCase):
    """值日生：名单解析 + 轮换计算。"""

    def test_parse_names(self):
        self.assertEqual(svc.parse_duty_names("小明、小红，小刚,小丽"), ["小明", "小红", "小刚", "小丽"])
        self.assertEqual(svc.parse_duty_names("小明  小红 / 小刚"), ["小明", "小红", "小刚"])
        self.assertEqual(svc.parse_duty_names("小明，小明"), ["小明"])
        self.assertEqual(svc.parse_duty_names("  "), [])

    def test_disabled_without_names(self):
        duty = svc.build_duty("", now=datetime(2026, 9, 2))
        self.assertFalse(duty["enabled"])
        self.assertEqual(duty["todayNames"], [])

    def test_groups_split_by_per_day(self):
        duty = svc.build_duty("小明、小红、小刚、小丽、小美", per_day=2, now=datetime(2026, 9, 2))
        self.assertEqual(duty["groups"], [["小明", "小红"], ["小刚", "小丽"], ["小美"]])
        self.assertEqual(duty["groupCount"], 3)

    def test_weekly_rotation(self):
        names = "小明、小红、小刚、小丽"
        start = "2026-09-07"  # 周一
        week1 = svc.build_duty(names, per_day=2, cycle="week", start_date=start, now=datetime(2026, 9, 9))
        week2 = svc.build_duty(names, per_day=2, cycle="week", start_date=start, now=datetime(2026, 9, 16))
        self.assertEqual(week1["todayText"], "小明、小红")
        self.assertEqual(week2["todayText"], "小刚、小丽")
        self.assertEqual(week1["nextDate"], "2026-09-14")  # 下周一
        self.assertEqual(week1["nextText"], "小刚、小丽")

    def test_daily_rotation(self):
        names = "小明、小红、小刚"
        start = "2026-09-07"
        day1 = svc.build_duty(names, per_day=1, cycle="day", start_date=start, now=datetime(2026, 9, 7))
        day2 = svc.build_duty(names, per_day=1, cycle="day", start_date=start, now=datetime(2026, 9, 8))
        day4 = svc.build_duty(names, per_day=1, cycle="day", start_date=start, now=datetime(2026, 9, 10))
        self.assertEqual(day1["todayText"], "小明")
        self.assertEqual(day2["todayText"], "小红")
        self.assertEqual(day4["todayText"], "小明")  # 3 人 3 天一圈
        self.assertEqual(day1["nextDate"], "2026-09-08")

    def test_start_date_aligned_to_monday(self):
        # 2026-09-09 是周三，起算日期应对齐到当周周一（09-07）
        duty = svc.build_duty("小明、小红", per_day=1, cycle="week", start_date="2026-09-09",
                              now=datetime(2026, 9, 10))
        self.assertEqual(duty["groupIndex"], 0)
        self.assertEqual(duty["todayText"], "小明")

    def test_per_day_clamped(self):
        duty = svc.build_duty("小明", per_day=99, now=datetime(2026, 9, 2))
        self.assertEqual(duty["perDay"], svc.DUTY_MAX_PER_DAY)
        duty = svc.build_duty("小明", per_day=0, now=datetime(2026, 9, 2))
        self.assertEqual(duty["perDay"], 1)


class OpenMeteoTest(unittest.TestCase):
    """备用数据源：代码映射 + 整理 + 降级链。"""

    def test_wmo_mapping(self):
        self.assertEqual(svc.wmo_text_emoji(0), ("晴", "☀️"))
        self.assertEqual(svc.wmo_text_emoji(95)[0], "雷阵雨")
        self.assertEqual(svc.wmo_text_emoji(None)[1], "🌡️")

    def test_wind_direction(self):
        self.assertEqual(svc._wind_direction_text(0), "北风")
        self.assertEqual(svc._wind_direction_text(90), "东风")
        self.assertEqual(svc._wind_direction_text(45), "东北风")
        self.assertEqual(svc._wind_direction_text(None), "")

    def test_build_bundle(self):
        raw = {
            "place": {"name": "北京", "admin1": "北京市", "country": "中国"},
            "forecast": {
                "current": {
                    "time": "2026-11-14T12:00",
                    "temperature_2m": 12.4,
                    "relative_humidity_2m": 55,
                    "apparent_temperature": 11.8,
                    "weather_code": 0,
                    "wind_speed_10m": 5.0,
                    "wind_direction_10m": 45,
                    "precipitation": 0.0,
                },
                "daily": {
                    "time": ["2026-11-14", "2026-11-15"],
                    "weather_code": [0, 61],
                    "temperature_2m_max": [13.2, 12.1],
                    "temperature_2m_min": [3.4, 2.9],
                    "precipitation_sum": [0.0, 0.6],
                    "wind_direction_10m_dominant": [45, 90],
                    "sunrise": ["2026-11-14T06:57", "2026-11-15T06:58"],
                    "sunset": ["2026-11-14T16:59", "2026-11-15T16:58"],
                },
                "hourly": {
                    "time": ["2026-11-14T11:00", "2026-11-14T12:00"],
                    "temperature_2m": [11.0, 12.4],
                    "precipitation": [0.0, 0.0],
                },
            },
        }
        bundle = svc.build_open_meteo_bundle("北京", raw, now=datetime(2026, 11, 14, 12, 30))
        self.assertEqual(bundle["now"]["temp"], 12)
        self.assertEqual(bundle["now"]["text"], "晴")
        self.assertEqual(bundle["now"]["windDirect"], "东北风")
        self.assertEqual(bundle["now"]["sunrise"], "06:57")
        self.assertEqual(len(bundle["daily"]), 2)
        self.assertEqual(bundle["daily"][0]["label"], "今天")
        self.assertEqual(bundle["daily"][1]["text"], "小雨")
        self.assertEqual(bundle["daily"][0]["tempMax"], 13)
        self.assertEqual(len(bundle["trend"]["points"]), 2)
        self.assertEqual(bundle["trend"]["summary"]["last"], 12.4)
        self.assertEqual(bundle["place"]["province"], "北京市")

    def test_bundle_prefers_nmc(self):
        original_nmc = svc.fetch_weather_by_code
        original_om = svc.fetch_open_meteo
        try:
            svc.fetch_weather_by_code = lambda code, timeout=20: WEATHER_FIXTURE
            svc.fetch_open_meteo = lambda city, timeout=20: (_ for _ in ()).throw(AssertionError("不该走备用源"))
            bundle = svc.fetch_weather_bundle("北京")
            self.assertEqual(bundle["source"], svc.SOURCE_NMC)
            self.assertEqual(bundle["now"]["temp"], 12)
        finally:
            svc.fetch_weather_by_code = original_nmc
            svc.fetch_open_meteo = original_om

    def test_bundle_falls_back_to_open_meteo(self):
        original_nmc = svc.fetch_weather_by_code
        original_om = svc.fetch_open_meteo
        try:
            def boom(code, timeout=20):
                raise ValueError("气象台抽风了")

            svc.fetch_weather_by_code = boom
            svc.fetch_open_meteo = lambda city, timeout=20: {
                "place": {"name": "北京", "admin1": "北京市", "country": "中国"},
                "forecast": {
                    "current": {"time": "2026-11-14T12:00", "temperature_2m": 12.4, "weather_code": 2},
                    "daily": {"time": ["2026-11-14"], "weather_code": [2],
                              "temperature_2m_max": [13], "temperature_2m_min": [3]},
                    "hourly": {"time": ["2026-11-14T12:00"], "temperature_2m": [12.4]},
                },
            }
            bundle = svc.fetch_weather_bundle("北京")
            self.assertEqual(bundle["source"], svc.SOURCE_OPEN_METEO)
            self.assertEqual(bundle["now"]["text"], "多云")
            self.assertEqual(bundle["resolved"]["name"], "北京")
        finally:
            svc.fetch_weather_by_code = original_nmc
            svc.fetch_open_meteo = original_om

    def test_bundle_reports_both_failures(self):
        original_nmc = svc.fetch_weather_by_code
        original_om = svc.fetch_open_meteo
        try:
            def boom_nmc(code, timeout=20):
                raise ValueError("气象台不可用")

            def boom_om(city, timeout=20):
                raise ValueError("备用源也不可用")

            svc.fetch_weather_by_code = boom_nmc
            svc.fetch_open_meteo = boom_om
            with self.assertRaises(ValueError) as ctx:
                svc.fetch_weather_bundle("北京")
            message = str(ctx.exception)
            self.assertIn("中央气象台", message)
            self.assertIn("Open-Meteo", message)
        finally:
            svc.fetch_weather_by_code = original_nmc
            svc.fetch_open_meteo = original_om
