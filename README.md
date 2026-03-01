# GitHub Release 监控与自动备份工具

使用 Python 编写业务逻辑（纯 Python 下载，无外部下载工具依赖），定期监控多个 GitHub 仓库的 Release，并将符合规则的资产下载到本地按版本归档，同时支持保留最近 N 个版本并清理旧版本。

## 功能

- 支持配置多个 GitHub 仓库
- 定期检查每个仓库的最新 Release（支持一次性运行或常驻循环）
- 自动下载符合规则的 Release 资产到本地，并按版本归档
- 记录已下载版本与资产，避免重复下载
- 自动清理旧版本，只保留最近 N 个 Release
- Web 模式支持「按仓库自适应调度」：默认每仓库 2 天检查一次；若上次检查遇到网络错误，会在 2~6 小时内随机重试；并根据历史发布间隔自动延长检查频率以节省资源
- 每个仓库独立统计与活动页：下载次数、当前版本、清理记录、更新频率等

## 依赖

- Python 3.12+

建议（可选）：

- 配置环境变量 `GITHUB_TOKEN`（用于私有仓库或避免限流）

## 快速开始

1) 复制示例配置并按需修改：

`config.example.toml` → `config.toml`

2) 运行一次：

```bash
python3 watcher.py --config config.toml --once
```

或使用模块入口：

```bash
python3 -m github_release_watcher --config config.toml --once
```

3) 常驻运行（按 `interval_seconds` 周期轮询）：

```bash
python3 watcher.py --config config.toml
```

> 说明：CLI 常驻模式为「全仓库一起跑」的固定间隔轮询；若希望按仓库自适应调度与活动页，请使用下面的 Web 模式。

## Web 模式（API + 可选前端）

启动内置 Web 服务（默认带前端 UI）：

```bash
python3 watcher.py --config config.toml --web --web-host 127.0.0.1 --web-port 8000
```

打开：`http://127.0.0.1:8000/`

仅启用 API（不提供前端）：

```bash
python3 watcher.py --config config.toml --web --no-ui
```

主要 API：

- `POST /api/v1/login`：登录（默认 `admin/admin`，成功后设置 Cookie 会话）
- `POST /api/v1/logout`：退出登录
- `GET /api/v1/status`：运行状态、最近一次执行结果、当前配置（脱敏）
- `POST /api/v1/run`：触发一次检查/下载（可传 `{"repo":"owner/repo"}` 执行单仓库，或 `{"repos":["owner/repo","foo/bar"]}` 批量执行）
- `PUT /api/v1/settings`：更新运行配置（写入 `config.override.json`）
- `PUT /api/v1/scheduler`：开启/关闭自动轮询
- `GET /api/v1/repos`：仓库列表（包含统计、下次检查时间、推荐间隔）
- `GET /api/v1/repos/<owner>/<repo>`：单仓库统计
- `GET /api/v1/repos/<owner>/<repo>/activity?limit=...`：单仓库活动列表
- `GET /api/v1/repos/<owner>/<repo>/releases?limit=...`：单仓库已保存版本列表（来自 `state.json`）
- `POST /api/v1/storage/test`：测试 WebDAV 连通性（可传 `{"webdav":{...}}`）
- `GET /api/v1/storage/capabilities`：探测 WebDAV 能力（PROPFIND/MKCOL/PUT/DELETE/HEAD/MOVE）
- `GET /api/v1/storage/health`：查看上传健康统计（重试次数、校验失败、队列深度）
- `POST /api/v1/cleanup/preview`：预演清理结果（不实际删除）
- Web 页面：
  - 首页「活动」：仅展示下载/清理等关键动作（全局）
  - 首页「仓库与资产规则」支持名称搜索 + 状态筛选（启用/停用/异常/网络异常/缓存异常）以及批量选择（全选/反选/选中启用/选中异常/选中缓存异常）并批量检查、启停（“缓存异常”相关能力需先执行一次同步缓存）
  - 首页状态卡会显示上次执行范围（全量/单仓库/批量）和触发来源（手动/调度）
  - 设置页 WebDAV 诊断中的“同步缓存”会展示异常仓库 Top（可点击直达仓库活动页）
  - 仓库页「活动」：每个仓库独立记录检查/下载/清理等事件（`/repo.html?repo=owner/repo`）
  - 完整日志默认写入配置同目录的 `watcher.log`

