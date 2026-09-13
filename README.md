<div align="center">

<img src="icon.png" width="96" alt="更好的一天" />

# 更好的一天 · A Better Day 🌸

<p>把天气、节日、黄历、课程表和每日一言，<br>都装进你桌面的一张可爱小卡片里～</p>

![Stars](https://img.shields.io/github/stars/starfall-miao/better-day?style=for-the-badge&color=pink&label=%E6%98%9F%E6%A0%87)
![License](https://img.shields.io/badge/license-MIT-blue.svg?style=for-the-badge&label=%E8%AE%B8%E5%8F%AF%E8%AF%81)

</div>

## ✨ 它是什么

「更好的一天」是一个给 [Class Widgets 2](https://github.com/RinLit-233-shiroko/Class-Widgets-2) 用的桌面小组件插件。它会安静地待在你的桌面上，用一张小卡片轮换讲给你听今天的一切：

- ☀️ **现在天气** —— 今天的温度和天气现象
- 🌤️ **将来天气** —— 明天会是什么样子
- 🎉 **节日** —— 今天是什么节日 / 最近的节气
- 📜 **黄历** —— 农历、干支、宜忌

小卡片旁边还有一颗小小的 `ⓘ` 按钮，轻轻一点，就会浮出一张**详情卡片**：

| 分区 | 内容 |
| --- | --- |
| 🌦️ 天气 | 当前天气、空气质量、未来 7 天 |
| 📅 日历 · 黄历 | 带农历、节日、节气的月历 + 今日宜忌 |
| 📚 课表 | 整周课程表（表格形式，一目了然） |
| 💌 一言 | 每天一句悄悄话（可以手动换一句） |

## 🛠️ 小卡片可以怎么玩

右键小卡片 →「编辑」，你可以：

- 🎚️ 调整**轮换速度**（默认 10 秒一换，3～120 秒随便调）
- ✅ 勾选 / 取消小卡片要**轮换的内容**（现在天气、将来天气、节日、黄历）

第一次用记得去 **设置 → 插件 → 更好的一天** 里填上你的城市（比如「北京」「上海」「广州」），天气就会乖乖出现啦。天气数据来自**中央气象台**（nmc.cn），**不用申请 API Key**，开箱即用～

## 📦 安装

1. 从 [Releases](https://github.com/starfall-miao/better-day/releases) 下载最新的 `.cwplugin` 文件；
2. 打开 Class Widgets 2 → **设置 → 插件** → 导入插件；
3. 在桌面上添加「更好的一天」小组件；
4. 去插件设置页填上你的城市，完成！🎉

## 🔧 从源码开发

```bash
# 1. 安装 SDK 工具
pip install class-widgets-sdk

# 2. 打包
cw-plugin-pack          # 生成 .cwplugin
cw-plugin-pack --format zip   # 生成 .zip
```

推送 `v*.*.*` 的 tag，GitHub Actions 会自动帮你打包并发布 Release：

```bash
git tag v1.0.0
git push origin v1.0.0
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
