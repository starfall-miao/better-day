import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import ClassWidgets.Plugins

// 小卡片实例设置：轮换速度 + 轮换内容
SettingsLayout {

    SettingCard {
        Layout.fillWidth: true
        icon.name: "ic_fluent_timer_20_regular"
        title: qsTr("轮换速度")
        description: qsTr("小卡片内容每隔多少秒切换一次")

        SpinBox {
            id: rotationSpin
            from: 3
            to: 120
            stepSize: 1
            editable: true
            onValueChanged: settings.rotation_seconds = rotationSpin.value
            Component.onCompleted: rotationSpin.value = settings.rotation_seconds || 10
        }
    }

    SettingCard {
        Layout.fillWidth: true
        icon.name: "ic_fluent_weather_sunny_20_regular"
        title: qsTr("现在天气")
        description: qsTr("显示当前温度与天气现象")

        Switch {
            onCheckedChanged: settings.show_now = checked
            Component.onCompleted: checked = settings.show_now !== false
        }
    }

    SettingCard {
        Layout.fillWidth: true
        icon.name: "ic_fluent_weather_partly_cloudy_day_20_regular"
        title: qsTr("将来天气")
        description: qsTr("显示明日天气")

        Switch {
            onCheckedChanged: settings.show_forecast = checked
            Component.onCompleted: checked = settings.show_forecast !== false
        }
    }

    SettingCard {
        Layout.fillWidth: true
        icon.name: "ic_fluent_calendar_20_regular"
        title: qsTr("节日")
        description: qsTr("显示今日节日或最近的节气")

        Switch {
            onCheckedChanged: settings.show_festival = checked
            Component.onCompleted: checked = settings.show_festival !== false
        }
    }

    SettingCard {
        Layout.fillWidth: true
        icon.name: "ic_fluent_book_20_regular"
        title: qsTr("黄历")
        description: qsTr("显示农历、宜忌")

        Switch {
            onCheckedChanged: settings.show_almanac = checked
            Component.onCompleted: checked = settings.show_almanac !== false
        }
    }
}
