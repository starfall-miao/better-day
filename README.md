<div align="center">

<img src="icon.png" width="96" alt="更好的一天" />

# 更好的一天 · A Better Day 🌸

<p>把天气、节日、黄历、课程表和每日一言，<br>都装进你桌面的一张可爱小卡片里～</p>

![Stars](https://img.shields.io/github/stars/starfall-miao/better-day?style=for-the-badge&color=pink&label=%E6%98%9F%E6%A0%87)
![License](https://img.shields.io/badge/license-MIT-blue.svg?style=for-the-badge&label=%E8%AE%B8%E5%8F%AF%E8%AF%81)
![Version](https://img.shields.io/badge/version-1.1.0-blue.svg?style=for-the-badge&label=%E7%89%88%E6%9C%AC)

</div>

## ✨ 它是什么

「更好的一天」是一个给 [Class Widgets 2](https://github.com/RinLit-233-shiroko/Class-Widgets-2) 用的桌面小组件插件。它会安静地待在你的桌面上，用一张小卡片轮换讲给你听今天的一切：

- ☀️ **现在天气** —— 今天的温度和天气现象（有气象预警时会标一个小 🔺）
- 🌤️ **将来天气** —— 明天会是什么样子
- 🎉 **节日** —— 今天是什么节日，没有节日就告诉你最近的那个
- 📜 **黄历** —— 农历、干支、宜忌
- 📚 **课程** —— 现在正在上什么课 / 下一节是什么（可选，默认关闭）

鼠标停在卡片上，轮换会暂停，方便你把这一页看完。小卡片旁边还有一颗小小的 `ⓘ` 按钮，轻轻一点，就会浮出一张**详情卡片**：

| 分区 | 内容 |
| --- | --- |
| 🌦️ 天气 | 当前天气、体感、湿度、风、空气质量、日出日落、气象预警、**过去 24 小时温度走势**、未来 7 天 |
| 📅 日历 · 黄历 | 带农历、节日、节气、法定节假日的月历 + 今日宜忌冲煞 + **最近的节日倒计时** |
| 📚 课表 | 整周课程表（表格形式，标出今天，悬停看老师/教室） |
| 💌 一言 | 每天一句悄悄话（可以手动换一句） |

详情卡按 `Esc` 或点右上角 ✕ 关闭，也可以直接拖着走。

## 🛠️ 小卡片可以怎么玩

右键小卡片 →「编辑」，你可以：

- 🎚️ 调整**轮换速度**（默认 10 秒一换，3～120 秒随便调）
- ✅ 勾选 / 取消小卡片要**轮换的内容**（现在天气、将来天气、节日、黄历、课程）

## ⚙️ 插件设置

第一次用记得去 **设置 → 插件 → 更好的一天** 里填上你的城市（比如「北京」「广东深圳」「朝阳区」都能认），天气就会乖乖出现啦。

| 设置项 | 说明 |
| --- | --- |
| 所在城市 | 支持「北京」「北京市」「广东深圳」「海淀区」甚至站点代码 `Wqsps`；写错会告诉你没找到，同名地点会给出候选 |
| 刷新间隔 | 天气自动刷新间隔，5～240 分钟（默认 15 分钟） |
| 自动刷新 | 关掉之后就只在手动刷新 / 换城市时更新 |
| 气象预警 | 是否在小卡片和详情卡上显示中央气象台的预警 |
| 立即刷新 | 天气、课表、黄历、一言一起重新拉一遍 |

另外，插件会在**跨天那一刻**自动换上新一天的黄历、课表周次和一言，不用整晚开着也没关系～

天气数据来自**中央气象台**（nmc.cn），**不用申请 API Key**，开箱即用；课表信息直接读 Class Widgets 里当前使用的那份课表（单双周 / 指定周 / 调课都会照做）。

## 📦 安装

1. 从 [Releases](https://github.com/starfall-miao/better-day/releases) 下载最新的 `.cwplugin` 文件；
2. 打开 Class Widgets 2 → **设置 → 插件** → 导入插件；
3. 在桌面上添加「更好的一天」小组件；
4. 去插件设置页填上你的城市，完成！🎉

## 🔧 从源码开发

```bash
# 1. 安装 SDK 工具
pip install class-widgets-sdk

# 2. 打包（依赖会被装进插件的 libs/ 目录）
cw-plugin-pack                # 生成 .cwplugin
cw-plugin-pack --format zip   # 生成 .zip
```

### 跑测试

服务层是纯逻辑、不依赖 Qt，插件主体的冒烟测试用假的 SDK 把插件真跑起来（网络请求全部打桩）：

```bash
pip install lunar-python
python -m unittest discover -s tests -v        # 只跑服务层测试
pip install PySide6-Essentials
python -m unittest discover -s tests -v        # 顺带跑插件冒烟测试
```

推送 `v*.*.*` 的 tag，GitHub Actions 会自动帮你打包并发布 Release：

```bash
git tag v1.1.0
git push origin v1.1.0
```

> 想要自动发布到插件广场？在仓库 Settings → Secrets 里添加 `CWPT_TOKEN`（从[插件广场控制台](https://plaza.cw.rinlit.cn/console)获取）就好啦。

## 💐 致谢

数据与能力来自这些可爱的小伙伴：

- ☁️ 天气 —— [中央气象台 nmc.cn](https://www.nmc.cn)（免费、无需 Key）
- 💬 每日一言 —— [Hitokoto](https://hitokoto.cn)
- 📜 农历黄历 —— [lunar-python](https://github.com/6tail/lunar-python)
- 🧩 平台 —— [Class Widgets 2](https://github.com/RinLit-233-shiroko/Class-Widgets-2) & [Class Widgets SDK](https://github.com/Class-Widgets/class-widgets-sdk)

## 📝 许可

MIT License，详见 [LICENSE](LICENSE)。

---

<p align="center">愿你每天，都是更好的一天 🌈</p>
