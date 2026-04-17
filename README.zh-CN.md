# Interview Assistant

> 面试时的实时副驾——听见问题，**毫秒级把你提前写好的答案**原文打到屏幕上。

简体中文 · [English](./README.md)

---

## 这个项目为什么存在（以及为什么和别人不一样）

GitHub 上现有的"AI 面试助手"几乎都是同一个套路：把面试官的语音灌进 Whisper 转写，把转写的问题塞给 GPT-4 / Claude，把模型生成的回答流式打回给候选人。

**这套方案在真实面试里其实并不靠谱**，原因有四个：

| LLM 即时生成的问题 | 实际发生的情况 |
|---|---|
| **延迟** | 第一个有用的 token 要 2–6 秒。面试官已经在追问了。 |
| **不是你的语气** | LLM 输出的是漂亮的通用书面语；你听起来像在念稿子。面试官第一耳朵就能听出来。 |
| **幻觉** | LLM 会编出你根本没做过的项目、没拿过的指标、没经历过的团队规模。一旦面试官追问"你刚才说 23%，这个数据怎么来的？"，你就崩了。 |
| **按问题计费 + 限流** | 越是关键时刻越需要稳定，但偏偏在这时候吃 429、欠费、超额。 |

### Instant-Recall 的反向设计

Interview Assistant 把这件事彻底反过来：

> **答案是你自己提前写好的。工具的唯一职责是用最快速度找到对应那条。**

实战时是这样的：

1. Whisper 把面试官的问题转成文字。
2. 混合检索（BM25 + 嵌入向量）从**你本地的 Markdown 知识库**里找最匹配的那条 Q&A —— 知识库里装的是**你**亲自写的、用**你自己的语气**、带着**你真实数据**的答案。
3. 命中度高时，助手**逐字打印你存档的答案**，不调任何 chat-LLM、不二次改写、不会幻觉，从问题结束到屏幕出字常常 200ms 以内。
4. 命中度低时（也仅在这种时候），可以选择性地走 LLM 兜底，但它是失败路径，不是主路径。

这里有一个诚实的取舍：**你必须自己做前期准备**。指望 LLM 替一个它根本不了解的人讲好他的人生故事，那是不存在的免费午餐。这个工具给你的不是"代你思考"，而是**让你的准备产生复利**：之前花的所有备题时间变成一份永远可检索的资产，下一场面试直接复用。

为了让前期准备本身也别太累，项目附带了一个 Cursor / Claude Code / Codex 通用 Skill（`interview-knowledge-format`），能自动把你的简历 / 旧面试记录 / JD 整理成正确格式的 Q&A。

---

## 亮点

### 主要

- **Instant Recall 是一等模式。** 整个 app 可以完全关掉 chat-LLM 跑：Whisper + 你的知识库，就够了。零幻觉风险、零 per-token 成本、面试中途也不用担心 API 抽风。
- **原话级保真。** 检索层会**优先打印你的存档原文**而不是改写它。你听到的就是你写过的。你说出来就是你的语气。
- **可预测的延迟。** 命中 instant recall 时，从问题结束到答案上屏常常 1 秒以内 —— 关键路径上根本不存在"远端 API 流式吐 token"这一步。

### 次要（但都是真做了的）

- **混合检索 + Q-hint instant recall。** BM25 + 嵌入向量（FastEmbed `bge-small-zh-v1.5`）+ Reciprocal Rank Fusion。另有一份独立的"问题级"索引，命中那种"语义上几乎是同一个题"时近似 O(1) 召回。
- **两个通用 Skill（同时被 Cursor / Claude Code / Codex 识别）：**
  - `interview-knowledge-format` —— 把简历 / JD / 旧面试记录整理成结构化 Q&A（含可选的 Unicode `tree` 速查块）。通过 `prompt-inject` runtime 钩子加载，AI 编辑器在你修改时也始终保持格式感。
  - `homophone-detector` —— 扩充多音字表（`RAG/LAG`、`KPI/KBI`、重 zhòng/chóng、还 hái/huán…）和 STT 幻觉过滤集（`悠悠独播剧场`、`字幕组`、`Subtitles by the Amara.org community`…）。通过 `data-source` runtime 钩子加载，AI 编辑器还能持续把它在你知识库里发现的新词追加进去。
