# MiniBox — GPT-SoVITS 角色语音聊天机器人

**超かぐや姫！ 超時空輝夜姫！ — 月読空間へようこそ**

基于 GPT-SoVITS 本地语音合成 + 云端大语言模型（LLM）的**角色扮演语音聊天机器人**。

支持 PC 网页端实时对话，也可通过 ESP32-S3 硬件嵌入手办底座，实现**实体手办语音交互**。

---

## Features / 功能亮点

- **角色语音对话** — 基于 GPT-SoVITS 训练的角色模型，生成高质量拟真语音（日语/中文）
- **多轮对话记忆** — LLM 记住最近 6 轮对话，角色保持上下文连贯
- **完整角色人设** — 内置《超时空辉夜姬！》酒寄彩叶双语人设（日文/中文），含性格、人际关系、口调规则
- **多 TTS 引擎** — GPT-SoVITS（本地）/ MiniMax（云端）/ Edge-TTS（免费兜底）自由切换
- **语音输入** — 支持麦克风录音 → 语音识别 → 自动对话
- **自动翻译** — 非中文回复自动附加中文翻译
- **模型热加载** — Web UI 内直接切换/加载不同角色模型和参考音频
- **交互式抚摸器** — 对话区角色图像支持点击互动，切换表情+爱心粒子
- **ESP32 手办客户端** — 通过 WiFi 连接局域网 PC，按住按钮即可与手办对话
- **REST API** — 内置 `/api/voice_chat` 端点，支持第三方硬件/客户端接入

---

## Architecture / 系统架构

```
┌─────────────────────────────────────────────┐
│              PC Server (webui.py)            │
│                                             │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐ │
│  │  Gradio  │  │   LLM    │  │ GPT-SoVITS│ │
│  │  Web UI  │  │ (Vtrix)  │  │  TTS API  │ │
│  └────┬─────┘  └────┬─────┘  └─────┬─────┘ │
│       │             │              │        │
│       └──────┬──────┴──────────────┘        │
│              │                              │
│     ┌────────┴────────┐                     │
│     │  REST API       │                     │
│     │ /api/voice_chat │                     │
│     └────────┬────────┘                     │
└──────────────┼──────────────────────────────┘
               │ WiFi (HTTP)
┌──────────────┼──────────────────────────────┐
│    ESP32-S3 手办客户端 (可选)                 │
│  INMP441 麦克风 → 录音 → POST → 播放回复     │
│  MAX98357A 功放 + 喇叭                       │
└─────────────────────────────────────────────┘
```

---

## Quick Start / 快速开始

### 环境要求

| 项目 | 最低要求 |
|------|---------|
| 操作系统 | Windows 10/11 (64 位) |
| Python | 3.10+ |
| 显卡 | NVIDIA GPU（推荐 6GB+ 显存，用于 GPT-SoVITS 推理） |
| 内存 | 8GB+ |
| 网络 | 需联网（LLM 使用云端 API） |

### 1. 克隆仓库

```bash
git clone https://github.com/YOUR_USERNAME/minibox.git
cd minibox
```

### 2. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 3. 安装 GPT-SoVITS

下载 **花儿不哭老师开源一键安装包**：

> **下载地址：<http://bilihua.psce.pw/839f28>**

解压后将文件夹放在任意位置，然后修改 `webui.py` 中的 `GSV_DIR` 路径指向它：

```python
GSV_DIR = r"E:\GPT-SoVITS-v2pro-20250604"  # 改为你的实际路径
```

### 4. 安装 FFmpeg

下载 `minibox_ffmpeg.zip` 并解压到 `bin/` 目录：

> **Google Drive：<https://drive.google.com/file/d/1LodrOsX15BUH8B0jq_k6GskZ_S4buQWk/view?usp=sharing>**
>
> **夸克网盘：<https://pan.quark.cn/s/f08624f913db>**

