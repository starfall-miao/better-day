import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import ClassWidgets.Theme

// 「更好的一天」详情卡片：一张独立浮动窗口，样式与小卡片一致。
Window {
    id: root
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
    color: "transparent"
    width: 380
    height: 520
    visible: false

    property var backend: null

    // 主题文字颜色（与小卡片同源）
    readonly property color textColor: Colors.proxy.textColor
    readonly property color dimColor: Colors.proxy.textSecondaryColor
    readonly property color accentColor: Colors.proxy.primaryColor

    function openNear(x, y) {
        root.x = Math.round(x)
        root.y = Math.round(y)
        root.visible = true
        root.requestActivate()
    }
    function close() { root.visible = false }

    // ---------------- 日历状态 ----------------
    property int calYear: 0
    property int calMonth: 0
    property var calDays: []
    property int leadingBlanks: calDays.length > 0 ? calDays[0].weekday : 0

    function loadCalendar() {
        if (backend && calYear > 0 && calMonth > 0)
            calDays = backend.calendar(calYear, calMonth)
    }

    Component.onCompleted: {
        var now = new Date()
        calYear = now.getFullYear()
        calMonth = now.getMonth() + 1
        loadCalendar()
    }

    // ---------------- 与小卡片一致的卡片外壳 ----------------
    Widget {
        width: root.width
        height: root.height
        implicitWidth: root.width
        implicitHeight: root.height

        ColumnLayout {
            anchors.fill: parent
            spacing: 8

            // 头部
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Title {
                    px: 18
                    text: qsTr("更好的一天")
                }
                Item { Layout.fillWidth: true }
                ToolButton {
                    icon.name: "ic_fluent_dismiss_20_regular"
                    implicitWidth: 26
                    implicitHeight: 26
                    onClicked: root.close()
                }
            }

            TabBar {
                id: bar
                Layout.fillWidth: true
                background: Rectangle {
                    radius: 8
                    color: Theme.isDark() ? Qt.alpha("#ffffff", 0.06) : Qt.alpha("#000000", 0.05)
                }
                TabButton { text: qsTr("天气") }
                TabButton { text: qsTr("日历") }
                TabButton { text: qsTr("黄历") }
                TabButton { text: qsTr("课表") }
                TabButton { text: qsTr("一言") }
            }

            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: bar.currentIndex

                // ---------------- 0. 天气 ----------------
                Flickable {
                    clip: true
                    contentWidth: width
                    contentHeight: weatherColumn.height
                    boundsBehavior: Flickable.StopAtBounds

                    Column {
                        id: weatherColumn
                        width: parent.width
                        spacing: 10

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
                                        : qsTr("加载中…")
                                }
                                Subtitle {
                                    text: {
                                        var n = (backend && backend.nowWeather) ? backend.nowWeather : {}
                                        var loc = (backend && backend.locationName) ? backend.locationName : ""
                                        var parts = []
                                        if (loc) parts.push(loc)
                                        if (n.feelsLike !== undefined && n.feelsLike !== null) parts.push(qsTr("体感 ") + n.feelsLike + "°")
                                        return parts.join(" · ")
                                    }
                                }
                                Subtitle {
                                    text: {
                                        var n = (backend && backend.nowWeather) ? backend.nowWeather : {}
                                        var parts = []
                                        if (n.humidity !== undefined && n.humidity !== null) parts.push(qsTr("湿度 ") + n.humidity + "%")
                                        if (n.wind) parts.push(n.wind)
                                        return parts.join(" · ")
                                    }
                                }
                                Subtitle {
                                    visible: (backend && backend.nowWeather.aqi !== undefined && backend.nowWeather.aqi !== null)
                                    text: {
                                        var n = (backend && backend.nowWeather) ? backend.nowWeather : {}
                                        return qsTr("空气 ") + (n.aqiCategory || "") + " (AQI " + n.aqi + ")"
                                    }
                                }
                            }
                        }

                        Text {
                            width: parent.width
                            text: qsTr("24 小时预报")
                            color: root.dimColor
                            font.pixelSize: 12
                        }
                        ListView {
                            width: parent.width
                            height: 82
                            orientation: ListView.Horizontal
                            clip: true
                            spacing: 8
                            model: (backend && backend.hourlyWeather) ? backend.hourlyWeather : []
                            delegate: Column {
                                width: 42
                                spacing: 2
                                Text {
                                    width: 42
                                    horizontalAlignment: Text.AlignHCenter
                                    text: modelData.emoji || ""
                                    font.pixelSize: 16
                                }
                                Text {
                                    width: 42
                                    horizontalAlignment: Text.AlignHCenter
                                    text: (modelData.temp !== undefined && modelData.temp !== null) ? modelData.temp + "°" : ""
                                    color: root.textColor
                                    font.pixelSize: 12
                                }
                                Text {
                                    width: 42
                                    horizontalAlignment: Text.AlignHCenter
                                    text: modelData.hour || ""
                                    color: root.dimColor
                                    font.pixelSize: 10
                                }
                            }
                        }

                        Text {
                            width: parent.width
                            text: qsTr("未来 7 天")
                            color: root.dimColor
                            font.pixelSize: 12
                        }
                        Repeater {
                            model: (backend && backend.dailyWeather) ? backend.dailyWeather : []
                            delegate: Row {
                                width: weatherColumn.width
                                spacing: 8
                                Text { text: modelData.emoji || ""; font.pixelSize: 16 }
                                Text {
                                    width: 40
                                    text: modelData.weekday || modelData.date || ""
                                    color: root.textColor
                                    font.pixelSize: 13
                                }
                                Text {
                                    width: 88
                                    elide: Text.ElideRight
                                    text: modelData.text || ""
                                    color: root.dimColor
                                    font.pixelSize: 13
                                }
                                Text {
                                    text: (modelData.tempMin !== undefined && modelData.tempMax !== undefined && modelData.tempMin !== null && modelData.tempMax !== null)
                                        ? (modelData.tempMin + "~" + modelData.tempMax + "°") : ""
                                    color: root.textColor
                                    font.pixelSize: 13
                                }
                            }
                        }
                    }
                }

                // ---------------- 1. 日历 ----------------
                Item {
                    RowLayout {
                        id: monthNav
                        anchors.top: parent.top
                        anchors.left: parent.left
                        anchors.right: parent.right
                        ToolButton {
                            icon.name: "ic_fluent_chevron_left_20_regular"
                            onClicked: {
                                calMonth -= 1
                                if (calMonth < 1) { calMonth = 12; calYear -= 1 }
                                loadCalendar()
                            }
                        }
                        Title {
                            px: 20
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

                    Row {
                        id: weekHeader
                        anchors.top: monthNav.bottom
                        anchors.topMargin: 6
                        anchors.horizontalCenter: parent.horizontalCenter
                        spacing: 2
                        Repeater {
                            model: [qsTr("一"), qsTr("二"), qsTr("三"), qsTr("四"), qsTr("五"), qsTr("六"), qsTr("日")]
                            delegate: Text {
                                width: 36
                                horizontalAlignment: Text.AlignHCenter
                                text: modelData
                                color: root.dimColor
                                font.pixelSize: 12
                            }
                        }
                    }

                    Grid {
                        anchors.top: weekHeader.bottom
                        anchors.topMargin: 2
                        anchors.horizontalCenter: parent.horizontalCenter
                        columns: 7
                        spacing: 2
                        Repeater {
                            model: leadingBlanks + calDays.length
                            delegate: Rectangle {
                                width: 36
                                height: 36
                                radius: 8
                                color: {
                                    var idx = index - leadingBlanks
                                    if (idx < 0) return "transparent"
                                    var d = calDays[idx]
                                    if (d && d.isToday) return Theme.isDark() ? Qt.alpha("#5CDCFF", 0.35) : Qt.alpha("#4099b2", 0.25)
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
                                    text: {
                                        var idx = index - leadingBlanks
                                        if (idx < 0) return ""
                                        var d = calDays[idx]
                                        return d.festival || d.jieqi || (d.solarDay === 1 ? d.lunarMonth : d.lunarDay)
                                    }
                                    color: root.dimColor
                                    font.pixelSize: 9
                                }
                            }
                        }
                    }
                }

                // ---------------- 2. 黄历 ----------------
                Flickable {
                    clip: true
                    contentWidth: width
                    contentHeight: almanacColumn.height
                    boundsBehavior: Flickable.StopAtBounds

                    Column {
                        id: almanacColumn
                        width: parent.width
                        spacing: 9

                        property var al: (backend && backend.almanac) ? backend.almanac : {}

                        Title {
                            px: 24
                            text: almanacColumn.al.lunarFull || qsTr("黄历加载中…")
                        }
                        Subtitle {
                            text: [almanacColumn.al.ganzhiYear, almanacColumn.al.ganzhiDay, almanacColumn.al.shengxiao]
                                .filter(function (x) { return x }).join(" · ")
                        }
                        Subtitle {
                            text: almanacColumn.al.chong ? qsTr("冲 ") + almanacColumn.al.chong : ""
                        }
                        Rectangle {
                            width: parent.width
                            height: 1
                            color: Theme.isDark() ? Qt.alpha("#ffffff", 0.12) : Qt.alpha("#000000", 0.08)
                        }
                        Text {
                            width: parent.width
                            wrapMode: Text.WordWrap
                            text: qsTr("宜") + "  " + (almanacColumn.al.yi || []).join("、")
                            color: root.textColor
                            font.pixelSize: 14
                        }
                        Text {
                            width: parent.width
                            wrapMode: Text.WordWrap
                            text: qsTr("忌") + "  " + (almanacColumn.al.ji || []).join("、")
                            color: root.textColor
                            font.pixelSize: 14
                        }
                        Text {
                            width: parent.width
                            wrapMode: Text.WordWrap
                            visible: (almanacColumn.al.festivals && almanacColumn.al.festivals.length > 0) || almanacColumn.al.jieqi
                            text: qsTr("节日") + "  " + ((almanacColumn.al.festivals || []).concat(almanacColumn.al.jieqi ? [almanacColumn.al.jieqi] : []).join("、"))
                            color: root.textColor
                            font.pixelSize: 14
                        }
                        Text {
                            width: parent.width
                            wrapMode: Text.WordWrap
                            visible: almanacColumn.al.nextJieQi ? true : false
                            text: almanacColumn.al.nextJieQi
                                ? (qsTr("下一个节气") + "  " + almanacColumn.al.nextJieQi
                                   + (almanacColumn.al.daysToNextJieQi !== null && almanacColumn.al.daysToNextJieQi !== undefined
                                      ? qsTr("（还有 ") + almanacColumn.al.daysToNextJieQi + qsTr(" 天）") : ""))
                                : ""
                            color: root.dimColor
                            font.pixelSize: 12
                        }
                    }
                }

                // ---------------- 3. 课表 ----------------
                Flickable {
                    clip: true
                    contentWidth: width
                    contentHeight: scheduleColumn.height
                    boundsBehavior: Flickable.StopAtBounds

                    Column {
                        id: scheduleColumn
                        width: parent.width
                        spacing: 10

                        Repeater {
                            model: (backend && backend.weekSchedule) ? backend.weekSchedule : []
                            delegate: Column {
                                width: scheduleColumn.width
                                spacing: 4

                                Row {
                                    width: parent.width
                                    spacing: 8
                                    Rectangle {
                                        width: 4
                                        height: 16
                                        radius: 2
                                        color: (modelData.entries && modelData.entries.length > 0)
                                            ? (modelData.entries[0].color || "#46CEA3")
                                            : Qt.alpha("#ffffff", 0.2)
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                    Text {
                                        text: modelData.dayName || ""
                                        color: root.textColor
                                        font.pixelSize: 14
                                        font.weight: 700
                                    }
                                    Text {
                                        text: (modelData.entries && modelData.entries.length > 0)
                                            ? (modelData.entries.length + qsTr(" 节")) : qsTr("无课")
                                        color: root.dimColor
                                        font.pixelSize: 12
                                    }
                                }

                                Repeater {
                                    model: modelData.entries || []
                                    delegate: Row {
                                        width: scheduleColumn.width
                                        leftPadding: 12
                                        spacing: 8
                                        Text {
                                            width: 82
                                            text: (modelData.startTime || "") + (modelData.endTime ? "-" + modelData.endTime : "")
                                            color: root.dimColor
                                            font.pixelSize: 11
                                        }
                                        Text {
                                            width: 120
                                            elide: Text.ElideRight
                                            text: modelData.title || qsTr("未命名")
                                            color: root.textColor
                                            font.pixelSize: 12
                                        }
                                        Text {
                                            text: modelData.location || ""
                                            color: root.dimColor
                                            font.pixelSize: 11
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // ---------------- 4. 一言 ----------------
                Item {
                    Column {
                        anchors.centerIn: parent
                        width: parent.width - 24
                        spacing: 12

                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: qsTr("“")
                            font.pixelSize: 30
                            color: root.accentColor
                        }
                        Title {
                            px: 20
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
                            font.pixelSize: 13
                        }
                        ToolButton {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: qsTr("换一句")
                            icon.name: "ic_fluent_arrow_sync_20_regular"
                            onClicked: { if (backend) backend.refreshQuote() }
                        }
                    }
                }
            }
        }
    }
}
