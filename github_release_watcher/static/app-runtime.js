const API = window.GRWApiClient?.API;
const formatError = window.GRWFormatters?.formatError;
const isoToLocal = window.GRWFormatters?.isoToLocal;
const formatSignedDelta = window.GRWFormatters?.formatSignedDelta;
const formatRunScope = window.GRWFormatters?.formatRunScope;
const escapeHtml = window.GRWFormatters?.escapeHtml;
const renderStructuredLogs = window.GRWLogsView?.renderStructuredLogs;
const createRepoController = window.GRWRepoController?.createRepoController;
const createSettingsController = window.GRWSettingsController?.createSettingsController;
const createStorageDiagnosticsController = window.GRWStorageDiagnostics?.createStorageDiagnosticsController;
const createBatchSelectorsController = window.GRWBatchSelectors?.createBatchSelectorsController;
const createBatchActionsController = window.GRWBatchActions?.createBatchActionsController;
const createMobileBehaviorController = window.GRWMobileBehavior?.createMobileBehaviorController;
const createAppUiUtils = window.GRWAppUiUtils?.createAppUiUtils;
const createAuthController = window.GRWAppAuth?.createAuthController;
const createSettingsDialogController = window.GRWAppSettingsDialog?.createSettingsDialogController;
const createAppEventsController = window.GRWAppEvents?.createAppEventsController;

if (
  !API ||
  !formatError ||
  !isoToLocal ||
  !formatSignedDelta ||
  !formatRunScope ||
  !escapeHtml ||
  !renderStructuredLogs ||
  !createRepoController ||
  !createSettingsController ||
  !createStorageDiagnosticsController ||
  !createBatchSelectorsController ||
  !createBatchActionsController ||
  !createMobileBehaviorController ||
  !createAppUiUtils ||
  !createAuthController ||
  !createSettingsDialogController ||
  !createAppEventsController
) {
  throw new Error("Shared frontend modules not loaded");
}

const PRESET_TYPES = [
  { key: "exe", label: "Windows (.exe)" },
  { key: "apk", label: "Android (.apk)" },
  { key: "zip", label: "ZIP (.zip)" },
  { key: "tar.gz", label: "tar.gz" },
  { key: "dmg", label: "macOS (.dmg)" },
  { key: "deb", label: "Linux (.deb)" },
  { key: "rpm", label: "Linux (.rpm)" },
];
const PRESET_TYPE_MAP = new Map(PRESET_TYPES.map((t) => [t.key, t.label]));

let config = null;
let draft = null;
let dirty = false;
let currentUser = null;
let repoSummaryByKey = new Map();
let settingsDialogDraftSnapshot = null;
let settingsDialogDirtyBefore = false;
let settingsDialogAuthUsernameBefore = "";
let settingsDialogSaved = false;
let settingsDialogReturnFocusEl = null;
let repoDialogReturnFocusEl = null;
let lastWebdavTest = null;
let mustChangePassword = false;
let lastStorageHealthTotals = null;
let lastStorageHealthAt = 0;
let selectedRepoKeys = new Set();
let lastSyncCacheAnomalyRepoKeys = new Set();
let hasSyncCacheSnapshot = false;
let batchToolsExpanded = true;

const $ = (id) => document.getElementById(id);
const uiUtils = createAppUiUtils({ getEl: $ });
const getFocusableTriggerEl = () => uiUtils.getFocusableTriggerEl();
const focusIfPossible = (el) => uiUtils.focusIfPossible(el);
const syncDialogOpenState = () => uiUtils.syncDialogOpenState();
const prefersReducedMotion = () => uiUtils.prefersReducedMotion();
const isMobileLikeViewport = () => uiUtils.isMobileLikeViewport();
const revealHintIfNeeded = (el) => uiUtils.revealHintIfNeeded(el);
const isBusy = (el) => uiUtils.isBusy(el);
const toast = (message, kind) => uiUtils.toast(message, kind);
const setButtonBusy = (btn, busy, busyText) => uiUtils.setButtonBusy(btn, busy, busyText);
const cloneDeep = (obj) => uiUtils.cloneDeep(obj);
const stableCopy = (value) => uiUtils.stableCopy(value);
const stableStringify = (value) => uiUtils.stableStringify(value);

const repoController = createRepoController({
  getConfig: () => config,
  getDraft: () => draft,
  getRepoSummaryByKey: () => repoSummaryByKey,
  getLastSyncCacheAnomalyRepoKeys: () => lastSyncCacheAnomalyRepoKeys,
  setLastSyncCacheAnomalyRepoKeys: (next) => {
    lastSyncCacheAnomalyRepoKeys = next;
  },
  getSelectedRepoKeysSet: () => selectedRepoKeys,
  setSelectedRepoKeysSet: (next) => {
    selectedRepoKeys = next;
  },
  getFilterText: () => $("repoFilterInput")?.value || "",
  getStateFilter: () => $("repoStateFilterSelect")?.value || "all",
  getSortMode: () => $("repoSortSelect")?.value || "default",
});

const settingsController = createSettingsController({
  getEl: $,
  normalizeAssetType: (value) => normalizeAssetType(value),
});

const storageDiagnosticsController = createStorageDiagnosticsController({
  getEl: $,
  getStorageMode: () => String(draft?.storage?.mode || "local"),
  withAuth: (fn) => withAuth(fn),
  apiGet: (path) => API.get(path),
  formatError: (e) => formatError(e),
  secondsToElapsedText: (seconds) => secondsToElapsedText(seconds),
  formatSignedDelta: (value) => formatSignedDelta(value),
  escapeHtml: (value) => escapeHtml(value),
  revealHintIfNeeded: (el) => revealHintIfNeeded(el),
  renderRepos: () => renderRepos(),
  updateBatchControlsUI: () => updateBatchControlsUI(),
  getLastStorageHealthTotals: () => lastStorageHealthTotals,
  setLastStorageHealthTotals: (value) => {
    lastStorageHealthTotals = value;
  },
  getLastStorageHealthAt: () => lastStorageHealthAt,
  setLastStorageHealthAt: (value) => {
    lastStorageHealthAt = value;
  },
  setHasSyncCacheSnapshot: (value) => {
    hasSyncCacheSnapshot = !!value;
  },
  setLastSyncCacheAnomalyRepoKeys: (value) => {
    lastSyncCacheAnomalyRepoKeys = value instanceof Set ? value : new Set();
  },
});

