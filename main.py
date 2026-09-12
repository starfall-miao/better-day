"""
更好的一天 · A Better Day
Class Widgets 2 插件入口。

把天气、节日、黄历、课程表与每日一言，装进你桌面的一张可爱小卡片里。
作者：落落
"""

import threading

from PySide6.QtCore import Property, Signal, Slot

from ClassWidgets.SDK import CW2Plugin, ConfigBaseModel, PluginAPI

import betterday_services as svc


class BetterDayConfig(ConfigBaseModel):
    """插件全局配置。"""

    location: str = ""  # 城市名，例如「北京」「上海」「广州」


class Plugin(CW2Plugin):
    """「更好的一天」插件主体，同时作为 Widget 与设置页的后端对象。"""

    dataChanged = Signal()
    configChanged = Signal()

    def __init__(self, api: PluginAPI):
        super().__init__(api)
        self.config = BetterDayConfig()

        self._now_weather: dict = {}
        self._daily_weather: list = []
        self._hourly_weather: list = []
        self._almanac: dict = {}
        self._quote: dict = {}
        self._week_schedule: list = []
        self._location_name: str = ""
        self._status: str = ""

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def on_load(self):
        super().on_load()
        if not self.pid:
            return

        self.api.config.register_plugin_model(self.pid, self.config)

        self.api.widgets.register(
            widget_id="com.starfall.betterday",
            name="更好的一天",
            qml_path="assets/widget.qml",
            backend_obj=self,
            settings_qml="assets/settings.qml",
            default_settings={
                "rotation_seconds": 10,
                "show_now": True,
                "show_forecast": True,
                "show_festival": True,
                "show_almanac": True,
            },
        )

        self.api.ui.register_settings_page(
            qml_path="assets/settings_page.qml",
            title="更好的一天",
            icon="ic_fluent_weather_sunny_20_regular",
        )

        self._refresh_almanac()
        self._refresh_schedule()
        self._refresh_weather()
        self._refresh_quote()

    def on_unload(self):
        pass

    # ------------------------------------------------------------------
    # 暴露给 QML 的数据属性
    # ------------------------------------------------------------------
    @Property(dict, notify=dataChanged)
    def nowWeather(self):
        return self._now_weather

    @Property(list, notify=dataChanged)
    def dailyWeather(self):
        return self._daily_weather

    @Property(list, notify=dataChanged)
    def hourlyWeather(self):
        return self._hourly_weather

    @Property(dict, notify=dataChanged)
    def almanac(self):
        return self._almanac

    @Property(dict, notify=dataChanged)
    def quote(self):
        return self._quote

    @Property(list, notify=dataChanged)
    def weekSchedule(self):
        return self._week_schedule

    @Property(str, notify=dataChanged)
    def locationName(self):
        return self._location_name

    @Property(str, notify=dataChanged)
    def statusText(self):
        return self._status

    # ------------------------------------------------------------------
    # 配置属性（供设置页读写）
    # ------------------------------------------------------------------
    def _get_location(self) -> str:
        return self.config.location

    def _set_location(self, value: str) -> None:
        self.config.location = value
        self.configChanged.emit()

    location = Property(str, _get_location, _set_location, notify=configChanged)

    # ------------------------------------------------------------------
    # 槽函数
    # ------------------------------------------------------------------
    @Slot()
    def refreshAll(self):
        self._refresh_almanac()
        self._refresh_schedule()
        self._refresh_weather()
        self._refresh_quote()

    @Slot()
    def refreshWeather(self):
        self._refresh_weather()

    @Slot()
    def refreshQuote(self):
        self._refresh_quote()

    @Slot()
    def applyLocation(self):
        self._refresh_weather()

    @Slot(int, int, result=list)
    def calendar(self, year: int, month: int):
        return svc.build_month_calendar(year, month)

    # ------------------------------------------------------------------
    # 内部刷新逻辑
    # ------------------------------------------------------------------
    def _refresh_almanac(self):
        self._almanac = svc.build_almanac()
        self.dataChanged.emit()

    def _refresh_schedule(self):
        schedule = None
        try:
            schedule_api = getattr(self.api, "schedule", None)
            if schedule_api is not None:
                schedule = schedule_api.get()
        except Exception:
            schedule = None
        self._week_schedule = svc.build_week_schedule(schedule)
        self.dataChanged.emit()

    def _refresh_weather(self):
        location = (self.config.location or "").strip()
        if not location:
            self._now_weather = {}
            self._daily_weather = []
            self._hourly_weather = []
            self._location_name = ""
            self._status = "还没有设置城市哦，去插件设置里填写吧～"
            self.dataChanged.emit()
            return

        self._status = "正在更新天气…"
        self.dataChanged.emit()
        self._run_async(self._do_fetch_weather)

    def _do_fetch_weather(self):
        location = (self.config.location or "").strip()
        geo = svc.geocode(location)
        if not geo:
            self._status = f"找不到「{location}」这座城市，换个写法试试？"
            self.dataChanged.emit()
            return

        raw = svc.fetch_weather_raw(geo["lat"], geo["lon"], geo["timezone"])
        self._now_weather = svc.build_now_weather(raw)
        self._daily_weather = svc.build_daily_weather(raw)
        self._hourly_weather = svc.build_hourly_weather(raw)
        self._location_name = geo["name"]
        self._status = "天气更新好啦 ✨"
        self.dataChanged.emit()

    def _refresh_quote(self):
        self._run_async(self._do_fetch_quote)

    def _do_fetch_quote(self):
        self._quote = svc.fetch_quote()
        self.dataChanged.emit()

    def _run_async(self, fn):
        def task():
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                self._status = f"出错了：{exc}"
                self.dataChanged.emit()

        threading.Thread(target=task, daemon=True).start()
