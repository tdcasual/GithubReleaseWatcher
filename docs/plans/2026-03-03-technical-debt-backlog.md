# GithubReleaseWatcher 技术债执行 Backlog（2026-03-03）

> 基于当前仓库实测与历史提交（截至 2026-03-03）整理。
> 目标是把“结构可用但演进成本高”的状态，收敛到“可持续演进、回归可控、流程无噪声”。

## 0. 执行原则

1. 先还高利息债：先流程与可靠性，再做结构洁癖。
2. 每个条目必须有可执行验收命令。
3. 禁止大包提交：每个条目单独 commit，保持可回滚。
4. 行为不变优先：重构不改对外 API 契约。
5. 本地产物零入库：防止持续制造新债。

## 1. 债务优先级总览

| ID | 优先级 | 债务类型 | 问题摘要 | 预估 |
|---|---|---|---|---|
| TD-001 | P0 | 流程/仓库卫生 | `.playwright-cli`、本地状态文件被追踪，仓库噪声高 | 0.5 天 |
| TD-002 | P1 | 运行时可靠性 | 运行队列是“单槽拒绝模型”，请求容易被丢弃 | 1.5 天 |
| TD-003 | P1 | 架构边界 | `WatcherService` 仍是胖服务，职责过宽 | 2 天 |
| TD-004 | P1 | 状态演进 | `state.json` 缺 schema 迁移，异常时回退空状态 | 2 天 |
| TD-005 | P2 | 配置一致性 | config/payload/settings/overrides 校验规则重复 | 1.5 天 |
| TD-006 | P2 | 前端架构 | 全局 `window` 注入 + 手工装配，静态约束弱 | 2 天 |
| TD-007 | P2 | 测试策略 | 文本断言偏多，行为回归覆盖不足 | 2 天 |
| TD-008 | P2 | CI 质量门禁 | CI 只覆盖部分脚本语法，拆分模块未全面守卫 | 1 天 |
| TD-009 | P2 | 安全基线 | 默认账号密码路径仍暴露，公网误配风险 | 1 天 |
| TD-010 | P3 | 观测能力 | 指标仅基础计数，缺关键 SLO 视角 | 1 天 |

## 2. 四周执行节奏

### Week 1（止血周）

- 目标：停止新增技术债，并提升运行入口稳定性。
- 范围：TD-001、TD-002、TD-008（部分）。

### Week 2（边界周）

- 目标：收窄后端职责边界，降低单点修改风险。
- 范围：TD-003、TD-005。

### Week 3（可靠性周）

- 目标：完成状态演进治理与回归补盲。
- 范围：TD-004、TD-007。

### Week 4（收口周）

- 目标：前端与安全收口，补足观测可运营性。
- 范围：TD-006、TD-009、TD-010。

## 3. 详细 Backlog（可直接开工）

### TD-001（P0）清理仓库本地产物与忽略策略

**问题**

- `.playwright-cli/*` 与本地状态样本进入版本库，污染提交历史和审查视野。

**涉及文件**

- `/.gitignore`
- `/.playwright-cli/*`（从跟踪中移除）
- `/real_state 2.json`（从跟踪中移除）
- 可选：新增 `/.gitattributes`（标记大二进制 diff 策略）

**实施步骤**

1. 扩展 `.gitignore`，加入 `.playwright-cli/`、`config.toml`、`real_state 2.json`。
2. 仅从 Git 索引移除已有 tracked 本地产物（不删本地文件）。
3. 增加 CI 守卫：若新增 `.playwright-cli/` 跟踪文件则失败。
4. 在 README 增加“本地产物不可入库”约定。

**验收命令**

```bash
git ls-files | rg '^\.playwright-cli/'
git ls-files | rg 'real_state 2\.json|config\.toml'
```

期望：无输出。

---

### TD-002（P1）将运行队列从“单槽拒绝”升级为“可排队去重”

**问题**

- 当前 `RunQueueService` 在已请求/运行中时直接拒绝新请求，吞吐与可预测性不足。

**涉及文件**

- `/github_release_watcher/run_queue.py`
- `/github_release_watcher/webapp.py`
- `/tests/test_run_queue.py`
- `/tests/test_webapp_api_smoke.py`

**实施步骤**

1. 引入有限队列（例如 `max_pending`）与请求去重键（全量/单仓库/批量）。
2. API 返回明确状态：`accepted`、`deduplicated`、`rejected_overflow`。
3. 保留现有行为兼容字段，避免前端立即破坏。
4. 为边界条件补测试：重复入队、队列满、批量+单仓混合。