const batchSelectorsController = createBatchSelectorsController({
  getVisibleRepoKeys: () => getVisibleRepoKeys(),
  getSelectedRepoKeysSet: () => selectedRepoKeys,
  setSelectedRepoKeysSet: (next) => {
    selectedRepoKeys = next instanceof Set ? next : new Set();
  },
  setBatchActionHint: (message, kind) => setBatchActionHint(message, kind),
  renderRepos: () => renderRepos(),
  isRepoEnabledForRun: (key) => isRepoEnabledForRun(key),
  isRepoInErrorState: (key) => isRepoInErrorState(key),
  isRepoInCacheAnomalyState: (key) => isRepoInCacheAnomalyState(key),
  isWebdavStorageMode: () => isWebdavStorageMode(),
  getHasSyncCacheSnapshot: () => hasSyncCacheSnapshot,
});

const batchActionsController = createBatchActionsController({
  getSelectedRepoKeys: () => getSelectedRepoKeys(),
  setBatchActionHint: (message, kind) => setBatchActionHint(message, kind),
  toast: (message, kind) => toast(message, kind),
  repoDraft: (key) => repoDraft(key),
  setDirty: (value) => setDirty(value),
  renderRepos: () => renderRepos(),
  saveSettings: (options) => saveSettings(options),
  isRepoEnabledForRun: (key) => isRepoEnabledForRun(key),
  getMustChangePassword: () => mustChangePassword,
  renderSecurityBanner: () => renderSecurityBanner(),
  setButtonBusy: (btn, busy, busyText) => setButtonBusy(btn, busy, busyText),
  withAuth: (fn) => withAuth(fn),
  apiPost: (path, payload) => API.post(path, payload),
  formatError: (e) => formatError(e),
  refreshStatusSafe: () => refreshStatusSafe(),
  updateBatchControlsUI: () => updateBatchControlsUI(),
});

const mobileBehaviorController = createMobileBehaviorController({
  getEl: $,
  prefersReducedMotion: () => prefersReducedMotion(),
});

const setupMobileSectionNav = () => mobileBehaviorController.setupMobileSectionNav();

const setupLogsScrollHint = () => mobileBehaviorController.setupLogsScrollHint();

function setDirty(v) {
  dirty = v;
  const saveBtn = $("saveBtn");
  saveBtn.disabled = isBusy(saveBtn) || !dirty || !config;
}

async function withAuth(fn) {
  try {
    return await fn();
  } catch (e) {
    if (e?.code !== "unauthorized") throw e;
    await requireLogin();
    return await fn();
  }
}

function normalizeAssetType(raw) {
  const value = String(raw || "")
    .trim()
    .toLowerCase()
    .replace(/^\./, "");
  if (!value) throw new Error("类型不能为空。");
  if (!/^[a-z0-9][a-z0-9._-]{0,31}$/.test(value)) {
    throw new Error("类型格式不合法：仅允许 a-z 0-9 . _ -，长度最多 32。");
  }
  return value;
}

function isoToRelative(iso) {
  if (!iso) return "-";
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return "-";
  const delta = Math.round((t - Date.now()) / 1000);
  if (delta <= 0) return "已到期";
  return secondsToHuman(delta);
}

function secondsToHoursValue(seconds) {
  const s = Number(seconds);
  if (!Number.isFinite(s) || s <= 0) return "48";
  const hours = s / 3600;
  const rounded = Math.round(hours * 10000) / 10000;
  const raw = String(rounded);
  return raw.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
}

function secondsToHuman(seconds) {
  const s = Number(seconds);
  if (!Number.isFinite(s) || s <= 0) return "-";
  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  if (days > 0) return `${days}天${hours ? `${hours}小时` : ""}`;
  if (hours > 0) return `${hours}小时${minutes ? `${minutes}分钟` : ""}`;
  return `${minutes}分钟`;
}

function secondsToElapsedText(seconds) {
  const s = Math.max(0, Math.round(Number(seconds) || 0));
  if (s < 60) return `${s}秒`;
  return secondsToHuman(s);
}

function repoDomId(key) {
  return `repoMeta-${String(key || "").replace(/[^a-zA-Z0-9_-]/g, "_")}`;
}

function repoSummaryText(summary) {
  if (!summary) return "";
  const stats = summary.stats || {};
  const current = stats.current_tag || stats.latest_release_tag || "-";
  const statusText =
    stats.last_check_ok === true ? "正常" : stats.last_check_ok === false ? (stats.last_error_type === "network" ? "网络错误" : "错误") : "未知";
  const versions = summary.downloaded_releases_total ?? 0;
  const downloads = stats.download_assets_total ?? 0;
  const cleanups = stats.cleanup_tags_total ?? 0;
  const median = summary.update?.median_interval_seconds;
  const next = summary.next_run_at ? isoToRelative(summary.next_run_at) : "-";
  const updateEvery = median ? secondsToHuman(median) : "-";
  const checkEvery = summary.recommended_interval_seconds ? secondsToHuman(summary.recommended_interval_seconds) : "-";
  return `状态：${statusText} · 当前：${current} · 版本：${versions} · 资产：${downloads} · 删除：${cleanups} · 更新约：${updateEvery} · 检查约：${checkEvery} · 下次：${next}`;
}

function buildBadge(text, cls) {
  const el = $("statusBadge");
  el.textContent = text;
  el.className = `badge ${cls ?? ""}`.trim();
}

function renderSecurityBanner() {
  const el = $("securityBanner");
  if (!el) return;
  if (!mustChangePassword) {
    el.classList.add("hidden");
    el.textContent = "";
    return;
  }
  el.classList.remove("hidden");
  el.innerHTML =
    '<span>安全限制：当前账号需先修改密码，创建/更新类操作会被拒绝。</span><button id="securityOpenSettingsBtn" class="btn security-banner-action" type="button">立即改密</button>';
  const actionBtn = $("securityOpenSettingsBtn");
  if (actionBtn) {
    actionBtn.onclick = () => openSettingsDialog({ focusAuthPassword: true });
  }
}

