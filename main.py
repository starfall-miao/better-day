"""
更好的一天 · A Better Day
Class Widgets 2 插件入口。

把天气、节日、黄历、课程表与每日一言，装进你桌面的一张可爱小卡片里。
作者：落落
"""

import threading
from datetime import datetime, timedelta

from PySide6.QtCore import Property, Qt, QTimer, Signal, Slot

from ClassWidgets.SDK import CW2Plugin, ConfigBaseModel, PluginAPI

import betterday_services as svc


# 刷新间隔的上下限（分钟）
_MIN_REFRESH_MINUTES = 5
_MAX_REFRESH_MINUTES = 240


class BetterDayConfig(ConfigBaseModel):
    """插件全局配置（由 Class Widgets 2 持久化）。"""

    location: str = ""  # 城市名，例如「北京」「广东深圳」
    refresh_minutes: int = 15  # 天气自动刷新间隔（分钟）
    auto_refresh: bool = True  # 是否自动刷新天气
    show_warning: bool = True  # 是否显示气象预警


class Plugin(CW2Plugin):
    """「更好的一天」插件主体，同时作为 Widget 与设置页的后端对象。"""

    dataChanged = Signal()
    configChanged = Signal()

    # 后台线程 → 主线程的投递信号。
    # 这些信号跨线程 connect，Qt 会自动排队到主线程执行对应槽，
    # 因此所有属性赋值与 dataChanged 都在 GUI 线程里发生。
    _weatherDone = Signal(object)
    _weatherError = Signal(str)
    _quoteDone = Signal(object)
    _quoteError = Signal(str)
    _extrasDone = Signal(object)

    def __init__(self, api: PluginAPI):
        super().__init__(api)
        self.config = BetterDayConfig()

        # ---- 数据 ----
        self._now_weather: dict = {}
        self._daily_weather: list = []
        self._hourly_trend: dict = {"points": [], "summary": {"min": None, "max": None, "last": None}}
        self._almanac: dict = {}
        self._upcoming_festivals: list = []
        self._quote: dict = {}
        self._week_schedule: dict = {"periods": [], "days": []}
        self._today_course: dict = {}
        self._calendar_cache: dict = {}

        # ---- 状态 ----
        self._location_name: str = ""
        self._city_match: dict = {}
        self._status: str = ""
        self._last_updated: str = ""
        self._version: str = ""
        self._alive: bool = True
        self._weather_loading: bool = False
        self._quote_loading: bool = False

        # ---- 定时器（在 on_load 里创建，确保落在 GUI 线程）----
        self._weather_timer: QTimer | None = None
        self._clock_timer: QTimer | None = None
        self._day_timer: QTimer | None = None
        self._schedule_debounce: QTimer | None = None
        self._runtime_hooked: bool = False
        self._workers: list = []

        self._weatherDone.connect(self._on_weather_done, Qt.QueuedConnection)
        self._weatherError.connect(self._on_weather_error, Qt.QueuedConnection)
        self._quoteDone.connect(self._on_quote_done, Qt.QueuedConnection)
        self._quoteError.connect(self._on_quote_error, Qt.QueuedConnection)
        self._extrasDone.connect(self._on_extras_done, Qt.QueuedConnection)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def on_load(self):
        super().on_load()
        if not self.pid:
            return

        self._version = str((self.meta or {}).get("version") or "")
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
                "show_course": False,
            },
        )

        self.api.ui.register_settings_page(
            qml_path="assets/settings_page.qml",
            title="更好的一天",
            icon="ic_fluent_weather_sunny_20_regular",
        )

        self._setup_timers()
        self._hook_runtime()

        self._refresh_almanac()
        self._refresh_schedule()
        self._refresh_extras()
        self._refresh_weather()
        self._refresh_quote()

    def on_unload(self):
        self._alive = False
        for timer in (
            self._weather_timer,
            self._clock_timer,
            self._day_timer,
            self._schedule_debounce,
        ):
            if timer is not None:
                try:
                    timer.stop()
                except Exception:
                    pass
        self._weather_timer = None
        self._clock_timer = None
        self._day_timer = None
        self._schedule_debounce = None

        try:
            self.api.runtime.updated.disconnect(self._on_runtime_updated)
        except Exception:
            pass

        # 等后台线程收尾（最多 1.5 秒），避免插件卸载后线程还在跑
        for worker in list(self._workers):
            try:
                worker.join(timeout=0.5)
            except RuntimeError:
                pass
        self._workers.clear()

    def _spawn(self, target, *args):
        """开一个可回收的后台线程（卸载时会 join，避免线程残留）。"""

        def run():
            try:
                target(*args)
            finally:
                thread = threading.current_thread()
                try:
                    self._workers.remove(thread)
                except ValueError:
                    pass

        thread = threading.Thread(target=run, daemon=True)
        self._workers.append(thread)
        thread.start()
        return thread

    # ------------------------------------------------------------------
    # 定时器与运行时挂钩
    # ------------------------------------------------------------------
    def _setup_timers(self):
        self._weather_timer = QTimer(self)
        self._weather_timer.setSingleShot(False)
        self._weather_timer.timeout.connect(self.refreshWeather)
        self._apply_weather_interval()

        # 每分钟刷一次「今天这节课」的剩余时间，并顺手校准日期
        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(30 * 1000)
        self._clock_timer.timeout.connect(self.refreshTodayCourse)
        self._clock_timer.start()

        self._day_timer = QTimer(self)
        self._day_timer.setSingleShot(True)
        self._day_timer.timeout.connect(self._on_day_rollover)
        self._schedule_day_rollover()

        self._schedule_debounce = QTimer(self)
        self._schedule_debounce.setSingleShot(True)
        self._schedule_debounce.setInterval(2000)
        self._schedule_debounce.timeout.connect(self._refresh_schedule)

    def _apply_weather_interval(self):
        if self._weather_timer is None:
            return
        minutes = self._clamped_refresh_minutes()
        if self.config.auto_refresh and minutes > 0:
            self._weather_timer.start(minutes * 60 * 1000)
        else:
            self._weather_timer.stop()

    def _clamped_refresh_minutes(self) -> int:
        try:
            minutes = int(self.config.refresh_minutes)
        except (TypeError, ValueError):
            minutes = 15
        return max(_MIN_REFRESH_MINUTES, min(_MAX_REFRESH_MINUTES, minutes))

    def _schedule_day_rollover(self):
        """在明天 00:00:30 触发一次「换日」刷新。"""
        if self._day_timer is None:
            return
        now = datetime.now()
        tomorrow = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=30, microsecond=0
        )
        delay_ms = max(5000, int((tomorrow - now).total_seconds() * 1000))
        self._day_timer.start(delay_ms)

    def _on_day_rollover(self):
        if not self._alive:
            return
        # 新的一天：黄历、课表、日历缓存、天气、一言、最近节日都要更新
        self._calendar_cache.clear()
        self._refresh_almanac()
        self._refresh_schedule()
        self._refresh_extras()
        self._refresh_weather()
        self._refresh_quote()
        self._schedule_day_rollover()

    def _hook_runtime(self):
        """课表 / 星期变化时重建整周课表。"""
        try:
            self.api.runtime.updated.connect(self._on_runtime_updated)
            self._runtime_hooked = True
        except Exception:
            self._runtime_hooked = False

    def _on_runtime_updated(self):
        if not self._alive or self._schedule_debounce is None:
            return
        # 运行时刷新可能很频繁，这里做 2 秒防抖
        self._schedule_debounce.start()

    # ------------------------------------------------------------------
    # 暴露给 QML 的数据属性
    # ------------------------------------------------------------------
    @Property(dict, notify=dataChanged)
    def nowWeather(self):
        return self._now_weather

    @Property(list, notify=dataChanged)
    def dailyWeather(self):
        return self._daily_weather

    @Property(dict, notify=dataChanged)
    def hourlyTrend(self):
        return self._hourly_trend

    @Property(dict, notify=dataChanged)
    def almanac(self):
        return self._almanac

    @Property(list, notify=dataChanged)
    def upcomingFestivals(self):
        return self._upcoming_festivals

    @Property(dict, notify=dataChanged)
    def quote(self):
        return self._quote

    @Property(dict, notify=dataChanged)
    def weekSchedule(self):
        return self._week_schedule

    @Property(dict, notify=dataChanged)
    def todayCourse(self):
        return self._today_course

    @Property(str, notify=dataChanged)
    def locationName(self):
        return self._location_name

    @Property(dict, notify=dataChanged)
    def cityMatch(self):
        """当前城市的匹配结果（供设置页展示命中 / 候选）。"""
        return self._city_match

    @Property(str, notify=dataChanged)
    def statusText(self):
        return self._status

    @Property(str, notify=dataChanged)
    def lastUpdated(self):
        return self._last_updated

    @Property(str, notify=dataChanged)
    def version(self):
        return self._version

    @Property(bool, notify=dataChanged)
    def hasWeather(self):
        return self._now_weather.get("temp") is not None

    @Property(bool, notify=dataChanged)
    def hasWarning(self):
        return bool(self._now_weather.get("warning")) and bool(self.config.show_warning)

    # ------------------------------------------------------------------
    # 配置属性（供设置页读写）
    # ------------------------------------------------------------------
    def _get_location(self) -> str:
        return self.config.location

    def _set_location(self, value: str) -> None:
        text = str(value or "").strip()
        if text == (self.config.location or ""):
            return
        self.config.location = text
        self._city_match = svc.resolve_city_verbose(text) if text else {}
        if not text:
            self._status = "还没有设置城市哦，去插件设置里填写吧～"
        self.configChanged.emit()
        self.dataChanged.emit()

    location = Property(str, _get_location, _set_location, notify=configChanged)

    def _get_refresh_minutes(self) -> int:
        return self._clamped_refresh_minutes()

    def _set_refresh_minutes(self, value: int) -> None:
        minutes = max(_MIN_REFRESH_MINUTES, min(_MAX_REFRESH_MINUTES, int(value or 15)))
        if minutes == self.config.refresh_minutes:
            return
        self.config.refresh_minutes = minutes
        self._apply_weather_interval()
        self.configChanged.emit()

    refreshMinutes = Property(int, _get_refresh_minutes, _set_refresh_minutes, notify=configChanged)

    def _get_auto_refresh(self) -> bool:
        return bool(self.config.auto_refresh)

    def _set_auto_refresh(self, value: bool) -> None:
        value = bool(value)
        if value == self.config.auto_refresh:
            return
        self.config.auto_refresh = value
        self._apply_weather_interval()
        self.configChanged.emit()

    autoRefresh = Property(bool, _get_auto_refresh, _set_auto_refresh, notify=configChanged)

    def _get_show_warning(self) -> bool:
        return bool(self.config.show_warning)

    def _set_show_warning(self, value: bool) -> None:
        value = bool(value)
        if value == self.config.show_warning:
            return
        self.config.show_warning = value
        self.configChanged.emit()
        self.dataChanged.emit()

    showWarning = Property(bool, _get_show_warning, _set_show_warning, notify=configChanged)

    # ------------------------------------------------------------------
    # 槽函数
    # ------------------------------------------------------------------
    @Slot()
    def refreshAll(self):
        self._refresh_almanac()
        self._refresh_schedule()
        self._refresh_extras()
        self._refresh_weather()
        self._refresh_quote()

    @Slot()
    def refreshWeather(self):
        self._refresh_weather()

    @Slot()
    def refreshQuote(self):
        self._refresh_quote()

    @Slot()
    def refreshSchedule(self):
        self._refresh_schedule()

    @Slot()
    def refreshAlmanac(self):
        self._refresh_almanac()

    @Slot()
    def applyLocation(self):
        """设置页「保存并刷新」：重新匹配城市并刷天气。"""
        self._city_match = svc.resolve_city_verbose(self.config.location or "")
        self._refresh_weather()

    @Slot()
    def refreshTodayCourse(self):
        """只重算「现在 / 下一节」，不碰网络。"""
        course = svc.pick_today_course(
            self._week_schedule,
            day_of_week=self._current_day_of_week(),
        )
        if course != self._today_course:
            self._today_course = course
            self.dataChanged.emit()

    @Slot(int, int, result=list)
    def calendar(self, year: int, month: int):
        key = (year, month)
        if key not in self._calendar_cache:
            try:
                self._calendar_cache[key] = svc.build_month_calendar(year, month)
            except Exception:  # noqa: BLE001
                return []
        return self._calendar_cache[key]

    @Slot(str, result=dict)
    def resolveCity(self, name: str):
        return svc.resolve_city_verbose(name)

    @Slot(str, result=list)
    def searchCities(self, keyword: str):
        try:
            return svc.search_cities(keyword, limit=8)
        except Exception:  # noqa: BLE001
            return []

    @Slot(result=dict)
    def diagnostics(self):
        """给设置页看的调试信息。"""
        return {
            "version": self._version,
            "cityCount": svc.city_count(),
            "refreshMinutes": self._clamped_refresh_minutes(),
            "autoRefresh": bool(self.config.auto_refresh),
            "runtimeHooked": self._runtime_hooked,
            "weatherLoading": self._weather_loading,
            "scheduleWeek": self._week_schedule.get("weekNumber") or 0,
            "hasSchedule": bool(self._week_schedule.get("hasData")),
            "lastUpdated": self._last_updated,
        }

    # ------------------------------------------------------------------
    # 内部刷新逻辑（主线程）
    # ------------------------------------------------------------------
    def _current_day_of_week(self) -> int:
        try:
            day = int(self.api.runtime.current_day_of_week or 0)
            if 1 <= day <= 7:
                return day
        except Exception:  # noqa: BLE001
            pass
        return datetime.now().isoweekday()

    def _current_week(self) -> int:
        try:
            return int(self.api.runtime.current_week or 0)
        except Exception:  # noqa: BLE001
            return 0

    def _current_max_week_cycle(self) -> int:
        try:
            meta = self.api.runtime.schedule_meta or {}
            return max(1, int(meta.get("maxWeekCycle") or 1))
        except Exception:  # noqa: BLE001
            return 1

    def _refresh_almanac(self):
        try:
            self._almanac = svc.build_almanac()
            self._status = self._status or "黄历准备好了 ✨"
        except Exception as error:  # noqa: BLE001
            self._status = f"黄历计算失败：{error}"
        self.dataChanged.emit()

    def _refresh_schedule(self):
        schedule = None
        try:
            schedule_api = getattr(self.api, "schedule", None)
            if schedule_api is not None:
                schedule = schedule_api.get()
        except Exception:  # noqa: BLE001
            schedule = None

        try:
            self._week_schedule = svc.build_week_schedule(
                schedule,
                week=self._current_week(),
                day_of_week=self._current_day_of_week(),
                max_week_cycle=self._current_max_week_cycle(),
            )
        except Exception as error:  # noqa: BLE001
            self._week_schedule = svc.build_week_schedule(None)
            self._status = f"课表整理失败：{error}"

        self._today_course = svc.pick_today_course(
            self._week_schedule, day_of_week=self._current_day_of_week()
        )
        self.dataChanged.emit()

    def _refresh_extras(self):
        """最近节日 + 前后月日历：耗时较长，放后台线程算。"""
        if not self._alive:
            return

        def work():
            bundle = {"festivals": [], "calendars": {}}
            try:
                bundle["festivals"] = svc.upcoming_festivals(limit=6)
            except Exception:  # noqa: BLE001
                bundle["festivals"] = []
            try:
                now = datetime.now()
                for delta in (-1, 0, 1):
                    year, month = now.year, now.month + delta
                    while month < 1:
                        year -= 1
                        month += 12
                    while month > 12:
                        year += 1
                        month -= 12
                    bundle["calendars"][f"{year}-{month}"] = svc.build_month_calendar(year, month)
            except Exception:  # noqa: BLE001
                pass
            if self._alive:
                self._extrasDone.emit(bundle)

        self._spawn(work)

    def _refresh_weather(self):
        location = (self.config.location or "").strip()
        if not location:
            self._now_weather = {}
            self._daily_weather = []
            self._hourly_trend = {"points": [], "summary": {"min": None, "max": None, "last": None}}
            self._location_name = ""
            self._city_match = {}
            self._status = "还没有设置城市哦，去插件设置里填写吧～"
            self.dataChanged.emit()
            return

        if self._weather_loading:
            return
        self._weather_loading = True
        self._status = "正在更新天气…"
        self.dataChanged.emit()
        self._spawn(self._worker_weather, location)

    def _worker_weather(self, location):
        try:
            resolved = svc.resolve_city(location)
            if not resolved:
                raise ValueError(f"找不到「{location}」这座城市，换个写法试试？")
            raw = svc.fetch_weather_by_code(resolved["code"])
            bundle = {
                "resolved": resolved,
                "now": svc.build_now_weather(raw),
                "daily": svc.build_daily_weather(raw),
                "trend": svc.build_hourly_trend(raw),
                "fetchedAt": datetime.now(),
            }
            if self._alive:
                self._weatherDone.emit(bundle)
        except Exception as error:  # noqa: BLE001
            if self._alive:
                self._weatherError.emit(str(error))

    @Slot(object)
    def _on_weather_done(self, bundle):
        self._weather_loading = False
        if not self._alive or not isinstance(bundle, dict):
            return

        resolved = bundle.get("resolved") or {}
        self._now_weather = bundle.get("now") or {}
        self._daily_weather = bundle.get("daily") or []
        self._hourly_trend = bundle.get("trend") or {
            "points": [],
            "summary": {"min": None, "max": None, "last": None},
        }
        self._location_name = self._format_location(resolved)
        self._city_match = {
            "query": resolved.get("name") or (self.config.location or ""),
            "ok": True,
            "code": resolved.get("code") or "",
            "name": resolved.get("name") or "",
            "province": resolved.get("province") or "",
            "message": f"已匹配 {self._location_name}",
            "alternatives": [],
        }
        fetched_at = bundle.get("fetchedAt") or datetime.now()
        self._last_updated = fetched_at.strftime("%H:%M")
        self._status = "天气更新好啦 ✨"
        self.dataChanged.emit()

    @Slot(str)
    def _on_weather_error(self, message):
        self._weather_loading = False
        # 保留上一次成功的天气数据，只在状态栏提示失败原因
        self._status = f"天气更新失败：{message}"
        self.dataChanged.emit()

    def _refresh_quote(self):
        if self._quote_loading or not self._alive:
            return
        self._quote_loading = True
        self._spawn(self._worker_quote)

    def _worker_quote(self):
        try:
            quote = svc.fetch_quote()
            if self._alive:
                self._quoteDone.emit(quote)
        except Exception as error:  # noqa: BLE001
            if self._alive:
                self._quoteError.emit(str(error))

    @Slot(object)
    def _on_quote_done(self, quote):
        self._quote_loading = False
        if not self._alive or not isinstance(quote, dict):
            return
        self._quote = quote
        self.dataChanged.emit()

    @Slot(str)
    def _on_quote_error(self, message):
        self._quote_loading = False
        if not self._alive:
            return
        if not self._quote.get("text"):
            self._quote = {"text": "今天的一言没有取到，过会儿再试试～", "from": ""}
        self._status = f"一言获取失败：{message}"
        self.dataChanged.emit()

    @Slot(object)
    def _on_extras_done(self, bundle):
        if not self._alive or not isinstance(bundle, dict):
            return
        festivals = bundle.get("festivals")
        if isinstance(festivals, list):
            self._upcoming_festivals = festivals
        calendars = bundle.get("calendars")
        if isinstance(calendars, dict):
            for key, days in calendars.items():
                try:
                    year, month = (int(part) for part in str(key).split("-"))
                except (TypeError, ValueError):
                    continue
                if isinstance(days, list) and days:
                    self._calendar_cache[(year, month)] = days
        self.dataChanged.emit()

    @staticmethod
    def _format_location(resolved: dict) -> str:
        city = (resolved or {}).get("name") or ""
        province = (resolved or {}).get("province") or ""
        if not city:
            return province
        if not province or province.startswith(city) or city in province:
            # 「北京」+「北京市」这类直辖市，只显示城市名就好
            return city
        return f"{province}·{city}"
