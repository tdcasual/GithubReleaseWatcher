# Gate 2 真机验收执行脚本与流程（Desktop + Mobile）

目标：给发布前 Gate 2（桌面与移动核心流程）提供可重复执行的人工验收脚本与证据采集流程。

---

## 1. 适用范围

- 首页核心流程：登录、状态卡、仓库筛选、批量操作、设置对话框、活动日志。
- 设备覆盖：
  - Desktop：至少 1 台（推荐 macOS 或 Windows）
  - Mobile：至少 2 台（iOS Safari + Android Chrome）

---

## 2. 快速启动脚本

在仓库根目录执行：

```bash
scripts/qa/manual_acceptance_bootstrap.sh --config config.toml --host 127.0.0.1 --port 18000
```

脚本会输出：
- 测试 URL
- 进程 PID
- 日志路径
- 本轮证据目录（`artifacts/manual-qa/<timestamp>/`）

结束验收后：

```bash
scripts/qa/manual_acceptance_stop.sh
```

---

## 3. 建议证据命名规范

将截图/录屏统一放在脚本输出的证据目录中，建议使用：

- `desktop-home.png`
- `desktop-batch-actions.png`
- `desktop-settings-dialog.png`
- `mobile-ios-home.png`
- `mobile-ios-dialog.png`
- `mobile-android-home.png`
- `mobile-android-batch-tools.png`

可选补充：
- `notes.txt`（记录异常时间点与复现步骤）

---

## 4. Desktop 验收脚本（逐步执行）

1. 打开首页并登录（默认 `admin/admin` 或你当前配置账号）。
2. 验证状态卡：
   - 自动轮询开关可操作。
   - 上次执行范围、时间信息显示正常。
3. 验证仓库区：
   - 搜索 + 状态筛选 + 排序组合后列表行为一致。
   - 批量操作按钮状态和禁用原因提示正确。
4. 验证设置对话框：
   - `测试 WebDAV / 检查能力 / 同步缓存 / 预演清理 / 保存` 都有明确反馈。
   - 关闭对话框后焦点回到触发按钮。
5. 验证活动区：
   - 日志可读；复制按钮可用。
6. 在模板中勾选并填写备注。

---

## 5. Mobile 验收脚本（逐步执行）

建议至少在以下两台设备各执行一次：
- iOS Safari
- Android Chrome

每台设备执行：

1. 登录并检查顶部区域：
   - topbar 与状态卡无重叠。
2. 检查仓库区：
   - 批量工具栏按钮可点击、可换行。
   - repo 卡控件无截断/重叠。
3. 打开设置对话框：
   - 按钮可达、文本可读、滚动稳定。
4. 检查底部移动导航：
   - 跳转到状态/仓库/活动锚点稳定。
5. 在模板中逐项勾选并记录设备信息。

---

## 6. 回填位置

验收结果请填写到：

- `docs/plans/2026-03-01-gate2-device-acceptance-template.md`
- `docs/plans/2026-03-01-release-acceptance-checklist.md`（第 3/4/5 节与 Gate 2）

通过标准：
- Desktop 与 Mobile 关键检查项全部通过；
- 无 `P1/P2` 新缺陷；
- 验收证据路径可追溯。