function setUser(username) {
  currentUser = username || null;
  $("userBadge").textContent = currentUser ? currentUser : "未登录";
  const logoutBtn = $("logoutBtn");
  logoutBtn.disabled = isBusy(logoutBtn) || !currentUser;
}

const authController = createAuthController({
  getEl: $,
  apiGetMe: () => API.get("/me"),
  syncDialogOpenState: () => syncDialogOpenState(),
  onAuthResolved: ({ username, mustChangePassword: nextMustChangePassword }) => {
    mustChangePassword = !!nextMustChangePassword;
    renderSecurityBanner();
    setUser(username || "admin");
  },
});

const startLoginFlow = (message) => authController.startLoginFlow(message);

const requireLogin = () => authController.requireLogin();

const settingsDialogController = createSettingsDialogController({
  getEl: $,
  getDraft: () => draft,
  getSettingsDialogDraftSnapshot: () => settingsDialogDraftSnapshot,
  stableStringify: (value) => stableStringify(value),
  getLastWebdavTest: () => lastWebdavTest,
  setLastWebdavTest: (value) => {
    lastWebdavTest = value;
  },
  revealHintIfNeeded: (el) => revealHintIfNeeded(el),
});

const hasSettingsDialogUnsavedChanges = () => settingsDialogController.hasSettingsDialogUnsavedChanges();

const renderWebdavTestHint = () => settingsDialogController.renderWebdavTestHint();

const invalidateWebdavTest = () => settingsDialogController.invalidateWebdavTest();

const syncSettingsFormFromDraft = () => settingsDialogController.syncSettingsFormFromDraft();

const syncDraftFromSettingsForm = () => settingsDialogController.syncDraftFromSettingsForm();

const recordWebdavTestResult = (result) => {
  lastWebdavTest = result;
};

function repoDraft(key) {
  if (!draft.repos[key]) {
    draft.repos[key] = {};
  }
  return draft.repos[key];
}

const getRepoListView = () => repoController.getRepoListView();

const getVisibleRepoKeys = () => repoController.getVisibleRepoKeys();

const syncSelectedReposWithConfig = () => repoController.syncSelectedReposWithConfig();

const getSelectedRepoKeys = () => repoController.getSelectedRepoKeys();

const getRepoConfigByKey = (key) => repoController.getRepoConfigByKey(key);

const isRepoEnabledForRun = (key) => repoController.isRepoEnabledForRun(key);

const isRepoInErrorState = (key) => repoController.isRepoInErrorState(key);

const isRepoInCacheAnomalyState = (key) => repoController.isRepoInCacheAnomalyState(key);

function isWebdavStorageMode() {
  const mode = String(draft?.storage?.mode || config?.storage?.mode || "local").trim().toLowerCase();
  return mode === "webdav";
}

function setBatchActionHint(message, kind) {
  const el = $("batchActionHint");
  if (!el) return;
  el.className = kind === "danger" ? "hint danger" : "hint";
  el.textContent = String(message || "");
  revealHintIfNeeded(el);
}

function setControlDisabledWithReason(btn, disabled, reason) {
  if (!btn) return;
  btn.disabled = !!disabled;
  btn.title = disabled && reason ? String(reason) : "";
}

function isCompactMobileViewport() {
  return window.matchMedia("(max-width: 640px)").matches;
}

function syncBatchToolsPresentation(selectedCount = 0) {
  const wrap = $("batchToolsWrap");
  const panel = $("batchToolsPanel");
  const toggle = $("batchToolsToggleBtn");
  if (!wrap || !panel || !toggle) return;
  const mobile = isCompactMobileViewport();
  if (!mobile) batchToolsExpanded = true;
  const expanded = mobile ? !!batchToolsExpanded : true;
  const count = Number.isFinite(selectedCount) ? Math.max(0, Math.trunc(selectedCount)) : 0;
  wrap.dataset.expanded = expanded ? "true" : "false";
  panel.hidden = !expanded;
  toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
  toggle.textContent = expanded ? `收起批量操作（已选 ${count}）` : `展开批量操作（已选 ${count}）`;
}

function updateBatchControlsUI() {
  const countEl = $("batchSelectedCount");
  const selectVisibleBtn = $("batchSelectVisibleBtn");
  const invertVisibleBtn = $("batchInvertVisibleBtn");
  const selectEnabledBtn = $("batchSelectEnabledBtn");
  const selectErrorBtn = $("batchSelectErrorBtn");
  const selectCacheAnomalyBtn = $("batchSelectCacheAnomalyBtn");
  const runBtn = $("batchRunBtn");
  const enableBtn = $("batchEnableBtn");
  const disableBtn = $("batchDisableBtn");
  const clearBtn = $("batchClearBtn");
  const selected = getSelectedRepoKeys();
  const visible = getVisibleRepoKeys();
  const webdavMode = isWebdavStorageMode();
  const cacheSelectReady = webdavMode && hasSyncCacheSnapshot;
  const runnableCount = selected.filter((key) => isRepoEnabledForRun(key)).length;
  const count = selected.length;
  if (countEl) countEl.textContent = `已选 ${count} 个仓库（当前筛选 ${visible.length} 个，可检查 ${runnableCount} 个）`;
  syncBatchToolsPresentation(count);
  const missingConfig = !config;
  const selectedMissing = count <= 0;
  const visibleMissing = visible.length <= 0;
  const disabled = missingConfig || selectedMissing;
  const visibleDisabled = missingConfig || visibleMissing;
  const visibleReason = missingConfig ? "配置未加载。" : visibleMissing ? "当前筛选结果为空。" : "";
  if (selectVisibleBtn) setControlDisabledWithReason(selectVisibleBtn, isBusy(selectVisibleBtn) || visibleDisabled, visibleReason);
  if (invertVisibleBtn) setControlDisabledWithReason(invertVisibleBtn, isBusy(invertVisibleBtn) || visibleDisabled, visibleReason);
  if (selectEnabledBtn) setControlDisabledWithReason(selectEnabledBtn, isBusy(selectEnabledBtn) || visibleDisabled, visibleReason);
  if (selectErrorBtn) setControlDisabledWithReason(selectErrorBtn, isBusy(selectErrorBtn) || visibleDisabled, visibleReason);
  if (selectCacheAnomalyBtn) {
    let reason = visibleReason;
    if (!reason && !webdavMode) reason = "当前存储模式不是 WebDAV。";
    else if (!reason && !hasSyncCacheSnapshot) reason = '请先在设置中执行一次“同步缓存”。';
    setControlDisabledWithReason(selectCacheAnomalyBtn, isBusy(selectCacheAnomalyBtn) || visibleDisabled || !cacheSelectReady, reason);
  }
  const runReason = missingConfig ? "配置未加载。" : selectedMissing ? "请先选择至少一个仓库。" : runnableCount <= 0 ? "所选仓库均为停用状态。" : "";
  if (runBtn) setControlDisabledWithReason(runBtn, isBusy(runBtn) || missingConfig || runnableCount <= 0, runReason);
  const selectReason = missingConfig ? "配置未加载。" : selectedMissing ? "请先选择至少一个仓库。" : "";
  if (enableBtn) setControlDisabledWithReason(enableBtn, isBusy(enableBtn) || disabled, selectReason);
  if (disableBtn) setControlDisabledWithReason(disableBtn, isBusy(disableBtn) || disabled, selectReason);
  if (clearBtn) setControlDisabledWithReason(clearBtn, missingConfig || selectedMissing, selectReason);
}

