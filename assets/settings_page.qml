import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import ClassWidgets.Plugins

// 插件全局设置页：城市、刷新节奏、预警与状态
PluginPage {
    id: page

    readonly property var cityInfo: (backend && backend.cityMatch) ? backend.cityMatch : ({})
    readonly property var info: backend ? backend.diagnostics() : ({})

    function saveCity() {
        if (!backend) return
        backend.location = locationField.text
        backend.applyLocation()
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        Text {
            typography: Typography.BodyStrong
            text: qsTr("天气")
        }

        SettingCard {
            Layout.fillWidth: true
            icon.name: "ic_fluent_location_20_regular"
            title: qsTr("所在城市")
            description: {
                if (!cityInfo || !cityInfo.message)
                    return qsTr("填写城市名，例如「北京」「上海」「广东深圳」")
                return cityInfo.message
            }

            RowLayout {
                spacing: 8

                TextField {
                    id: locationField
                    width: 220
                    placeholderText: qsTr("例如：北京 / 广东深圳 / Wqsps")
                    onEditingFinished: {
                        if (backend) backend.location = text
                    }
                    Component.onCompleted: text = backend ? backend.location : ""
                }

                Button {
                    highlighted: true
                    text: qsTr("保存并刷新")
                    onClicked: page.saveCity()
                }
            }
        }

        // 城市没匹配上时给个明确的提示
        Text {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            visible: !!cityInfo.query && cityInfo.ok === false
            color: "#D96A32"
            font.pixelSize: 12
            text: qsTr("没有找到这座城市。可以试试「省 + 市」（如「浙江杭州」）或者区县名。")
        }

        // 同名候选（例如「朝阳」可能指不同地方）
        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            visible: !!cityInfo.alternatives && cityInfo.alternatives.length > 0

            Text {
                text: qsTr("其它候选：")
                color: (Colors && Colors.proxy && Colors.proxy.textSecondaryColor)
                    ? Colors.proxy.textSecondaryColor : "#6A6A6A"
                font.pixelSize: 12
            }

            Repeater {
                model: cityInfo.alternatives ? cityInfo.alternatives : []
                delegate: Button {
                    flat: true
                    implicitHeight: 26
                    text: (modelData.province && modelData.province !== modelData.name)
                        ? (modelData.province + "·" + modelData.name) : modelData.name
                    onClicked: {
                        if (!backend) return
                        locationField.text = modelData.province + modelData.name
                        page.saveCity()
                    }
                }
            }
        }

        SettingCard {
            Layout.fillWidth: true
            icon.name: "ic_fluent_timer_20_regular"
            title: qsTr("刷新间隔")
            description: qsTr("天气每隔多少分钟自动更新一次（5 ~ 240 分钟）")

            SpinBox {
                id: refreshSpin
                from: 5
                to: 240
                stepSize: 5
                editable: true
                onValueChanged: { if (backend) backend.refreshMinutes = refreshSpin.value }
                Component.onCompleted: refreshSpin.value = backend ? backend.refreshMinutes : 15
            }
        }

        SettingCard {
            Layout.fillWidth: true
            icon.name: "ic_fluent_arrow_sync_20_regular"
            title: qsTr("自动刷新")
            description: qsTr("关掉之后只在手动刷新或换城市时更新天气")

            Switch {
                checked: backend ? backend.autoRefresh : true
                onCheckedChanged: { if (backend) backend.autoRefresh = checked }
            }
        }

        SettingCard {
            Layout.fillWidth: true
            icon.name: "ic_fluent_alert_20_regular"
            title: qsTr("气象预警")
            description: qsTr("有预警时在小卡片和详情卡上提醒（中央气象台数据）")

            Switch {
                checked: backend ? backend.showWarning : true
                onCheckedChanged: { if (backend) backend.showWarning = checked }
            }
        }

        SettingCard {
            Layout.fillWidth: true
            icon.name: "ic_fluent_arrow_clockwise_20_regular"
            title: qsTr("立即刷新")
            description: qsTr("天气、课表、黄历、一言一起重新拉一遍")

            Button {
                text: qsTr("刷新全部")
                onClicked: { if (backend) backend.refreshAll() }
            }
        }

        SettingCard {
            Layout.fillWidth: true
            icon.name: "ic_fluent_info_20_regular"
            title: qsTr("当前状态")
            description: {
                if (!backend) return qsTr("插件未就绪")
                var parts = [backend.statusText || qsTr("等待刷新")]
                if (backend.lastUpdated) parts.push(qsTr("更新于 ") + backend.lastUpdated)
                return parts.join(" · ")
            }
        }

        Text {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            typography: Typography.Caption
            opacity: 0.6
            text: {
                var count = info && info.cityCount ? info.cityCount : 0
                var version = (backend && backend.version) ? (" v" + backend.version) : ""
                return qsTr("天气来自中央气象台 nmc.cn（无需 API Key），一言来自 hitokoto，黄历由 lunar-python 本地计算。")
                    + qsTr("内置 %1 座城市。").arg(count)
                    + qsTr("更好的一天") + version
            }
        }
    }
}
