import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import ClassWidgets.Theme

// 「更好的一天」小卡片：轮换展示天气 / 节日 / 黄历 / 课程，右侧 ⓘ 打开详情卡
Widget {
    id: root

    // ---------------- 数据代理（backend 可能还没就绪） ----------------
    readonly property var nowWeather: (backend && backend.nowWeather) ? backend.nowWeather : ({})
    readonly property var dailyWeather: (backend && backend.dailyWeather) ? backend.dailyWeather : []
    readonly property var almanac: (backend && backend.almanac) ? backend.almanac : ({})
    readonly property var course: (backend && backend.todayCourse) ? backend.todayCourse : ({})
    readonly property var festivals: (backend && backend.upcomingFestivals) ? backend.upcomingFestivals : []
    readonly property var duty: (backend && backend.duty) ? backend.duty : ({})
    readonly property bool hasWeather: !!(backend && backend.hasWeather)
    readonly property bool hasWarning: !!(backend && backend.hasWarning)

    // 灵动通知退让：通知出现时先淡出、再让出位置，通知结束后回来
    readonly property bool retreating: !!(backend && backend.retreatActive)
    property bool retreatHidden: false
    visible: !retreatHidden
    opacity: retreating ? 0 : 1
    Behavior on opacity { NumberAnimation { duration: 150; easing.type: Easing.OutQuad } }

    Timer {
        id: retreatHideTimer
        interval: 140
        onTriggered: root.retreatHidden = root.retreating
    }

    onRetreatingChanged: {
        if (retreating) {
            retreatHideTimer.restart()
        } else {
            retreatHideTimer.stop()
            retreatHidden = false
        }
    }
    // 主题还没准备好时 Colors.proxy 可能还没有值，这里兜底成灰色
    readonly property color dimColor: (Colors && Colors.proxy && Colors.proxy.textSecondaryColor)
        ? Colors.proxy.textSecondaryColor : "#777777"

    // ---------------- 尺寸 ----------------
    // 每页文字宽度 + emoji 列 + ⓘ 按钮 + 左右内边距，值固定下来，
    // 否则 BaseWidget 的 implicitWidth 会跟着内容区一起回缩、把文字挤扁
    readonly property int pageTextWidth: 130
    readonly property int pageWidth: pageTextWidth + 26
    readonly property int infoButtonWidth: 28
    implicitWidth: pageWidth + infoButtonWidth + 6 + 48

    // ---------------- 轮换配置 ----------------
    property int currentIndex: 0

    property var items: {
        var arr = []
        if (!settings || settings.show_now !== false) arr.push("now")
        if (!settings || settings.show_forecast !== false) arr.push("forecast")
        if (!settings || settings.show_festival !== false) arr.push("festival")
        if (!settings || settings.show_almanac !== false) arr.push("almanac")
        if (settings && settings.show_course === true) arr.push("course")
        if ((!settings || settings.show_duty !== false) && backend && backend.duty && backend.duty.enabled)
            arr.push("duty")
        if (arr.length === 0) arr = ["now"]
        return arr
    }

    property string currentKey: items.length > 0 ? items[currentIndex % items.length] : "now"

    property int viewIndex: {
        // 视图顺序固定为 现在 / 将来 / 节日 / 黄历 / 课程
        switch (currentKey) {
        case "now": return 0
        case "forecast": return 1
        case "festival": return 2
        case "almanac": return 3
        case "course": return 4
        case "duty": return 5
        default: return 0
        }
    }

    Timer {
        id: rotateTimer
        interval: (settings && settings.rotation_seconds ? settings.rotation_seconds : 10) * 1000
        // 指针停在卡片上 / 通知退让期间暂停轮换，方便把内容看完
        running: !root.hovered && !root.retreating
        repeat: true
        onTriggered: {
            if (root.items.length > 1)
                root.currentIndex = (root.currentIndex + 1) % root.items.length
        }
    }

    // ---------------- 主体布局（紧凑版，文字超宽自动慢速滚动） ----------------
    RowLayout {
        anchors.centerIn: parent
        spacing: 6

        StackLayout {
            id: contentStack
            currentIndex: root.viewIndex
            Layout.maximumWidth: root.pageWidth

            // ---- 0. 现在天气 ----
            RowLayout {
                spacing: 6
                Text {
                    text: root.nowWeather.emoji ? root.nowWeather.emoji : "🌡️"
                    font.pixelSize: 18
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    MarqueeTitle {
                        Layout.fillWidth: true
                        Layout.maximumWidth: root.pageTextWidth
                        maximumWidth: root.pageTextWidth
                        font.pixelSize: root.miniMode ? 13 : 15
                        speed: 40
                        text: {
                            if (root.hasWeather)
                                return root.nowWeather.temp + "° " + (root.nowWeather.text || "")
                            return (backend && backend.statusText) ? backend.statusText : qsTr("天气加载中…")
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        Layout.maximumWidth: root.pageTextWidth
                        elide: Text.ElideRight
                        maximumLineCount: 1
                        font.pixelSize: root.miniMode ? 10 : 12
                        opacity: 0.6
                        color: root.hasWarning ? "#D96A32" : root.dimColor
                        text: {
                            if (root.hasWarning)
                                return "⚠️ " + (root.nowWeather.warning.title || qsTr("气象预警"))
                            if (backend && backend.locationName)
                                return backend.locationName
                            return qsTr("现在天气")
                        }
                    }
                }
            }

            // ---- 1. 将来天气 ----
            RowLayout {
                spacing: 6
                Text {
                    text: (root.dailyWeather.length > 1 && root.dailyWeather[1].emoji)
                        ? root.dailyWeather[1].emoji : "🌤️"
                    font.pixelSize: 18
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    MarqueeTitle {
                        Layout.fillWidth: true
                        Layout.maximumWidth: root.pageTextWidth
                        maximumWidth: root.pageTextWidth
                        font.pixelSize: root.miniMode ? 13 : 15
                        speed: 40
                        text: (root.dailyWeather.length > 1)
                            ? (qsTr("明天 ") + (root.dailyWeather[1].text || ""))
                            : (root.hasWeather ? qsTr("明天天气还没出来") : qsTr("天气加载中…"))
                    }
                    Text {
                        Layout.fillWidth: true
                        Layout.maximumWidth: root.pageTextWidth
                        elide: Text.ElideRight
                        maximumLineCount: 1
                        font.pixelSize: root.miniMode ? 10 : 12
                        opacity: 0.6
                        color: root.dimColor
                        text: (root.dailyWeather.length > 1
                               && root.dailyWeather[1].tempMin !== null && root.dailyWeather[1].tempMin !== undefined)
                            ? (root.dailyWeather[1].tempMin + "~" + root.dailyWeather[1].tempMax + "°")
                            : qsTr("明日天气")
                    }
                }
            }

            // ---- 2. 节日 ----
            RowLayout {
                spacing: 6
                Text {
                    text: "🎉"
                    font.pixelSize: 18
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    MarqueeTitle {
                        Layout.fillWidth: true
                        Layout.maximumWidth: root.pageTextWidth
                        maximumWidth: root.pageTextWidth
                        font.pixelSize: root.miniMode ? 13 : 15
                        speed: 40
                        text: {
                            var al = root.almanac
                            var names = (al.festivals || []).slice()
                            if (al.legalHoliday) names.push(al.legalHoliday)
                            if (al.jieqi) names.push(al.jieqi)
                            if (names.length > 0) return names[0]
                            var up = root.festivals
                            if (up.length > 0) return up[0].name
                            if (al.nextJieQi) return al.nextJieQi
                            return qsTr("今天没有节日")
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        Layout.maximumWidth: root.pageTextWidth
                        elide: Text.ElideRight
                        maximumLineCount: 1
                        font.pixelSize: root.miniMode ? 10 : 12
                        opacity: 0.6
                        color: root.dimColor
                        text: {
                            var al = root.almanac
                            var names = (al.festivals || []).slice()
                            if (al.legalHoliday) names.push(al.legalHoliday)
                            if (names.length === 0 && al.jieqi) names.push(al.jieqi)
                            var up = root.festivals
                            // 今天有节日就显示农历日期，否则显示最近的节日倒计时
                            if (names.length > 0)
                                return al.lunarMonthDay || qsTr("今日节日")
                            if (up.length > 0)
                                return up[0].name + " · " + (up[0].daysLeft === 1 ? qsTr("明天") : (up[0].daysLeft + qsTr(" 天后")))
                            return qsTr("今日节日")
                        }
                    }
                }
            }

            // ---- 3. 黄历 ----
            RowLayout {
                spacing: 6
                Text {
                    text: "📜"
                    font.pixelSize: 18
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    MarqueeTitle {
                        Layout.fillWidth: true
                        Layout.maximumWidth: root.pageTextWidth
                        maximumWidth: root.pageTextWidth
                        font.pixelSize: root.miniMode ? 13 : 15
                        speed: 40
                        text: root.almanac.lunarMonthDay
                            ? root.almanac.lunarMonthDay
                            : qsTr("黄历加载中…")
                    }
                    Text {
                        Layout.fillWidth: true
                        Layout.maximumWidth: root.pageTextWidth
                        elide: Text.ElideRight
                        maximumLineCount: 1
                        font.pixelSize: root.miniMode ? 10 : 12
                        opacity: 0.6
                        color: root.dimColor
                        text: {
                            var al = root.almanac
                            if (al.yi && al.yi.length > 0) return qsTr("宜 ") + al.yi.slice(0, 3).join("·")
                            if (al.ganzhiDay) return al.ganzhiDay
                            return qsTr("今日黄历")
                        }
                    }
                }
            }

            // ---- 4. 课程（可在小卡片设置里打开） ----
            RowLayout {
                spacing: 6
                Text {
                    text: "📚"
                    font.pixelSize: 18
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    MarqueeTitle {
                        Layout.fillWidth: true
                        Layout.maximumWidth: root.pageTextWidth
                        maximumWidth: root.pageTextWidth
                        font.pixelSize: root.miniMode ? 13 : 15
                        speed: 40
                        text: root.course.title ? root.course.title : qsTr("今天没有课")
                    }
                    Text {
                        Layout.fillWidth: true
                        Layout.maximumWidth: root.pageTextWidth
                        elide: Text.ElideRight
                        maximumLineCount: 1
                        font.pixelSize: root.miniMode ? 10 : 12
                        opacity: 0.6
                        color: root.dimColor
                        text: {
                            var c = root.course
                            if (!c.title) return c.subtitle || qsTr("课表")
                            var time = (c.startTime && c.endTime) ? (c.startTime + "-" + c.endTime) : ""
                            return c.subtitle ? ((time ? time + " · " : "") + c.subtitle) : time
                        }
                    }
                }
            }

            // ---- 5. 值日生 ----
            RowLayout {
                spacing: 6
                Text {
                    text: "🧹"
                    font.pixelSize: 18
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    MarqueeTitle {
                        Layout.fillWidth: true
                        Layout.maximumWidth: root.pageTextWidth
                        maximumWidth: root.pageTextWidth
                        font.pixelSize: root.miniMode ? 13 : 15
                        speed: 40
                        text: root.duty.todayText ? (qsTr("值日 ") + root.duty.todayText) : qsTr("今天没有值日")
                    }
                    Text {
                        Layout.fillWidth: true
                        Layout.maximumWidth: root.pageTextWidth
                        elide: Text.ElideRight
                        maximumLineCount: 1
                        font.pixelSize: root.miniMode ? 10 : 12
                        opacity: 0.6
                        color: root.dimColor
                        text: {
                            var d = root.duty
                            if (!d.enabled) return qsTr("还没配置值日名单")
                            if (d.groupLabel) return d.groupLabel + " · " + qsTr("下次 ") + (d.nextDateShort || "")
                            return d.nextDateShort ? (qsTr("下次 ") + d.nextDateShort) : qsTr("值日生")
                        }
                    }
                }
            }
        }

        ToolButton {
            id: infoButton
            icon.name: "ic_fluent_info_20_regular"
            Layout.preferredWidth: root.infoButtonWidth
            Layout.preferredHeight: root.infoButtonWidth
            Layout.minimumWidth: root.infoButtonWidth
            Layout.maximumWidth: root.infoButtonWidth
            onClicked: toggleDetail()
            ToolTip {
                text: qsTr("查看详情")
                visible: parent.hovered
            }
        }
    }

    // ---------------- 详情（独立浮动窗口，样式与小卡片一致） ----------------
    DetailCard {
        id: detailCard
        backend: root.backend
    }

    function toggleDetail() {
        if (detailCard.visible) {
            detailCard.close()
        } else {
            var w = root.mapToItem(null, 0, 0)
            var win = root.Window.window
            var sx = win ? win.x : 0
            var sy = win ? win.y : 0
            detailCard.openNear(sx + w.x, sy + w.y, root.width, root.height)
        }
    }
}