function renderTypeChips(container, selected, onChange) {
  const list = Array.isArray(selected) ? selected : [];
  const selectedSet = new Set(list);
  const customKeys = [];
  for (const k of list) {
    if (!PRESET_TYPE_MAP.has(k) && !customKeys.includes(k)) customKeys.push(k);
  }

  const keys = [...PRESET_TYPES.map((t) => t.key), ...customKeys];
  container.innerHTML = "";
  for (const key of keys) {
    const label = document.createElement("label");
    label.className = "chip";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = selectedSet.has(key);
    input.addEventListener("change", () => onChange(key, input.checked));
    label.appendChild(input);
    const span = document.createElement("span");
    span.textContent = PRESET_TYPE_MAP.get(key) || `.${key}`;
    label.appendChild(span);
    container.appendChild(label);
  }
}

function renderRepos() {
  const wrap = $("repos");
  wrap.innerHTML = "";
  const countHint = $("repoCountHint");
  if (!config || !Array.isArray(config.repos)) {
    if (countHint) countHint.textContent = "";
    updateBatchControlsUI();
    return;
  }
  syncSelectedReposWithConfig();
  const view = getRepoListView();
  const repos = view.repos;
  const filterText = view.filterText;
  const stateFilter = view.stateFilter;
  const total = view.total;

  if (countHint) {
    const stateLabelMap = {
      all: "全部",
      enabled: "启用",
      disabled: "停用",
      error: "异常",
      network_error: "网络异常",
      cache_anomaly: "缓存异常",
    };
    const stateLabel = stateLabelMap[stateFilter] || "全部";
    const hasFilter = !!filterText || stateFilter !== "all";
    const suffix = hasFilter ? `（筛选：${repos.length}/${total}，状态：${stateLabel}）` : `（共 ${total}）`;
    countHint.textContent = suffix;
  }

  for (const repo of repos) {
    const row = document.createElement("div");
    row.className = "repo";

    const head = document.createElement("div");
    head.className = "repo-head";

    const title = document.createElement("div");
    title.className = "repo-title";

    const nameBox = document.createElement("div");
    const name = document.createElement("div");
    name.className = "repo-name";
    name.textContent = repo.key;
    nameBox.appendChild(name);

    const sub = document.createElement("div");
    sub.className = "repo-sub";
    sub.textContent = repo.repo_url ? repo.repo_url : repo.name;
    nameBox.appendChild(sub);

    const meta = document.createElement("div");
    meta.className = "repo-sub";
    meta.id = repoDomId(repo.key);
    const summary = repoSummaryByKey.get(repo.key);
    meta.textContent = summary ? repoSummaryText(summary) : "统计加载中…";
    nameBox.appendChild(meta);
    title.appendChild(nameBox);

    const right = document.createElement("div");
    right.className = "repo-actions";

    const selectWrap = document.createElement("label");
    selectWrap.className = "repo-select";
    const selectInput = document.createElement("input");
    selectInput.type = "checkbox";
    selectInput.setAttribute("aria-label", `选择仓库 ${repo.key}`);
    selectInput.checked = selectedRepoKeys.has(repo.key);
    selectInput.addEventListener("change", () => {
      if (selectInput.checked) selectedRepoKeys.add(repo.key);
      else selectedRepoKeys.delete(repo.key);
      updateBatchControlsUI();
    });
    const selectText = document.createElement("span");
    selectText.className = "muted";
    selectText.textContent = "选中";
    selectWrap.appendChild(selectInput);
    selectWrap.appendChild(selectText);

    const repoPatch = draft?.repos?.[repo.key] || {};
    const enabledValue = repoPatch.enabled ?? repo.enabled;

    const runBtn = document.createElement("button");
    runBtn.className = "btn";
    runBtn.type = "button";
    runBtn.setAttribute("aria-label", `检查仓库 ${repo.key}`);
    runBtn.textContent = "检查";
    runBtn.disabled = !enabledValue;
    runBtn.addEventListener("click", async () => {
      setButtonBusy(runBtn, true, "触发中…");
      try {
        const res = await withAuth(() => API.post("/run", { repo: repo.key }));
        if (res.error) toast(`触发失败：${res.error}`, "bad");
        else toast(res.queued ? "已加入队列。" : "任务已在运行/队列中。", "ok");
      } catch (e) {
        toast(`触发失败：${formatError(e)}`, "bad");
      } finally {
        setButtonBusy(runBtn, false);
        runBtn.disabled = !enabled.checked;
        await refreshStatusSafe().catch(() => {});
      }
    });

    const activityBtn = document.createElement("button");
    activityBtn.className = "btn";
    activityBtn.type = "button";
    activityBtn.setAttribute("aria-label", `查看仓库 ${repo.key} 活动`);
    activityBtn.textContent = "活动";
    activityBtn.addEventListener("click", () => {
      window.location.href = `/repo.html?repo=${encodeURIComponent(repo.key)}`;
    });

    const enabledWrap = document.createElement("div");
    enabledWrap.className = "inline";
    const enabledLabel = document.createElement("span");
    enabledLabel.className = "muted";
    enabledLabel.textContent = "启用";
    const sw = document.createElement("label");
    sw.className = "switch";
    const enabled = document.createElement("input");
    enabled.type = "checkbox";
    enabled.setAttribute("aria-label", `启用仓库 ${repo.key}`);
    enabled.checked = !!enabledValue;
    enabled.addEventListener("change", () => {
      repoDraft(repo.key).enabled = enabled.checked;
      runBtn.disabled = isBusy(runBtn) || !enabled.checked;
      setDirty(true);
    });
    const slider = document.createElement("span");
    slider.className = "slider";
    sw.appendChild(enabled);
    sw.appendChild(slider);
    enabledWrap.appendChild(enabledLabel);
    enabledWrap.appendChild(sw);

    head.appendChild(title);
    right.appendChild(selectWrap);
    right.appendChild(activityBtn);
    right.appendChild(runBtn);
    right.appendChild(enabledWrap);
    head.appendChild(right);
    row.appendChild(head);

    const controls = document.createElement("div");
    controls.className = "row";
    controls.style.marginTop = "10px";

    const keepBox = document.createElement("div");
    keepBox.className = "grow";
    const keepLabel = document.createElement("div");
    keepLabel.className = "label";
    keepLabel.textContent = "保留最近 N 个（留空表示使用全局）";
    const keepInput = document.createElement("input");
    keepInput.className = "input";
    keepInput.type = "number";
    keepInput.setAttribute("aria-label", `仓库 ${repo.key} 保留最近 N 个版本`);
    keepInput.min = "1";
    keepInput.max = "1000";
    const globalKeepLastRaw = Number($("keepLastInput")?.value || NaN);
    const globalKeepLast = Number.isFinite(globalKeepLastRaw) && globalKeepLastRaw >= 1 ? Math.trunc(globalKeepLastRaw) : Number(config.app.keep_last || 1);
    const repoKeepLast = repoPatch.keep_last;
    const effectiveKeepLast = typeof repoKeepLast === "number" && Number.isFinite(repoKeepLast) ? repoKeepLast : globalKeepLast;
    keepInput.placeholder = String(effectiveKeepLast);
    keepInput.value = repoKeepLast ?? "";
    keepInput.addEventListener("input", () => {
      const v = keepInput.value.trim();
      repoDraft(repo.key).keep_last = v ? Number(v) : null;
      setDirty(true);
    });
    keepBox.appendChild(keepLabel);
    keepBox.appendChild(keepInput);

    const typesBox = document.createElement("div");
    typesBox.className = "grow";
    const typesLabel = document.createElement("div");
    typesLabel.className = "label";
    typesLabel.textContent = "保存哪些发布资产（按类型后缀）";
    const chips = document.createElement("div");
    chips.className = "chips";
    const baseTypes = Array.isArray(repoPatch.asset_types) ? repoPatch.asset_types : repo.asset_types_effective || [];
    const getTypes = () => repoDraft(repo.key).asset_types ?? baseTypes;
    const onTypeChange = (key, checked) => {
      const current = new Set(getTypes());
      if (checked) current.add(key);
      else current.delete(key);
      repoDraft(repo.key).asset_types = Array.from(current);
      setDirty(true);
      renderTypeChips(chips, getTypes(), onTypeChange);
    };
    renderTypeChips(chips, getTypes(), onTypeChange);

    const typeAdder = document.createElement("div");
    typeAdder.className = "type-adder";

    const typeInput = document.createElement("input");
    typeInput.className = "input sm";
    typeInput.placeholder = "自定义类型，如: msi";
    typeInput.setAttribute("aria-label", `仓库 ${repo.key} 添加自定义类型`);

    const addBtn = document.createElement("button");
    addBtn.className = "btn";
    addBtn.type = "button";
    addBtn.textContent = "添加";

    const addType = () => {
      let normalized = "";
      try {
        normalized = normalizeAssetType(typeInput.value);
      } catch (e) {
        toast(formatError(e), "bad");
        typeInput.focus();
        return;
      }
      const current = new Set(getTypes());
      current.add(normalized);
      repoDraft(repo.key).asset_types = Array.from(current);
      typeInput.value = "";
      setDirty(true);
      renderTypeChips(chips, getTypes(), onTypeChange);
    };

    addBtn.addEventListener("click", addType);
    typeInput.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      addType();
    });

    typeAdder.appendChild(typeInput);
    typeAdder.appendChild(addBtn);
    typesBox.appendChild(typesLabel);
    typesBox.appendChild(chips);
    typesBox.appendChild(typeAdder);

    controls.appendChild(keepBox);
    controls.appendChild(typesBox);
    row.appendChild(controls);

    const note = document.createElement("p");
    note.className = "hint";
    note.textContent =
      "提示：asset_types 会与 include_assets/exclude_assets 正则叠加生效；需要更精细匹配可直接编辑 config.toml 或通过 API settings 更新正则。";
    row.appendChild(note);

    wrap.appendChild(row);
  }
  updateBatchControlsUI();
}