- **STT 幻觉过滤内置。** Whisper 在静音段会周期性吐出流媒体水印（"悠悠独播剧场""感谢观看"之类），我们直接静默丢弃。集合可以通过 skill 或 `[stt_filter].extra_hallucinations` 配置继续扩充。
- **网络感知 onboarding，针对国内 / 公司网络。** `init` 会先探一下连通性，不通时自动读系统代理设置（macOS `scutil --proxy`、Windows 注册表、Linux `gsettings`）**并**扫描众所周知的本地代理端口（Clash 7890、Surge 6152、V2RayN 10809、Stash 7777、Privoxy 8118…）。Y/N 一下就用上。
- **Chat 不绑定厂商**（如果你确实需要 LLM 兜底）。任意 OpenAI 兼容 endpoint：Groq / OpenAI / OpenRouter / DeepSeek / n1n / Azure / 本地 vLLM。可选 fallback endpoint 在 429/503 时自动切。
- **Push-to-Talk 不和系统打架。** 默认右 Option（Discord 风格 —— macOS 上无任何系统冲突）。可改 F8 / 右 Cmd / 右 Ctrl / F5；选 F5 时向导会提示"会触发 Siri"。
- **跨平台音频抽象。** macOS BlackHole / Windows WASAPI loopback / Linux PulseAudio `*.monitor`，统一在一个 `find_loopback()` 接口后面。麦克风发现会自动跳过虚拟设备。
- **双语界面** —— 中文 / English，第一次启动时选好就持久化；超薄 YAML 驱动的 `i18n.t()`，缺词自动回落英文。
- **知识库 CLI 工作流。** `knowledge new`（一题一题问）、`knowledge ingest`（PDF / DOCX / MD → 草稿 Q&A，**先报 token 估算和成本再花钱**，结果写到 `draft_*.md` 强制你审阅后才会被检索用到）、`knowledge validate`、`knowledge status`、`ask`（不开音频，单题干跑）。
- **Local-first 隐私设计。** 所有知识文件留在本地。默认 `.gitignore` 忽略 `knowledge/*` 除示例文件外的所有内容 —— 你不会不小心把面试备题推到 GitHub。无遥测、无分析、无自动更新。
- **`doctor --fix`。** `interview-assistant doctor --fix` 跑同一套自检并尝试自动修复（比如 `brew install blackhole-2ch`、`apt install portaudio19-dev`）。
- **Tree 块渲染。** 你存档答案里的 ` ```tree ` 块在终端里会被着色和缩进，扫一眼就能讲。
- **Skill 安装器。** `interview-assistant skills install/list/upgrade/uninstall` 把内置 skill 复制（不是 symlink —— Windows 友好）到目标编辑器目录（`./.cursor/skills/`、`./.claude/skills/`，项目级或用户级）。
- **配置可全部覆盖。** 单一 TOML 在 `~/.config/interview-assistant/config.toml`，任何字段都能用 `IA_*` 环境变量覆盖。

---

## 安装

```bash
pipx install interview-assistant
# 或者
pip install --user interview-assistant
```

按需装可选 extras：

```bash
pip install "interview-assistant[embed]"      # 嵌入向量召回（推荐）
pip install "interview-assistant[hotkey]"     # Push-to-Talk
pip install "interview-assistant[offline]"    # 本地 Whisper，不调云端
pip install "interview-assistant[ingest]"     # PDF/DOCX → Q&A 草稿
pip install "interview-assistant[windows]"    # Windows WASAPI + ANSI
pip install "interview-assistant[all]"        # 全套
```

源码安装：

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
2. **选模式**：
   - **A) 仅 Instant-recall** *（推荐）* —— 只跑 Whisper + 本地 Q&A，**全程不调任何 chat-LLM**。只需要一个 Groq Whisper key（免费、无需信用卡）或本地 Whisper。
   - **B) 在线全功能** —— Groq Whisper + Groq Llama-3.3 免费版。
   - **C) 自带 chat key** —— 任意 OpenAI 兼容 endpoint。
   - **D) 完全离线** —— 本地 Whisper，零云端。
3. **环境自检 + 自动修复** —— 缺音频后端、缺包、缺权限。
4. **网络探测 + 代理自动嗅探** —— 针对国内 / 公司网络。
5. **STT / chat key + 连通性测试。**
6. **示例知识库** 拷贝到 `./knowledge/00_starter.md`。
7. **Skill 安装** 到检测到的 AI 编辑器（Cursor / Claude Code / Codex）。
8. **音频设备验证。**

之后：

```bash
interview-assistant            # 启动助手
interview-assistant doctor     # 重跑诊断
interview-assistant doctor --fix
interview-assistant ask "请做个自我介绍"   # 不开音频，单题干跑
```

## 建立你的知识库

三条路：

### A. AI 编辑器（最快）

在 Cursor / Claude Code 里打开本目录，把简历 / JD 拖进对话，说：

> 用 `interview-knowledge-format` skill，按规范帮我整理 Q&A，写到 `knowledge/` 下，按主题分文件。

附带的 skill 会让 AI 严格按 RAG 期望的格式输出 —— 正确的标题层级、`Q:` / `A:` 标记、可选的 `tree` 块，原文里缺数据的地方用 `[需补充]` 占位而不是编造。

### B. 命令行

```bash
interview-assistant knowledge new                # 一题一题问
interview-assistant knowledge ingest 简历.pdf    # PDF/DOCX/MD/TXT → draft_*.md
interview-assistant knowledge validate
interview-assistant knowledge status
```

`ingest` 永远写到 `draft_*.md`，并在花钱前先报 token 估算。

### C. 手写

照 `knowledge/00_starter.md` 改。`interview-knowledge-format` skill 描述了完整规范。

## 快捷键（运行时）

| 按键 / 命令 | 作用 |
|---|---|
| 按住 `⌥`（右 Option，默认） | Push-to-Talk 录入麦克风 |
| `listen` | 切换系统音监听（面试官侧） |
| `off` | 停止系统音监听 |
| `/search <关键词>` | 检索知识库 |
| `/reload` | 重新加载知识库 |
| `q` / `quit` / `exit` | 退出 |

PTT 键可改 —— 见 `~/.config/interview-assistant/config.toml` 的 `[hotkey].ptt`。**macOS 不要用 F5**（Siri）。

## Skill 管理

```bash
interview-assistant skills install               # 安装两个 skill
interview-assistant skills list                  # 查看已安装位置
interview-assistant skills upgrade
interview-assistant skills uninstall <name>
```

Skill 复制（不是 symlink —— Windows 友好）到：

| 编辑器 | 项目级 | 用户级 |
|---|---|---|
| Cursor | `./.cursor/skills/<name>/` | `~/.cursor/skills/<name>/` |
| Claude Code | `./.claude/skills/<name>/` | `~/.claude/skills/<name>/` |
| Codex / 通用 | `./AGENTS.md` | — |

## 平台说明

| 平台 | 系统音 | 麦克风 | PTT | 备注 |
|---|---|---|---|---|
| **macOS** | 装 [BlackHole](https://github.com/ExistentialAudio/BlackHole) + Audio MIDI Setup 建多输出 | 默认可用 | 给终端开 Accessibility | F5 与 Siri 冲突——默认是 `⌥` |
| **Windows** | 默认可用（装 `[windows]` extra 启用 WASAPI loopback） | 默认可用 | 默认可用 | 不需要装任何虚拟声卡 |
| **Linux** | PulseAudio `*.monitor` | 默认可用 | 仅 X11（Wayland 禁用全局热键） | 需 `apt install portaudio19-dev` |

`interview-assistant doctor` 会逐项检查。

## 隐私

- 所有知识文件留在本地。`.gitignore` 默认忽略 `knowledge/*` 除示例外的全部 —— 你不会不小心把备题推到 GitHub。
- 音频只发到你配置的 STT 服务。离线模式音频完全不出本机。
- 无遥测、无分析、无自动更新。

## 许可证

MIT —— 见 [LICENSE](./LICENSE)。
