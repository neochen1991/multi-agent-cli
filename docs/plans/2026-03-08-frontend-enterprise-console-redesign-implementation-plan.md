# Frontend Enterprise Console Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将前端首页、故障分析页和关键公共组件重构为企业控制台风格，并保留现有业务能力与数据联动。

**Architecture:** 先产出静态效果稿，锁定布局和视觉 token；再重构全局 shell、首页和故障分析页；最后收敛责任田、历史、设置等辅助页面。保留 Ant Design 组件体系，不重写基础组件库。

**Tech Stack:** React 18, TypeScript, Vite, Ant Design 5, Figma MCP

---

### Task 1: 产出 Figma 效果稿

**Files:**
- Create: `/Users/neochen/multi-agent-cli_v2/frontend/public/figma-mockups/console-home.html`
- Create: `/Users/neochen/multi-agent-cli_v2/frontend/public/figma-mockups/incident-workbench.html`
- Create: `/Users/neochen/multi-agent-cli_v2/frontend/public/figma-mockups/mockups.css`

**Step 1:** 编写首页静态效果稿

**Step 2:** 编写故障分析页静态效果稿

**Step 3:** 使用 Figma MCP 抓取到新文件，完成首页与分析页设计稿

### Task 2: 重构全局视觉系统

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/styles/global.css`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/common/Sider/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/common/Header/index.tsx`

**Step 1:** 重写全局 token、背景、边框、阴影和布局约束

**Step 2:** 重构页头与侧边栏的企业控制台样式

**Step 3:** 校验桌面端与小屏布局

### Task 3: 重构首页

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Home/index.tsx`

**Step 1:** 调整首页信息架构

**Step 2:** 重构快速创建分析和状态摘要模块

**Step 3:** 重构事件列表和 Agent 能力矩阵

### Task 4: 重构故障分析工作台

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DialogueStream.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DebateProcessPanel.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/AssetMappingPanel.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DebateResultPanel.tsx`

**Step 1:** 将分析页改为左中右三栏调查台

**Step 2:** 重构对话流，区分主 Agent、专家 Agent、工具证据和结论

**Step 3:** 调整责任田映射和辩论结果的阅读路径

### Task 5: 收口辅助页面

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Assets/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/History/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Settings/index.tsx`

**Step 1:** 重构责任田页为资产总览 + 导入维护

**Step 2:** 收紧历史页交互

**Step 3:** 调整设置页为折叠分组控制台