function materializeDraftFromConfig() {
  draft = { app: {}, repos: {}, storage: {} };
  draft.app.keep_last = config.app.keep_last;
  draft.app.interval_seconds = config.app.interval_seconds;
  const storage = config.storage || {};
  draft.storage.mode = storage.mode || "local";
  draft.storage.local_dir = storage.local_dir || config.app.download_dir;
  draft.storage.webdav = {
    base_url: storage.webdav?.base_url || "",
    username: storage.webdav?.username || "",
    verify_tls: storage.webdav?.verify_tls ?? true,
    timeout_seconds: storage.webdav?.timeout_seconds ?? 60,
    upload_concurrency: storage.webdav?.upload_concurrency ?? 2,
    max_retries: storage.webdav?.max_retries ?? 3,
    retry_backoff_seconds: storage.webdav?.retry_backoff_seconds ?? 2,
    verify_after_upload: storage.webdav?.verify_after_upload ?? true,
    upload_temp_suffix: storage.webdav?.upload_temp_suffix || ".uploading",
    cleanup_mode: storage.webdav?.cleanup_mode || "delete",
  };
  for (const repo of config.repos) {
    draft.repos[repo.key] = {
      name: repo.name,
      enabled: repo.enabled,
      keep_last: repo.keep_last,
      asset_types: repo.asset_types.length ? repo.asset_types : repo.asset_types_effective,
      include_prereleases: repo.include_prereleases,
      include_drafts: repo.include_drafts,
      include_assets: repo.include_assets,
      exclude_assets: repo.exclude_assets,
    };
  }
}

