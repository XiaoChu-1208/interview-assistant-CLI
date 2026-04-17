# Interview Assistant

> 面试时的实时副驾——听见问题，秒查你的本地知识库，给出 STAR 化的回答建议。

简体中文 · [English](./README.md)

一个跑在终端里的实时面试副驾。它通过系统音监听面试官的问题、通过 Push-to-Talk 录入你想自查的句子，自动转写后在你的本地 Markdown 知识库里做混合检索（BM25 + 嵌入），再调用任意 OpenAI 兼容大模型生成简洁的回答建议。

知识库 **100% 本地存放**。离线模式 **完全不需要任何 API key**。

---

## 特性

- **实时语音识别**：Groq Whisper（免费版无需信用卡）或本地 `faster-whisper`（完全离线）。
- **混合 RAG**：在你自己的 Markdown 知识库上跑 BM25 + 嵌入向量检索，问题级别的 instant recall。
- **Push-to-Talk**：默认按住右 Option（`⌥`）录音，可改 F8 / 右 Cmd / Ctrl / F5。
- **大模型不绑定厂商**：任意 OpenAI 兼容 endpoint —— Groq / OpenAI / OpenRouter / DeepSeek / 智谱 / 本地 vLLM 都行。
- **两个通用 Skill**（同时被 Cursor / Claude Code / Codex 识别）：
  - `interview-knowledge-format` —— 把简历 / 旧面试记录转成检索友好的 Q&A 文件。
  - `homophone-detector` —— 识别多音字与语音转写歧义，附带可自动扩充的"幻觉句"过滤集。
- **双语界面** —— 首次启动选 中文 / English。
- **5 分钟上手** —— 一条 `init` 命令搞定语言、模型、skill、示例知识库、音频设备。

## 安装

### 推荐方式（PyPI）

```bash
pipx install interview-assistant
# 或者，如果没有 pipx：
pip install --user interview-assistant
```

按平台/功能装可选 extra：

```bash
# Windows：开启 WASAPI loopback（系统音捕获）+ ANSI 颜色
pip install "interview-assistant[windows]"

# 嵌入向量检索（首次会下 ~30MB 模型）
pip install "interview-assistant[embed]"

# Push-to-Talk 全局热键
pip install "interview-assistant[hotkey]"

# 完全离线模式（本地 Whisper）
pip install "interview-assistant[offline]"

# 知识库 ingest（PDF / DOCX → Q&A）
pip install "interview-assistant[ingest]"

# 全套
pip install "interview-assistant[all]"
```

### 从源码安装

```bash
git clone https://github.com/XiaoChu-1208/interview-assistant-CLI.git
cd interview-assistant-CLI
pip install -e ".[all]"
```

## 第一次运行

```bash
interview-assistant init
```

向导会引导你：

1. **选语言** —— 中文 或 English。
2. **选模式** —— A) 在线全功能（Groq，推荐）；B) 自带 OpenAI 兼容 key；C) 完全离线。
3. **环境自检 + 自动修复** —— 缺音频后端、缺系统包、缺权限，能自动的就自动。
4. **配置 chat 模型** —— endpoint + key + model + 连通性测试。
5. **拷贝示例知识库** 到 `./knowledge/00_starter.md`。
6. **安装两个 skill** 到你的编辑器（Cursor / Claude Code / Codex），默认项目级。
7. **检测音频设备**。

之后：

```bash
interview-assistant            # 启动助手
interview-assistant doctor     # 重新跑诊断
interview-assistant doctor --fix    # 让能自动修的全自动修
```

## 建立你的知识库

三条路任选：

### A. 在 AI 编辑器里（最快）

1. 用 **Cursor** 或 **Claude Code** 打开本项目。
2. 把简历 / JD / 旧面试记录拖进对话。
3. 说：
   > 用 `interview-knowledge-format` skill，按规范帮我整理 Q&A 文件，
   > 写到 `knowledge/` 下，按主题分文件。

AI 会按格式产出 MD 文件（含 Unicode tree 块和 RAG 期望的 Q&A 结构）。

### B. 命令行

```bash
interview-assistant knowledge new                # 一题一题问，引导式录入
interview-assistant knowledge ingest 简历.pdf    # PDF/DOCX/MD/TXT → 草稿 Q&A
interview-assistant knowledge validate           # 校验格式
interview-assistant knowledge status             # 查看 approved/draft/invalid
interview-assistant ask "请做个自我介绍"          # 单题干跑（不开音频）
```

### C. 手写

照着 `knowledge/00_starter.md` 的格式抄。`interview-knowledge-format` skill 描述了完整规范。

## 快捷键（运行时）

| 按键 / 命令 | 作用 |
|---|---|
| 按住 `⌥`（右 Option） | Push-to-Talk 录入麦克风 |
| `listen` | 切换系统音监听（面试官侧） |
| `off` | 停止监听 |
| `/search <关键词>` | 检索知识库 |
| `/reload` | 修改知识库 MD 后重新加载 |
| `q` / `quit` / `exit` | 退出 |

PTT 键可改 —— 见 `~/.config/interview-assistant/config.toml` 的 `[hotkey].ptt`。**macOS 不要用 F5**（会触发 Siri）。

## Skill 安装

```bash
interview-assistant skills install               # 安装两个 skill 到检测到的编辑器
interview-assistant skills list                  # 查看已安装位置
interview-assistant skills upgrade               # 升级到内置最新版
interview-assistant skills uninstall <name>      # 删除
```

Skill 是复制（不是 symlink）到：

| 编辑器 | 项目级 | 用户级 |
|---|---|---|
| Cursor | `./.cursor/skills/<name>/` | `~/.cursor/skills/<name>/` |
| Claude Code | `./.claude/skills/<name>/` | `~/.claude/skills/<name>/` |
| Codex / 通用 | 追加到 `./AGENTS.md` | — |

## 配置

存放在 `~/.config/interview-assistant/config.toml`（Linux/macOS）或 `%APPDATA%\interview-assistant\config.toml`（Windows）。任何字段都能用 `IA_*` 环境变量覆盖。

## 平台说明

| 平台 | 系统音 | 麦克风 | PTT | 备注 |
|---|---|---|---|---|
| **macOS** | 装 [BlackHole](https://github.com/ExistentialAudio/BlackHole) + Audio MIDI Setup 建多输出 | 默认可用 | 给终端开 Accessibility | F5 与 Siri 冲突——默认是 `⌥` |
| **Windows** | 默认可用（装 `[windows]` extra 启用 WASAPI loopback） | 默认可用 | 默认可用 | 不需要装任何虚拟声卡 |
| **Linux** | PulseAudio `*.monitor` 设备 | 默认可用 | 仅 X11（Wayland 禁用全局热键） | 需 `apt install portaudio19-dev` |

`interview-assistant doctor` 会逐项检查。

## 隐私

- 知识库文件留在本地。`.gitignore` 默认忽略 `knowledge/` 下除 starter 外的全部文件。
- 音频只发到你配置的 STT 服务（默认 Groq；或离线模式下完全不出本机）。
- 问题 + 检索到的上下文发给你配置的 chat LLM 服务。
- 无遥测、无分析。

## 许可证

MIT —— 见 [LICENSE](./LICENSE)。
