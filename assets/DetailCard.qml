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
    width: 400
    height: 560
    visible: false

    property var backend: null

    readonly property color textColor: Colors.proxy.textColor
    readonly property color dimColor: Colors.proxy.textSecondaryColor
    readonly property color accentColor: Colors.proxy.primaryColor

    // 日历状态
    property int calYear: 0
    property int calMonth: 0
    property var calDays: []
    property int leadingBlanks: calDays.length > 0 ? calDays[0].weekday : 0

    function loadCalendar() {
        if (backend && calYear > 0 && calMonth > 0)
            calDays = backend.calendar(calYear, calMonth)
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
        var s = screenAt(ax, ay)
        var x = ax
        var y = ay + ah + 8  // 默认显示在小卡片下方，左对齐

        if (y + root.height > s.virtualY + s.height - 8)
            y = ay - root.height - 8  // 放不下就翻到上方
        if (x + root.width > s.virtualX + s.width - 8)
            x = ax + aw - root.width  // 右侧放不下就右对齐

        x = Math.max(s.virtualX + 8, Math.min(s.virtualX + s.width - root.width - 8, x))
        y = Math.max(s.virtualY + 8, Math.min(s.virtualY + s.height - root.height - 8, y))
        root.x = Math.round(x)
        root.y = Math.round(y)
        root.visible = true
        root.requestActivate()
    }

    function close() { root.visible = false }

    Component.onCompleted: {
        var now = new Date()
        calYear = now.getFullYear()
        calMonth = now.getMonth() + 1
        loadCalendar()
    }

    // ---------------- 卡片外壳（不透明、可拖动） ----------------
    Rectangle {
        id: shell
        anchors.fill: parent
        radius: 14
        color: Theme.isDark() ? "#242329" : "#F7F6FB"
        border.width: 1
        border.color: Theme.isDark() ? Qt.alpha("#ffffff", 0.16) : Qt.alpha("#ffffff", 0.9)
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
                    text: (backend && backend.locationName) ? backend.locationName : ""
                    color: root.dimColor
                    font.pixelSize: 12
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                ToolButton {
                    icon.name: "ic_fluent_dismiss_20_regular"
                    implicitWidth: 26
                    implicitHeight: 26
                    onClicked: root.close()
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
                        color: Theme.isDark() ? Qt.alpha("#ffffff", 0.06) : Qt.alpha("#000000", 0.035)
                        Column {
                            width: parent.width - 24
                            anchors.horizontalCenter: parent.horizontalCenter
                            topPadding: 14
                            bottomPadding: 14
                            spacing: 10

                            // 当前天气
                            Row {
                                width: parent.width
                                spacing: 12
                                Text {
                                    text: (backend && backend.nowWeather.emoji) ? backend.nowWeather.emoji : "🌡️"
                                    font.pixelSize: 40
                                }
                                Column {
                                    spacing: 0
                                    Title {
                                        px: 26
                                        text: (backend && backend.nowWeather.temp !== undefined && backend.nowWeather.temp !== null)
                                            ? (backend.nowWeather.temp + "°  " + (backend.nowWeather.text || ""))
                                            : ((backend && backend.statusText) ? backend.statusText : qsTr("加载中…"))
                                    }
                                    Text {
                                        color: root.dimColor
                                        font.pixelSize: 12
                                        text: {
                                            var n = (backend && backend.nowWeather) ? backend.nowWeather : {}
                                            var parts = []
                                            if (n.feelsLike !== undefined && n.feelsLike !== null) parts.push(qsTr("体感 ") + n.feelsLike + "°")
                                            if (n.humidity !== undefined && n.humidity !== null) parts.push(qsTr("湿度 ") + n.humidity + "%")
                                            if (n.wind) parts.push(n.wind)
                                            if (n.aqi !== undefined && n.aqi !== null) parts.push(qsTr("空气 ") + (n.aqiCategory || "") + " " + n.aqi)
                                            return parts.join(" · ")
                                        }
                                    }
                                }
                            }

                            Rectangle { width: parent.width; height: 1; color: Theme.isDark() ? Qt.alpha("#fff", 0.08) : Qt.alpha("#000", 0.06) }

                            // 7 日预报表格
                            Row {
                                width: parent.width
                                Text { width: 40; text: qsTr("日期"); color: root.dimColor; font.pixelSize: 12 }
                                Text { width: 86; text: qsTr("天气"); color: root.dimColor; font.pixelSize: 12 }
                                Text { width: 74; text: qsTr("温度"); color: root.dimColor; font.pixelSize: 12 }
                                Text { width: 96; text: qsTr("风"); color: root.dimColor; font.pixelSize: 12 }
                            }
                            Repeater {
                                model: (backend && backend.dailyWeather) ? backend.dailyWeather : []
                                delegate: Row {
                                    width: panelColumn.width - 24
                                    spacing: 0
                                    Text { width: 40; text: modelData.weekday || modelData.date || ""; color: root.textColor; font.pixelSize: 13 }
                                    Text { width: 86; elide: Text.ElideRight; text: (modelData.emoji ? modelData.emoji + " " : "") + (modelData.text || ""); color: root.textColor; font.pixelSize: 13 }
                                    Text {
                                        width: 74
                                        text: (modelData.tempMin !== undefined && modelData.tempMax !== undefined && modelData.tempMin !== null && modelData.tempMax !== null)
                                            ? (modelData.tempMin + "~" + modelData.tempMax + "°") : ""
                                        color: root.textColor; font.pixelSize: 13
                                    }
                                    Text { width: 96; elide: Text.ElideRight; text: modelData.wind || ""; color: root.dimColor; font.pixelSize: 12 }
                                }
                            }
                        }
                    }

                    // ============ 卡片 2：日历 · 黄历 ============
                    Rectangle {
                        width: parent.width
                        radius: 12
                        color: Theme.isDark() ? Qt.alpha("#ffffff", 0.06) : Qt.alpha("#000000", 0.035)
                        Column {
                            width: parent.width - 24
                            anchors.horizontalCenter: parent.horizontalCenter
                            topPadding: 14
                            bottomPadding: 14
                            spacing: 8

                            RowLayout {
                                width: parent.width
                                ToolButton {
                                    icon.name: "ic_fluent_chevron_left_20_regular"
                                    onClicked: {
                                        calMonth -= 1
                                        if (calMonth < 1) { calMonth = 12; calYear -= 1 }
                                        loadCalendar()
                                    }
                                }
                                Title {
                                    px: 18
                                    Layout.fillWidth: true
                                    horizontalAlignment: Text.AlignHCenter
                                    text: calYear + qsTr(" 年 ") + calMonth + qsTr(" 月")
                                }
                                ToolButton {
                                    icon.name: "ic_fluent_chevron_right_20_regular"
                                    onClicked: {
                                        calMonth += 1
                                        if (calMonth > 12) { calMonth = 1; calYear += 1 }
                                        loadCalendar()
                                    }
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
                                    model: leadingBlanks + calDays.length
                                    delegate: Rectangle {
                                        width: 38
                                        height: 38
                                        radius: 8
                                        color: {
                                            var idx = index - leadingBlanks
                                            if (idx < 0) return "transparent"
                                            var d = calDays[idx]
                                            if (d && d.isToday) return Qt.alpha(root.accentColor, Theme.isDark() ? 0.32 : 0.18)
                                            if (d && (d.festival || d.jieqi)) return Theme.isDark() ? Qt.alpha("#ffffff", 0.06) : Qt.alpha("#000000", 0.05)
                                            return "transparent"
                                        }
                                        Text {
                                            anchors.top: parent.top
                                            anchors.topMargin: 3
                                            anchors.horizontalCenter: parent.horizontalCenter
                                            text: {
                                                var idx = index - leadingBlanks
                                                return idx < 0 ? "" : String(calDays[idx].solarDay)
                                            }
                                            font.pixelSize: 14
                                            color: {
                                                var idx = index - leadingBlanks
                                                if (idx < 0) return root.textColor
                                                return (calDays[idx].weekday === 5 || calDays[idx].weekday === 6) ? "#D28B59" : root.textColor
                                            }
                                        }
                                        Text {
                                            anchors.bottom: parent.bottom
                                            anchors.bottomMargin: 3
                                            anchors.horizontalCenter: parent.horizontalCenter
                                            width: 36
                                            elide: Text.ElideRight
                                            text: {
                                                var idx = index - leadingBlanks
                                                if (idx < 0) return ""
                                                var d = calDays[idx]
                                                return d.festival || d.jieqi || (d.solarDay === 1 ? d.lunarMonth : d.lunarDay)
                                            }
                                            color: (function() {
                                                var idx = index - leadingBlanks
                                                if (idx >= 0 && calDays[idx] && (calDays[idx].festival || calDays[idx].jieqi))
                                                    return root.accentColor
                                                return root.dimColor
                                            })()
                                            font.pixelSize: 9
                                        }
                                    }
                                }
                            }

                            Rectangle { width: parent.width; height: 1; color: Theme.isDark() ? Qt.alpha("#fff", 0.08) : Qt.alpha("#000", 0.06) }

                            // 今日黄历摘要
                            property var al: (backend && backend.almanac) ? backend.almanac : {}
                            Row {
                                width: parent.width
                                spacing: 12
                                Column {
                                    spacing: 2
                                    Text { text: al.lunarFull || qsTr("黄历加载中…"); color: root.textColor; font.pixelSize: 14; font.weight: 700 }
                                    Text { text: [al.ganzhiYear, al.ganzhiDay, al.shengxiao].filter(function (x) { return x }).join(" · "); color: root.dimColor; font.pixelSize: 12 }
                                }
                            }
                            Text {
                                width: parent.width
                                wrapMode: Text.WordWrap
                                text: qsTr("宜 ") + (al.yi || []).join("、")
                                color: root.textColor
                                font.pixelSize: 13
                            }
                            Text {
                                width: parent.width
                                wrapMode: Text.WordWrap
                                text: qsTr("忌 ") + (al.ji || []).join("、")
                                color: root.textColor
                                font.pixelSize: 13
                            }
                        }
                    }

                    // ============ 卡片 3：整周课表（表格） ============
                    Rectangle {
                        width: parent.width
                        radius: 12
                        color: Theme.isDark() ? Qt.alpha("#ffffff", 0.06) : Qt.alpha("#000000", 0.035)
                        Column {
                            width: parent.width - 24
                            anchors.horizontalCenter: parent.horizontalCenter
                            topPadding: 14
                            bottomPadding: 14
                            spacing: 6

                            Text { text: qsTr("整周课表"); color: root.textColor; font.pixelSize: 14; font.weight: 700 }

                            Flickable {
                                width: parent.width
                                height: Math.max(0, scheduleColumn.height)
                                clip: true
                                contentWidth: scheduleColumn.width + 4
                                contentHeight: scheduleColumn.height
                                boundsBehavior: Flickable.StopAtBounds

                                Column {
                                    id: scheduleColumn
                                    spacing: 3

                                    // 表头
                                    Row {
                                        id: scheduleHeader
                                        spacing: 3
                                        Rectangle {
                                            width: 58; height: 24; radius: 6
                                            color: "transparent"
                                            Text { anchors.centerIn: parent; text: qsTr("节次"); color: root.dimColor; font.pixelSize: 11 }
                                        }
                                        Repeater {
                                            model: (backend && backend.weekSchedule && backend.weekSchedule.days) ? backend.weekSchedule.days : []
                                            delegate: Rectangle {
                                                width: 44; height: 24; radius: 6
                                                color: "transparent"
                                                Text { anchors.centerIn: parent; text: modelData.dayName; color: root.dimColor; font.pixelSize: 11 }
                                            }
                                        }
                                    }

                                    // 数据行
                                    Repeater {
                                        id: periodRows
                                        model: (backend && backend.weekSchedule && backend.weekSchedule.periods) ? backend.weekSchedule.periods : []
                                        delegate: Row {
                                            property int rowIndex: index
                                            spacing: 3
                                            Rectangle {
                                                width: 58; height: 34; radius: 6
                                                color: Theme.isDark() ? Qt.alpha("#ffffff", 0.04) : Qt.alpha("#000000", 0.03)
                                                Text {
                                                    anchors.centerIn: parent
                                                    text: modelData.start || ""
                                                    color: root.dimColor
                                                    font.pixelSize: 10
                                                }
                                            }
                                            Repeater {
                                                model: (backend && backend.weekSchedule && backend.weekSchedule.days) ? backend.weekSchedule.days : []
                                                delegate: Rectangle {
                                                    width: 44; height: 34; radius: 6
                                                    property var cell: (modelData && modelData.cells && modelData.cells.length > rowIndex) ? modelData.cells[rowIndex] : null
                                                    color: (cell && cell.color) ? Qt.alpha(cell.color, Theme.isDark() ? 0.35 : 0.22) : "transparent"
                                                    Text {
                                                        anchors.centerIn: parent
                                                        text: cell ? (cell.title || "") : ""
                                                        color: root.textColor
                                                        font.pixelSize: 11
                                                        elide: Text.ElideRight
                                                        width: 40
                                                        horizontalAlignment: Text.AlignHCenter
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // ============ 卡片 4：每日一言 ============
                    Rectangle {
                        width: parent.width
                        radius: 12
                        color: Theme.isDark() ? Qt.alpha("#ffffff", 0.06) : Qt.alpha("#000000", 0.035)
                        Column {
                            width: parent.width - 24
                            anchors.horizontalCenter: parent.horizontalCenter
                            topPadding: 16
                            bottomPadding: 16
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
                                text: (backend && backend.quote && backend.quote.text) ? backend.quote.text : qsTr("正在为你摘一句悄悄话…")
                            }
                            Text {
                                width: parent.width
                                horizontalAlignment: Text.AlignHCenter
                                text: (backend && backend.quote && backend.quote.from) ? ("—— " + backend.quote.from) : ""
                                color: root.dimColor
                                font.pixelSize: 12
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