function setConfigLoadedUI(loaded) {
  const runNowBtn = $("runNowBtn");
  runNowBtn.disabled = isBusy(runNowBtn) || !loaded;

  const settingsBtn = $("settingsBtn");
  settingsBtn.disabled = isBusy(settingsBtn) || !loaded;

  const addRepoBtn = $("addRepoBtn");
  addRepoBtn.disabled = isBusy(addRepoBtn) || !loaded;

  const schedulerToggle = $("schedulerToggle");
  schedulerToggle.disabled = !loaded;

  $("intervalInput").disabled = !loaded;
  $("keepLastInput").disabled = !loaded;
  $("repoFilterInput").disabled = !loaded;
  $("repoStateFilterSelect").disabled = !loaded;
  $("repoSortSelect").disabled = !loaded;
  setDirty(dirty);
  renderSecurityBanner();
  updateBatchControlsUI();
}

async function loadAll() {
  const status = await API.get("/status");
  config = status.config;
  mustChangePassword = !!status?.security?.must_change_password;
  renderSecurityBanner();
  if (!config) {
    buildBadge("配置未加载", "bad");
    $("configHint").textContent = status.config_error ? `配置错误：${status.config_error}` : "配置未加载。";
    $("repos").innerHTML = "";
    setDirty(false);
    setConfigLoadedUI(false);
    return;
  }
  setConfigLoadedUI(true);
  $("configHint").textContent = `配置文件：${status.config_path}（覆盖文件：${status.overrides_path}） · 调度：按仓库自适应`;
  if (mustChangePassword) {
    $("configHint").textContent += " · 安全提示：请先修改默认登录密码";
  }
  if (status.auth?.username) {
    setUser(status.auth.username);
    $("authUsername").value = status.auth.username;
  }

  materializeDraftFromConfig();
  setDirty(false);

  $("keepLastInput").value = String(config.app.keep_last);
  $("intervalInput").value = secondsToHoursValue(config.app.interval_seconds);
  syncSettingsFormFromDraft();

  renderRepos();
  await refreshStatus();
  await refreshRepoSummariesSafe();
  await refreshStorageDiagnostics();
}

async function refreshStatus() {
  const status = await API.get("/status");
  mustChangePassword = !!status?.security?.must_change_password;
  renderSecurityBanner();

  if (mustChangePassword) buildBadge("需先改密", "bad");
  else if (status.config_error) buildBadge("配置错误", "bad");
  else if (status.run?.in_progress) buildBadge("运行中…", "warn");
  else buildBadge("运行正常", "ok");

  $("schedulerToggle").checked = !!status.scheduler?.enabled;
  $("nextRunAt").textContent = isoToLocal(status.scheduler?.next_run_at);

  const last = status.run?.last;
  const finishedAt = last?.finished_at || last?.started_at || last?.queued_at;
  const suffix = last?.exit_code === 0 ? "（成功）" : last?.exit_code != null ? "（有错误）" : "";
  $("lastRunAt").textContent = finishedAt ? `${isoToLocal(finishedAt)} ${suffix}` : "-";
  $("lastRunScope").textContent = formatRunScope(last);
}

async function refreshStatusSafe() {
  try {
    await refreshStatus();
  } catch (e) {
    if (e?.code === "unauthorized") await requireLogin();
    else throw e;
  }
}

async function refreshLogs() {
  const data = await API.get("/logs?limit=200");
  const items = Array.isArray(data.items) ? data.items : [];
  const logsEl = $("logs");
  if (logsEl) {
    renderStructuredLogs(logsEl, items);
  }

  const hint = $("logFileHint");
  if (hint) {
    const rawPath = String(data.log_file || "").trim();
    if (rawPath) {
      const baseName = rawPath.split(/[\\/]/).filter(Boolean).pop() || rawPath;
      hint.textContent = `完整日志：${baseName}`;
      hint.title = rawPath;
    } else {
      hint.textContent = "";
      hint.removeAttribute("title");
    }
  }
}

async function refreshRepoSummariesSafe() {
  try {
    const data = await withAuth(() => API.get("/repos"));
    const items = data.items || [];
    repoSummaryByKey = new Map(items.map((x) => [x.key, x]));
    for (const item of items) {
      const el = document.getElementById(repoDomId(item.key));
      if (el) el.textContent = repoSummaryText(item);
    }
  } catch {}
}

const formatSyncCacheTopRepos = (items, limit = 3) =>
  storageDiagnosticsController.formatSyncCacheTopRepos(items, limit);

const refreshStorageDiagnostics = () => storageDiagnosticsController.refreshStorageDiagnostics();

async function runNow() {
  if (mustChangePassword) {
    renderSecurityBanner();
    toast("当前账号需先修改密码，请先在设置中更新账号密码。", "warn");
    return;
  }
  const btn = $("runNowBtn");
  setButtonBusy(btn, true, "检查中…");
  try {
    const res = await withAuth(() => API.post("/run", {}));
    if (res.error) toast(`触发失败：${res.error}`, "bad");
    else toast(res.queued ? "已加入队列。" : "任务已在运行/队列中。", "ok");
  } catch (e) {
    toast(`触发失败：${formatError(e)}`, "bad");
  } finally {
    setButtonBusy(btn, false);
    await refreshStatusSafe().catch(() => {});
  }
}

