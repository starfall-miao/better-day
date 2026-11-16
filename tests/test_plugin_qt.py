"""插件主体的冒烟测试（需要 PySide6）。

用假的 ClassWidgets.SDK 替换 CW2 运行时注入，把插件真正跑起来，
验证：后台线程 → 主线程的信号投递、配置读写、刷新与「换日」定时器、
课表整理与错误兜底。网络请求全部打桩，不会真的联网。

没装 PySide6 时整个文件会被跳过，所以也可以在 CI 里当作可选测试跑。
"""

import gc
import os
import sys
import time
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
for _path in (ROOT, TESTS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:
    from PySide6.QtCore import QCoreApplication, QObject, Signal
    HAS_QT = True
except Exception:  # pragma: no cover - 没装 PySide6 时跳过
    HAS_QT = False

if HAS_QT:
    import betterday_services as svc
    from test_services import WEATHER_FIXTURE, make_schedule

    # ---- 假的 ClassWidgets.SDK：接口和 CW2 运行时保持一致 ----
    class _FakeConfigBaseModel:
        """CW2 的 ConfigBaseModel 是 pydantic 模型；测试里用最小实现即可。"""

        def __init__(self, **data):
            for key, value in data.items():
                setattr(self, key, value)

        def model_dump(self):
            return {key: value for key, value in self.__dict__.items() if not key.startswith("_")}

    class _FakeCW2Plugin(QObject):
        initialized = Signal()

        def __init__(self, api):
            super().__init__()
            self.PATH = None
            self.meta = {}
            self.pid = None
            self.api = api

        def on_load(self):
            self.pid = self.meta.get("id")
            self.api.set_current_plugin(self)
            self.initialized.emit()

        def on_unload(self):
            pass

    _sdk = types.ModuleType("ClassWidgets.SDK")
    _sdk.CW2Plugin = _FakeCW2Plugin
    _sdk.ConfigBaseModel = _FakeConfigBaseModel
    _sdk.PluginAPI = object
    _package = types.ModuleType("ClassWidgets")
    _package.__path__ = []
    _package.SDK = _sdk
    sys.modules.setdefault("ClassWidgets", _package)
    sys.modules["ClassWidgets.SDK"] = _sdk

    import main as plugin_main  # noqa: E402


class _FakeSignal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def disconnect(self, slot):
        if slot in self._slots:
            self._slots.remove(slot)

    def emit(self, *args):
        for slot in list(self._slots):
            slot(*args)


class _FakeRuntime:
    def __init__(self):
        self.updated = _FakeSignal()
        self.current_week = 1
        self.current_day_of_week = 1
        self.schedule_meta = {"id": "s1", "version": 1, "maxWeekCycle": 2, "startDate": "2026-09-01"}


class _FakeSchedule:
    def __init__(self, schedule):
        self._schedule = schedule

    def get(self):
        return self._schedule


class _FakeNotification(QObject):
    pushed = Signal(dict)

    def __init__(self):
        super().__init__()
        self.providers = {}

    def register_provider(self, *args, **kwargs):
        return None


class _FakePreferences:
    def __init__(self, presets=None, current="默认"):
        self.widgets_presets = presets if presets is not None else {}
        self.current_preset = current


class _FakeConfigManager:
    def __init__(self, preferences):
        self.preferences = preferences


class _FakeGlobalConfig:
    def __init__(self, preferences):
        self.configs = _FakeConfigManager(preferences)


class _FakeConfig:
    def __init__(self):
        self.registered = None

    def register_plugin_model(self, plugin_id, model):
        self.registered = (plugin_id, model)


class _FakeWidgets:
    def __init__(self):
        self.registered = None

    def register(self, **kwargs):
        self.registered = kwargs


class _FakeUi:
    def __init__(self):
        self.registered = None

    def register_settings_page(self, **kwargs):
        self.registered = kwargs


class _FakeWidgetEntry:
    def __init__(self, type_id):
        self.type_id = type_id


class _FakeAPI:
    def __init__(self, schedule, with_notification_widget=True):
        self.config = _FakeConfig()
        self.widgets = _FakeWidgets()
        self.ui = _FakeUi()
        self.runtime = _FakeRuntime()
        self.schedule = _FakeSchedule(schedule)
        self.notification = _FakeNotification()
        entries = [_FakeWidgetEntry("classwidgets.dynamicNotification")] if with_notification_widget else []
        entries.append(_FakeWidgetEntry("com.starfall.betterday"))
        self.globalconfig = _FakeGlobalConfig(_FakePreferences({"默认": entries}, "默认"))
        self.current = None

    def set_current_plugin(self, plugin):
        self.current = plugin


def make_weather_bundle(city, now=None, timeout=20):
    """测试用的天气包：结构和服务层一致，避免联网。"""
    from datetime import datetime as _dt

    moment = now or _dt.now()
    return {
        "resolved": {
            "query": city,
            "ok": True,
            "code": "Wqsps",
            "name": city,
            "province": "北京市",
            "message": f"已匹配 北京市·{city}",
            "alternatives": [],
        },
        "source": svc.SOURCE_NMC,
        "now": svc.build_now_weather(WEATHER_FIXTURE, moment),
        "daily": svc.build_daily_weather(WEATHER_FIXTURE, now=moment),
        "trend": svc.build_hourly_trend(WEATHER_FIXTURE),
    }


@unittest.skipUnless(HAS_QT, "需要 PySide6 才能跑插件冒烟测试")
class PluginSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import QStandardPaths
        QStandardPaths.setTestModeEnabled(True)
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    @classmethod
    def tearDownClass(cls):
        # 显式销毁插件与事件循环，避免解释器收尾时 PySide6 回收 QObject 出问题
        gc.collect()

    def setUp(self):
        self._patched = {
            "fetch_weather_bundle": svc.fetch_weather_bundle,
            "fetch_quote": svc.fetch_quote,
            "upcoming_festivals": svc.upcoming_festivals,
        }
        svc.fetch_weather_bundle = make_weather_bundle
        svc.fetch_quote = lambda category="", timeout=10: {"text": "今天也要开开心心的", "from": "更好的一天"}
        svc.upcoming_festivals = lambda now=None, horizon=45, limit=5: [
            {
                "name": "小雪",
                "date": "2026-11-22",
                "dateShort": "11-22",
                "weekday": "周日",
                "daysLeft": 8,
                "kind": "jieqi",
            }
        ]

        self.api = _FakeAPI(make_schedule())
        self.plugin = plugin_main.Plugin(self.api)
        self.plugin.meta = {"id": "com.starfall.betterday", "version": "1.1.0"}
        self.plugin.on_load()

    def tearDown(self):
        try:
            self.plugin.on_unload()
        finally:
            for name, original in self._patched.items():
                setattr(svc, name, original)
            # 主动回收插件（含它名下的 QTimer），别留到解释器退出时再收
            self.plugin.deleteLater()
            self.plugin = None
            self.api = None
            QCoreApplication.processEvents()

    # ------------------------------------------------------------------
    def pump(self, predicate, timeout=5.0):
        """跑一会儿事件循环，直到条件成立（后台线程的结果需要排队投递回来）。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            QCoreApplication.processEvents()
            if predicate():
                return True
            time.sleep(0.02)
        QCoreApplication.processEvents()
        return predicate()

    def test_widget_and_settings_page_registered(self):
        widget = self.api.widgets.registered
        self.assertIsNotNone(widget)
        self.assertEqual(widget["widget_id"], "com.starfall.betterday")
        self.assertEqual(widget["backend_obj"], self.plugin)
        self.assertTrue(widget["settings_qml"].endswith("settings.qml"))
        self.assertEqual(widget["default_settings"]["rotation_seconds"], 10)

        page = self.api.ui.registered
        self.assertTrue(page["qml_path"].endswith("settings_page.qml"))
        self.assertEqual(page["title"], "更好的一天")

        self.assertEqual(self.api.config.registered[0], "com.starfall.betterday")

    def test_weather_arrives_on_main_thread(self):
        self.plugin.location = "北京"
        self.plugin.refreshWeather()
        self.assertTrue(self.pump(lambda: self.plugin.nowWeather.get("temp") is not None))
        self.assertEqual(self.plugin.nowWeather["temp"], 12)
        self.assertEqual(self.plugin.nowWeather["emoji"], "☀️")
        self.assertEqual(self.plugin.locationName, "北京")
        self.assertTrue(self.plugin.lastUpdated)
        self.assertTrue(self.plugin.hasWeather)
        self.assertIn("更新", self.plugin.statusText)
        self.assertEqual(len(self.plugin.dailyWeather), 2)
        self.assertTrue(self.plugin.hourlyTrend["points"])

    def test_quote_arrives(self):
        self.assertTrue(self.pump(lambda: bool(self.plugin.quote.get("text"))))
        self.assertEqual(self.plugin.quote["text"], "今天也要开开心心的")

    def test_calendar_slot(self):
        days = self.plugin.calendar(2026, 11)
        self.assertEqual(len(days), 30)
        # 第二次调用走缓存，结果一致
        self.assertEqual(self.plugin.calendar(2026, 11), days)

    def test_week_schedule_and_today_course(self):
        schedule = self.plugin.weekSchedule
        self.assertTrue(schedule["hasData"])
        self.assertEqual(schedule["weekNumber"], 1)
        self.assertEqual(schedule["weekOfCycle"], 1)
        # 周一第一节被调课覆盖成数学
        self.assertEqual(schedule["days"][0]["cells"][0]["title"], "数学")
        self.assertTrue(self.plugin.todayCourse)  # 至少有说明文字

    def test_schedule_rebuild_on_runtime_update(self):
        self.plugin._on_runtime_updated()
        self.assertTrue(self.pump(lambda: self.plugin._schedule_debounce.isActive(), timeout=1.0))

    def test_city_resolution_feedback(self):
        self.plugin.location = "广东深圳"
        match = self.plugin.cityMatch
        self.assertTrue(match["ok"])
        self.assertEqual(match["name"], "深圳")
        self.assertEqual(match["province"], "广东省")

        self.plugin.location = "火星基地"
        self.assertFalse(self.plugin.cityMatch["ok"])
        self.assertIn("找不到", self.plugin.cityMatch["message"])

    def test_resolve_city_slot_and_search(self):
        self.assertEqual(self.plugin.resolveCity("北京")["code"], "Wqsps")
        hits = self.plugin.searchCities("哈尔")
        self.assertTrue(hits and hits[0]["name"].startswith("哈尔"))

    def test_refresh_minutes_clamped(self):
        self.plugin.refreshMinutes = 1
        self.assertEqual(self.plugin.refreshMinutes, 5)
        self.plugin.refreshMinutes = 999
        self.assertEqual(self.plugin.refreshMinutes, 240)
        self.plugin.refreshMinutes = 30
        self.assertEqual(self.plugin.refreshMinutes, 30)
        self.assertTrue(self.plugin._weather_timer.isActive())
        self.assertEqual(self.plugin._weather_timer.interval(), 30 * 60 * 1000)

    def test_auto_refresh_toggle(self):
        self.plugin.autoRefresh = False
        self.assertFalse(self.plugin._weather_timer.isActive())
        self.plugin.autoRefresh = True
        self.assertTrue(self.plugin._weather_timer.isActive())

    def test_empty_location_clears_weather(self):
        self.plugin.location = "北京"
        self.plugin.refreshWeather()
        self.assertTrue(self.pump(lambda: self.plugin.nowWeather.get("temp") is not None))

        self.plugin.location = ""
        self.plugin.refreshWeather()
        self.assertEqual(self.plugin.nowWeather, {})
        self.assertFalse(self.plugin.hasWeather)
        self.assertIn("城市", self.plugin.statusText)

    def test_weather_error_keeps_old_data(self):
        self.plugin.location = "北京"
        self.plugin.refreshWeather()
        self.assertTrue(self.pump(lambda: self.plugin.nowWeather.get("temp") is not None))
        self.assertTrue(self.pump(lambda: not self.plugin._weather_loading))

        def boom(city, now=None, timeout=20):
            raise ValueError("中央气象台：网络好像不太顺；Open-Meteo：也不太行")

        svc.fetch_weather_bundle = boom
        self.plugin.refreshWeather()
        self.assertTrue(self.pump(lambda: "失败" in self.plugin.statusText))
        # 失败时保留上一次成功的数据，不要把卡片清空
        self.assertEqual(self.plugin.nowWeather["temp"], 12)

    def test_day_rollover_keeps_timers(self):
        self.assertTrue(self.plugin._day_timer.isActive())
        self.plugin._on_day_rollover()
        self.assertTrue(self.plugin._day_timer.isActive())
        self.assertTrue(self.plugin.weekSchedule["hasData"])

    def test_unload_stops_everything(self):
        self.plugin.on_unload()
        self.assertFalse(self.plugin._alive)
        self.assertIsNone(self.plugin._weather_timer)
        self.assertIsNone(self.plugin._clock_timer)
        self.assertIsNone(self.plugin._day_timer)

    # ------------------------------------------------------------------
    # 灵动通知退让
    # ------------------------------------------------------------------
    def test_retreat_on_notification(self):
        self.plugin.config.retreat_on_notify = True
        self.api.notification.pushed.emit({"title": "上课铃", "duration": 800})
        self.assertTrue(self.pump(lambda: self.plugin.retreatActive, timeout=1.0))
        self.assertTrue(self.plugin.retreatActive)
        # 通知时长 + 余量之后自动回来
        self.assertTrue(self.pump(lambda: not self.plugin.retreatActive, timeout=4.0))
        self.assertFalse(self.plugin.retreatActive)

    def test_retreat_extends_with_more_notifications(self):
        self.api.notification.pushed.emit({"title": "第一条", "duration": 600})
        self.assertTrue(self.pump(lambda: self.plugin.retreatActive, timeout=1.0))
        self.api.notification.pushed.emit({"title": "第二条", "duration": 900})
        self.assertTrue(self.plugin.retreatActive)
        self.assertTrue(self.pump(lambda: not self.plugin.retreatActive, timeout=5.0))

    def test_no_retreat_without_notification_widget(self):
        api = _FakeAPI(make_schedule(), with_notification_widget=False)
        plugin = plugin_main.Plugin(api)
        plugin.meta = {"id": "com.starfall.betterday", "version": "1.1.0"}
        plugin.on_load()
        try:
            api.notification.pushed.emit({"title": "上课铃", "duration": 800})
            self.pump(lambda: False, timeout=0.5)
            self.assertFalse(plugin.retreatActive)
        finally:
            plugin.on_unload()

    def test_retreat_can_be_disabled(self):
        self.plugin.retreatOnNotify = False
        self.assertFalse(self.plugin.retreatOnNotify)
        self.api.notification.pushed.emit({"title": "上课铃", "duration": 800})
        self.pump(lambda: False, timeout=0.5)
        self.assertFalse(self.plugin.retreatActive)
        self.plugin.retreatOnNotify = True
        self.assertTrue(self.plugin.retreatOnNotify)

    # ------------------------------------------------------------------
    # 值日生
    # ------------------------------------------------------------------
    def test_duty_disabled_by_default(self):
        self.assertFalse(self.plugin.duty["enabled"])
        self.assertEqual(self.plugin.dutyNames, "")

    def test_duty_rotation_and_start_date(self):
        self.plugin.dutyNames = "小明、小红、小刚、小丽"
        self.plugin.dutyPerDay = 2
        self.plugin.dutyCycle = "week"
        duty = self.plugin.duty
        self.assertTrue(duty["enabled"])
        self.assertEqual(duty["todayNames"], ["小明", "小红"])
        self.assertEqual(duty["groupCount"], 2)
        # 第一次保存名单时自动记录起算日期
        self.assertTrue(self.plugin.dutyStartDate)

        self.plugin.dutyStartDate = "2026-09-07"
        self.assertEqual(self.plugin.duty["groupIndex"], 0)
        # 起算日期往前推 7 天 → 轮到第二组
        self.plugin.dutyStartDate = "2026-08-31"
        self.assertEqual(self.plugin.duty["groupIndex"], 1)

    def test_duty_cycle_validation(self):
        self.plugin.dutyCycle = "乱填的"
        self.assertEqual(self.plugin.dutyCycle, "week")
        self.plugin.dutyCycle = "day"
        self.assertEqual(self.plugin.dutyCycle, "day")
        self.plugin.dutyPerDay = 99
        self.assertEqual(self.plugin.dutyPerDay, svc.DUTY_MAX_PER_DAY)
        self.plugin.dutyPerDay = 0
        self.assertEqual(self.plugin.dutyPerDay, 1)

    def test_clearing_names_disables_duty(self):
        self.plugin.dutyNames = "小明、小红"
        self.assertTrue(self.plugin.duty["enabled"])
        self.plugin.dutyNames = ""
        self.assertFalse(self.plugin.duty["enabled"])

    # ------------------------------------------------------------------
    # 数据源与缓存
    # ------------------------------------------------------------------
    def test_weather_source_exposed(self):
        self.plugin.location = "北京"
        self.plugin.refreshWeather()
        self.assertTrue(self.pump(lambda: self.plugin.nowWeather.get("temp") is not None))
        self.assertEqual(self.plugin.weatherSource, svc.SOURCE_NMC)

    def test_weather_cache_roundtrip(self):
        self.plugin.location = "北京"
        self.plugin.refreshWeather()
        self.assertTrue(self.pump(lambda: self.plugin.nowWeather.get("temp") is not None))

        # 新实例应当能从缓存里立刻拿到上次的数据
        api2 = _FakeAPI(make_schedule())
        plugin2 = plugin_main.Plugin(api2)
        plugin2.meta = {"id": "com.starfall.betterday", "version": "1.1.0"}
        plugin2.config.location = "北京"
        self.assertTrue(plugin2._load_weather_cache())
        self.assertEqual(plugin2.nowWeather["temp"], 12)
        self.assertTrue(plugin2.lastUpdated)
        plugin2.on_unload()

    def test_weather_cache_ignores_other_city(self):
        self.plugin.location = "北京"
        self.plugin.refreshWeather()
        self.assertTrue(self.pump(lambda: self.plugin.nowWeather.get("temp") is not None))

        api2 = _FakeAPI(make_schedule())
        plugin2 = plugin_main.Plugin(api2)
        plugin2.meta = {"id": "com.starfall.betterday", "version": "1.1.0"}
        plugin2.config.location = "上海"
        self.assertFalse(plugin2._load_weather_cache())
        plugin2.on_unload()

    def test_diagnostics(self):
        info = self.plugin.diagnostics()
        self.assertEqual(info["version"], "1.1.0")
        self.assertGreater(info["cityCount"], 1000)
        self.assertTrue(info["runtimeHooked"])


if __name__ == "__main__":
    unittest.main()