**验收命令**

```bash
python3 -m pytest -q tests/test_run_queue.py tests/test_webapp_api_smoke.py
```

期望：全部通过。

---

### TD-003（P1）继续拆分 `WatcherService` 的聚合职责

**问题**

- `WatcherService` 仍承载配置、状态聚合、缓存诊断、调度协同等多职责。

**涉及文件**

- `/github_release_watcher/webapp.py`
- 新增：`/github_release_watcher/repo_query_service.py`
- 新增：`/github_release_watcher/storage_health_service.py`
- `/tests/test_webapp_api_contract.py`
- `/tests/test_webapp_api_smoke.py`

**实施步骤**

1. 抽离 repo 查询相关方法（summary/activity/releases）。
2. 抽离 storage 统计与 cache sync 逻辑。
3. `webapp.py` 仅保留 orchestration，不直接做大段数据变换。
4. 维持 API 响应字段不变，快照测试保护契约。

**验收命令**

```bash
python3 -m pytest -q tests/test_webapp_api_contract.py tests/test_webapp_api_smoke.py tests/test_line_budgets.py
```

期望：全部通过，且 `webapp.py` 行数不回升。

---

### TD-004（P1）为 `state.json` 增加版本迁移链路

**问题**

- 版本不匹配时直接回空状态，历史信息不可演进。

**涉及文件**

- `/github_release_watcher/state.py`
- 新增：`/github_release_watcher/state_migrations.py`
- `/tests/test_state_robustness.py`
- 新增：`/tests/test_state_migrations.py`

**实施步骤**

1. 定义 `STATE_VERSION` 迁移策略（v1 -> v2 可扩展）。
2. `load_state` 在可迁移场景执行迁移，而非直接清空。
3. 损坏文件保留备份行为不变。
4. 记录迁移元信息，便于排障。

**验收命令**

```bash
python3 -m pytest -q tests/test_state_robustness.py tests/test_state_migrations.py
```

期望：迁移成功且异常路径可回退。

---

### TD-005（P2）统一配置校验规则，消除多处重复

**问题**

- `config.py`、`webapp_payloads.py`、`settings_service.py`、`webapp_overrides.py` 存在同类校验重复。

**涉及文件**

- 新增：`/github_release_watcher/config_validation.py`
- `/github_release_watcher/config.py`
- `/github_release_watcher/settings_service.py`
- `/github_release_watcher/webapp_overrides.py`
- `/github_release_watcher/webapp_payloads.py`
- 新增：`/tests/test_config_validation_unified.py`

**实施步骤**

1. 抽出统一校验函数（storage mode/webdav suffix/asset types/int ranges）。
2. 让 4 个入口共享同一套规则。
3. 用参数化测试覆盖一致性。

**验收命令**

```bash
python3 -m pytest -q tests/test_config_unknown_keys.py tests/test_webdav_reliability.py tests/test_settings_service.py tests/test_config_validation_unified.py
```

期望：规则一致，无入口漂移。

---

### TD-006（P2）前端模块边界收敛（不引入框架）

**问题**

- 全局注入与手工 wiring 依赖顺序脆弱，静态约束不足。

**涉及文件**

- `/github_release_watcher/static/app-runtime.js`
- `/github_release_watcher/static/app-events.js`
- `/github_release_watcher/static/index.html`
- `/tests/test_frontend_module_split.py`
- 新增：`/tests/test_frontend_bootstrap_contract.py`

**实施步骤**

1. 定义唯一 bootstrap 协议（模块导出能力列表 + 版本号）。
2. 将 `app-events` 依赖参数按 domain 拆包，减小 options 巨对象。
3. 增加启动前契约检查测试。

**验收命令**

```bash
python3 -m pytest -q tests/test_frontend_module_split.py tests/test_frontend_bootstrap_contract.py tests/test_line_budgets.py
node --check github_release_watcher/static/app.js
action="github_release_watcher/static/app-runtime.js"; node --check "$action"
```

期望：通过且启动契约明确。

---

### TD-007（P2）从“文本断言”补到“行为回归”

**问题**

- 现有前端测试较多依赖字符串包含，行为覆盖不足。

**涉及文件**

