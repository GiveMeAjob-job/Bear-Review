# Bear Review

Bear Review 是一个代码优先、SQLite 优先的个人执行与复盘系统。

它不再把核心结构绑在 Notion 这类外部工具上，而是把任务、状态、复盘和通知策略都收回到代码里，让 AI 可以直接帮你改流程、改数据结构、改产品行为。

## 它现在解决什么问题

- 任务记录要足够轻，不能为了记一条完成事项先打开一堆工具
- 复盘不能每天失忆，必须带着上下文持续跟进
- 通知不能变成噪音，应该只在值得打断的时候出现
- 当前主线、教练模式、熄火状态这些“系统脑子”必须和任务放在一起管理

## 当前版本的核心形态

- `SQLite` 是推荐的主任务源
- `Notion` 仍然可用，但只是可选适配器
- `python -m src.capture serve` 已经是统一首页
- 首页同时承担：
  - 快速记录完成任务
  - 查看最近任务
  - 查看系统状态
  - 编辑当前主线 / 当前阶段 / 教练模式
- 复盘输出不再只有一篇长文，还会生成：
  - `report`
  - `preview`
  - `decision card`
  - `metadata`

## 统一首页

启动本地首页：

```bash
python -m src.capture serve --host 127.0.0.1 --port 8765
```

然后打开：

```text
http://127.0.0.1:8765
```

如果想让手机访问同一局域网下的服务：

```bash
python -m src.capture serve --host 0.0.0.0 --port 8765
```

首页现在包含：

- 当前主线
- 当前阶段
- 当前教练模式
- 当前建议动作
- 系统状态
- 最近 7 天完成情况
- 手工别名数量
- 焦点控制台
- 快速录入表单
- 最近任务列表
- 手工别名、自动别名、模板复用、变体起点

这意味着你现在不需要再手改 `JSON` 才能更新主线，也不需要打开 Notion 才能记录任务。

## 快速开始

### 1. 安装依赖

要求：

- Python `3.9+`

安装：

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

最小可用配置：

```bash
export TASK_SOURCE=sqlite
export SQLITE_DB_PATH=.bear_review/tasks.db
export DEEPSEEK_KEY=your_key
```

如果你更想用 OpenAI：

```bash
export TASK_SOURCE=sqlite
export SQLITE_DB_PATH=.bear_review/tasks.db
export LLM_PROVIDER=openai
export OPENAI_KEY=your_key
```

常用可选项：

```bash
export LLM_MODEL=deepseek-chat
export TIMEZONE=America/Toronto
export NOTIFICATION_MODE=smart
export NOTIFICATION_TITLE_PREFIX="Bear Review"
export TELEGRAM_BOT_TOKEN=xxx
export TELEGRAM_CHAT_ID=xxx
```

### 3. 先记一条完成任务

```bash
python -m src.capture done \
  "剪完第一条视频" \
  --category Content \
  --priority MIT \
  --minutes 45 \
  --tomatoes 2
```

查看最近任务：

```bash
python -m src.capture recent --limit 10
```

### 4. 生成一轮复盘

日报：

```bash
TASK_SOURCE=sqlite python -m src.main --period daily --dry-run
```

昨天日报：

```bash
TASK_SOURCE=sqlite python -m src.main --period daily --yesterday --dry-run
```

三日趋势：

```bash
TASK_SOURCE=sqlite python -m src.main --period three-days --dry-run
```

周报：

```bash
TASK_SOURCE=sqlite python -m src.main --period weekly --notification-mode full
```

导出完整产物：

```bash
TASK_SOURCE=sqlite python -m src.main \
  --period daily \
  --dry-run \
  --output-file build/reports/report.txt \
  --preview-file build/reports/preview.txt \
  --decision-file build/reports/decision.txt \
  --metadata-file build/reports/metadata.json
```

## 任务源

### SQLite，推荐

这是当前项目的主路径。

适合你在这些情况下使用：

- 希望 AI 直接修改数据模型和工作流
- 不想把核心结构放在外部工具里
- 想用本地网页或命令行快速记完成项
- 想让任务、状态、记忆、焦点档案放在一起

默认数据库路径：

```text
.bear_review/tasks.db
```

### Notion，可选

如果你仍然想继续用 Notion：

```bash
export TASK_SOURCE=notion
export NOTION_TOKEN=your_token
export NOTION_DB_ID=your_database_id
export DEEPSEEK_KEY=your_key
```

然后运行：

```bash
python -m src.main --period daily --yesterday --dry-run --init-focus-profile
```

Notion 现在只负责数据适配，不再决定系统整体架构。

## 统一状态存储

当前项目已经把“系统脑子”也统一进了 SQLite。

当 `TASK_SOURCE=sqlite` 且你没有显式改状态路径时，下面这些状态会和任务一起进同一个数据库：

