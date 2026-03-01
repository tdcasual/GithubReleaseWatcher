class UnauthorizedError extends Error {
  constructor() {
    super("unauthorized");
    this.code = "unauthorized";
  }
}

const API = {
  async request(path, options) {
    const mergedHeaders = { Accept: "application/json", ...(options?.headers ?? {}) };
    const { headers: _ignored, ...rest } = options ?? {};
    const res = await fetch(`/api/v1${path}`, {
      credentials: "same-origin",
      ...rest,
      headers: mergedHeaders,
    });
    let data = {};
    try {
      data = await res.json();
    } catch {
      data = {};
    }
    if (res.status === 401 || data?.error === "unauthorized") throw new UnauthorizedError();
    return data;
  },
  async get(path) {
    return await API.request(path, { method: "GET" });
  },
  async post(path, body) {
    return await API.request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    });
  },
  async put(path, body) {
    return await API.request(path, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    });
  },
};

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
let loginPromise = null;
let toastTimer = null;
let repoSummaryByKey = new Map();
let settingsDialogDraftSnapshot = null;
let settingsDialogDirtyBefore = false;
let settingsDialogAuthUsernameBefore = "";
let settingsDialogSaved = false;
let lastWebdavTest = null;
let mustChangePassword = false;
let lastStorageHealthTotals = null;
let lastStorageHealthAt = 0;
let selectedRepoKeys = new Set();
let lastSyncCacheAnomalyRepoKeys = new Set();
let hasSyncCacheSnapshot = false;

const $ = (id) => document.getElementById(id);

function isBusy(el) {
  return el?.getAttribute("aria-busy") === "true";
}

function setDirty(v) {
  dirty = v;
  const saveBtn = $("saveBtn");
  saveBtn.disabled = isBusy(saveBtn) || !dirty || !config;
}

function formatError(e) {
  if (!e) return "未知错误";
  if (e?.code === "unauthorized") return "未登录或登录已过期。";
  if (e?.code === "password_change_required") return "首次登录后请先在设置中修改账号密码。";
  if (e?.code === "rate_limited") return "登录尝试过于频繁，请稍后再试。";
  return String(e?.message || e);
}

function toast(message, kind) {
  const el = $("toast");
  if (!el) return;
  if (!message) {
    el.classList.add("hidden");
    return;
  }
  el.textContent = message;
  el.className = `toast ${kind ?? ""}`.trim();
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.classList.add("hidden");
  }, 2400);
}