- `/tests/test_frontend_module_split.py`
- `/tests/test_repo_page_shared_modules.py`
- 新增：`/tests/test_webapp_end_to_end_minimal.py`
- 新增：`/scripts/qa/smoke_api_flow.sh`

**实施步骤**

1. 保留必要文本断言，但减少作为主验证手段。
2. 增加端到端最小流：登录 -> 读取状态 -> 触发 run -> 查询 repos。
3. 让行为测试可在本地 deterministic 运行（mock/fake）。

**验收命令**

```bash
python3 -m pytest -q tests/test_webapp_end_to_end_minimal.py tests/test_webapp_api_smoke.py
bash scripts/qa/smoke_api_flow.sh
```

期望：关键用户路径可复现。

---

### TD-008（P2）加强 CI 质量门禁覆盖

**问题**

- CI 目前只检查部分 JS 入口，模块拆分后的文件未全覆盖。

**涉及文件**

- `/.github/workflows/ci.yml`
- `/tests/test_ci_presence.py`
- 新增：`/tests/test_ci_checks_modules.py`

**实施步骤**

1. CI 增加对 `static/*.js` 与 `deploy/vercel/public/*.js` 的全量 `node --check`。
2. 加一个轻量契约检查：`sync_vercel_public` 后哈希一致。
3. 将本地产物入库检测加入 CI。

**验收命令**

```bash
python3 -m pytest -q tests/test_ci_presence.py tests/test_ci_checks_modules.py tests/test_vercel_static_sync.py
```

期望：CI 能拦截结构漂移与产物污染。

---

### TD-009（P2）安全基线收口（默认口令路径降风险）

**问题**

- 默认账号密码路径在 UI/文档显式存在，尽管有强制改密。

**涉及文件**

- `/github_release_watcher/auth_service.py`
- `/github_release_watcher/webapp_api_router.py`
- `/github_release_watcher/static/index.html`
- `/README.md`
- `/tests/test_auth_security.py`

**实施步骤**

1. 明确首次启动初始化口令流程（随机初始口令或必须显式设置）。
2. 将“默认口令提示”改成“首次初始化提示”。
3. 文档补公网暴露最低安全清单。

**验收命令**

```bash
python3 -m pytest -q tests/test_auth_security.py tests/test_webapp_api_smoke.py
```

期望：无固定默认弱口令路径。

---

### TD-010（P3）观测能力补齐为可运营指标

**问题**

- 现有 metrics 只到基础计数，不足以支撑排障与容量判断。

**涉及文件**

- `/github_release_watcher/metrics.py`
- `/github_release_watcher/webapp.py`
- 新增：`/tests/test_runtime_metrics_extended.py`
- 更新快照：`/tests/snapshots/status_shape.json`

**实施步骤**

1. 增加关键指标：队列长度分布、运行耗时分位、最近失败类型计数。
2. 保持 `snapshot().metrics` 后向兼容。
3. 对新增字段做契约快照更新。

**验收命令**

```bash
python3 -m pytest -q tests/test_runtime_metrics.py tests/test_runtime_metrics_extended.py tests/test_webapp_api_contract.py
```

期望：观测字段可用于日常运维决策。

## 4. 每周完成定义（Definition of Done）

### Week 1 DoD

1. `TD-001`、`TD-002`、`TD-008(部分)` 合并到主干。
2. 仓库中不再跟踪本地产物。
3. 稳定回归命令可一键通过。

### Week 2 DoD

1. `WatcherService` 至少拆出 2 个查询/诊断服务。
2. API 契约快照无破坏性变更。

### Week 3 DoD

1. 状态迁移链路可验证。
2. 新增行为级回归测试进入 CI。

### Week 4 DoD

1. 前端 bootstrap 契约稳定。
2. 安全基线完成升级。
3. 扩展指标上线并可读取。

## 5. 全局验收命令（每周末）

```bash
bash scripts/release/sync_vercel_public.sh
python3 -m pytest -q -k "not download_integration"
node --check github_release_watcher/static/app.js
node --check github_release_watcher/static/repo.js
node --check deploy/vercel/public/app.js
node --check deploy/vercel/public/repo.js
```

## 6. 风险与回滚策略

1. 每个 TD 单独 commit，不混入跨条目改动。
2. 若 API 契约变更误伤，优先回滚最近一条 refactor commit。
3. 回滚不触碰数据目录：`state.json`、`config.override.json`、下载目录只读保留。
4. 任何涉及调度/队列语义修改，必须先补测试再改实现。