## 部署

> 说明：本项目需要「长驻进程 + 持久化存储」来完成轮询与下载；Cloudflare Workers / Vercel 这类 Serverless 平台不适合直接运行 watcher 本体（执行时长/磁盘/后台任务限制）。
> 推荐做法：用 Docker/VM/NAS 长驻运行 watcher，然后用 Worker/Vercel 做 UI/API 反向代理（同源，Cookie 登录可用）。

### Docker（推荐）

1) 准备数据目录与配置（容器内统一使用 `/data`）：

```bash
mkdir -p data
cp config.example.toml data/config.toml
```

建议在 `data/config.toml` 中使用相对路径（相对配置文件目录解析），例如：

```toml
download_dir = "downloads"
state_file = "state.json"
```

2) 启动（Docker Compose）：

```bash
docker compose up -d --build
```

访问：`http://127.0.0.1:8000/`

或使用 `docker run`：

```bash
docker build -t github-release-watcher .
docker run --rm -p 8000:8000 -v "$PWD/data:/data" -e GITHUB_TOKEN="$GITHUB_TOKEN" github-release-watcher
```

> 数据会写入 `./data/`（如 `config.override.json`、`watcher.log`、`downloads/`、`state.json`）。
> 若遇到权限问题，可考虑给目录赋权或使用 `docker run --user "$(id -u):$(id -g)" ...`。

### Vercel（托管 UI + 代理 API）

前提：后端 watcher 需要在可长驻的环境运行（Docker/VM/NAS），并提供可访问的 Web 地址（建议 HTTPS）。

本仓库已提供 `deploy/vercel`（静态 UI + `/api/v1/*` 代理函数）：

1) 在 Vercel 导入仓库，Root Directory 选择 `deploy/vercel`
2) 配置环境变量：`UPSTREAM=https://your-backend.example.com`（不要以 `/` 结尾）
3) 部署后直接访问 Vercel 域名即可

### Cloudflare Worker（反向代理）

前提同上。使用 `deploy/cloudflare-worker` 作为反向代理，将你的后端 Web 服务“挂到” Cloudflare 上：

1) 安装并登录 `wrangler`：`npm i -g wrangler && wrangler login`
2) 修改 `deploy/cloudflare-worker/wrangler.toml` 的 `UPSTREAM=https://your-backend.example.com`
3) 可选加一层 Basic Auth（推荐用 secret）：`wrangler secret put BASIC_AUTH_PASS`（以及 `BASIC_AUTH_USER`）
4) 部署：`cd deploy/cloudflare-worker && wrangler deploy`

### 安全建议（强烈建议）

- 首次登录后必须修改默认账号密码（默认 `admin/admin`，系统会限制敏感操作直到完成改密）
- 暴露到公网建议再加一层访问控制（Cloudflare Zero Trust / BasicAuth / IP 白名单 / 反向代理鉴权等）
- 登录失败会触发限流（短时多次失败会返回 429）

## 测试

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## 收尾与发布文档

- 收尾执行计划：`docs/plans/2026-03-01-release-polish-plan.md`
- 发布验收清单：`docs/plans/2026-03-01-release-acceptance-checklist.md`
- Gate 2 真机验收执行套件：`docs/plans/2026-03-01-gate2-device-acceptance-kit.md`
- Gate 2 真机验收填写模板：`docs/plans/2026-03-01-gate2-device-acceptance-template.md`
- Gate 3 WebDAV 关键链路 runbook：`docs/plans/2026-03-01-gate3-webdav-critical-flow-runbook.md`
- 验收辅助脚本：
  - `scripts/qa/manual_acceptance_bootstrap.sh`
  - `scripts/qa/manual_acceptance_stop.sh`

## 2026-03-01 收尾更新摘要

- UI 与交互：
  - 首页批量工具栏支持“全选/反选当前筛选”“选中启用”“选中异常”“选中缓存异常”。
  - 状态卡新增“上次执行范围”（全量/单仓库/批量 + 触发来源）。
  - 批量按钮在禁用时给出明确原因，降低误操作与理解成本。
