"""
更好的一天 · A Better Day
Class Widgets 2 插件入口。

把天气、节日、黄历、课程表与每日一言，装进你桌面的一张可爱小卡片里。
作者：落落
"""

import json
import os
import threading
from datetime import datetime, timedelta

from PySide6.QtCore import (
    Property,
    QStandardPaths,
    Qt,
    QTimer,
    Signal,
    Slot,
)

from ClassWidgets.SDK import CW2Plugin, ConfigBaseModel, PluginAPI

import betterday_services as svc


# 刷新间隔的上下限（分钟）
_MIN_REFRESH_MINUTES = 5
_MAX_REFRESH_MINUTES = 240

# 灵动通知退让：通知展示时长之外再留一点动画余量
_RETREAT_EXTRA_MS = 700
_RETREAT_MIN_MS = 600
_RETREAT_MAX_MS = 30000


class BetterDayConfig(ConfigBaseModel):
    """插件全局配置（由 Class Widgets 2 持久化）。"""

    location: str = ""  # 城市名，例如「北京」「广东深圳」
    refresh_minutes: int = 15  # 天气自动刷新间隔（分钟）
    auto_refresh: bool = True  # 是否自动刷新天气
    show_warning: bool = True  # 是否显示气象预警

    # ---- 值日生 ----
    duty_names: str = ""  # 名单，逗号 / 顿号分隔
    duty_per_day: int = 2  # 每天几人
    duty_cycle: str = "week"  # week：按周轮换；day：按天轮换
    duty_start_date: str = ""  # 起算日期（留空则自动填成配置当天）

    # ---- 交互 ----
    retreat_on_notify: bool = True  # 灵动通知出现时暂时隐藏小卡片


