import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import ClassWidgets.Theme

// 「更好的一天」小卡片：轮换展示内容 + 详情按钮
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

    // ---------------- 主体布局 ----------------
    RowLayout {
        anchors.centerIn: parent
        spacing: 10

        StackLayout {
            id: contentStack
            currentIndex: root.viewIndex

            // ---- 0. 现在天气 ----
            RowLayout {
                spacing: 8
                Text {
                    text: (backend && backend.nowWeather.emoji) ? backend.nowWeather.emoji : "🌡️"
                    font.pixelSize: 26
                }
                ColumnLayout {
                    spacing: 0
                    Title {
                        text: (backend && backend.nowWeather.temp !== undefined && backend.nowWeather.temp !== null)
                            ? (backend.nowWeather.temp + "° " + (backend.nowWeather.text || ""))
                            : qsTr("天气加载中…")
                        maximumLineCount: 1
                    }
                    Subtitle {
                        text: (backend && backend.locationName) ? backend.locationName : qsTr("现在天气")
                    }
                }
            }

            // ---- 1. 将来天气 ----
            RowLayout {
                spacing: 8
                Text {
                    text: (backend && backend.dailyWeather && backend.dailyWeather.length > 1 && backend.dailyWeather[1].emoji)
                        ? backend.dailyWeather[1].emoji : "🌤️"
                    font.pixelSize: 26
                }
                ColumnLayout {
                    spacing: 0
                    Title {
                        text: (backend && backend.dailyWeather && backend.dailyWeather.length > 1)
                            ? (qsTr("明天 ") + (backend.dailyWeather[1].text || "") + " "
                               + (backend.dailyWeather[1].tempMin ?? "") + "~" + (backend.dailyWeather[1].tempMax ?? "") + "°")
                            : qsTr("天气加载中…")
                        maximumLineCount: 1
                    }
                    Subtitle {
                        text: qsTr("明日天气")
                    }
                }
            }

            // ---- 2. 节日 ----
            RowLayout {
                spacing: 8
                Text {
                    text: "🎉"
                    font.pixelSize: 26
                }
                ColumnLayout {
                    spacing: 0
                    Title {
                        text: {
                            var al = (backend && backend.almanac) ? backend.almanac : {}
                            var names = (al.festivals || []).slice()
                            if (al.legalHoliday) names.push(al.legalHoliday)
                            if (al.jieqi) names.push(al.jieqi)
                            if (names.length > 0) return names[0]
                            if (al.nextJieQi) return al.nextJieQi
                            return qsTr("今天没有节日")
                        }
                        maximumLineCount: 1
                    }
                    Subtitle {
                        text: {
                            var al = (backend && backend.almanac) ? backend.almanac : {}
                            if (al.lunarFull) return al.lunarFull
                            if (al.nextJieQi && (al.daysToNextJieQi !== null && al.daysToNextJieQi !== undefined))
                                return qsTr("还有 ") + al.daysToNextJieQi + qsTr(" 天")
                            return qsTr("今日节日")
                        }
                    }
                }
            }

            // ---- 3. 黄历 ----
            RowLayout {
                spacing: 8
                Text {
                    text: "📜"
                    font.pixelSize: 26
                }
                ColumnLayout {
                    spacing: 0
                    Title {
                        text: (backend && backend.almanac && backend.almanac.lunarFull)
                            ? backend.almanac.lunarFull : qsTr("黄历加载中…")
                        maximumLineCount: 1
                    }
                    Subtitle {
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
            implicitWidth: 28
            implicitHeight: 28
            onClicked: openDetail()
        }
    }

    // ---------------- 详情弹窗 ----------------
    function openDetail() {
        var g = infoButton.mapToItem(null, 0, 0)
        detailPopup.x = g.x + infoButton.width + 8
        detailPopup.y = g.y + infoButton.height / 2 - detailPopup.height / 2
        detailPopup.open()
    }

    Popup {
        id: detailPopup
        modal: false
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        width: 380
        height: 520
        padding: 14

        contentItem: DetailCard {
            backend: root.backend
        }
    }
}
