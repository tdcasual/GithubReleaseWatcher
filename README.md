# GitHub Release 监控与自动备份工具

使用 Python 编写业务逻辑（纯 Python 下载，无外部下载工具依赖），定期监控多个 GitHub 仓库的 Release，并将符合规则的资产下载到本地按版本归档，同时支持保留最近 N 个版本并清理旧版本。

## 功能

- 支持配置多个 GitHub 仓库
- 定期检查每个仓库的最新 Release（支持一次性运行或常驻循环）
- 自动下载符合规则的 Release 资产到本地，并按版本归档
- 记录已下载版本与资产，避免重复下载
- 自动清理旧版本，只保留最近 N 个 Release

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
- `POST /api/v1/run`：触发一次检查/下载（可传 `{"repo":"owner/repo"}` 仅执行单个仓库）
- `PUT /api/v1/settings`：更新运行配置（写入 `config.override.json`）
- `PUT /api/v1/scheduler`：开启/关闭自动轮询
- `POST /api/v1/storage/test`：测试 WebDAV 连通性（可传 `{"webdav":{...}}`）
- Web 页面「活动」：仅展示下载/清理等关键动作；完整日志默认写入配置同目录的 `watcher.log`

## 测试

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## 目录结构

默认会下载到 `download_dir/<owner>/<repo>/<tag>/`，例如：

`downloads/gruntwork-io/fetch/v0.4.6/`

每个版本目录下会写入 `release.json` 作为元数据标记。

## 配置说明（TOML）

- `interval_seconds`：轮询间隔（秒）
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
