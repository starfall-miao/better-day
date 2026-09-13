import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import ClassWidgets.Theme

// 「更好的一天」小卡片：轮换展示内容（文字超长时慢速滚动）+ 详情按钮
Widget {
    id: root

    // ---------------- 轮换配置 ----------------
    property int currentIndex: 0

    property var items: {
        var arr = []
        if (!settings || settings.show_now !== false) arr.push("now")
        if (!settings || settings.show_forecast !== false) arr.push("forecast")
        if (!settings || settings.show_festival !== false) arr.push("festival")
        if (!settings || settings.show_almanac !== false) arr.push("almanac")
        if (arr.length === 0) arr = ["now"]
        return arr
    }

    property string currentKey: items.length > 0 ? items[currentIndex % items.length] : "now"

    property int viewIndex: {
        switch (currentKey) {
        case "now": return 0
        case "forecast": return 1
        case "festival": return 2
        case "almanac": return 3
        default: return 0
        }
    }

    Timer {
        id: rotateTimer
        interval: (settings && settings.rotation_seconds ? settings.rotation_seconds : 10) * 1000
        running: true
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
            Layout.maximumWidth: 178

            // ---- 0. 现在天气 ----
            RowLayout {
                spacing: 6
                Text {
                    text: (backend && backend.nowWeather.emoji) ? backend.nowWeather.emoji : "🌡️"
                    font.pixelSize: 18
                }
                ColumnLayout {
                    spacing: 0
                    MarqueeTitle {
                        Layout.maximumWidth: 138
                        maximumWidth: 138
                        font.pixelSize: 15
                        speed: 40
                        text: (backend && backend.nowWeather.temp !== undefined && backend.nowWeather.temp !== null)
                            ? (backend.nowWeather.temp + "° " + (backend.nowWeather.text || ""))
                            : ((backend && backend.statusText) ? backend.statusText : qsTr("天气加载中…"))
                    }
                    Text {
                        Layout.maximumWidth: 138
                        width: 138
                        elide: Text.ElideRight
                        maximumLineCount: 1
                        font.pixelSize: 12
                        opacity: 0.6
                        text: (backend && backend.locationName) ? backend.locationName : qsTr("现在天气")
                    }
                }
            }

            // ---- 1. 将来天气 ----
            RowLayout {
                spacing: 6
                Text {
                    text: (backend && backend.dailyWeather && backend.dailyWeather.length > 1 && backend.dailyWeather[1].emoji)
                        ? backend.dailyWeather[1].emoji : "🌤️"
                    font.pixelSize: 18
                }
                ColumnLayout {
                    spacing: 0
                    MarqueeTitle {
                        Layout.maximumWidth: 138
                        maximumWidth: 138
                        font.pixelSize: 15
                        speed: 40
                        text: (backend && backend.dailyWeather && backend.dailyWeather.length > 1)
                            ? (qsTr("明天 ") + (backend.dailyWeather[1].text || ""))
                            : qsTr("天气加载中…")
                    }
                    Text {
                        Layout.maximumWidth: 138
                        width: 138
                        elide: Text.ElideRight
                        maximumLineCount: 1
                        font.pixelSize: 12
                        opacity: 0.6
                        text: (backend && backend.dailyWeather && backend.dailyWeather.length > 1
                               && backend.dailyWeather[1].tempMin !== null && backend.dailyWeather[1].tempMin !== undefined)
                            ? (backend.dailyWeather[1].tempMin + "~" + backend.dailyWeather[1].tempMax + "°")
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
                    spacing: 0
                    MarqueeTitle {
                        Layout.maximumWidth: 138
                        maximumWidth: 138
                        font.pixelSize: 15
                        speed: 40
                        text: {
                            var al = (backend && backend.almanac) ? backend.almanac : {}
                            var names = (al.festivals || []).slice()
                            if (al.legalHoliday) names.push(al.legalHoliday)
                            if (al.jieqi) names.push(al.jieqi)
                            if (names.length > 0) return names[0]
                            if (al.nextJieQi) return al.nextJieQi
                            return qsTr("今天没有节日")
                        }
                    }
                    Text {
                        Layout.maximumWidth: 138
                        width: 138
                        elide: Text.ElideRight
                        maximumLineCount: 1
                        font.pixelSize: 12
                        opacity: 0.6
                        text: {
                            var al = (backend && backend.almanac) ? backend.almanac : {}
                            if (al.lunarMonth && al.lunarDay) return al.lunarMonth + "月" + al.lunarDay
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
                    spacing: 0
                    MarqueeTitle {
                        Layout.maximumWidth: 138
                        maximumWidth: 138
                        font.pixelSize: 15
                        speed: 40
                        text: {
                            var al = (backend && backend.almanac) ? backend.almanac : {}
                            if (al.lunarMonth && al.lunarDay) return al.lunarMonth + "月" + al.lunarDay
                            return qsTr("黄历加载中…")
                        }
                    }
                    Text {
                        Layout.maximumWidth: 138
                        width: 138
                        elide: Text.ElideRight
                        maximumLineCount: 1
                        font.pixelSize: 12
                        opacity: 0.6
                        text: {
                            var al = (backend && backend.almanac) ? backend.almanac : {}
                            if (al.yi && al.yi.length > 0) return qsTr("宜 ") + al.yi.slice(0, 3).join("·")
                            if (al.ganzhiDay) return al.ganzhiDay
                            return qsTr("今日黄历")
                        }
                    }
                }
            }
        }

        ToolButton {
            id: infoButton
            icon.name: "ic_fluent_info_20_regular"
            implicitWidth: 22
            implicitHeight: 22
            onClicked: toggleDetail()
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