function setButtonBusy(btn, busy, busyText) {
  if (!btn) return;
  if (busy) {
    btn.dataset.prevDisabled = String(btn.disabled);
    btn.dataset.prevText = btn.textContent || "";
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
    if (busyText) btn.textContent = busyText;
  } else {
    btn.disabled = btn.dataset.prevDisabled === "true";
    btn.removeAttribute("aria-busy");
    if (btn.dataset.prevText != null) btn.textContent = btn.dataset.prevText;
    delete btn.dataset.prevDisabled;
    delete btn.dataset.prevText;
  }
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

function isoToLocal(iso) {
  if (!iso) return "-";
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso;
  }
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

function formatSignedDelta(value) {
  const n = Number(value) || 0;
  if (n > 0) return `+${n}`;
  return String(n);
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
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

function cloneDeep(obj) {
  return JSON.parse(JSON.stringify(obj));
}

function stableCopy(value) {
  if (Array.isArray(value)) return value.map(stableCopy);
  if (!value || typeof value !== "object") return value;
  const out = {};
  for (const key of Object.keys(value).sort()) {
    out[key] = stableCopy(value[key]);
  }
  return out;
}

function stableStringify(value) {
  return JSON.stringify(stableCopy(value));
}

function hasSettingsDialogUnsavedChanges() {
  if (!settingsDialogDraftSnapshot || !draft) return false;
  try {
    return stableStringify(draft) !== stableStringify(settingsDialogDraftSnapshot);
  } catch {
    return false;
  }
}

function renderWebdavTestHint() {
  const el = $("webdavTestHint");
  if (!el) return;
  if (!lastWebdavTest) {
    el.className = "hint";
    el.textContent = "上次测试：未测试";
    return;
  }
  el.className = lastWebdavTest.ok ? "hint" : "hint danger";
  el.textContent = `上次测试：${lastWebdavTest.time} · ${lastWebdavTest.ok ? "连接正常" : `失败：${lastWebdavTest.message}`}`;
}

function invalidateWebdavTest() {
  lastWebdavTest = null;
  renderWebdavTestHint();
}

function repoDraft(key) {
  if (!draft.repos[key]) {
    draft.repos[key] = {};
  }
  return draft.repos[key];
}

function getRepoListView() {
  if (!config || !Array.isArray(config.repos)) {
    return { repos: [], filterText: "", total: 0 };
  }
  const filterText = String($("repoFilterInput")?.value || "")
    .trim()
    .toLowerCase();
  const stateFilter = String($("repoStateFilterSelect")?.value || "all").trim();
  const sortMode = String($("repoSortSelect")?.value || "default").trim();
  let repos = Array.from(config.repos);
  if (filterText) {
    repos = repos.filter((r) => {
      const key = String(r?.key || "").toLowerCase();
      const name = String(r?.name || "").toLowerCase();
      return key.includes(filterText) || name.includes(filterText);
    });
  }
  if (stateFilter !== "all") {
    const validRepoKeys = new Set(repos.map((r) => String(r?.key || "")));
    if (stateFilter === "cache_anomaly") {
      const next = new Set();
      for (const key of lastSyncCacheAnomalyRepoKeys) {
        if (validRepoKeys.has(key)) next.add(key);
      }
      lastSyncCacheAnomalyRepoKeys = next;
    }
    repos = repos.filter((r) => {
      const key = String(r?.key || "");
      const enabled = isRepoEnabledForRun(key);
      if (stateFilter === "enabled") return enabled;
      if (stateFilter === "disabled") return !enabled;
      if (stateFilter === "error") return isRepoInErrorState(key);
      if (stateFilter === "network_error") {
        const summary = repoSummaryByKey.get(key);
        return summary?.stats?.last_check_ok === false && summary?.stats?.last_error_type === "network";
      }
      if (stateFilter === "cache_anomaly") {
        return lastSyncCacheAnomalyRepoKeys.has(key);
      }
      return true;
    });
  }

  const statusRank = (repoKey) => {
    const summary = repoSummaryByKey.get(repoKey);
    const ok = summary?.stats?.last_check_ok;
    if (ok === false) return summary?.stats?.last_error_type === "network" ? 0 : 1;
    if (ok === true) return 3;
    return 2;
  };
  const nextRank = (repoKey) => {
    const summary = repoSummaryByKey.get(repoKey);
    const iso = summary?.next_run_at;
    const t = iso ? Date.parse(iso) : Number.POSITIVE_INFINITY;
    return Number.isFinite(t) ? t : Number.POSITIVE_INFINITY;
  };

  if (sortMode === "status") {
    repos.sort((a, b) => {
      const ak = String(a.key || "");
      const bk = String(b.key || "");
      const ar = statusRank(ak);
      const br = statusRank(bk);
      if (ar !== br) return ar - br;
      const an = nextRank(ak);
      const bn = nextRank(bk);
      if (an !== bn) return an - bn;
      return ak.localeCompare(bk);
    });
  } else if (sortMode === "next") {
    repos.sort((a, b) => {
      const ak = String(a.key || "");
      const bk = String(b.key || "");
      const an = nextRank(ak);
      const bn = nextRank(bk);
      if (an !== bn) return an - bn;
      return ak.localeCompare(bk);
    });
  }

  return { repos, filterText, stateFilter, total: config.repos.length };
}

function getVisibleRepoKeys() {
  const view = getRepoListView();
  const keys = [];
  for (const repo of view.repos) {
    const key = String(repo?.key || "");
    if (key) keys.push(key);
  }
  return keys;
}

function syncSelectedReposWithConfig() {
  const existing = new Set(Array.isArray(config?.repos) ? config.repos.map((r) => String(r?.key || "")) : []);
  const next = new Set();
  for (const key of selectedRepoKeys) {
    if (existing.has(key)) next.add(key);
  }
  selectedRepoKeys = next;
}

function getSelectedRepoKeys() {
  syncSelectedReposWithConfig();
  return Array.from(selectedRepoKeys);
}

function getRepoConfigByKey(key) {
  if (!config || !Array.isArray(config.repos)) return null;
  for (const repo of config.repos) {
    if (String(repo?.key || "") === String(key || "")) return repo;
  }
  return null;
}

function isRepoEnabledForRun(key) {
  const repoCfg = getRepoConfigByKey(key);
  if (!repoCfg) return false;
  const patch = draft?.repos?.[key] || {};
  if (Object.prototype.hasOwnProperty.call(patch, "enabled")) return !!patch.enabled;
  return !!repoCfg.enabled;
}

function isRepoInErrorState(key) {
  const summary = repoSummaryByKey.get(String(key || ""));
  return summary?.stats?.last_check_ok === false;
}

function isRepoInCacheAnomalyState(key) {
  return lastSyncCacheAnomalyRepoKeys.has(String(key || ""));
}

function isWebdavStorageMode() {
  const mode = String(draft?.storage?.mode || config?.storage?.mode || "local").trim().toLowerCase();
  return mode === "webdav";
}

function setBatchActionHint(message, kind) {
  const el = $("batchActionHint");
  if (!el) return;
  el.className = kind === "danger" ? "hint danger" : "hint";
  el.textContent = String(message || "");
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
  const disabled = !config || count <= 0;
  const visibleDisabled = !config || visible.length <= 0;
  if (selectVisibleBtn) selectVisibleBtn.disabled = isBusy(selectVisibleBtn) || visibleDisabled;
  if (invertVisibleBtn) invertVisibleBtn.disabled = isBusy(invertVisibleBtn) || visibleDisabled;
  if (selectEnabledBtn) selectEnabledBtn.disabled = isBusy(selectEnabledBtn) || visibleDisabled;
  if (selectErrorBtn) selectErrorBtn.disabled = isBusy(selectErrorBtn) || visibleDisabled;
  if (selectCacheAnomalyBtn) {
    selectCacheAnomalyBtn.disabled = isBusy(selectCacheAnomalyBtn) || visibleDisabled || !cacheSelectReady;
    if (!webdavMode) selectCacheAnomalyBtn.title = "当前存储模式不是 WebDAV。";
    else if (!hasSyncCacheSnapshot) selectCacheAnomalyBtn.title = '请先在设置中执行一次“同步缓存”。';
    else selectCacheAnomalyBtn.title = "";
  }
  if (runBtn) runBtn.disabled = isBusy(runBtn) || !config || runnableCount <= 0;
  if (enableBtn) enableBtn.disabled = isBusy(enableBtn) || disabled;
  if (disableBtn) disableBtn.disabled = isBusy(disableBtn) || disabled;
  if (clearBtn) clearBtn.disabled = !config || count <= 0;
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
    typeAdder.className = "inline";
    typeAdder.style.marginTop = "8px";

    const typeInput = document.createElement("input");
    typeInput.className = "input sm";
    typeInput.placeholder = "自定义类型，如: msi";
    typeInput.setAttribute("aria-label", "添加自定义类型");

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

function syncSettingsFormFromDraft() {
  const mode = draft?.storage?.mode || "local";
  $("storageModeLocal").checked = mode === "local";
  $("storageModeWebdav").checked = mode === "webdav";

  $("localDirInput").value = draft?.storage?.local_dir || "";
  $("webdavBaseUrl").value = draft?.storage?.webdav?.base_url || "";
  $("webdavUsername").value = draft?.storage?.webdav?.username || "";
  $("webdavTimeout").value = String(draft?.storage?.webdav?.timeout_seconds ?? 60);
  $("webdavVerifyTls").checked = !!(draft?.storage?.webdav?.verify_tls ?? true);
  $("webdavUploadConcurrency").value = String(draft?.storage?.webdav?.upload_concurrency ?? 2);
  $("webdavMaxRetries").value = String(draft?.storage?.webdav?.max_retries ?? 3);
  $("webdavRetryBackoffSeconds").value = String(draft?.storage?.webdav?.retry_backoff_seconds ?? 2);
  $("webdavVerifyAfterUpload").checked = !!(draft?.storage?.webdav?.verify_after_upload ?? true);
  $("webdavUploadTempSuffix").value = String(draft?.storage?.webdav?.upload_temp_suffix || ".uploading");
  $("webdavCleanupMode").value = String(draft?.storage?.webdav?.cleanup_mode || "delete");

  const fields = $("webdavFields");
  fields.classList.toggle("hidden", mode !== "webdav");
  renderWebdavTestHint();
}

function syncDraftFromSettingsForm() {
  const mode = $("storageModeWebdav").checked ? "webdav" : "local";
  draft.storage.mode = mode;
  draft.storage.local_dir = $("localDirInput").value.trim();
  draft.storage.webdav.base_url = $("webdavBaseUrl").value.trim();
  draft.storage.webdav.username = $("webdavUsername").value.trim();
  draft.storage.webdav.verify_tls = $("webdavVerifyTls").checked;
  draft.storage.webdav.timeout_seconds = Number($("webdavTimeout").value.trim() || 60);
  draft.storage.webdav.upload_concurrency = Number($("webdavUploadConcurrency").value.trim() || 2);
  draft.storage.webdav.max_retries = Number($("webdavMaxRetries").value.trim() || 3);
  draft.storage.webdav.retry_backoff_seconds = Number($("webdavRetryBackoffSeconds").value.trim() || 2);
  draft.storage.webdav.verify_after_upload = $("webdavVerifyAfterUpload").checked;
  draft.storage.webdav.upload_temp_suffix = String($("webdavUploadTempSuffix").value || ".uploading").trim();
  draft.storage.webdav.cleanup_mode = String($("webdavCleanupMode").value || "delete").trim();
  $("webdavFields").classList.toggle("hidden", mode !== "webdav");
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
  const items = data.items || [];
  const lines = items.map((x) => `${isoToLocal(x.time)} ${x.message}`);
  $("logs").textContent = lines.join("\n") || "暂无活动。";

  const hint = $("logFileHint");
  if (hint) {
    hint.textContent = data.log_file ? `日志文件：${data.log_file}` : "";
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

function formatStorageHealthTopRepos(repos, limit = 3) {
  const list = Array.isArray(repos) ? repos : [];
  const ranked = list
    .map((item) => ({
      repo: String(item?.repo || "").trim(),
      retry: Number(item?.upload_retry_total || 0),
      verifyFailed: Number(item?.upload_verify_failed_total || 0),
      queue: Number(item?.upload_queue_depth || 0),
    }))
    .filter((x) => x.repo && (x.retry > 0 || x.verifyFailed > 0 || x.queue > 0))
    .sort((a, b) => {
      if (a.verifyFailed !== b.verifyFailed) return b.verifyFailed - a.verifyFailed;
      if (a.retry !== b.retry) return b.retry - a.retry;
      if (a.queue !== b.queue) return b.queue - a.queue;
      return a.repo.localeCompare(b.repo);
    })
    .slice(0, Math.max(1, limit));
  return ranked;
}

function formatSyncCacheTopRepos(items, limit = 3) {
  const list = Array.isArray(items) ? items : [];
  const ranked = list
    .map((item) => ({
      repo: String(item?.repo || "").trim(),
      stale: Number(item?.stale_files || 0),
      missing: Number(item?.missing_files || 0),
      pruned: Number(item?.pruned_files || 0),
    }))
    .filter((x) => x.repo && (x.stale > 0 || x.missing > 0 || x.pruned > 0))
    .sort((a, b) => {
      if (a.missing !== b.missing) return b.missing - a.missing;
      if (a.stale !== b.stale) return b.stale - a.stale;
      if (a.pruned !== b.pruned) return b.pruned - a.pruned;
      return a.repo.localeCompare(b.repo);
    })
    .slice(0, Math.max(1, limit));
  return ranked;
}

async function refreshStorageDiagnostics() {
  const capsEl = $("webdavCapabilitiesHint");
  const healthEl = $("storageHealthHint");
  if (!capsEl || !healthEl) return;
  const mode = String(draft?.storage?.mode || "local");
  if (mode !== "webdav") {
    lastStorageHealthTotals = null;
    lastStorageHealthAt = 0;
    hasSyncCacheSnapshot = false;
    lastSyncCacheAnomalyRepoKeys = new Set();
    const stateSelect = $("repoStateFilterSelect");
    if (stateSelect?.value === "cache_anomaly") {
      stateSelect.value = "all";
      renderRepos();
    } else {
      updateBatchControlsUI();
    }
    capsEl.className = "hint";
    capsEl.textContent = "当前为本地存储模式。";
    healthEl.className = "hint";
    healthEl.textContent = "";
    return;
  }
  try {
    const caps = await withAuth(() => API.get("/storage/capabilities"));
    if (caps.error || caps.ok === false) {
      capsEl.className = "hint danger";
      capsEl.textContent = `能力探测失败：${caps.error || "未知错误"}`;
    } else {
      const enabled = Object.entries(caps.capabilities || {})
        .filter(([, v]) => !!v)
        .map(([k]) => k.toUpperCase());
      capsEl.className = "hint";
      capsEl.textContent = `WebDAV 能力：${enabled.length ? enabled.join(", ") : "未探测到"}`;
    }
  } catch (e) {
    capsEl.className = "hint danger";
    capsEl.textContent = `能力探测失败：${formatError(e)}`;
  }

  try {
    const health = await withAuth(() => API.get("/storage/health"));
    const totals = health.totals || {};
    const current = {
      retry: Number(totals.upload_retry_total || 0),
      verify_failed: Number(totals.upload_verify_failed_total || 0),
      queue: Number(totals.upload_queue_depth || 0),
    };
    let trendText = "趋势：首次采样。";
    const now = Date.now();
    if (lastStorageHealthTotals && lastStorageHealthAt > 0) {
      const elapsed = secondsToElapsedText((now - lastStorageHealthAt) / 1000);
      trendText = `趋势（较 ${elapsed} 前）：重试 ${formatSignedDelta(
        current.retry - (lastStorageHealthTotals.retry || 0)
      )}，校验失败 ${formatSignedDelta(
        current.verify_failed - (lastStorageHealthTotals.verify_failed || 0)
      )}，队列 ${formatSignedDelta(current.queue - (lastStorageHealthTotals.queue || 0))}`;
    }
    lastStorageHealthTotals = current;
    lastStorageHealthAt = now;
    const topRepos = formatStorageHealthTopRepos(health.repos || [], 3);
    healthEl.className = "hint";
    const mainText = `上传健康：重试 ${current.retry} 次，校验失败 ${current.verify_failed} 次，队列深度 ${current.queue}。${trendText}`;
    if (!topRepos.length) {
      healthEl.textContent = `${mainText} 重点仓库：暂无异常。`;
      return;
    }
    const topLinks = topRepos
      .map((x) => {
        const href = `/repo.html?repo=${encodeURIComponent(x.repo)}`;
        const label = `${x.repo}(重试${x.retry}/校验${x.verifyFailed}/队列${x.queue})`;
        return `<a href="${href}">${escapeHtml(label)}</a>`;
      })
      .join("；");
    healthEl.innerHTML = `${escapeHtml(mainText)} 重点仓库：${topLinks}`;
  } catch (e) {
    healthEl.className = "hint danger";
    healthEl.textContent = `上传健康读取失败：${formatError(e)}`;
  }
}

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

function batchSelectVisible() {
  const visible = getVisibleRepoKeys();
  if (!visible.length) {
    setBatchActionHint("当前筛选结果为空，无可选仓库。", "danger");
    return;
  }
  let added = 0;
  for (const key of visible) {
    if (selectedRepoKeys.has(key)) continue;
    selectedRepoKeys.add(key);
    added += 1;
  }
  const msg = added > 0 ? `已新增选择 ${added} 个仓库。` : `当前筛选内 ${visible.length} 个仓库已全部选中。`;
  setBatchActionHint(msg, "");
  renderRepos();
}

function batchSelectByFilter(predicate, successMessage, emptyMessage) {
  const visible = getVisibleRepoKeys();
  if (!visible.length) {
    setBatchActionHint("当前筛选结果为空，无可选仓库。", "danger");
    return;
  }
  let selectedNow = 0;
  for (const key of visible) {
    if (!predicate(key)) continue;
    if (selectedRepoKeys.has(key)) continue;
    selectedRepoKeys.add(key);
    selectedNow += 1;
  }
  if (selectedNow <= 0) {
    setBatchActionHint(emptyMessage, "danger");
    renderRepos();
    return;
  }
  setBatchActionHint(successMessage(selectedNow), "");
  renderRepos();
}

function batchInvertVisible() {
  const visible = getVisibleRepoKeys();
  if (!visible.length) {
    setBatchActionHint("当前筛选结果为空，无法反选。", "danger");
    return;
  }
  let selectedNow = 0;
  let unselectedNow = 0;
  for (const key of visible) {
    if (selectedRepoKeys.has(key)) {
      selectedRepoKeys.delete(key);
      unselectedNow += 1;
    } else {
      selectedRepoKeys.add(key);
      selectedNow += 1;
    }
  }
  const msg = `反选完成：选中 ${selectedNow} 个，取消 ${unselectedNow} 个。`;
  setBatchActionHint(msg, "");
  renderRepos();
}

function batchSelectEnabledVisible() {
  batchSelectByFilter(
    (key) => isRepoEnabledForRun(key),
    (count) => `已选中 ${count} 个启用仓库。`,
    "当前筛选结果中没有可新增的启用仓库。"
  );
}

function batchSelectErrorVisible() {
  batchSelectByFilter(
    (key) => isRepoInErrorState(key),
    (count) => `已选中 ${count} 个异常仓库。`,
    "当前筛选结果中没有可新增的异常仓库。"
  );
}

function batchSelectCacheAnomalyVisible() {
  if (!isWebdavStorageMode()) {
    setBatchActionHint("当前存储模式不是 WebDAV，无法选择缓存异常仓库。", "danger");
    return;
  }
  if (!hasSyncCacheSnapshot) {
    setBatchActionHint("请先在设置中执行一次“同步缓存”，再选择缓存异常仓库。", "danger");
    return;
  }
  batchSelectByFilter(
    (key) => isRepoInCacheAnomalyState(key),
    (count) => `已选中 ${count} 个缓存异常仓库。`,
    "当前筛选结果中没有可新增的缓存异常仓库。"
  );
}

async function batchSetEnabled(enabled, triggerBtn) {
  const selected = getSelectedRepoKeys();
  if (!selected.length) {
    setBatchActionHint("请先选择至少一个仓库。", "danger");
    toast("请先选择至少一个仓库。", "warn");
    return;
  }
  setBatchActionHint("", "");
  for (const key of selected) {
    repoDraft(key).enabled = !!enabled;
  }
  setDirty(true);
  renderRepos();
  const ok = await saveSettings({ busyButtons: triggerBtn ? [triggerBtn] : [] });
  if (!ok) {
    setBatchActionHint(`批量${enabled ? "启用" : "停用"}失败。`, "danger");
    return;
  }
  const msg = `批量${enabled ? "启用" : "停用"}完成：${selected.length} 个仓库。`;
  setBatchActionHint(msg, "");
  toast(msg, "ok");
}

async function batchRunSelected(triggerBtn) {
  const selected = getSelectedRepoKeys();
  if (!selected.length) {
    setBatchActionHint("请先选择至少一个仓库。", "danger");
    toast("请先选择至少一个仓库。", "warn");
    return;
  }
  const runnableSelected = selected.filter((key) => isRepoEnabledForRun(key));
  if (!runnableSelected.length) {
    setBatchActionHint("所选仓库均为停用状态，无法批量检查。", "danger");
    toast("所选仓库均为停用状态，请先启用后再批量检查。", "warn");
    return;
  }
  if (mustChangePassword) {
    renderSecurityBanner();
    setBatchActionHint("当前账号需先修改密码，已阻止批量触发。", "danger");
    toast("当前账号需先修改密码，请先在设置中更新账号密码。", "warn");
    return;
  }
  const skipped = selected.length - runnableSelected.length;
  const skippedSuffix = skipped > 0 ? `（跳过 ${skipped} 个停用仓库）` : "";
  setBatchActionHint("", "");
  setButtonBusy(triggerBtn, true, "触发中…");
  try {
    const res = await withAuth(() => API.post("/run", { repos: runnableSelected }));
    if (res.error) {
      const msg = `批量触发失败：${res.error}`;
      setBatchActionHint(msg, "danger");
      toast(msg, "bad");
      return;
    }
    const msg = res.queued
      ? `批量检查已入队：${runnableSelected.length} 个仓库。${skippedSuffix}`
      : "已有任务在运行或队列中，本次批量请求未入队。";
    setBatchActionHint(msg, "");
    toast(msg, res.queued ? "ok" : "warn");
  } catch (e) {
    const msg = `批量触发失败：${formatError(e)}`;
    setBatchActionHint(msg, "danger");
    toast(msg, "bad");
  } finally {
    setButtonBusy(triggerBtn, false);
    await refreshStatusSafe().catch(() => {});
    updateBatchControlsUI();
  }
}

function validateIntField({ inputId, label, min, max, emptyOk }) {
  const el = $(inputId);
  const raw = String(el.value || "").trim();
  if (!raw) {
    if (emptyOk) return null;
    throw new Error(`${label}不能为空。`);
  }
  const num = Number(raw);
  if (!Number.isFinite(num) || !Number.isInteger(num)) throw new Error(`${label}必须为整数。`);
  if (min != null && num < min) throw new Error(`${label}必须 ≥ ${min}。`);
  if (max != null && num > max) throw new Error(`${label}必须 ≤ ${max}。`);
  return num;
}

function validateNumberField({ inputId, label, min, max, emptyOk }) {
  const el = $(inputId);
  const raw = String(el.value || "").trim();
  if (!raw) {
    if (emptyOk) return null;
    throw new Error(`${label}不能为空。`);
  }
  const num = Number(raw);
  if (!Number.isFinite(num)) throw new Error(`${label}必须为数字。`);
  if (min != null && num < min) throw new Error(`${label}必须 ≥ ${min}。`);
  if (max != null && num > max) throw new Error(`${label}必须 ≤ ${max}。`);
  return num;
}

function normalizeRepoPatch(key, patch) {
  const normalized = { ...patch };
  if ("keep_last" in normalized) {
    const raw = normalized.keep_last;
    if (raw === null || raw === undefined || raw === "") normalized.keep_last = null;
    else {
      const num = Number(raw);
      if (!Number.isFinite(num) || !Number.isInteger(num) || num < 1 || num > 1000) {
        throw new Error(`仓库 ${key} 的保留数量必须为 1~1000 或留空。`);
      }
      normalized.keep_last = num;
    }
  }
  if ("asset_types" in normalized) {
    const list = Array.isArray(normalized.asset_types) ? normalized.asset_types : [];
    const out = [];
    for (const item of list) {
      const norm = normalizeAssetType(item);
      if (!out.includes(norm)) out.push(norm);
    }
    normalized.asset_types = out;
  }
  return normalized;
}

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
      $("settingsHint").textContent = `保存失败：${res.error}`;
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
    $("settingsHint").textContent = `保存失败：${formatError(e)}`;
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
  setTimeout(() => $("newRepoName")?.focus(), 0);
}

async function copyText(text) {
  try {
    await navigator.clipboard?.writeText(text);
    return true;
  } catch {}
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "true");
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    ta.style.top = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    return ok;
  } catch {
    return false;
  }
}

async function copyLogs() {
  const text = $("logs").textContent || "";
  const ok = await copyText(text);
  toast(ok ? "已复制活动。" : "复制失败，请手动选择复制。", ok ? "ok" : "warn");
}

function openSettingsDialog(options = {}) {
  const focusAuthPassword = !!options.focusAuthPassword;
  if (!draft) {
    toast("配置未加载。", "bad");
    return;
  }
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
  refreshStorageDiagnostics().catch(() => {});
  setTimeout(() => {
    if (focusAuthPassword) $("authPassword")?.focus();
    else $("localDirInput")?.focus();
  }, 0);
}

function wireEvents() {
  $("runNowBtn").addEventListener("click", runNow);
  $("settingsBtn").addEventListener("click", () => openSettingsDialog({ focusAuthPassword: false }));
  $("logoutBtn").addEventListener("click", async () => {
    const btn = $("logoutBtn");
    setButtonBusy(btn, true, "退出中…");
    try {
      await API.post("/logout", {});
    } catch {}
    setUser(null);
    try {
      await requireLogin();
      await withAuth(() => loadAll());
      toast("已重新登录。", "ok");
    } finally {
      setButtonBusy(btn, false);
      setUser(currentUser);
    }
  });
  $("reloadBtn").addEventListener("click", async () => {
    const btn = $("reloadBtn");
    setButtonBusy(btn, true, "加载中…");
    try {
      await withAuth(() => API.post("/reload", {}));
      await withAuth(() => loadAll());
      toast("配置已重新加载。", "ok");
    } catch (e) {
      toast(`重新加载失败：${formatError(e)}`, "bad");
    } finally {
      setButtonBusy(btn, false);
    }
  });
  $("saveBtn").addEventListener("click", async () => {
    await saveSettings({ busyButtons: [$("saveBtn")] });
  });
  $("schedulerToggle").addEventListener("change", async (e) => {
    const el = e.target;
    const desired = !!el.checked;
    el.disabled = true;
    try {
      await setScheduler(desired);
      toast(desired ? "自动轮询已开启。" : "自动轮询已关闭。", "ok");
    } catch (err) {
      el.checked = !desired;
      toast(`设置失败：${formatError(err)}`, "bad");
    } finally {
      el.disabled = false;
    }
  });
  $("keepLastInput").addEventListener("input", () => {
    setDirty(true);
    renderRepos();
  });
  $("intervalInput").addEventListener("input", () => setDirty(true));
  $("repoFilterInput").addEventListener("input", () => renderRepos());
  $("repoStateFilterSelect").addEventListener("change", () => renderRepos());
  $("repoSortSelect").addEventListener("change", () => renderRepos());
  $("addRepoBtn").addEventListener("click", openRepoDialog);
  $("copyLogsBtn").addEventListener("click", copyLogs);
  $("batchSelectVisibleBtn").addEventListener("click", batchSelectVisible);
  $("batchInvertVisibleBtn").addEventListener("click", batchInvertVisible);
  $("batchSelectEnabledBtn").addEventListener("click", batchSelectEnabledVisible);
  $("batchSelectErrorBtn").addEventListener("click", batchSelectErrorVisible);
  $("batchSelectCacheAnomalyBtn").addEventListener("click", batchSelectCacheAnomalyVisible);
  $("batchRunBtn").addEventListener("click", async () => batchRunSelected($("batchRunBtn")));
  $("batchEnableBtn").addEventListener("click", async () => batchSetEnabled(true, $("batchEnableBtn")));
  $("batchDisableBtn").addEventListener("click", async () => batchSetEnabled(false, $("batchDisableBtn")));
  $("batchClearBtn").addEventListener("click", () => {
    selectedRepoKeys.clear();
    setBatchActionHint("已清空选择。", "");
    renderRepos();
  });

  const settingsForm = $("settingsDialog").querySelector("form");
  settingsForm?.addEventListener("submit", (e) => e.preventDefault());
  const repoForm = $("repoDialog").querySelector("form");
  repoForm?.addEventListener("submit", (e) => e.preventDefault());

  const settingsDialog = $("settingsDialog");
  for (const btn of settingsDialog.querySelectorAll('button[value="cancel"]')) {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      settingsDialogSaved = false;
      if (hasSettingsDialogUnsavedChanges()) {
        const ok = window.confirm("设置未保存，确定取消并丢弃本次修改吗？");
        if (!ok) return;
      }
      try {
        settingsDialog.close();
      } catch {}
    });
  }
  settingsDialog.addEventListener("cancel", (e) => {
    settingsDialogSaved = false;
    if (!hasSettingsDialogUnsavedChanges()) return;
    const ok = window.confirm("设置未保存，确定取消并丢弃本次修改吗？");
    if (!ok) e.preventDefault();
  });
  settingsDialog.addEventListener("close", () => {
    const saved = settingsDialogSaved;
    settingsDialogSaved = false;

    if ($("webdavPassword")) $("webdavPassword").value = "";
    if ($("authPassword")) $("authPassword").value = "";
    $("settingsHint").textContent = "";

    if (!saved && settingsDialogDraftSnapshot) {
      draft = settingsDialogDraftSnapshot;
      dirty = settingsDialogDirtyBefore;
      setDirty(dirty);
      if ($("authUsername")) $("authUsername").value = settingsDialogAuthUsernameBefore || $("authUsername").value;
      syncSettingsFormFromDraft();
      renderRepos();
    }

    settingsDialogDraftSnapshot = null;
    settingsDialogAuthUsernameBefore = "";
  });

  const repoDialog = $("repoDialog");
  for (const btn of repoDialog.querySelectorAll('button[value="cancel"]')) {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      try {
        repoDialog.close();
      } catch {}
    });
  }
  for (const id of [
    "storageModeLocal",
    "storageModeWebdav",
    "localDirInput",
    "webdavBaseUrl",
    "webdavUsername",
    "webdavPassword",
    "webdavTimeout",
    "webdavVerifyTls",
    "webdavUploadConcurrency",
    "webdavMaxRetries",
    "webdavRetryBackoffSeconds",
    "webdavVerifyAfterUpload",
    "webdavUploadTempSuffix",
    "webdavCleanupMode",
    "authUsername",
    "authPassword",
  ]) {
    $(id).addEventListener("input", () => setDirty(true));
    $(id).addEventListener("change", () => setDirty(true));
  }
  for (const id of [
    "webdavBaseUrl",
    "webdavUsername",
    "webdavPassword",
    "webdavTimeout",
    "webdavVerifyTls",
    "webdavUploadConcurrency",
    "webdavMaxRetries",
    "webdavRetryBackoffSeconds",
    "webdavVerifyAfterUpload",
    "webdavUploadTempSuffix",
    "webdavCleanupMode",
  ]) {
    $(id).addEventListener("input", invalidateWebdavTest);
    $(id).addEventListener("change", invalidateWebdavTest);
  }
  $("storageModeLocal").addEventListener("change", syncDraftFromSettingsForm);
  $("storageModeWebdav").addEventListener("change", syncDraftFromSettingsForm);

  $("testWebdavBtn").addEventListener("click", async () => {
    const btn = $("testWebdavBtn");
    setButtonBusy(btn, true, "测试中…");
    $("settingsHint").textContent = "";
    if (!$("storageModeWebdav").checked) {
      toast("提示：当前不是 WebDAV 模式，仍可测试填写的连接信息。", "warn");
    }
    const patch = {
      base_url: $("webdavBaseUrl").value.trim(),
      username: $("webdavUsername").value.trim(),
      password: $("webdavPassword").value || "",
      verify_tls: $("webdavVerifyTls").checked,
      timeout_seconds: Number($("webdavTimeout").value.trim() || 60),
      upload_concurrency: Number($("webdavUploadConcurrency").value.trim() || 2),
      max_retries: Number($("webdavMaxRetries").value.trim() || 3),
      retry_backoff_seconds: Number($("webdavRetryBackoffSeconds").value.trim() || 2),
      verify_after_upload: $("webdavVerifyAfterUpload").checked,
      upload_temp_suffix: String($("webdavUploadTempSuffix").value || ".uploading").trim(),
      cleanup_mode: String($("webdavCleanupMode").value || "delete").trim().toLowerCase(),
    };
    try {
      const res = await withAuth(() => API.post("/storage/test", { webdav: patch }));
      lastWebdavTest = {
        time: new Date().toLocaleString(),
        ok: !!res.ok,
        message: String(res.error || ""),
      };
      renderWebdavTestHint();
      toast(res.ok ? "WebDAV 连接正常。" : `WebDAV 测试失败：${res.error || ""}`, res.ok ? "ok" : "warn");
    } catch (e) {
      lastWebdavTest = { time: new Date().toLocaleString(), ok: false, message: formatError(e) };
      renderWebdavTestHint();
      toast(`WebDAV 测试失败：${formatError(e)}`, "bad");
    } finally {
      setButtonBusy(btn, false);
    }
  });

  $("checkWebdavCapsBtn").addEventListener("click", async () => {
    const btn = $("checkWebdavCapsBtn");
    setButtonBusy(btn, true, "探测中…");
    try {
      await refreshStorageDiagnostics();
      toast("能力探测已更新。", "ok");
    } catch (e) {
      toast(`能力探测失败：${formatError(e)}`, "bad");
    } finally {
      setButtonBusy(btn, false);
    }
  });

  $("previewCleanupBtn").addEventListener("click", async () => {
    const btn = $("previewCleanupBtn");
    const hint = $("cleanupPreviewHint");
    setButtonBusy(btn, true, "预演中…");
    hint.className = "hint";
    hint.textContent = "";
    try {
      const data = await withAuth(() => API.post("/cleanup/preview", {}));
      const items = Array.isArray(data.items) ? data.items : [];
      const total = items.reduce((acc, x) => acc + Number(x.delete_count || 0), 0);
      hint.textContent = `清理预演：${items.length} 个仓库，预计删除 ${total} 个版本。`;
      if (items.length) {
        const top = items
          .filter((x) => Number(x.delete_count || 0) > 0)
          .sort((a, b) => Number(b.delete_count || 0) - Number(a.delete_count || 0))
          .slice(0, 3)
          .map((x) => `${x.repo}:${x.delete_count}`)
          .join("，");
        if (top) hint.textContent += ` 主要仓库：${top}`;
      }
      toast("清理预演完成。", "ok");
    } catch (e) {
      hint.className = "hint danger";
      hint.textContent = `清理预演失败：${formatError(e)}`;
      toast(`清理预演失败：${formatError(e)}`, "bad");
    } finally {
      setButtonBusy(btn, false);
    }
  });

  $("syncCacheBtn").addEventListener("click", async () => {
    const btn = $("syncCacheBtn");
    const hint = $("syncCacheHint");
    const prune = !!$("syncCachePruneToggle")?.checked;
    setButtonBusy(btn, true, "同步中…");
    hint.className = "hint";
    hint.textContent = "";
    try {
      const data = await withAuth(() => API.post("/storage/sync-cache", { prune }));
      const totals = data.totals || {};
      const items = Array.isArray(data.items) ? data.items : [];
      const anomalyRepos = items
        .map((item) => ({
          repo: String(item?.repo || "").trim(),
          stale: Number(item?.stale_files || 0),
          missing: Number(item?.missing_files || 0),
        }))
        .filter((x) => x.repo && (x.stale > 0 || x.missing > 0))
        .map((x) => x.repo);
      lastSyncCacheAnomalyRepoKeys = new Set(anomalyRepos);
      hasSyncCacheSnapshot = true;
      const pruned = Number(totals.pruned_files || 0);
      const staleCount = Number(totals.stale_files || 0);
      const missingCount = Number(totals.missing_files || 0);
      const summary = `缓存同步${prune ? "（已执行清理）" : ""}：检查 ${totals.cache_files_checked || 0} 个文件，发现 stale ${
        totals.stale_files || 0
      } 个，缺失 ${totals.missing_files || 0} 个。`;
      const topRepos = formatSyncCacheTopRepos(items, 3);
      const hasAnomaly = staleCount > 0 || missingCount > 0;
      hint.className = hasAnomaly ? "hint danger" : "hint";
      if (!topRepos.length) {
        hint.textContent = `${summary}${prune ? ` 已清理 ${pruned} 个。` : ""} 异常仓库：无。`;
      } else {
        const topLinks = topRepos
          .map((x) => {
            const href = `/repo.html?repo=${encodeURIComponent(x.repo)}`;
            const label = `${x.repo}(stale${x.stale}/缺失${x.missing}${prune ? `/清理${x.pruned}` : ""})`;
            return `<a href="${href}">${escapeHtml(label)}</a>`;
          })
          .join("；");
        hint.innerHTML = `${escapeHtml(summary)}${prune ? ` 已清理 ${pruned} 个。` : ""} 重点仓库：${topLinks}。可在仓库状态筛选中选择“仅缓存异常”进行批量处理。`;
      }
      if ($("repoStateFilterSelect")?.value === "cache_anomaly") renderRepos();
      if (prune) {
        // Keep toast lightweight; detailed cleanup context is shown in hint.
        toast(`缓存同步完成，已清理 ${pruned} 个。`, "ok");
      } else {
        toast("缓存同步完成。", "ok");
      }
    } catch (e) {
      hint.className = "hint danger";
      hint.textContent = `缓存同步失败：${formatError(e)}`;
      toast(`缓存同步失败：${formatError(e)}`, "bad");
    } finally {
      setButtonBusy(btn, false);
      updateBatchControlsUI();
    }
  });

  $("saveSettingsBtn").addEventListener("click", async () => {
    const ok = await saveSettings({ busyButtons: [$("saveSettingsBtn")] });
    if (!ok) return;
    settingsDialogSaved = true;
    try {
      $("settingsDialog").close();
    } catch {}
  });
}

