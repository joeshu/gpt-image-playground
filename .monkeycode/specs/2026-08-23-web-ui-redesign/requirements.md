# Web UI 设计需求

## 介绍

本需求定义 GPT Image Playground Web 端的工作台 UI、视觉资产和响应式布局方案。目标是将现有功能组织为以图像画布为中心的创作工作台，覆盖图片生成、Agent 编排、任务历史、画廊管理、图片详情和 Provider 设置。

## 术语

- **创作工作台**：用户输入提示词、选择生成参数并提交图片任务的主界面。
- **画布**：展示当前生成结果、画廊图片和任务状态的主要视觉区域。
- **输入栏**：承载提示词、参考图、快捷参数和提交操作的生成控制区域。
- **任务卡片**：展示图片、任务状态、收藏状态和选择状态的图片单元。
- **详情弹窗**：展示图片预览、任务元数据及图片操作的模态视图。
- **视觉资产**：品牌标记、图标、状态标识、空状态图形和交互反馈元素。

## 需求

### 需求 1：创作工作台

**用户故事：** 作为图片创作者，我希望在一个连续的工作台中输入提示词和参数，以便快速完成图片生成。

#### 验收标准

1. WHEN 用户进入创建图片视图，系统 SHALL 显示顶部 Header、页面标题、画布区域和输入栏。
2. WHILE 用户编辑提示词，系统 SHALL 保持输入栏中的提示词、Profile、画布比例、质量和风格状态。
3. WHEN 用户选择单张、批量或 Agent 模式，系统 SHALL 更新输入提示、提交标签和参数说明。
4. WHEN 用户提交有效任务，系统 SHALL 在画布区域显示任务状态，并在任务完成后显示生成结果。

### 需求 2：画廊与任务网格

**用户故事：** 作为图片创作者，我希望按任务和图片浏览生成结果，以便管理创作资产。

#### 验收标准

1. WHEN 用户进入画廊视图，系统 SHALL 按网格展示可用图片，并显示图片标识和收藏状态。
2. WHEN 用户输入搜索词，系统 SHALL 根据图片标识或任务文本过滤任务卡片。
3. WHEN 用户选择收藏或已选筛选器，系统 SHALL 仅展示符合当前筛选条件的任务卡片。
4. WHEN 用户选择一个或多个任务卡片，系统 SHALL 显示明确的选中状态和批量操作区域。
5. WHEN 用户点击图片卡片，系统 SHALL 打开对应的详情弹窗。

### 需求 3：详情与任务历史

**用户故事：** 作为图片创作者，我希望查看图片和任务上下文，以便判断结果并继续创作。

#### 验收标准

1. WHEN 用户打开图片详情，系统 SHALL 显示图片预览、结果序号、来源、下载操作和新窗口打开操作。
2. WHEN 用户打开历史弹窗，系统 SHALL 显示可搜索的任务列表、任务状态和任务时间。
3. WHEN 用户打开历史任务详情，系统 SHALL 显示任务状态和提示词，并清理当前图片详情中的旧图片状态。
4. WHEN 用户关闭任一弹窗，系统 SHALL 恢复打开弹窗前的焦点位置和页面滚动状态。
5. WHEN 用户按下 Escape 或点击遮罩区域，系统 SHALL 关闭当前弹窗。

### 需求 4：视觉语言与资产

**用户故事：** 作为产品使用者，我希望界面拥有稳定、克制且适合图片创作的视觉语言，以便持续专注于图像内容。

#### 验收标准

1. The Web UI SHALL use a restrained editorial visual language with warm neutral surfaces, high-contrast typography, and thin structural borders.
2. The Web UI SHALL use consistent visual states for ready, running, completed, failed, selected, and favorite tasks.
3. The Web UI SHALL provide a text-based fallback for every decorative visual asset.
4. The Web UI SHALL keep primary actions visually distinct from secondary actions across desktop and mobile layouts.

### 需求 5：响应式与可访问性

**用户故事：** 作为桌面端或移动端用户，我希望在不同屏幕尺寸下完成核心操作，以便在不同环境中使用工作台。

#### 验收标准

1. WHEN viewport width is at least 1200px, the system SHALL display the full navigation rail, canvas grid, and docked input bar.
2. WHEN viewport width is between 701px and 1199px, the system SHALL collapse navigation labels while retaining accessible labels and icons.
3. WHEN viewport width is at most 700px, the system SHALL stack the canvas and input controls and preserve access to generation, gallery, history, and settings.
4. WHILE a modal is open, the system SHALL lock background scrolling and keep keyboard focus inside the modal.
5. WHEN an interactive control receives keyboard focus, the system SHALL display a visible focus indicator.

### 需求 6：安全与数据呈现

**用户故事：** 作为本地工作台用户，我希望连接状态清晰且敏感信息受到保护，以便安全配置 Provider。

#### 验收标准

1. WHEN the Web UI displays Provider status, the system SHALL show configured state, host information, and connection health without displaying secret values.
2. WHEN the user submits an API key, the system SHALL clear the key input after a successful save.
3. The Web UI SHALL present browser token persistence as an explicit user-controlled setting.
4. The Web UI SHALL show actionable status feedback for loading, success, and failure states.

## 视觉资产清单

- `GI` 品牌标记：几何字母组合，适用于侧栏和移动端 Header。
- 导航图标：创建、画廊、历史、设置，使用统一 1.5px 线性图标。
- 状态点：使用颜色和文本双重表达连接状态。
- 任务标签：显示任务序号、状态和收藏状态。
- 空画布图形：使用低对比度几何网格或纸张构图线，避免引入具体产品图片。
- 参考图缩略图：统一尺寸、圆角和边框，支持键盘可见焦点。
- 弹窗遮罩：使用半透明深色遮罩和轻微背景模糊。
- 操作反馈：使用短文本状态条和按钮禁用状态表达请求进度。

## 约束

- 保持现有 `web/index.html` 单文件入口和 Python API 服务。
- 保持现有 `/v1/generate`、`/v1/batch`、`/v1/agent`、`/v1/history`、`/v1/gallery`、`/v1/setup` 接口契约。
- 保持 Native、Batch、Agent 三种生成模式。
- API Key 不进入前端源码、浏览器响应、任务文件或历史数据。
- 设计方案使用现有本地工作区路径和预览服务。
