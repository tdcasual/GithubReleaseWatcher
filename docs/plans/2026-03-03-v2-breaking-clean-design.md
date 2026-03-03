# 2026-03-03 V2 Breaking-Clean Design

## 1. Goal And Decision Record

### 1.1 Goal

在不保留兼容层的前提下，完成从 V1 到 V2 的彻底重建，目标为：

- 干净整洁：移除历史双写、双目录、隐式耦合和运行时兼容分支。
- 健壮：统一任务状态机、统一错误分类、统一重试策略。
- 解耦：分离 API / 应用编排 / 领域规则 / 基础设施适配器。
- 易扩展：新增存储后端、调度策略、UI 功能时不需要改核心路径。

### 1.2 Hard Decisions (Confirmed)

- 技术栈升级为 `FastAPI + TypeScript` 前后端工程化。
- 采用 Breaking-Clean 路线，不保留运行时兼容层。
- V2 切流完成后，仓库中完全删除 V1 运行代码和旧发布链路。
- 仅允许一次性离线导入工具，不允许线上读取 V1 格式。

### 1.3 Non-Goals

- 不做“旧 API 保持可用”的兼容承诺。
- 不做“旧 state/config 自动在线迁移”。
- 不做“边迁移边双跑长期共存”的中间方案。

## 2. Architecture (V2 Target State)

### 2.1 Layered Monolith With Strict Boundaries

V2 架构分为四层，所有调用单向流动：

1. `API Layer`  
   FastAPI 路由、鉴权、DTO 解析、响应组装。仅处理 HTTP 语义，不落业务规则。
2. `Application Layer`  
   用例编排（触发检查、批量运行、清理预演、状态查询）。只调用接口，不依赖具体实现。
3. `Domain Layer`  
   纯业务策略（版本筛选、资产匹配、保留策略、错误分类、调度规则）。
4. `Infrastructure Layer`  
   GitHub/WebDAV/LocalFS/DB/任务执行器等适配器实现。

### 2.2 Runtime Model

- 单一作业模型：`job` 作为唯一执行单位。
- 单一状态机：`queued -> running -> succeeded|failed|canceled`。
- 单一重试入口：由任务执行器处理退避和最大重试，不允许业务代码内 `sleep + retry`。
- 单一观测流：结构化事件和指标从作业生命周期自动产出。

### 2.3 Replace Current Hotspots

V2 直接替代当前热点复杂区域：

- 取代 [watcher.py](/Users/lvxiaoer/Documents/GithubReleaseWatcher/github_release_watcher/watcher.py) 的巨型流程函数组合。
- 拆解 [webapp.py](/Users/lvxiaoer/Documents/GithubReleaseWatcher/github_release_watcher/webapp.py) 的聚合职责中心。
- 终止 `window.GRW*` 全局注入模式，重建前端模块边界。

## 3. Data Model, Flow, Error Handling

### 3.1 Storage Strategy

V2 使用 SQLite + Alembic（单机稳定、迁移可控），核心表：

- `repos`：仓库配置、启停、策略参数。
- `release_checks`：每次检查任务的执行摘要。
- `releases`：版本元数据。
- `assets`：资产下载、上传、校验结果。
- `cleanup_actions`：清理执行记录。
- `jobs`：任务状态机主表。
- `events`：结构化事件流。
- `auth_users` / `sessions`：认证和会话。

### 3.2 Read/Write Separation

- 写路径以 `jobs/events` 为主，确保可追溯。
- 读路径使用聚合查询模型，避免 API 每次直接扫原始日志。
- 禁止在查询服务中隐式读磁盘状态文件。

### 3.3 Error Taxonomy

所有错误归一为三类：

- `retryable`：网络抖动、短期限流、可恢复外部错误。
- `non_retryable`：配置非法、参数错误、资源不存在、鉴权失败。
- `bug`：未捕获异常或不变量破坏。

重试器只对 `retryable` 生效，避免重复执行不可恢复请求。

## 4. Frontend Engineering Plan

### 4.1 Frontend Source Of Truth

- 建立独立 `frontend/` 工程（TypeScript）。
- 构建产物输出到单一目录（例如 `frontend/dist`）。
- 后端静态服务只读取该唯一产物目录。

### 4.2 Remove Existing Duplication

删除当前双目录同步模式：

- [github_release_watcher/static](/Users/lvxiaoer/Documents/GithubReleaseWatcher/github_release_watcher/static)
- [deploy/vercel/public](/Users/lvxiaoer/Documents/GithubReleaseWatcher/deploy/vercel/public)
- [scripts/release/sync_vercel_public.sh](/Users/lvxiaoer/Documents/GithubReleaseWatcher/scripts/release/sync_vercel_public.sh)

V2 不再允许“源码目录复制部署目录”的维护方式。

### 4.3 Contract Strategy

- 前后端共享 API schema（OpenAPI 生成 types）。
- 不保留 V1 字段和旧响应形状。
- 所有页面交互以 typed client 调用 API。

## 5. Cutover Strategy And V1 Full Deletion

### 5.1 Two-Phase Hard Cut

1. 阶段 A：在隔离环境完成 V2 全功能验收。  
2. 阶段 B：切流窗口执行停 V1、备份、导入、切换、验证、删除。

### 5.2 One-Time Offline Import Only

- 提供一次性导入脚本：读取 V1 配置和状态，转换入 V2 表结构。
- 导入完成后生成核对报告（repo 数、版本数、资产数、关键统计）。
- V2 运行时不得再读取 V1 文件格式。

### 5.3 V1 Deletion Scope (Mandatory)

切流成功后，必须从主分支删除：

- V1 Web/API 入口与服务实现。
- V1 任务执行与调度实现。
- V1 静态页面和双目录发布逻辑。
- V1 兼容字段、兼容测试、兼容文档。

## 6. Milestones And Acceptance Gates

### Milestone A: Skeleton

- FastAPI、DB、Job runner、TS 前端框架搭建。
- 跑通最小链路：`login -> repos -> enqueue -> worker -> events`。

### Milestone B: Core Capability

- Release 拉取、资产过滤、下载、清理、WebDAV/Local 适配器完成。
- 完成后端集成测试和最小 e2e。

### Milestone C: Offline Import

- V1 到 V2 的一次性离线导入工具完成并验证。

### Milestone D: Cutover + Deletion

- 在同一窗口完成切流与 V1 删除。

### Definition Of Done

- 主分支不含 V1 运行代码。
- 无兼容读取逻辑。
- 无双目录静态同步脚本。
- 文档仅描述 V2。
- CI 门禁全部通过。

## 7. CI Guardrails (Anti-Regression)

新增强制检查：

- 禁止出现 V1 目录与旧路由前缀。
- 禁止出现 `window.GRW` 旧全局模块命名。
- 禁止 `state.json` 运行时依赖。
- API schema snapshot 只允许 V2。
- 数据库 migration 前后校验必须通过。

若触发任何旧模式残留，CI 直接失败。

## 8. Risks And Controls

- 风险：Big-Bang 切流窗口失败影响可用性。  
  控制：切前冷备 + 演练 + 明确回滚镜像。

- 风险：离线导入数据不完整。  
  控制：导入后自动核对报告与抽样比对。

- 风险：团队在实现中“临时加兼容”。  
  控制：CI 守卫 + 代码评审 checklist 明确禁止。

## 9. Implementation Readiness

设计已完成并确认以下约束：

- 使用 `FastAPI + TypeScript`。
- 运行时零兼容。
- V2 完成后完全删除 V1。

下一步进入实现前准备：建立隔离分支/工作树，产出详细实施计划并拆分任务。