const batchSelectVisible = () => batchSelectorsController.batchSelectVisible();

const batchInvertVisible = () => batchSelectorsController.batchInvertVisible();

const batchSelectEnabledVisible = () => batchSelectorsController.batchSelectEnabledVisible();

const batchSelectErrorVisible = () => batchSelectorsController.batchSelectErrorVisible();

const batchSelectCacheAnomalyVisible = () => batchSelectorsController.batchSelectCacheAnomalyVisible();

const batchSetEnabled = (enabled, triggerBtn) => batchActionsController.batchSetEnabled(enabled, triggerBtn);

const batchRunSelected = (triggerBtn) => batchActionsController.batchRunSelected(triggerBtn);

const validateIntField = (options) => settingsController.validateIntField(options);

const validateNumberField = (options) => settingsController.validateNumberField(options);

const normalizeRepoPatch = (key, patch) => settingsController.normalizeRepoPatch(key, patch);

async function saveSettings({ busyButtons } = {}) {
  const btns = Array.isArray(busyButtons) ? busyButtons.filter(Boolean) : [];
  for (const b of btns) setButtonBusy(b, true, "保存中…");
  $("settingsHint").textContent = "";

  try {
    syncDraftFromSettingsForm();

    try {
      draft.app.keep_last = validateIntField({ inputId: "keepLastInput", label: "保留数量", min: 1, max: 1000 });
    } catch (e) {
      $("keepLastInput").focus();
      throw e;
    }
    let intervalHours = 48;
    try {
      intervalHours = validateNumberField({ inputId: "intervalInput", label: "基础间隔（小时）", min: 0.01, max: 8760 });
    } catch (e) {
      $("intervalInput").focus();
      throw e;
    }
    draft.app.interval_seconds = Math.max(1, Math.round(intervalHours * 3600));

    const mode = draft.storage.mode || "local";
    if (mode === "webdav" && !String(draft.storage.webdav?.base_url || "").trim()) {
      $("webdavBaseUrl").focus();
      throw new Error("WebDAV Base URL 不能为空。");
    }
    if (mode === "webdav") {
      draft.storage.webdav.upload_concurrency = validateIntField({
        inputId: "webdavUploadConcurrency",
        label: "上传并发",
        min: 1,
        max: 32,
      });
      draft.storage.webdav.max_retries = validateIntField({
        inputId: "webdavMaxRetries",
        label: "失败重试次数",
        min: 1,
        max: 20,
      });
      draft.storage.webdav.retry_backoff_seconds = validateIntField({
        inputId: "webdavRetryBackoffSeconds",
        label: "重试退避秒数",
        min: 1,
        max: 300,
      });
      draft.storage.webdav.upload_temp_suffix = String($("webdavUploadTempSuffix").value || "").trim();
      if (!draft.storage.webdav.upload_temp_suffix) {
        $("webdavUploadTempSuffix").focus();
        throw new Error("临时上传后缀不能为空。");
      }
      if (/[\\/]/.test(draft.storage.webdav.upload_temp_suffix)) {
        $("webdavUploadTempSuffix").focus();
        throw new Error("临时上传后缀不能包含路径分隔符。");
      }
      draft.storage.webdav.cleanup_mode = String($("webdavCleanupMode").value || "delete").trim().toLowerCase();
      if (!["delete", "trash"].includes(draft.storage.webdav.cleanup_mode)) {
        $("webdavCleanupMode").focus();
        throw new Error("清理模式无效。");
      }
      draft.storage.webdav.verify_after_upload = $("webdavVerifyAfterUpload").checked;
    }

    const payload = cloneDeep(draft);
    payload.repos = payload.repos || {};
    for (const [key, patch] of Object.entries(payload.repos)) {
      if (!patch || typeof patch !== "object") continue;
      payload.repos[key] = normalizeRepoPatch(key, patch);
    }

    const localDirRaw = String($("localDirInput").value || "").trim();
    payload.storage = payload.storage || {};
    payload.storage.local_dir = localDirRaw ? localDirRaw : null;

    const webdavPassword = $("webdavPassword").value || "";
    if (webdavPassword) {
      payload.storage.webdav = payload.storage.webdav || {};
      payload.storage.webdav.password = webdavPassword;
    }

    const newUsername = ($("authUsername").value || "").trim();
    const newPassword = $("authPassword").value || "";
    if (newPassword) {
      payload.auth = { username: newUsername, password: newPassword };
    }

    const res = await withAuth(() => API.put("/settings", payload));
    if (res.error) {
      toast(`保存失败：${res.error}`, "bad");
      const settingsHintEl = $("settingsHint");
      settingsHintEl.textContent = `保存失败：${res.error}`;
      revealHintIfNeeded(settingsHintEl);
      return false;
    }

    toast("已保存。", "ok");
    $("webdavPassword").value = "";
    $("authPassword").value = "";
    await withAuth(() => loadAll());
    await refreshStatusSafe().catch(() => {});
    return true;
  } catch (e) {
    toast(`保存失败：${formatError(e)}`, "bad");
    const settingsHintEl = $("settingsHint");
    settingsHintEl.textContent = `保存失败：${formatError(e)}`;
    revealHintIfNeeded(settingsHintEl);
    return false;
  } finally {
    for (const b of btns) setButtonBusy(b, false);
    setDirty(dirty);
  }
}

async function setScheduler(enabled) {
  await withAuth(() => API.put("/scheduler", { enabled }));
  await refreshStatusSafe();
}

