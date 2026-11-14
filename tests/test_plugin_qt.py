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


class _FakeAPI:
    def __init__(self, schedule):
        self.config = _FakeConfig()
        self.widgets = _FakeWidgets()
        self.ui = _FakeUi()
        self.runtime = _FakeRuntime()
        self.schedule = _FakeSchedule(schedule)
        self.current = None

    def set_current_plugin(self, plugin):
        self.current = plugin


@unittest.skipUnless(HAS_QT, "需要 PySide6 才能跑插件冒烟测试")
class PluginSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    @classmethod
    def tearDownClass(cls):
        # 显式销毁插件与事件循环，避免解释器收尾时 PySide6 回收 QObject 出问题
        gc.collect()

    def setUp(self):
        self._patched = {
            "fetch_weather_by_code": svc.fetch_weather_by_code,
            "fetch_quote": svc.fetch_quote,
            "upcoming_festivals": svc.upcoming_festivals,
        }
        svc.fetch_weather_by_code = lambda code, timeout=20: WEATHER_FIXTURE
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

        def boom(code, timeout=20):
            raise ValueError("网络好像不太顺")

        svc.fetch_weather_by_code = boom
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

    def test_diagnostics(self):
        info = self.plugin.diagnostics()
        self.assertEqual(info["version"], "1.1.0")
        self.assertGreater(info["cityCount"], 1000)
        self.assertTrue(info["runtimeHooked"])


if __name__ == "__main__":
    unittest.main()