- `focus_profile`
- `review_memory`
- `engine_state`

如果仓库里已有旧的 JSON 状态文件，系统会在第一次使用 SQLite 状态时自动导入：

- `.bear_review/focus_profile.json`
- `.bear_review/review_memory.json`
- `.bear_review/engine_state.json`

这一步是迁移，不是强制继续依赖 JSON。

## 复盘引擎

Bear Review 不是单纯的“生成日报”脚本，它现在更像一个有状态的执行校准系统。

### 支持的周期

- `daily`
- `three-days`
- `weekly`
- `monthly`

### 每次运行的标准产物

- `report`：完整正文
- `preview`：适合通知和 Actions Summary 的短预览
- `decision card`：当前最重要的判断与下一步动作
- `metadata`：结构化统计、信号、模式、通知决策

### 干预逻辑

每次生成前，系统会先做这些判断：

- 行动闭环：上次承诺动作这次有没有任务证据
- 异常检测：MIT、XP、时长、空输出等是否异常
- 教练模式：`adaptive / recovery / stabilize / build / sprint`
- 逆境原则：`soldier on`、不要自怜、不要嫉妒、把逆风变成训练、押注少数真正机会
- 熄火状态：是否应该暂停常规通知，只保留低频重启提醒

### 通知模式

- `disabled`
  - 只生成，不发送
- `summary`
  - 发送摘要
- `smart`
  - 先判断值不值得打断，再发决策卡或摘要
- `full`
  - 发送完整正文

## 本地录入能力

本地录入页已经不是一个简单表单，而是轻量任务台。

当前支持：

- 记录完成任务
- 编辑和删除最近任务
- 常用分类按钮
- 最近 3 个分类记忆
- 一键 `MIT`
- 今天 / 现在开始 / 自动补结束时间
- 复制上一条时间配置
- 最近任务复用
- 以最近任务为变体起点
- 自动别名
- 手工别名的新增、载入、编辑、删除

目标是把“记一条完成事项”的摩擦压到足够低。

## 焦点档案、记忆和熄火机制

### 焦点档案

焦点档案决定系统现在该围绕什么来理解你的任务。

它包含：

- `current_focus`
- `current_stage`
- `coaching_mode`
- `coaching_notes`
- `active_priorities`
- `active_projects`
- `completed_items`
- `auto_dormancy`

### 复盘记忆

复盘记忆让系统不是每次都从零开始。

它会持续保留：

- 最近同周期摘要
- 高频复盘标签
- 上一轮跟进动作
- 关键指标变化

### 自动熄火

当系统发现你一段时间没有新的完成任务时：

- 进入休眠
- 停止常规通知
- 按间隔发送低频重启提醒
- 一旦有新的完成任务，再自动恢复

## CLI 速查

### 录入

```bash
python -m src.capture --help
python -m src.capture done "完成事项"
python -m src.capture recent --limit 10
python -m src.capture serve
```

### 复盘

```bash
python -m src.main --help
python -m src.main --period daily --dry-run
python -m src.main --period daily --yesterday --dry-run
python -m src.main --period weekly --notification-mode full
python -m src.main --period daily --coaching-mode sprint --dry-run
```

## GitHub Actions

当前工作流已经分层：

- `ci.yml`
  - 负责测试和基础检查
- `report-runner.yml`
  - 负责统一生成报告、预览、决策卡、元数据和 artifact
- `daily.yml`
  - 日报触发与调度
- `weekly.yml`
  - 周报触发与调度
- `monthly.yml`
  - 月报触发与调度

其中 `daily` 默认更偏保守，优先走 `smart` 模式，尽量减少无效提醒。

## 测试

运行测试：

```bash
pytest -q
python -m compileall src tests
```

当前测试主要覆盖：

- SQLite 任务存储与查询
- 本地录入命令与网页入口
- 状态统一存储与 JSON 导入
- 任务源切换
- Notion 适配
- 统计与趋势分析
- 干预引擎
- 通知模式
- 复盘服务编排

## 项目结构

```text
src/
  capture.py
  coaching_modes.py
  coaching_principles.py
  config.py
  engine_state.py
  focus_profile.py
  intervention_engine.py
  llm_client.py
  main.py
  models.py
  notifier.py
  notion_client.py
  review_memory.py
  review_service.py
  sqlite_state_store.py
  sqlite_task_store.py
  summarizer.py
  task_source.py
  web_capture.py
tests/
.github/workflows/
templates/
```

## 设计原则

- 代码是主系统，外部工具只是适配器
- 本地优先，SQLite 优先
- 先统一数据和状态，再做 prompt 和通知
- 先判断值不值得提醒，再发送内容
- 复盘要有记忆，不要每天重新认识用户一次
- 录入必须足够轻，否则再好的分析也会失效