- 移动端 UI：
  - topbar 改为紧凑网格布局，筛选控件在窄屏自动改单列全宽。
  - 批量工具栏在 `<=640px` 两列排布，在 `<=420px` 自动降为单列。
  - repo 行操作区改为可换行并优先保障关键按钮可触达。
  - 底部导航增加当前区块高亮与平滑锚点滚动，减少长页面定位成本。
  - 对话框在移动端支持内容区滚动 + 操作栏底部粘附，降低长表单操作负担。
  - 弹窗打开时自动隐藏底部导航并锁定背景滚动，关闭后恢复，减少误触与视图跳动。
  - 关键反馈提示在移动端可自动滚动到可视区域，降低“操作后看不到结果”的认知成本。
  - 输入控件在移动端使用 16px 字号，减少 iOS Safari 自动缩放干扰。
  - 日志区域补充“可上下滑动查看更多”提示，并强化可滚动区域边界与触控滚动体验。
  - 触屏设备按钮按压反馈增强（缩放/亮度变化），提升触控确认感。
- WebDAV 能力与诊断：
  - “同步缓存”结果展示异常仓库 Top，并支持直达仓库活动页。
  - 新增“仅缓存异常”筛选与对应批量选择，并加前置条件守卫（WebDAV 模式 + 已有同步快照）。
- 可访问性基线：
  - 关键动态提示区域补齐 `aria-live/role=status`。
  - 设置/新增仓库对话框关闭后恢复焦点到触发控件（含兜底）。
  - 仓库行交互控件补充 `aria-label`，仓库页折叠按钮补充 `aria-expanded/aria-controls`，移动导航补充 `:focus-visible`。

发布前仍需人工完成：
- iOS Safari / Android Chrome 真机触控与布局验收。
- WebDAV 关键链路端到端人工走查（测试连接 -> 能力探测 -> 同步缓存 -> 缓存异常筛选/选中 -> 批量动作）。

## 目录结构

默认会下载到 `download_dir/<owner>/<repo>/<tag>/`，例如：

`downloads/gruntwork-io/fetch/v0.4.6/`

每个版本目录下会写入 `release.json` 作为元数据标记。

## 配置说明（TOML）

- `interval_seconds`：基础轮询间隔（秒）。Web 模式调度为「按仓库自适应」：每仓库下一次检查间隔 = `max(interval_seconds, median_release_interval * 1.1)`；若上次检查遇到网络错误，会在 2~6 小时内随机重试
- `download_dir`：下载归档根目录（相对路径以配置文件所在目录为基准）
- `state_file`：下载状态记录文件（相对路径以配置文件所在目录为基准）
- `keep_last`：全局保留最近 N 个 Release（可被仓库级 `keep_last` 覆盖）
- `[github].token`：GitHub Token（可留空，工具也会读取环境变量 `GITHUB_TOKEN` / `GITHUB_OAUTH_TOKEN`）
- `[[repos]].name`：`owner/repo` 或完整仓库 URL
- `[[repos]].include_assets` / `exclude_assets`：资产名匹配规则（Python `re` 正则），`include_assets` 为空表示下载全部资产
- `[[repos]].enabled`：是否启用该仓库（默认 `true`）
- `[[repos]].asset_types`：按资产后缀筛选（如 `["exe","apk"]`，与 include/exclude 正则叠加生效）

可选存储配置（WebDAV）：

- `[storage].mode`：`local`（默认）或 `webdav`
- `[storage.webdav].base_url`：WebDAV 根目录 URL（以 `/` 结尾更稳妥）
- `[storage.webdav].username` / `password`：WebDAV 账号密码（可留空；也可仅通过 Web 设置写入 `config.override.json`）
- `[storage.webdav].verify_tls`：是否校验 TLS（默认 `true`）
- `[storage.webdav].timeout_seconds`：请求超时（默认 `60`）
- `[storage.webdav].upload_concurrency`：上传并发（默认 `2`，范围 `1~32`）
- `[storage.webdav].max_retries`：上传失败重试次数（默认 `3`，范围 `1~20`）
- `[storage.webdav].retry_backoff_seconds`：重试退避基础秒数（默认 `2`，范围 `1~300`）
- `[storage.webdav].verify_after_upload`：上传后是否校验远端文件（默认 `true`）
- `[storage.webdav].upload_temp_suffix`：临时上传后缀（默认 `.uploading`）
- `[storage.webdav].cleanup_mode`：清理模式，`delete`（直接删除）或 `trash`（移动到 `.trash`）
