import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import ClassWidgets.Theme

// 「更好的一天」详情卡：一张可拖动、无边框的独立浮动面板，
// 所有内容以「卡片」形式堆叠在同一个可滚动面板上。
Window {
    id: root
    flags: Qt.FramelessWindowHint | Qt.Window | Qt.WindowStaysOnTopHint | Qt.Tool
    color: "transparent"
    width: 420
    height: 620
    visible: false

    property var backend: null

    // 主题还没准备好时 Colors.proxy 可能还没有值，这里兜底
    readonly property color textColor: (Colors && Colors.proxy && Colors.proxy.textColor)
        ? Colors.proxy.textColor : (Theme.isDark() ? "#F2F2F2" : "#202020")
    readonly property color dimColor: (Colors && Colors.proxy && Colors.proxy.textSecondaryColor)
        ? Colors.proxy.textSecondaryColor : (Theme.isDark() ? "#A0A0A0" : "#6A6A6A")
    readonly property color accentColor: (Colors && Colors.proxy && Colors.proxy.primaryColor)
        ? Colors.proxy.primaryColor : "#4C8DDB"
    readonly property bool dark: Theme.isDark()

    // ---- 数据代理 ----
    readonly property var nowWeather: (backend && backend.nowWeather) ? backend.nowWeather : ({})
    readonly property var dailyWeather: (backend && backend.dailyWeather) ? backend.dailyWeather : []
    readonly property var trend: (backend && backend.hourlyTrend) ? backend.hourlyTrend : ({})
    readonly property var trendPoints: trend.points ? trend.points : []
    readonly property var trendSummary: trend.summary ? trend.summary : ({})
    readonly property var almanac: (backend && backend.almanac) ? backend.almanac : ({})
    readonly property var festivals: (backend && backend.upcomingFestivals) ? backend.upcomingFestivals : []
    readonly property var schedule: (backend && backend.weekSchedule) ? backend.weekSchedule : ({})
    readonly property var quoteData: (backend && backend.quote) ? backend.quote : ({})
    readonly property var duty: (backend && backend.duty) ? backend.duty : ({})
    readonly property bool warningVisible: !!(nowWeather.warning && (!backend || backend.showWarning))

    // ---- 日历状态 ----
    property int calYear: 0
    property int calMonth: 0
    property var calDays: []
    readonly property int leadingBlanks: calDays.length > 0 ? calDays[0].weekday : 0

    function loadCalendar() {
        if (backend && calYear > 0 && calMonth > 0) {
            var days = backend.calendar(calYear, calMonth)
            calDays = days ? days : []
        } else {
            calDays = []
        }
    }

    function shiftMonth(delta) {
        var month = calMonth + delta
        var year = calYear
        while (month < 1) { month += 12; year -= 1 }
        while (month > 12) { month -= 12; year += 1 }
        calYear = year
        calMonth = month
        loadCalendar()
    }

    function goToday() {
        var now = new Date()
        calYear = now.getFullYear()
        calMonth = now.getMonth() + 1
        loadCalendar()
    }

    function screenAt(x, y) {
        for (var i = 0; i < Qt.application.screens.length; i++) {
            var s = Qt.application.screens[i]
            if (x >= s.virtualX && x < s.virtualX + s.width && y >= s.virtualY && y < s.virtualY + s.height)
                return s
        }
        return Qt.application.screens[0]
    }

    function openNear(ax, ay, aw, ah) {
        goToday()
        var s = screenAt(ax, ay)
        // 小屏幕上把窗口高度收一收，免得超出屏幕
        var availableHeight = s.height - 24
        if (availableHeight > 240 && root.height > availableHeight)
            root.height = availableHeight
        var x = ax
        var y = ay + ah + 8 // 默认显示在小卡片下方，左对齐

        if (y + root.height > s.virtualY + s.height - 8)
            y = ay - root.height - 8 // 放不下就翻到上方
        if (x + root.width > s.virtualX + s.width - 8)
            x = ax + aw - root.width // 右侧放不下就右对齐

        x = Math.max(s.virtualX + 8, Math.min(s.virtualX + s.width - root.width - 8, x))
        y = Math.max(s.virtualY + 8, Math.min(s.virtualY + s.height - root.height - 8, y))
        root.x = Math.round(x)
        root.y = Math.round(y)
        root.visible = true
        root.requestActivate()
    }

    function close() { root.visible = false }

    Shortcut {
        sequence: "Escape"
        enabled: root.visible
        onActivated: root.close()
    }

    // 灵动通知出现时让位，别挡住通知
    Connections {
        target: root.backend
        ignoreUnknownSignals: true
        function onRetreatChanged() {
            if (root.backend && root.backend.retreatActive && root.visible)
                root.close()
        }
    }

    Component.onCompleted: goToday()

    // ---------------- 卡片外壳（不透明、可拖动） ----------------
    Rectangle {
        id: shell
        anchors.fill: parent
        radius: 14
        color: root.dark ? "#242329" : "#F7F6FB"
        border.width: 1
        border.color: root.dark ? Qt.alpha("#ffffff", 0.16) : Qt.alpha("#ffffff", 0.9)
        clip: true

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 12

            // ---- 头部（拖动区）----
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Title {
                    px: 18
                    text: qsTr("更好的一天")
                }
                Text {
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                    color: root.dimColor
                    font.pixelSize: 12
                    text: {
                        var parts = []
                        if (backend && backend.locationName) parts.push(backend.locationName)
                        if (backend && backend.weatherSource) parts.push(backend.weatherSource)
                        if (backend && backend.lastUpdated) parts.push(qsTr("更新于 ") + backend.lastUpdated)
                        return parts.join(" · ")
                    }
                }
                ToolButton {
                    icon.name: "ic_fluent_arrow_sync_20_regular"
                    implicitWidth: 26
                    implicitHeight: 26
                    onClicked: { if (backend) backend.refreshAll() }
                    ToolTip {
                        text: qsTr("刷新全部")
                        visible: parent.hovered
                    }
                }
                ToolButton {
                    icon.name: "ic_fluent_dismiss_20_regular"
                    implicitWidth: 26
                    implicitHeight: 26
                    onClicked: root.close()
                    ToolTip {
                        text: qsTr("关闭")
                        visible: parent.hovered
                    }
                }

                DragHandler {
                    id: dragHandler
                    property real startX: 0
                    property real startY: 0
                    onActiveChanged: {
                        if (active) { startX = root.x; startY = root.y }
                    }
                    onTranslationChanged: {
                        if (active) {
                            root.x = startX + translation.x
                            root.y = startY + translation.y
                        }
                    }
                }
            }

            // ---- 单面板滚动内容（所有卡片堆叠）----
            Flickable {
                id: panelFlick
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                contentWidth: width
                contentHeight: panelColumn.height
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { }

                Column {
                    id: panelColumn
                    width: parent.width
                    spacing: 12

                    // ============ 卡片 1：天气 ============
                    Rectangle {
                        width: parent.width
                        radius: 12
                        height: weatherColumn.height + 28
                        color: root.dark ? Qt.alpha("#ffffff", 0.06) : Qt.alpha("#000000", 0.035)

                        Column {
                            id: weatherColumn
                            width: parent.width - 24
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.top: parent.top
                            anchors.topMargin: 14
                            spacing: 10

                            // 当前天气
                            Row {
                                width: parent.width
                                spacing: 12
                                Text {
                                    text: root.nowWeather.emoji ? root.nowWeather.emoji : "🌡️"
                                    font.pixelSize: 40
                                }
                                Column {
                                    spacing: 2
                                    Title {
                                        px: 26
                                        width: Math.max(0, panelColumn.width - 100)
                                        wrapMode: Text.WordWrap
                                        maximumLineCount: 2
                                        text: (root.nowWeather.temp !== undefined && root.nowWeather.temp !== null)
                                            ? (root.nowWeather.temp + "°  " + (root.nowWeather.text || ""))
                                            : ((backend && backend.statusText) ? backend.statusText : qsTr("加载中…"))
                                    }
                                    Text {
                                        color: root.dimColor
                                        font.pixelSize: 12
                                        width: Math.max(0, panelColumn.width - 100)
                                        wrapMode: Text.WordWrap
                                        text: {
                                            var n = root.nowWeather
                                            var parts = []
                                            if (n.feelsLike !== undefined && n.feelsLike !== null)
                                                parts.push(qsTr("体感 ") + n.feelsLike + "°")
                                            if (n.humidity !== undefined && n.humidity !== null)
                                                parts.push(qsTr("湿度 ") + n.humidity + "%")
                                            if (n.wind) parts.push(n.wind)
                                            if (n.aqi !== undefined && n.aqi !== null)
                                                parts.push(qsTr("空气 ") + (n.aqiCategory || "") + " " + n.aqi)
                                            return parts.join(" · ")
                                        }
                                    }
                                    Text {
                                        color: root.dimColor
                                        font.pixelSize: 12
                                        text: {
                                            var n = root.nowWeather
                                            var parts = []
                                            if (n.sunrise) parts.push("🌅 " + n.sunrise)
                                            if (n.sunset) parts.push("🌇 " + n.sunset)
                                            return parts.join("    ")
                                        }
                                    }
                                }
                            }

                            // 气象预警
                            Rectangle {
                                width: parent.width
                                height: warningColumn.height + 16
                                radius: 8
                                visible: root.warningVisible
                                color: root.dark ? Qt.alpha("#E8A33D", 0.22) : Qt.alpha("#E8A33D", 0.16)

                                Column {
                                    id: warningColumn
                                    width: parent.width - 16
                                    anchors.centerIn: parent
                                    spacing: 2
                                    Text {
                                        width: parent.width
                                        wrapMode: Text.WordWrap
                                        color: root.textColor
                                        font.pixelSize: 12
                                        font.weight: 700
                                        text: {
                                            var w = root.nowWeather.warning
                                            return w ? ("⚠️ " + (w.title || qsTr("气象预警"))) : ""
                                        }
                                    }
                                    Text {
                                        width: parent.width
                                        wrapMode: Text.WordWrap
                                        color: root.textColor
                                        font.pixelSize: 12
                                        visible: !!((root.nowWeather.warning || {}).content)
                                        text: (root.nowWeather.warning || {}).content || ""
                                    }
                                }
                            }

                            Rectangle { width: parent.width; height: 1; color: root.dark ? Qt.alpha("#fff", 0.08) : Qt.alpha("#000", 0.06) }

                            // 过去 24 小时温度走势
                            Column {
                                width: parent.width
                                spacing: 4
                                visible: root.trendPoints.length > 1
                                Row {
                                    width: parent.width
                                    Text {
                                        text: qsTr("过去 24 小时")
                                        color: root.dimColor
                                        font.pixelSize: 12
                                    }
                                    Item { width: Math.max(0, parent.width - 190); height: 1 }
                                    Text {
                                        width: 120
                                        horizontalAlignment: Text.AlignRight
                                        color: root.dimColor
                                        font.pixelSize: 12
                                        text: (root.trendSummary.min !== null && root.trendSummary.min !== undefined)
                                            ? (root.trendSummary.min + "° ~ " + root.trendSummary.max + "°")
                                            : ""
                                    }
                                }
                                Row {
                                    id: trendRow
                                    width: parent.width
                                    height: 44
                                    spacing: 1
                                    Repeater {
                                        model: root.trendPoints
                                        delegate: Item {
                                            width: Math.max(1, (trendRow.width - Math.max(0, root.trendPoints.length - 1) * trendRow.spacing)
                                                           / Math.max(1, root.trendPoints.length))
                                            height: trendRow.height
                                            Rectangle {
                                                anchors.bottom: parent.bottom
                                                width: parent.width
                                                radius: 2
                                                height: 4 + (modelData.ratio || 0) * (trendRow.height - 8)
                                                color: Qt.alpha(root.accentColor, 0.35 + (modelData.ratio || 0) * 0.55)
                                            }
                                        }
                                    }
                                }
                                Row {
                                    width: parent.width
                                    Text {
                                        text: root.trendPoints.length > 0 ? root.trendPoints[0].timeShort : ""
                                        color: root.dimColor
                                        font.pixelSize: 10
                                    }
                                    Item { width: Math.max(0, parent.width - 80); height: 1 }
                                    Text {
                                        width: 60
                                        horizontalAlignment: Text.AlignRight
                                        text: root.trendPoints.length > 0
                                            ? root.trendPoints[root.trendPoints.length - 1].timeShort : ""
                                        color: root.dimColor
                                        font.pixelSize: 10
                                    }
                                }
                            }

                            Rectangle { width: parent.width; height: 1; color: root.dark ? Qt.alpha("#fff", 0.08) : Qt.alpha("#000", 0.06) }

                            // 7 日预报表格
                            Row {
                                width: parent.width
                                Text { width: 58; text: qsTr("日期"); color: root.dimColor; font.pixelSize: 12 }
                                Text { width: 92; text: qsTr("天气"); color: root.dimColor; font.pixelSize: 12 }
                                Text { width: 78; text: qsTr("温度"); color: root.dimColor; font.pixelSize: 12 }
                                Text { width: 80; text: qsTr("风"); color: root.dimColor; font.pixelSize: 12 }
                                Text { width: 44; text: qsTr("降水"); color: root.dimColor; font.pixelSize: 12 }
                            }
                            Repeater {
                                model: root.dailyWeather
                                delegate: Row {
                                    width: Math.max(0, panelColumn.width - 24)
                                    height: 22
                                    Text {
                                        width: 58
                                        text: (modelData.isToday ? qsTr("今天") : (modelData.label || modelData.weekday))
                                        color: modelData.isToday ? root.accentColor : root.textColor
                                        font.pixelSize: 13
                                        font.weight: modelData.isToday ? 700 : 400
                                    }
                                    Text {
                                        width: 92
                                        elide: Text.ElideRight
                                        text: (modelData.emoji ? modelData.emoji + " " : "") + (modelData.text || "")
                                        color: root.textColor
                                        font.pixelSize: 13
                                    }
                                    Text {
                                        width: 78
                                        text: (modelData.tempMin !== undefined && modelData.tempMax !== undefined
                                               && modelData.tempMin !== null && modelData.tempMax !== null)
                                            ? (modelData.tempMin + "~" + modelData.tempMax + "°") : "—"
                                        color: root.textColor
                                        font.pixelSize: 13
                                    }
                                    Text {
                                        width: 80
                                        elide: Text.ElideRight
                                        text: modelData.wind || ""
                                        color: root.dimColor
                                        font.pixelSize: 12
                                    }
                                    Text {
                                        width: 44
                                        text: (modelData.precipitation !== undefined && modelData.precipitation !== null
                                               && modelData.precipitation > 0) ? (modelData.precipitation + "mm") : "—"
                                        color: root.dimColor
                                        font.pixelSize: 12
                                    }
                                }
                            }
                        }
                    }

                    // ============ 卡片 2：日历 · 黄历 ============
                    Rectangle {
                        width: parent.width
                        radius: 12
                        height: calendarColumn.height + 28
                        color: root.dark ? Qt.alpha("#ffffff", 0.06) : Qt.alpha("#000000", 0.035)

                        Column {
                            id: calendarColumn
                            width: parent.width - 24
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.top: parent.top
                            anchors.topMargin: 14
                            spacing: 8

                            RowLayout {
                                width: parent.width
                                spacing: 4
                                ToolButton {
                                    icon.name: "ic_fluent_chevron_left_20_regular"
                                    implicitWidth: 30
                                    implicitHeight: 30
                                    onClicked: root.shiftMonth(-1)
                                }
                                Title {
                                    px: 18
                                    Layout.fillWidth: true
                                    horizontalAlignment: Text.AlignHCenter
                                    text: root.calYear + qsTr(" 年 ") + root.calMonth + qsTr(" 月")
                                }
                                Button {
                                    text: qsTr("今天")
                                    flat: true
                                    implicitHeight: 28
                                    onClicked: root.goToday()
                                }
                                ToolButton {
                                    icon.name: "ic_fluent_chevron_right_20_regular"
                                    implicitWidth: 30
                                    implicitHeight: 30
                                    onClicked: root.shiftMonth(1)
                                }
                            }

                            // 星期表头
                            Row {
                                anchors.horizontalCenter: parent.horizontalCenter
                                spacing: 2
                                Repeater {
                                    model: [qsTr("一"), qsTr("二"), qsTr("三"), qsTr("四"), qsTr("五"), qsTr("六"), qsTr("日")]
                                    delegate: Text {
                                        width: 38
                                        horizontalAlignment: Text.AlignHCenter
                                        text: modelData
                                        color: root.dimColor
                                        font.pixelSize: 12
                                    }
                                }
                            }

                            // 日历网格
                            Grid {
                                anchors.horizontalCenter: parent.horizontalCenter
                                columns: 7
                                spacing: 2
                                Repeater {
                                    model: root.leadingBlanks + root.calDays.length
                                    delegate: Rectangle {
                                        width: 38
                                        height: 38
                                        radius: 8
                                        color: {
                                            var idx = index - root.leadingBlanks
                                            if (idx < 0) return "transparent"
                                            var d = root.calDays[idx]
                                            if (!d) return "transparent"
                                            if (d.isToday) return Qt.alpha(root.accentColor, root.dark ? 0.32 : 0.18)
                                            if (d.isHolidayRest) return root.dark ? Qt.alpha("#E86A6A", 0.22) : Qt.alpha("#E86A6A", 0.14)
                                            if (d.festival || d.jieqi) return root.dark ? Qt.alpha("#ffffff", 0.06) : Qt.alpha("#000000", 0.05)
                                            return "transparent"
                                        }
                                        Text {
                                            anchors.top: parent.top
                                            anchors.topMargin: 3
                                            anchors.horizontalCenter: parent.horizontalCenter
                                            text: {
                                                var idx = index - root.leadingBlanks
                                                return (idx < 0 || !root.calDays[idx]) ? "" : String(root.calDays[idx].solarDay)
                                            }
                                            font.pixelSize: 14
                                            color: {
                                                var idx = index - root.leadingBlanks
                                                if (idx < 0 || !root.calDays[idx]) return root.textColor
                                                return root.calDays[idx].isWeekend ? "#D28B59" : root.textColor
                                            }
                                        }
                                        Text {
                                            anchors.bottom: parent.bottom
                                            anchors.bottomMargin: 3
                                            anchors.horizontalCenter: parent.horizontalCenter
                                            width: 36
                                            elide: Text.ElideRight
                                            horizontalAlignment: Text.AlignHCenter
                                            text: {
                                                var idx = index - root.leadingBlanks
                                                if (idx < 0 || !root.calDays[idx]) return ""
                                                var d = root.calDays[idx]
                                                if (d.legalHoliday) return d.legalHoliday
                                                return d.festival || d.jieqi || (d.solarDay === 1 ? d.lunarMonth + "月" : d.lunarDay)
                                            }
                                            color: {
                                                var idx = index - root.leadingBlanks
                                                if (idx >= 0 && root.calDays[idx] && (root.calDays[idx].festival || root.calDays[idx].jieqi))
                                                    return root.accentColor
                                                return root.dimColor
                                            }
                                            font.pixelSize: 9
                                        }
                                    }
                                }
                            }

                            Rectangle { width: parent.width; height: 1; color: root.dark ? Qt.alpha("#fff", 0.08) : Qt.alpha("#000", 0.06) }

                            // 今日黄历摘要
                            Column {
                                width: parent.width
                                spacing: 4
                                Text {
                                    text: root.almanac.lunarFull || qsTr("黄历加载中…")
                                    color: root.textColor
                                    font.pixelSize: 14
                                    font.weight: 700
                                }
                                Text {
                                    color: root.dimColor
                                    font.pixelSize: 12
                                    width: parent.width
                                    wrapMode: Text.WordWrap
                                    text: {
                                        var al = root.almanac
                                        var parts = [al.ganzhiYear, al.ganzhiMonth, al.ganzhiDay].filter(function (x) { return x })
                                        var line = parts.join(" · ")
                                        if (al.shengxiao) line += "   属" + al.shengxiao
                                        if (al.chong) line += "   冲" + al.chong
                                        if (al.sha) line += "   煞" + al.sha
                                        if (al.zhixing) line += "   值" + al.zhixing
                                        return line
                                    }
                                }
                                Text {
                                    width: parent.width
                                    wrapMode: Text.WordWrap
                                    color: root.textColor
                                    font.pixelSize: 13
                                    text: qsTr("宜 ") + ((root.almanac.yi || []).join("、") || "—")
                                }
                                Text {
                                    width: parent.width
                                    wrapMode: Text.WordWrap
                                    color: root.textColor
                                    font.pixelSize: 13
                                    text: qsTr("忌 ") + ((root.almanac.ji || []).join("、") || "—")
                                }
                                Text {
                                    color: root.dimColor
                                    font.pixelSize: 12
                                    width: parent.width
                                    wrapMode: Text.WordWrap
                                    visible: !!root.almanac.nextJieQi
                                    text: {
                                        var al = root.almanac
                                        if (!al.nextJieQi) return ""
                                        var days = al.daysToNextJieQi
                                        var suffix = ""
                                        if (days !== null && days !== undefined)
                                            suffix = "（" + (days === 0 ? qsTr("今天") : (days + qsTr(" 天后"))) + "）"
                                        return qsTr("下一节气：") + al.nextJieQi + suffix
                                    }
                                }
                            }

                            // 最近的节日
                            Column {
                                width: parent.width
                                spacing: 4
                                visible: root.festivals.length > 0
                                Rectangle { width: parent.width; height: 1; color: root.dark ? Qt.alpha("#fff", 0.08) : Qt.alpha("#000", 0.06) }
                                Text {
                                    text: qsTr("最近的节日")
                                    color: root.dimColor
                                    font.pixelSize: 12
                                }
                                Repeater {
                                    model: root.festivals.slice(0, 4)
                                    delegate: Row {
                                        width: calendarColumn.width
                                        height: 20
                                        Text {
                                            width: Math.max(0, parent.width - 120)
                                            elide: Text.ElideRight
                                            text: modelData.name
                                            color: root.textColor
                                            font.pixelSize: 13
                                        }
                                        Text {
                                            width: 120
                                            horizontalAlignment: Text.AlignRight
                                            text: modelData.dateShort + " · "
                                                + (modelData.daysLeft === 1 ? qsTr("明天") : (modelData.daysLeft + qsTr(" 天后")))
                                            color: root.dimColor
                                            font.pixelSize: 12
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // ============ 卡片 3：整周课表（表格） ============
                    Rectangle {
                        width: parent.width
                        radius: 12
                        height: scheduleColumn.height + 28
                        color: root.dark ? Qt.alpha("#ffffff", 0.06) : Qt.alpha("#000000", 0.035)

                        Column {
                            id: scheduleColumn
                            width: parent.width - 24
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.top: parent.top
                            anchors.topMargin: 14
                            spacing: 6

                            Row {
                                width: parent.width
                                Text {
                                    text: qsTr("整周课表")
                                    color: root.textColor
                                    font.pixelSize: 14
                                    font.weight: 700
                                }
                                Item { width: Math.max(0, parent.width - 220); height: 1 }
                                Text {
                                    width: 140
                                    horizontalAlignment: Text.AlignRight
                                    color: root.dimColor
                                    font.pixelSize: 12
                                    text: {
                                        var s = root.schedule
                                        if (!s.weekNumber) return ""
                                        var cycle = (s.weekOfCycle && s.maxWeekCycle > 1)
                                            ? qsTr("（轮换第 ") + s.weekOfCycle + qsTr(" 周）") : ""
                                        return qsTr("第 ") + s.weekNumber + qsTr(" 周") + cycle
                                    }
                                }
                            }

                            Text {
                                width: parent.width
                                wrapMode: Text.WordWrap
                                color: root.dimColor
                                font.pixelSize: 12
                                visible: !root.schedule.hasData
                                text: qsTr("还没有读到课表数据。先在 Class Widgets 里添加课表，这里就会自动出现啦。")
                            }

                            Flickable {
                                width: parent.width
                                height: Math.min(340, Math.max(0, scheduleGrid.height))
                                clip: true
                                visible: !!root.schedule.hasData
                                contentWidth: scheduleGrid.width
                                contentHeight: scheduleGrid.height
                                boundsBehavior: Flickable.StopAtBounds

                                Column {
                                    id: scheduleGrid
                                    spacing: 3

                                    // 表头
                                    Row {
                                        id: scheduleHeader
                                        spacing: 2
                                        Rectangle {
                                            width: 48; height: 28; radius: 6
                                            color: "transparent"
                                            Text { anchors.centerIn: parent; text: qsTr("节次"); color: root.dimColor; font.pixelSize: 11 }
                                        }
                                        Repeater {
                                            model: root.schedule.days ? root.schedule.days : []
                                            delegate: Rectangle {
                                                width: 42; height: 28; radius: 6
                                                color: modelData.isToday
                                                    ? Qt.alpha(root.accentColor, root.dark ? 0.3 : 0.16) : "transparent"
                                                Column {
                                                    anchors.centerIn: parent
                                                    spacing: -3
                                                    Text {
                                                        text: modelData.dayShort
                                                        color: modelData.isToday ? root.accentColor : root.dimColor
                                                        font.pixelSize: 11
                                                        font.weight: modelData.isToday ? 700 : 400
                                                    }
                                                    Text {
                                                        text: modelData.dateShort || ""
                                                        color: root.dimColor
                                                        font.pixelSize: 8
                                                        visible: !!modelData.dateShort
                                                    }
                                                }
                                            }
                                        }
                                    }

                                    // 数据行
                                    Repeater {
                                        id: periodRows
                                        model: root.schedule.periods ? root.schedule.periods : []
                                        delegate: Row {
                                            property int rowIndex: index
                                            spacing: 2
                                            Rectangle {
                                                width: 48; height: 34; radius: 6
                                                color: root.dark ? Qt.alpha("#ffffff", 0.04) : Qt.alpha("#000000", 0.03)
                                                Column {
                                                    anchors.centerIn: parent
                                                    spacing: -1
                                                    Text {
                                                        text: modelData.start || ""
                                                        anchors.horizontalCenter: parent.horizontalCenter
                                                        color: root.dimColor
                                                        font.pixelSize: 10
                                                    }
                                                    Text {
                                                        text: modelData.end || ""
                                                        anchors.horizontalCenter: parent.horizontalCenter
                                                        color: root.dimColor
                                                        font.pixelSize: 9
                                                        opacity: 0.7
                                                    }
                                                }
                                            }
                                            Repeater {
                                                model: root.schedule.days ? root.schedule.days : []
                                                delegate: Rectangle {
                                                    width: 42; height: 34; radius: 6
                                                    property var cell: (modelData && modelData.cells && modelData.cells.length > rowIndex)
                                                        ? modelData.cells[rowIndex] : null
                                                    color: (cell && cell.color)
                                                        ? Qt.alpha(cell.color, root.dark ? 0.35 : 0.22)
                                                        : "transparent"
                                                    Text {
                                                        anchors.centerIn: parent
                                                        width: 38
                                                        elide: Text.ElideRight
                                                        horizontalAlignment: Text.AlignHCenter
                                                        text: cell ? (cell.title || "") : ""
                                                        color: root.textColor
                                                        font.pixelSize: 11
                                                    }
                                                    HoverHandler { id: cellHover }
                                                    ToolTip {
                                                        visible: cellHover.hovered && !!cell
                                                        text: {
                                                            if (!cell) return ""
                                                            var parts = [cell.title]
                                                            if (cell.teacher) parts.push(cell.teacher)
                                                            if (cell.location) parts.push(cell.location)
                                                            if (cell.startTime) parts.push(cell.startTime + "-" + cell.endTime)
                                                            return parts.filter(function (x) { return !!x }).join(" · ")
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // ============ 卡片 4：值日生 ============
                    Rectangle {
                        width: parent.width
                        radius: 12
                        height: dutyColumn.height + 28
                        visible: !!root.duty.enabled
                        color: root.dark ? Qt.alpha("#ffffff", 0.06) : Qt.alpha("#000000", 0.035)

                        Column {
                            id: dutyColumn
                            width: parent.width - 24
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.top: parent.top
                            anchors.topMargin: 14
                            spacing: 6

                            Row {
                                width: parent.width
                                Text {
                                    text: qsTr("今天值日")
                                    color: root.textColor
                                    font.pixelSize: 14
                                    font.weight: 700
                                }
                                Item { width: Math.max(0, parent.width - 240); height: 1 }
                                Text {
                                    width: 140
                                    horizontalAlignment: Text.AlignRight
                                    color: root.dimColor
                                    font.pixelSize: 12
                                    text: root.duty.groupLabel || ""
                                }
                            }

                            MarqueeTitle {
                                width: parent.width
                                maximumWidth: parent.width
                                font.pixelSize: 18
                                speed: 45
                                text: root.duty.todayText || "—"
                            }

                            Text {
                                width: parent.width
                                wrapMode: Text.WordWrap
                                color: root.dimColor
                                font.pixelSize: 12
                                text: (root.duty.nextDateShort || "")
                                    ? (qsTr("下一次：") + root.duty.nextDateShort + " · " + (root.duty.nextText || ""))
                                    : ""
                            }
                        }
                    }

                    // ============ 卡片 5：每日一言 ============
                    Rectangle {
                        width: parent.width
                        radius: 12
                        height: quoteColumn.height + 32
                        color: root.dark ? Qt.alpha("#ffffff", 0.06) : Qt.alpha("#000000", 0.035)

                        Column {
                            id: quoteColumn
                            width: parent.width - 24
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.top: parent.top
                            anchors.topMargin: 16
                            spacing: 10

                            Text {
                                width: parent.width
                                horizontalAlignment: Text.AlignHCenter
                                text: qsTr("“")
                                font.pixelSize: 26
                                color: root.accentColor
                            }
                            Title {
                                px: 18
                                width: parent.width
                                horizontalAlignment: Text.AlignHCenter
                                wrapMode: Text.WordWrap
                                text: root.quoteData.text ? root.quoteData.text : qsTr("正在为你摘一句悄悄话…")
                            }
                            Text {
                                width: parent.width
                                horizontalAlignment: Text.AlignHCenter
                                color: root.dimColor
                                font.pixelSize: 12
                                text: root.quoteData.from ? ("—— " + root.quoteData.from) : ""
                            }
                            Button {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: qsTr("换一句")
                                flat: true
                                onClicked: { if (backend) backend.refreshQuote() }
                            }
                        }
                    }
                }
            }
        }
    }
}
