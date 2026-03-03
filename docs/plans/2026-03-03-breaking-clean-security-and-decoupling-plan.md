# Breaking Clean Security + Decoupling Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不保留兼容层的前提下，清除启动凭据泄露风险，并继续拆解 `WatcherService` 的混合职责，提升安全性与可维护性。

**Architecture:** 采用破坏式重构：将 bootstrap 口令从日志路径移除，改为一次性本地凭据文件；把 bootstrap 处理从 `reload_config` 主流程中抽离为专门方法；并统一配置/状态快照读取入口，减少服务层重复逻辑和隐式耦合。

**Tech Stack:** Python 3.12+, pytest/unittest, built-in http.server

---

### Task 1: Add failing tests for secure bootstrap flow

**Files:**
- Modify: `tests/test_webapp_api_smoke.py`

**Steps:**
1. 新增测试，断言首次启动不在日志里输出明文密码。
2. 新增测试，断言首次启动会生成 bootstrap 凭据文件，且后续设置正式账号后文件被清理。
3. 单测先运行并确认失败（RED）。

### Task 2: Refactor bootstrap auth handling out of reload_config

**Files:**
- Modify: `github_release_watcher/webapp.py`

**Steps:**
1. 抽取独立 bootstrap 处理方法，负责检测、持久化、写凭据文件与文件清理。
2. `reload_config()` 仅负责调用该流程并继续加载业务配置。
3. 保持首次登录强制改密语义，移除明文日志语义（GREEN）。

### Task 3: Continue backend decoupling with unified snapshot helpers

**Files:**
- Modify: `github_release_watcher/webapp.py`

**Steps:**
1. 提供统一配置快照读取 helper（含 fail-fast）。
2. 提供统一状态快照读取 helper。
3. 用 helper 收敛 repo/storage 查询路径重复代码，降低耦合并保证行为一致。

### Task 4: Verification

**Commands:**
- `python3 -m pytest -q tests/test_webapp_api_smoke.py`
- `python3 -m pytest -q -k "not download_integration"`
- `for f in github_release_watcher/static/*.js deploy/vercel/public/*.js; do node --check "$f"; done`