function openRepoDialog() {
  const dlg = $("repoDialog");
  if (!draft) {
    toast("配置未加载。", "bad");
    return;
  }
  repoDialogReturnFocusEl = getFocusableTriggerEl();

  $("newRepoName").value = "";
  $("newTypeInput").value = "";

  const typesWrap = $("newRepoTypes");
  const selected = new Set(["exe", "apk"]);

  const render = () => {
    renderTypeChips(typesWrap, Array.from(selected), (key, checked) => {
      if (checked) selected.add(key);
      else selected.delete(key);
      render();
    });
  };
  render();

  const addType = () => {
    const raw = $("newTypeInput").value;
    if (!raw.trim()) return;
    try {
      selected.add(normalizeAssetType(raw));
      $("newTypeInput").value = "";
      render();
    } catch (e) {
      toast(formatError(e), "bad");
      $("newTypeInput").focus();
    }
  };

  $("addTypeBtn").onclick = addType;
  $("newTypeInput").onkeydown = (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    addType();
  };

  const createBtn = $("createRepoBtn");
  createBtn.onclick = async (e) => {
    e.preventDefault();
    const name = $("newRepoName").value.trim();
    if (!name) {
      toast("请输入仓库名。", "bad");
      $("newRepoName").focus();
      return;
    }
    const patch = { name, enabled: true, asset_types: Array.from(selected) };
    draft.repos[name] = patch;
    setDirty(true);
    const ok = await saveSettings({ busyButtons: [createBtn] });
    if (ok) dlg.close();
  };

  dlg.showModal();
  syncDialogOpenState();
  setTimeout(() => $("newRepoName")?.focus(), 0);
}

function openSettingsDialog(options = {}) {
  const focusAuthPassword = !!options.focusAuthPassword;
  if (!draft) {
    toast("配置未加载。", "bad");
    return;
  }
  settingsDialogReturnFocusEl = getFocusableTriggerEl();
  settingsDialogDraftSnapshot = cloneDeep(draft);
  settingsDialogDirtyBefore = dirty;
  settingsDialogAuthUsernameBefore = $("authUsername")?.value || "";
  settingsDialogSaved = false;
  $("settingsHint").textContent = "";
  if (currentUser && $("authUsername")) $("authUsername").value = currentUser;
  if ($("webdavPassword")) $("webdavPassword").value = "";
  if ($("authPassword")) $("authPassword").value = "";
  syncSettingsFormFromDraft();
  $("settingsDialog").showModal();
  syncDialogOpenState();
  refreshStorageDiagnostics().catch(() => {});
  setTimeout(() => {
    if (focusAuthPassword) $("authPassword")?.focus();
    else $("localDirInput")?.focus();
  }, 0);
}

const appEventsController = createAppEventsController({
  getEl: $, api: API, runNow, openSettingsDialog, setButtonBusy, setUser, requireLogin, withAuth, loadAll, toast,
  getCurrentUser: () => currentUser, formatError, saveSettings, setScheduler, setDirty: (value) => setDirty(value),
  renderRepos, openRepoDialog, batchSelectVisible, batchInvertVisible, batchSelectEnabledVisible, batchSelectErrorVisible,
  batchSelectCacheAnomalyVisible, batchRunSelected, batchSetEnabled, isCompactMobileViewport,
  getBatchToolsExpanded: () => batchToolsExpanded, setBatchToolsExpanded: (value) => { batchToolsExpanded = !!value; },
  syncBatchToolsPresentation, getSelectedRepoKeys, clearSelectedRepoKeys: () => { selectedRepoKeys.clear(); }, setBatchActionHint,
  hasSettingsDialogUnsavedChanges, getSettingsDialogReturnFocusEl: () => settingsDialogReturnFocusEl,
  setSettingsDialogReturnFocusEl: (value) => { settingsDialogReturnFocusEl = value; },
  getSettingsDialogSaved: () => settingsDialogSaved, setSettingsDialogSaved: (value) => { settingsDialogSaved = !!value; },
  getSettingsDialogDraftSnapshot: () => settingsDialogDraftSnapshot,
  setSettingsDialogDraftSnapshot: (value) => { settingsDialogDraftSnapshot = value; },
  getSettingsDialogDirtyBefore: () => settingsDialogDirtyBefore, getSettingsDialogAuthUsernameBefore: () => settingsDialogAuthUsernameBefore,
  setSettingsDialogAuthUsernameBefore: (value) => { settingsDialogAuthUsernameBefore = String(value || ""); },
  getDraft: () => draft, setDraft: (value) => { draft = value; }, getDirty: () => dirty, syncSettingsFormFromDraft,
  focusIfPossible, syncDialogOpenState, getRepoDialogReturnFocusEl: () => repoDialogReturnFocusEl,
  setRepoDialogReturnFocusEl: (value) => { repoDialogReturnFocusEl = value; }, invalidateWebdavTest, syncDraftFromSettingsForm,
  recordWebdavTestResult, renderWebdavTestHint, refreshStorageDiagnostics, revealHintIfNeeded, formatSyncCacheTopRepos,
  setLastSyncCacheAnomalyRepoKeys: (value) => { lastSyncCacheAnomalyRepoKeys = value instanceof Set ? value : new Set(); },
  setHasSyncCacheSnapshot: (value) => { hasSyncCacheSnapshot = !!value; }, updateBatchControlsUI, escapeHtml,
});

async function main() {
  appEventsController.wireEvents();
  batchToolsExpanded = !isCompactMobileViewport();
  syncBatchToolsPresentation(0);
  setupMobileSectionNav();
  setupLogsScrollHint();
  syncDialogOpenState();
  setConfigLoadedUI(false);
  $("logoutBtn").disabled = true;
  setUser(null);
  await requireLogin();
  await loadAll();
  await refreshLogs();
  if (mustChangePassword) {
    toast("请先在设置中修改初始化账号密码。", "warn");
  }

  const pollStatus = () => {
    if (document.hidden) return;
    refreshStatusSafe();
  };
  const pollLogs = async () => {
    if (document.hidden) return;
    try {
      await refreshLogs();
    } catch (e) {
      if (e?.code === "unauthorized") await requireLogin();
      else throw e;
    }
  };

  setInterval(pollStatus, 3000);
  setInterval(pollLogs, 5000);
  setInterval(() => {
    if (document.hidden) return;
    refreshRepoSummariesSafe();
  }, 15000);
}

let appRuntimeStarted = false;

function startAppRuntime() {
  if (appRuntimeStarted) return;
  appRuntimeStarted = true;
  main().catch((e) => {
    buildBadge("初始化失败", "bad");
    $("logs").textContent = String(e?.stack || e);
  });
}

window.GRWAppRuntime = {
  start: startAppRuntime,
};