function startLoginFlow(message) {
  if (loginPromise) return loginPromise;
  loginPromise = new Promise((resolve) => {
    const dlg = $("loginDialog");
    $("loginError").textContent = message || "";
    $("loginUsername").value = "";
    $("loginPassword").value = "";
    dlg.showModal();
    setTimeout(() => $("loginUsername").focus(), 0);
    dlg.addEventListener(
      "cancel",
      (e) => {
        e.preventDefault();
      },
      { once: true }
    );

    const onDone = (username) => {
      setUser(username);
      try {
        dlg.close();
      } catch {}
      $("loginForm").onsubmit = null;
      loginPromise = null;
      resolve();
    };

    $("loginForm").onsubmit = async (e) => {
      e.preventDefault();
      const username = ($("loginUsername").value || "").trim();
      const password = $("loginPassword").value || "";
      if (!username || !password) {
        $("loginError").textContent = "请输入账号与密码。";
        return;
      }
      try {
        const resp = await fetch("/api/v1/login", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ username, password }),
        });
        const res = await resp.json().catch(() => ({}));
        if (!resp.ok || res.error) {
          if (res.error === "rate_limited" || resp.status === 429) {
            $("loginError").textContent = "登录过于频繁，请稍后再试。";
          } else {
            $("loginError").textContent = "账号或密码错误。";
          }
          return;
        }
        mustChangePassword = !!res.user?.must_change_password;
        renderSecurityBanner();
        onDone(res.user?.username || username);
      } catch (err) {
        $("loginError").textContent = String(err?.message || err);
      }
    };
  });
  return loginPromise;
}

async function requireLogin() {
  try {
    const me = await API.get("/me");
    mustChangePassword = !!me.user?.must_change_password;
    renderSecurityBanner();
    setUser(me.user?.username || "admin");
    return;
  } catch (e) {
    if (e?.code !== "unauthorized") throw e;
  }
  await startLoginFlow();
}

async function main() {
  wireEvents();
  setConfigLoadedUI(false);
  $("logoutBtn").disabled = true;
  setUser(null);
  await requireLogin();
  await loadAll();
  await refreshLogs();
  if (mustChangePassword) {
    toast("请先在设置中修改默认账号密码。", "warn");
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

main().catch((e) => {
  buildBadge("初始化失败", "bad");
  $("logs").textContent = String(e?.stack || e);
});
