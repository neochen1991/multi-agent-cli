# Project Intro PPT Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 生成一份面向团队内部培训的“项目架构讲解”PPT，基于 `docs/wiki/code_wiki_v2.md`，沿用已确认的 war-room briefing 视觉风格。

**Architecture:** 复用仓库内现有 `python-pptx` 生成方案，不依赖外部设计工具。PPT 采用“架构主线型”叙事：先讲目标与价值，再讲系统分层、端到端流程、LangGraph 运行时、多 Agent、Tool/Skill/Connector、前端战情页、可靠性与扩展路径，最终输出战情简报风 PPTX 和配套说明文件。

**Tech Stack:** Python 3、python-pptx、本地 Markdown 文档、仓库现有 war-room 视觉语言

---

### Task 1: 固化 PPT 结构与内容映射

**Files:**
- Create: `/Users/neochen/multi-agent-cli_v2/docs/plans/2026-03-06-project-intro-ppt-design.md`
- Reference: `/Users/neochen/multi-agent-cli_v2/docs/wiki/code_wiki_v2.md`
- Reference: `/Users/neochen/multi-agent-cli_v2/AGENTS.md`

**Step 1: 提炼 12-14 页结构**

覆盖：
- 系统目标与业务价值
- 整体分层架构
- 前端工作台架构
- 后端接入与服务流
- LangGraph 运行时架构
- 多 Agent 协作图
- Tool / Skill / Connector
- 端到端分析流程
- 状态与事件流
- 报告与结果视图
- 可靠性治理与 Benchmark
- 扩展路径与阅读建议

**Step 2: 定义每页的视觉类型**

每页只能有一个主结论，优先使用：
- 分层图
- 网络图
- 流程链路
- 指标卡
- 能力矩阵

**Step 3: 定义固定输出目录**

输出到：
- `/Users/neochen/multi-agent-cli_v2/output/project-intro-warroom-ppt/`

### Task 2: 实现新的 war-room 风格项目介绍生成器

**Files:**
- Create: `/Users/neochen/multi-agent-cli_v2/scripts/generate_project_intro_warroom_ppt.py`
- Reference: `/Users/neochen/multi-agent-cli_v2/scripts/generate_vibe_coding_warroom_ppt.py`
- Reference: `/Users/neochen/multi-agent-cli_v2/scripts/generate_project_intro_ppt_suite.py`

**Step 1: 复用现有主题系统**

保留：
- 深色背景
- 高对比卡片
- 顶部导航条
- Source 页脚

**Step 2: 重写内容与图示**

针对本项目替换为：
- 系统架构图
- 端到端分析流程图
- 多 Agent 协作图
- 工具 / Skill / Connector 图
- 前端页面结构图
- 可靠性与治理页

**Step 3: 生成配套产物**

输出：
- `project-intro-warroom.pptx`
- `slides.md`
- `notes.md`
- `refs.md`
- `README.md`

### Task 3: 生成、校验并交付

**Files:**
- Output: `/Users/neochen/multi-agent-cli_v2/output/project-intro-warroom-ppt/*`

**Step 1: 运行生成脚本**

Run:
```bash
python3 /Users/neochen/multi-agent-cli_v2/scripts/generate_project_intro_warroom_ppt.py
```

Expected:
- 输出目录存在
- PPTX 文件成功生成

**Step 2: 做基础校验**

校验项：
- 页数是否落在 12-14 页
- 标题和内容是否对齐 `code_wiki_v2`
- 非纯文字页占比足够
- 页脚是否带源码 / 文档来源

**Step 3: 输出交付结果**

交付时说明：
- 输出文件路径
- 这版 PPT 的结构
- 如需继续精修，优先优化哪些页面
