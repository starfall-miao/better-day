import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import ClassWidgets.Plugins

// 插件全局设置页：所在城市 + 刷新
PluginPage {

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
            description: qsTr("填写城市名，例如「北京」「上海」「广州」")

            TextField {
                id: locationField
                width: 240
                placeholderText: qsTr("例如：北京")
                onEditingFinished: {
                    if (backend)
                        backend.location = locationField.text
                }
                Component.onCompleted: locationField.text = backend ? backend.location : ""
            }
        }

        SettingCard {
            Layout.fillWidth: true
            icon.name: "ic_fluent_arrow_sync_20_regular"
            title: qsTr("刷新")
            description: qsTr("保存城市并立即更新天气")

            Button {
                highlighted: true
                text: qsTr("保存并刷新")
                onClicked: {
                    if (backend) {
                        backend.location = locationField.text
                        backend.refreshWeather()
                    }
                }
            }
        }

        SettingCard {
            Layout.fillWidth: true
            icon.name: "ic_fluent_info_20_regular"
            title: qsTr("当前状态")
            description: backend ? (backend.statusText || qsTr("等待刷新")) : qsTr("插件未就绪")
        }

        Text {
            typography: Typography.Caption
            opacity: 0.6
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            text: qsTr("天气数据来自 Open-Meteo（无需 API Key），每日一言来自 hitokoto，黄历由 lunar-python 本地计算。数据会定时自动刷新。")
        }
    }
}