class Plugin(CW2Plugin):
    """「更好的一天」插件主体，同时作为 Widget 与设置页的后端对象。"""

    dataChanged = Signal()
    configChanged = Signal()
    retreatChanged = Signal()  # 灵动通知退让状态变化（给详情卡用）

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
        self._duty: dict = {}
        self._weather_source: str = ""

        # ---- 状态 ----
        self._location_name: str = ""
        self._city_match: dict = {}
        self._status: str = ""
        self._last_updated: str = ""
        self._version: str = ""
        self._alive: bool = True
        self._weather_loading: bool = False
        self._quote_loading: bool = False
        self._retreat_active: bool = False

        # ---- 定时器（在 on_load 里创建，确保落在 GUI 线程）----
        self._weather_timer: QTimer | None = None
        self._clock_timer: QTimer | None = None
        self._day_timer: QTimer | None = None
        self._schedule_debounce: QTimer | None = None
        self._retreat_timer: QTimer | None = None
        self._runtime_hooked: bool = False
        self._notification_hooked: bool = False
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
                "show_duty": True,
            },
        )

        self.api.ui.register_settings_page(
            qml_path="assets/settings_page.qml",
            title="更好的一天",
            icon="ic_fluent_weather_sunny_20_regular",
        )

        self._setup_timers()
        self._hook_runtime()
        self._hook_notifications()

        self._load_weather_cache()
        self._refresh_almanac()
        self._refresh_schedule()
        self._refresh_duty()
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
            self._retreat_timer,
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
        self._retreat_timer = None

        if self._runtime_hooked:
            try:
                self.api.runtime.updated.disconnect(self._on_runtime_updated)
            except Exception:
                pass
            self._runtime_hooked = False
        if self._notification_hooked:
            try:
                self.api.notification.pushed.disconnect(self._on_notification_pushed)
            except Exception:
                pass
            self._notification_hooked = False

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
        self._clock_timer.timeout.connect(self._refresh_duty_if_changed)
        self._clock_timer.start()

        self._day_timer = QTimer(self)
        self._day_timer.setSingleShot(True)
        self._day_timer.timeout.connect(self._on_day_rollover)
        self._schedule_day_rollover()

        self._schedule_debounce = QTimer(self)
        self._schedule_debounce.setSingleShot(True)
        self._schedule_debounce.setInterval(2000)
        self._schedule_debounce.timeout.connect(self._refresh_schedule)

        # 灵动通知退让：通知消失后把卡片放回来
        self._retreat_timer = QTimer(self)
        self._retreat_timer.setSingleShot(True)
        self._retreat_timer.timeout.connect(lambda: self._set_retreat(False))

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
        self._refresh_duty()
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
    # 灵动通知退让
    # ------------------------------------------------------------------
    def _hook_notifications(self):
        """监听应用内通知，通知出现时让卡片暂时隐藏。"""
        try:
            self.api.notification.pushed.connect(self._on_notification_pushed)
            self._notification_hooked = True
        except Exception:  # noqa: BLE001
            self._notification_hooked = False

    def _notification_widget_present(self) -> bool:
        """当前小组件预设里是否存在「灵动通知」小组件。"""
        try:
            preferences = self.api.globalconfig.configs.preferences
            presets = preferences.widgets_presets or {}
            current = preferences.current_preset or ""
            entries = presets.get(current) or []
            for entry in entries:
                type_id = getattr(entry, "type_id", None)
                if type_id is None and isinstance(entry, dict):
                    type_id = entry.get("type_id")
                if type_id == "classwidgets.dynamicNotification":
                    return True
        except Exception:  # noqa: BLE001
            return False
        return False

    def _on_notification_pushed(self, payload):
        """有应用内通知时让开位置：隐藏小卡片，等通知消失后再回来。"""
        if not self._alive or not self.config.retreat_on_notify:
            return
        if self._retreat_timer is None:
            return
        if not self._notification_widget_present():
            # 没装灵动通知小组件就没必要让位置，免得卡片莫名其妙消失
            return
        try:
            duration = int((payload or {}).get("duration") or 8000)
        except (TypeError, ValueError):
            duration = 8000
        delay = max(_RETREAT_MIN_MS, min(_RETREAT_MAX_MS, duration + _RETREAT_EXTRA_MS))
        self._set_retreat(True)
        self._retreat_timer.start(delay)

    def _set_retreat(self, active: bool):
        active = bool(active)
        if active == self._retreat_active:
            return
        self._retreat_active = active
        self.retreatChanged.emit()
        self.dataChanged.emit()

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

    @Property(dict, notify=dataChanged)
    def duty(self):
        """今日值日生信息（含下一次）。"""
        return self._duty

    @Property(str, notify=dataChanged)
    def weatherSource(self):
        """这次天气数据来自哪个源（中央气象台 / Open-Meteo）。"""
        return self._weather_source

    @Property(bool, notify=retreatChanged)
    def retreatActive(self):
        """灵动通知正在展示：小卡片应当暂时让位。"""
        return self._retreat_active

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

    # ---- 值日生 ----
    def _get_duty_names(self) -> str:
        return self.config.duty_names

    def _set_duty_names(self, value: str) -> None:
        text = str(value or "").strip()
        if text == (self.config.duty_names or ""):
            return
        self.config.duty_names = text
        # 第一次配置名单时把起算日期记下来，之后轮换才不会「每周重置」
        if text and not (self.config.duty_start_date or "").strip():
            self.config.duty_start_date = datetime.now().date().isoformat()
        self._refresh_duty()
        self.configChanged.emit()

    dutyNames = Property(str, _get_duty_names, _set_duty_names, notify=configChanged)

    def _get_duty_per_day(self) -> int:
        try:
            return max(1, min(svc.DUTY_MAX_PER_DAY, int(self.config.duty_per_day)))
        except (TypeError, ValueError):
            return 2

    def _set_duty_per_day(self, value: int) -> None:
        try:
            count = int(value)
        except (TypeError, ValueError):
            count = 2
        count = max(1, min(svc.DUTY_MAX_PER_DAY, count))
        if count == self.config.duty_per_day:
            return
        self.config.duty_per_day = count
        self._refresh_duty()
        self.configChanged.emit()

    dutyPerDay = Property(int, _get_duty_per_day, _set_duty_per_day, notify=configChanged)

    def _get_duty_cycle(self) -> str:
        cycle = str(self.config.duty_cycle or svc.DUTY_CYCLE_WEEK)
        return cycle if cycle in (svc.DUTY_CYCLE_WEEK, svc.DUTY_CYCLE_DAY) else svc.DUTY_CYCLE_WEEK

    def _set_duty_cycle(self, value: str) -> None:
        cycle = str(value or svc.DUTY_CYCLE_WEEK)
        if cycle not in (svc.DUTY_CYCLE_WEEK, svc.DUTY_CYCLE_DAY):
            cycle = svc.DUTY_CYCLE_WEEK
        if cycle == self.config.duty_cycle:
            return
        self.config.duty_cycle = cycle
        self._refresh_duty()
        self.configChanged.emit()

    dutyCycle = Property(str, _get_duty_cycle, _set_duty_cycle, notify=configChanged)

    def _get_duty_start_date(self) -> str:
        return self.config.duty_start_date or ""

    def _set_duty_start_date(self, value: str) -> None:
        text = str(value or "").strip()
        if text == (self.config.duty_start_date or ""):
            return
        self.config.duty_start_date = text
        self._refresh_duty()
        self.configChanged.emit()

    dutyStartDate = Property(str, _get_duty_start_date, _set_duty_start_date, notify=configChanged)

    # ---- 灵动通知退让 ----
    def _get_retreat_on_notify(self) -> bool:
        return bool(self.config.retreat_on_notify)

    def _set_retreat_on_notify(self, value: bool) -> None:
        value = bool(value)
        if value == self.config.retreat_on_notify:
            return
        self.config.retreat_on_notify = value
        if not value:
            self._set_retreat(False)
        self.configChanged.emit()

    retreatOnNotify = Property(
        bool, _get_retreat_on_notify, _set_retreat_on_notify, notify=configChanged
    )

    # ------------------------------------------------------------------
    # 槽函数
    # ------------------------------------------------------------------
    @Slot()
    def refreshAll(self):
        self._refresh_almanac()
        self._refresh_schedule()
        self._refresh_duty()
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

    @Slot()
    def refreshDuty(self):
        self._refresh_duty()

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
            "weatherSource": self._weather_source,
            "notificationHooked": self._notification_hooked,
            "notificationWidget": self._notification_widget_present(),
            "retreatActive": self._retreat_active,
            "dutyEnabled": bool(self._duty.get("enabled")),
            "dutyGroup": self._duty.get("groupLabel") or "",
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

    def _refresh_duty(self):
        try:
            duty = svc.build_duty(
                self.config.duty_names,
                per_day=self._get_duty_per_day(),
                cycle=self._get_duty_cycle(),
                start_date=self.config.duty_start_date or "",
            )
        except Exception as error:  # noqa: BLE001
            duty = {"enabled": False, "names": [], "todayNames": [], "todayText": ""}
            self._status = f"值日生计算失败：{error}"
        self._duty = duty
        self.dataChanged.emit()

    def _refresh_duty_if_changed(self):
        """时钟定时器里低成本地检查一次（跨周 / 跨天时需要换组）。"""
        try:
            duty = svc.build_duty(
                self.config.duty_names,
                per_day=self._get_duty_per_day(),
                cycle=self._get_duty_cycle(),
                start_date=self.config.duty_start_date or "",
            )
        except Exception:  # noqa: BLE001
            return
        if duty != self._duty:
            self._duty = duty
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
            bundle = svc.fetch_weather_bundle(location)
            bundle["fetchedAt"] = datetime.now()
            bundle["query"] = location
            self._save_weather_cache(bundle)
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
        source = bundle.get("source") or ""
        self._weather_source = source
        fetched_at = bundle.get("fetchedAt") or datetime.now()
        self._last_updated = fetched_at.strftime("%H:%M")
        if source and source != svc.SOURCE_NMC:
            self._status = f"天气更新好啦（备用源 {source}）"
        else:
            self._status = "天气更新好啦 ✨"
        self.dataChanged.emit()

    def _weather_cache_file(self):
        try:
            base = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppDataLocation
            )
        except Exception:  # noqa: BLE001
            return None
        if not base:
            return None
        folder = os.path.join(base, "better-day")
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            return None
        return os.path.join(folder, "weather-cache.json")

    def _save_weather_cache(self, bundle):
        """把最近一次成功的天气存到磁盘，重启后先显示旧数据再更新。"""
        path = self._weather_cache_file()
        if not path:
            return
        try:
            fetched_at = bundle.get("fetchedAt") or datetime.now()
            payload = {
                "query": bundle.get("query") or (self.config.location or ""),
                "source": bundle.get("source") or "",
                "fetchedAt": fetched_at.isoformat() if hasattr(fetched_at, "isoformat") else "",
                "fetchedAtShort": fetched_at.strftime("%H:%M")
                if hasattr(fetched_at, "strftime")
                else "",
                "resolved": bundle.get("resolved") or {},
                "now": bundle.get("now") or {},
                "daily": bundle.get("daily") or [],
                "trend": bundle.get("trend") or {},
            }
            temp_path = path + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)
            os.replace(temp_path, path)
        except Exception:  # noqa: BLE001
            pass

    def _load_weather_cache(self):
        """读取上一次的天气缓存，让卡片一开机就有内容。"""
        path = self._weather_cache_file()
        if not path or not os.path.exists(path):
            return False
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            return False
        if not isinstance(payload, dict):
            return False
        query = (self.config.location or "").strip()
        cached_query = svc.clean_text(payload.get("query"))
        if cached_query and cached_query != query:
            return False
        now_weather = payload.get("now") or {}
        if not now_weather or now_weather.get("temp") is None:
            return False
        self._now_weather = now_weather
        self._daily_weather = payload.get("daily") or []
        trend = payload.get("trend") or {}
        if isinstance(trend, dict) and trend.get("points") is not None:
            self._hourly_trend = trend
        resolved = payload.get("resolved") or {}
        if resolved:
            self._location_name = self._format_location(resolved)
        self._weather_source = payload.get("source") or ""
        self._last_updated = payload.get("fetchedAtShort") or ""
        self._status = "已显示上次的天气，正在更新…"
        self.dataChanged.emit()
        return True

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
