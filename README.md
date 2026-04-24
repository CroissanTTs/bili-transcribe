<div align="center">

# 🎬 bilibili-transcribe

**B站视频语音转文字工具 | Batch Bilibili Video Transcriber**

将B站视频的语音内容批量转写为 Markdown 文字稿

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-Web_UI-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![faster-whisper](https://img.shields.io/badge/faster--whisper-CTranslate2-4A90D9?logo=openai&logoColor=white)](https://github.com/SYSTRAN/faster-whisper)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[功能特性](#-功能特性) • [快速开始](#-快速开始) • [使用方法](#-使用方法) • [技术架构](#-技术架构) • [常见问题](#-常见问题)

</div>

---

## ✨ 功能特性

- 🎯 **批量转写** — 一次添加多个视频链接，自动逐个处理
- 🖥️ **Web 可视化** — Streamlit 界面，进度条 + 实时日志 + 结果预览
- 📂 **文件夹选择器** — 原生系统对话框，一键选择输出目录
- 🔄 **断点恢复** — 中断后重新运行自动跳过已完成项
- ☑️ **选择性转写** — 勾选部分视频或全选，灵活控制
- ⏱️ **ETA 预估** — 实时显示已用时间和预计剩余时间
- 🤖 **多模型支持** — base / small / medium / large-v3 按需切换
- 📝 **Markdown 输出** — 带时间戳转录 + 完整纯文本，结构化好
- 🧹 **自动清理** — 转写完成后自动删除临时音频文件

## 📦 快速开始

### 前置要求

- **Python 3.9+**（推荐 3.10）
- **Git**（用于克隆仓库）

### 安装

```bash
# 克隆仓库
git clone https://github.com/CroissanTTs/bili-transcribe.git
cd bilibili-transcribe

# 安装依赖
pip install -r requirements.txt
```

> `imageio-ffmpeg` 会自动提供 ffmpeg 二进制文件，无需单独安装 ffmpeg。

### 启动

```bash
streamlit run app.py
```

浏览器会自动打开 `http://localhost:8501`。

### 首次使用

1. 在左侧栏点击 **📂 浏览文件夹...** 选择输出目录
2. 粘贴B站视频链接，点击 **🔍 解析链接**
3. 勾选要转写的视频，点击 **🚀 开始转写**

首次运行时会自动下载 Whisper 模型（medium ≈ 770MB）。

---

## 📖 使用方法

### 输入视频链接

**方式A：直接粘贴**

在主页面文本框中粘贴B站视频链接，每行一个：
```
https://www.bilibili.com/video/BV1ofobB9Erf
https://www.bilibili.com/video/BV1rndSB7EMM
BV1U5dHBmEEr
```

> 支持完整URL、短链接、纯BV号，混排也可以

**方式B：从文件加载**

在工作目录下创建 `urls.txt`，每行一个链接，然后在「📂 从 urls.txt 加载」标签页中点击加载。

### 指定输出文件夹

有两种方式：

1. **浏览选择（推荐）** — 在左侧栏点击「📂 浏览文件夹...」，弹出系统原生对话框
2. **手动输入** — 在路径输入框中直接粘贴路径

> 💡 如果先粘贴了链接但还没设置目录，页面会自动出现「📁 指定输出文件夹」区域，转写前必须设置。

### 选择要转写的视频

解析后会显示视频列表，支持：
- ☑️ 勾选框 — 选择是否转写
- ✅ 全选 / ⬜ 全不选 / 🔄 反选
- 已完成（done）的视频默认跳过

### 模型选择

| 模型 | 速度 | 准确率 | 体积 | 适用场景 |
|------|------|--------|------|----------|
| `base` | ⚡⚡⚡⚡⚡ | ⭐⭐⭐ | ~140MB | 快速预览 |
| `small` | ⚡⚡⚡⚡ | ⭐⭐⭐⭐ | ~460MB | 日常使用 |
| `medium` ⭐ | ⚡⚡⚡ | ⭐⭐⭐⭐⭐ | ~770MB | **推荐默认** |
| `large-v3` | ⚡⚡ | ⭐⭐⭐⭐⭐+ | ~1.5GB | 最高准确率 |

### 断点恢复

- 自动检测 `video_output/` 中已有文件
- 已完成的视频标记为 `done`，默认跳过
- 中途中断后重新运行，点击「开始转写」即可继续
- 如需重新转写，点击「🔄 重置所有状态」

---

## 📂 文件结构

### 工作目录（用户指定）

```
你的工作目录/
├── urls.txt                      ← URL清单（可选）
├── video_output/                  ← 转写结果（自动创建）
│   ├── BV1ofobB9Erf_量化交易入门.md
│   ├── BV1rndSB7EMM_海龟交易.md
│   └── ...
└── video_temp/                    ← 临时文件（自动创建）
    ├── audio_BV1xxx_P1.m4a       ← 音频缓存（完成后自动删除）
    └── .transcribe_state.json    ← 断点恢复状态文件
```

### 输出文件格式

```markdown
# 视频标题 [medium]

- **BV号**: BV1ofobB9Erf
- **链接**: https://www.bilibili.com/video/BV1ofobB9Erf
- **UP主**: 再加一份小鱼干
- **时长**: 13分2秒
- **转写引擎**: faster-whisper medium (CTranslate2)

---

**[00:00-00:02]** 大家好，我是小鱼

**[00:02-00:05]** 这期视频是要给大家讲一下

---

## 完整文本

大家好，我是小鱼 这期视频是要给大家讲一下 ...
```

### 项目源码结构

```
bilibili-transcribe/
├── app.py                 ← Streamlit 入口
├── requirements.txt       ← Python 依赖
├── LICENSE                ← MIT 许可证
├── README.md              ← 本文件
├── .gitignore
├── core/
│   ├── __init__.py
│   ├── fetcher.py         ← B站API封装（视频信息+音频下载）
│   ├── transcriber.py     ← faster-whisper 转写引擎
│   └── state.py           ← 断点恢复状态管理
└── docs/                  ← 示例输出（可选）
```

---

## 🛠️ 技术架构

```
┌──────────────────────────────────────────────┐
│            Streamlit Web UI                   │
│  ┌────────┐ ┌────────┐ ┌──────┐ ┌────────┐ │
│  │路径选择 │ │URL输入  │ │进度条│ │结果预览 │ │
│  └───┬────┘ └───┬────┘ └──┬───┘ └───┬────┘ │
│      └──────────┼─────────┼─────────┘       │
│                 ▼         ▼                   │
│        ┌──────────────────────┐              │
│        │   Core Transcriber   │              │
│        └─────┬──────┬────┬───┘              │
│              ▼      ▼    ▼                    │
│        ┌──────┐ ┌──────┐ ┌──────┐           │
│        │B站API│ │Whisper│ │状态  │           │
│        │获取器│ │引擎   │ │管理器│           │
│        └──────┘ └──────┘ └──────┘           │
└──────────────────────────────────────────────┘
```

核心依赖：
- **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** — 基于 CTranslate2 的高效语音识别引擎，比原版 whisper 快 5-8 倍
- **[streamlit](https://streamlit.io/)** — Python Web 可视化框架
- **requests** — B站 API 调用
- **imageio-ffmpeg** — 提供 ffmpeg 二进制文件

---

## ❓ 常见问题

### B站API返回412错误？

B站对频繁请求有风控机制，工具已内置重试。如果持续失败：
- 等待几分钟后重试
- 在浏览器中登录B站，将 Cookie 添加到 `fetcher.py` 的请求头中

### Whisper模型下载失败？

`faster-whisper` 从 HuggingFace 下载模型，国内网络可能不稳定：
- 设置 HuggingFace 镜像：`export HF_ENDPOINT=https://hf-mirror.com`
- 或手动下载模型文件到缓存目录

### 转写准确率不够？

- 确保使用 `medium` 或更高模型
- 专业术语（如"量化"、"K线"等）可能需要人工校对
- `large-v3` 模型准确率最高，但速度较慢

### 支持其他视频平台吗？

当前仅支持B站（bilibili.com），后续可扩展。

---

## 🤝 贡献

欢迎贡献！请遵循以下流程：

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/amazing-feature`
3. 提交改动：`git commit -m 'Add amazing feature'`
4. 推送分支：`git push origin feature/amazing-feature`
5. 提交 Pull Request

### 开发路线

- [ ] 支持更多视频平台（YouTube、抖音等）
- [ ] 多语言转写支持
- [ ] GPU 加速配置
- [ ] Docker 一键部署
- [ ] 转写内容后处理（自动纠错、分段摘要）

---

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源。

---

## ⚠️ 免责声明

**本工具仅作为技术演示和学习用途发布。**

- 本工具不存储、不分发任何视频或音频内容，转写由用户在本地执行
- 用户需自行确保对所转写的视频拥有合法使用权（如本人创作内容、已获授权、合理使用等）
- 未经授权下载、转写他人视频可能侵犯著作权，相关法律责任由用户自行承担
- 本工具开发者不对用户的任何使用行为承担责任

如你是视频创作者并认为本工具影响了你的权益，请联系我们处理。