或从 [FFmpeg 官网](https://ffmpeg.org/download.html) 自行下载，将 `ffmpeg.exe` 和 `ffprobe.exe` 放入 `bin/` 目录。

### 5. 准备语音模型

在 `gsv/` 目录下创建角色文件夹，放入训练好的模型文件：

```
gsv/
└── 你的角色名gsv模型/
    ├── 角色名_xxx.pth          # SoVITS 模型权重
    ├── 角色名_xxx.ckpt         # GPT 模型权重
    └── 训练集/
        ├── reference_audio.wav  # 参考音频（控制语气音色）
        └── 训练集.list          # 标注文件（可选）
```

> 本项目内置「酒寄彩叶」角色模型，下载 `minibox_models.zip` 解压到 `gsv/` 目录即可使用：
>
> **Google Drive：<https://drive.google.com/file/d/1Y16MYKvG31gruX32pmqUVO_8BK80msDg/view?usp=sharing>**
>
> **夸克网盘：<https://pan.quark.cn/s/abe9a12e4675>**

### 6. 获取 LLM API Key

1. 注册 [Vtrix Cloud](https://cloud.vtrix.ai) 账号
2. 创建 API Key（`sk-...` 格式）
3. 启动后在网页界面填入

### 7. 启动

```bash
python webui.py
```

浏览器访问 `http://127.0.0.1:7860` 即可开始对话。

---

## Project Structure / 项目结构

```
minibox/
├── webui.py                 # 主程序（Web UI + LLM + TTS + REST API）
├── requirements.txt         # Python 依赖
├── setup_ffmpeg.py          # FFmpeg 下载辅助脚本
├── test_mic.py              # 麦克风测试脚本
├── yachiyo_normal.png       # 抚摸器常态图片
├── yachiyo_happy.png        # 抚摸器开心图片
├── yachiyo.html             # 抚摸器独立网页版
├── README.md                # 本文档
├── LICENSE                  # MIT 协议
├── .gitignore
├── gsv/                     # 角色语音模型目录（需自行放入模型文件）
│   └── .gitkeep
├── bin/                     # FFmpeg 二进制（需自行下载放入）
│   └── .gitkeep
└── esp32/                   # ESP32 手办硬件固件
    └── minibox_firmware/
        ├── platformio.ini   # PlatformIO 工程配置
        └── src/
            ├── config.h     # WiFi / 服务器 / 引脚配置
            └── main.cpp     # 固件主程序
```

---

## 自定义配置（更换 LLM / API 服务商）

本项目的 LLM 调用基于 **OpenAI 兼容协议**，支持任何兼容该协议的服务商。修改 `webui.py` 中以下两处即可切换：

### LLM API 地址与模型

```python
# webui.py 第 21 行 — API 地址
VTRIX_BASE_URL = "https://cloud.vtrix.ai/llm"    # 默认使用 Vtrix Cloud

# webui.py _vtrix_chat() 函数内 — 模型名称
"model": "vtrix-claude-sonnet-4.5",               # 默认模型
```

替换示例：

| 服务商 | API 地址 | 模型名称 | API Key 获取 |
|--------|---------|----------|-------------|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` / `gpt-4o-mini` | [platform.openai.com](https://platform.openai.com) |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` | [platform.deepseek.com](https://platform.deepseek.com) |
| 硅基流动 | `https://api.siliconflow.cn/v1` | `Qwen/Qwen2.5-72B-Instruct` | [siliconflow.cn](https://siliconflow.cn) |
| Ollama（本地） | `http://127.0.0.1:11434/v1` | `qwen2.5:7b` | 无需 Key |
| Vtrix Cloud | `https://cloud.vtrix.ai/llm` | `vtrix-claude-sonnet-4.5` | [cloud.vtrix.ai](https://cloud.vtrix.ai) |

> **提示**：更换后，网页界面的 API Key 输入框需填入对应服务商的密钥。使用本地 Ollama 时可随意填写。

### GPT-SoVITS 路径

```python
# webui.py 第 28-29 行
GSV_DIR = r"C:\GPT-SoVITS-v2pro-20250604"   # 改为你的 GPT-SoVITS 安装路径
GSV_API_URL = "http://127.0.0.1:9880"       # API 端口，默认不用改
```

---

## GPT-SoVITS TTS 参数调优指南

`webui.py` 中 `gpt_sovits_tts_generate()` 函数的 TTS 请求参数经过针对性调优，以提升角色音色还原度和语音自然度。以下是各参数的说明和调参建议，便于开发者进一步优化：

| 参数 | 当前值 | 默认值 | 说明 |
|------|--------|--------|------|
| `top_k` | **12** | 15 | 采样时保留的候选 token 数量。降低可减少随机性，让音色更贴合参考音频。建议范围：5-20 |
| `top_p` | **0.8** | 1.0 | 核采样概率阈值。降低可减少发音"漂移"，提高输出稳定性。建议范围：0.6-1.0 |
| `temperature` | **0.8** | 1.0 | 生成温度。低于 1.0 使输出更保守/稳定，减少机器感和随机偏差。建议范围：0.5-1.0 |
| `speed` | **1.0** | 1.0 | 语速倍率。1.0 为原速，0.8 偏慢，1.2 偏快 |
| `text_split_method` | **cut5** (中文) / **cut0** (日文) | cut0 | 文本分句策略。`cut5` 按中文标点智能分句，显著改善中文韵律；`cut0` 不分句，适合日语短句直出 |
| `batch_size` | **1** | 1 | 推理批大小。单句实时推理建议设 1 |
| `repetition_penalty` | **1.35** | 1.0 | 重复惩罚系数。高于 1.0 可有效减少重复音节和机器人感，提升自然度。建议范围：1.0-1.5 |

### 参考音频的选择

参考音频（`ref_audio_path`）对最终音色影响**极大**，选择建议：

- **语气匹配**：选择与目标对话场景语气相近的参考音频（平静/开心/严肃等）
- **音质清晰**：避免带有背景噪音或混响的片段
- **长度适中**：2-8 秒为佳，太短音色不稳定，太长推理变慢
- **语言一致**：参考音频语言应与 `prompt_lang` 参数一致

### 调参实践经验

1. **减少机器感**：降低 `temperature`（0.7-0.8）+ 提高 `repetition_penalty`（1.3-1.5）
2. **提高音色稳定性**：降低 `top_k`（8-12）+ 降低 `top_p`（0.7-0.8）
3. **改善中文发音**：将 `text_split_method` 设为 `cut5`，让模型按标点分句处理
4. **如果音频卡顿/断裂**：尝试提高 `batch_size` 或调高 `top_k`

---

## ESP32 手办客户端

将语音聊天机器人嵌入手办底座，按住按钮即可与角色实体对话。

### 硬件清单

| 组件 | 型号 | 参考价格 | 用途 |
|------|------|---------|------|
| 主控 | ESP32-S3-DevKitC-1 (N16R8) | ¥35-50 | WiFi + 蓝牙 + PSRAM |
| 麦克风 | INMP441 I2S 数字麦克风 | ¥8-12 | 录音输入 |
| 功放 | MAX98357A I2S 功放模块 | ¥8-12 | 驱动喇叭 |
| 喇叭 | 3W 4Ω 小喇叭 (28mm) | ¥3-5 | 音频输出 |
| 按钮 | 微型轻触按钮 | ¥1 | 按住说话 |

**总成本约 ¥60-90**

### 接线图

```
ESP32-S3 DevKitC-1
┌─────────────────────┐
│                     │
│  GPIO 4  ──────────── INMP441 SCK
│  GPIO 5  ──────────── INMP441 WS
│  GPIO 6  ──────────── INMP441 SD
│                     │
│  GPIO 15 ──────────── MAX98357A BCLK
│  GPIO 16 ──────────── MAX98357A LRC
│  GPIO 17 ──────────── MAX98357A DIN
│                     │
│  GPIO 0  ──────────── 按钮 (另一端接 GND)
│                     │
│  3V3     ──────────── INMP441 VDD, MAX98357A VIN
│  GND     ──────────── INMP441 GND/L/R, MAX98357A GND
│                     │
│  USB     ──────────── 5V 供电 / 烧录
└─────────────────────┘
```

### 固件烧录

1. 安装 [VSCode](https://code.visualstudio.com/) + [PlatformIO 插件](https://platformio.org/install/ide?install=vscode)
2. 用 VSCode 打开 `esp32/minibox_firmware/` 文件夹
3. 编辑 `src/config.h`，填入 WiFi 和 PC 服务器 IP：
   ```cpp
   #define WIFI_SSID     "your_wifi"
   #define WIFI_PASSWORD "your_password"
   #define SERVER_HOST   "192.168.1.100"  // 运行 webui.py 的电脑 IP
   #define SERVER_PORT   7860
   ```
4. USB 连接 ESP32-S3，点击 PlatformIO 的 **Upload** 按钮烧录
5. 确保 PC 端 `webui.py` 已启动，ESP32 和 PC 在同一局域网
6. **按住按钮说话，松开等回复**

### PC 端 API

```
POST http://<PC-IP>:7860/api/voice_chat
Content-Type: audio/wav
Body: WAV 音频 (16kHz, 16bit, mono)

Response 200: WAV 音频（角色回复语音）
Response 400: 录音太短 / STT 失败
Response 500: LLM 或 TTS 失败
```

---

## Tech Stack / 技术栈

| 层级 | 技术 |
|------|------|
| 前端 UI | Gradio 3.50.2 |
| 大语言模型 | Vtrix Cloud API (OpenAI-compatible) |
| 语音合成 (TTS) | GPT-SoVITS v2 / MiniMax / Edge-TTS |
| 语音识别 (STT) | SpeechRecognition + Google Web Speech API |
| 音频处理 | FFmpeg / numpy |
| 硬件客户端 | ESP32-S3 + INMP441 + MAX98357A |
| 硬件框架 | Arduino (PlatformIO) |

---

## Acknowledgements / 致谢

本项目的实现离不开以下开源项目和社区贡献者，在此表示衷心感谢：

### 核心依赖

| 项目 | 作者 | 许可证 | 用途 |
|------|------|--------|------|
| [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) | RVC-Boss (花儿不哭) | MIT | 语音合成引擎，本项目的核心 TTS 后端 |
| [Gradio](https://github.com/gradio-app/gradio) | Gradio Team | Apache 2.0 | Web UI 框架 |
| [Edge-TTS](https://github.com/rany2/edge-tts) | rany2 | GPL-3.0 | 微软 TTS 引擎接口 |
| [SpeechRecognition](https://github.com/Uberi/speech_recognition) | Uberi | BSD-3-Clause | 语音识别库 |
| [FFmpeg](https://ffmpeg.org/) | FFmpeg Team | LGPL-2.1+ | 音频格式处理 |
| [aiohttp](https://github.com/aio-libs/aiohttp) | aio-libs | Apache 2.0 | 异步 HTTP 客户端 |

### 硬件相关

| 项目 | 作者 | 许可证 | 用途 |
|------|------|--------|------|
| [Arduino-ESP32](https://github.com/espressif/arduino-esp32) | Espressif | Apache 2.0 | ESP32 Arduino 框架 |
| [ArduinoJson](https://github.com/bblanchon/ArduinoJson) | Benoît Blanchon | MIT | JSON 序列化/反序列化 |
| [PlatformIO](https://platformio.org/) | PlatformIO Labs | Apache 2.0 | 嵌入式开发平台 |

### 特别感谢

- **[花儿不哭老师](https://space.bilibili.com/1592878818)** — GPT-SoVITS 项目作者，提供了优秀的语音合成框架和一键安装包
- **[Vtrix Cloud](https://cloud.vtrix.ai)** — 提供 OpenAI 兼容的 LLM API 服务
- **《超时空辉夜姬！》（超かぐや姫！）** — 角色「酒寄彩叶」的原作动画电影，角色设定和人设参考来源

### 角色声明

本项目中「酒寄彩叶」角色的人设和语音模型仅用于技术学习和研究目的。角色版权归原作者和制作方所有。如有侵权请联系删除。

---

## FAQ / 常见问题

<details>
<summary><b>Q: 启动时提示"GPT-SoVITS 服务未运行"</b></summary>

GPT-SoVITS 启动需要 30-60 秒加载模型。程序内置了端口冲突自动清理机制，如果之前的进程没关干净，会自动杀掉占用 9880 端口的进程再重启。也可查看 `gsv_api.log` 排查。
</details>

<details>
<summary><b>Q: LLM 报错 ASCII 编码错误</b></summary>

本项目已用 `aiohttp` 替代 `openai` + `httpx` 库进行 API 调用，解决了 Windows 下中文请求体的 ASCII 编码问题。如果仍有问题，请检查是否需要代理访问 API。
</details>

<details>
<summary><b>Q: 中文语音不够自然</b></summary>

当前模型基于日语数据训练，中文合成效果有限。建议：将 `text_split_method` 设为 `cut5`；或训练专门的中文模型；或中文对话使用 MiniMax 云端语音。
</details>

<details>
<summary><b>Q: ESP32 连不上服务器</b></summary>

1. 确认 ESP32 和 PC 在同一 WiFi（2.4GHz，ESP32 不支持 5GHz）
2. 检查 `config.h` 中的 IP 地址（Windows: `ipconfig` 查看 IPv4）
3. 检查 Windows 防火墙是否允许 7860 端口入站
</details>

---

## Contributing / 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 发起 Pull Request

---

## License / 协议

本项目基于 [MIT License](LICENSE) 开源。

GPT-SoVITS 部分遵循其原项目 [MIT 协议](https://github.com/RVC-Boss/GPT-SoVITS/blob/main/LICENSE)。

Edge-TTS 部分遵循 [GPL-3.0 协议](https://github.com/rany2/edge-tts/blob/master/LICENSE)。
