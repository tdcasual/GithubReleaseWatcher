# GitHub Release 监控与自动备份工具

使用 Python 编写业务逻辑，调用 [gruntwork-io/fetch](https://github.com/gruntwork-io/fetch) 作为底层下载工具，定期监控多个 GitHub 仓库的 Release，并将符合规则的资产下载到本地按版本归档，同时支持保留最近 N 个版本并清理旧版本。

## 功能

- 支持配置多个 GitHub 仓库
- 定期检查每个仓库的最新 Release（支持一次性运行或常驻循环）
- 自动下载符合规则的 Release 资产到本地，并按版本归档
- 记录已下载版本与资产，避免重复下载
- 自动清理旧版本，只保留最近 N 个 Release

## 依赖

- Python 3.12+
- `fetch`（gruntwork-io/fetch）

安装 `fetch`：

- 从 Release 下载：<https://github.com/gruntwork-io/fetch/releases>
- 或 macOS/Linux（Homebrew）：`brew install fetch`

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

- `GET /api/v1/status`：运行状态、最近一次执行结果、当前配置（脱敏）
- `POST /api/v1/run`：触发一次检查/下载
- `PUT /api/v1/settings`：更新运行配置（写入 `config.override.json`）
- `PUT /api/v1/scheduler`：开启/关闭自动轮询

## 目录结构

默认会下载到 `download_dir/<owner>/<repo>/<tag>/`，例如：

`downloads/gruntwork-io/fetch/v0.4.6/`

每个版本目录下会写入 `release.json` 作为元数据标记。

## 配置说明（TOML）

- `interval_seconds`：轮询间隔（秒）
- `download_dir`：下载归档根目录（相对路径以配置文件所在目录为基准）
- `state_file`：下载状态记录文件（相对路径以配置文件所在目录为基准）
- `keep_last`：全局保留最近 N 个 Release（可被仓库级 `keep_last` 覆盖）
- `fetch_path`：`fetch` 可执行文件路径（默认使用 PATH 中的 `fetch`）
- `[github].token`：GitHub Token（可留空，工具也会读取环境变量 `GITHUB_TOKEN` / `GITHUB_OAUTH_TOKEN`）
- `[[repos]].name`：`owner/repo` 或完整仓库 URL
- `[[repos]].include_assets` / `exclude_assets`：资产名匹配规则（Python `re` 正则），`include_assets` 为空表示下载全部资产
- `[[repos]].enabled`：是否启用该仓库（默认 `true`）
- `[[repos]].asset_types`：按资产后缀筛选（如 `["exe","apk"]`，与 include/exclude 正则叠加生效）
