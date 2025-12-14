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

function repoDomId(key) {
  return `repoMeta-${String(key || "").replace(/[^a-zA-Z0-9_-]/g, "_")}`;
}

function repoSummaryText(summary) {
  if (!summary) return "";
  const stats = summary.stats || {};
  const current = stats.current_tag || stats.latest_release_tag || "-";
  const downloads = stats.download_assets_total ?? 0;
  const cleanups = stats.cleanup_tags_total ?? 0;
  const median = summary.update?.median_interval_seconds;
  const next = summary.next_run_at ? isoToLocal(summary.next_run_at) : "-";
  const updateEvery = median ? secondsToHuman(median) : "-";
  return `当前：${current} · 下载：${downloads} · 删除：${cleanups} · 更新约：${updateEvery} · 下次：${next}`;
}

function buildBadge(text, cls) {
  const el = $("statusBadge");
  el.textContent = text;
  el.className = `badge ${cls ?? ""}`.trim();
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

function repoDraft(key) {
  if (!draft.repos[key]) {
    draft.repos[key] = {};
  }
  return draft.repos[key];
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
  for (const repo of config.repos) {
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
    right.className = "inline";
    right.style.gap = "10px";

    const runBtn = document.createElement("button");
    runBtn.className = "btn";
    runBtn.type = "button";
    runBtn.textContent = "下载";
    runBtn.disabled = !repo.enabled;
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
    enabled.checked = !!repo.enabled;
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
    keepInput.placeholder = String(repo.effective_keep_last ?? "");
    keepInput.value = repo.keep_last ?? "";
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
    const baseTypes = repo.asset_types_effective || [];
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

  const fields = $("webdavFields");
  fields.classList.toggle("hidden", mode !== "webdav");
}

function syncDraftFromSettingsForm() {
  const mode = $("storageModeWebdav").checked ? "webdav" : "local";
  draft.storage.mode = mode;
  draft.storage.local_dir = $("localDirInput").value.trim();
  draft.storage.webdav.base_url = $("webdavBaseUrl").value.trim();
  draft.storage.webdav.username = $("webdavUsername").value.trim();
  draft.storage.webdav.verify_tls = $("webdavVerifyTls").checked;
  draft.storage.webdav.timeout_seconds = Number($("webdavTimeout").value.trim() || 60);
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
  setDirty(dirty);
}

async function loadAll() {
  const status = await API.get("/status");
  config = status.config;
  if (!config) {
    buildBadge("配置未加载", "bad");
    $("configHint").textContent = status.config_error ? `配置错误：${status.config_error}` : "配置未加载。";
    $("repos").innerHTML = "";
    setDirty(false);
    setConfigLoadedUI(false);
    return;
  }
  setConfigLoadedUI(true);
  $("configHint").textContent = `配置文件：${status.config_path}（覆盖文件：${status.overrides_path}）`;
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
}

async function refreshStatus() {
  const status = await API.get("/status");

  if (status.config_error) buildBadge("配置错误", "bad");
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

async function runNow() {
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

function wireEvents() {
  $("runNowBtn").addEventListener("click", runNow);
  $("settingsBtn").addEventListener("click", () => {
    if (!draft) {
      toast("配置未加载。", "bad");
      return;
    }
    $("settingsHint").textContent = "";
    syncSettingsFormFromDraft();
    $("settingsDialog").showModal();
    setTimeout(() => $("localDirInput")?.focus(), 0);
  });
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
  $("keepLastInput").addEventListener("input", () => setDirty(true));
  $("intervalInput").addEventListener("input", () => setDirty(true));
  $("addRepoBtn").addEventListener("click", openRepoDialog);
  $("copyLogsBtn").addEventListener("click", copyLogs);

  const settingsForm = $("settingsDialog").querySelector("form");
  settingsForm?.addEventListener("submit", (e) => e.preventDefault());
  const repoForm = $("repoDialog").querySelector("form");
  repoForm?.addEventListener("submit", (e) => e.preventDefault());
  for (const id of [
    "storageModeLocal",
    "storageModeWebdav",
    "localDirInput",
    "webdavBaseUrl",
    "webdavUsername",
    "webdavPassword",
    "webdavTimeout",
    "webdavVerifyTls",
    "authUsername",
    "authPassword",
  ]) {
    $(id).addEventListener("input", () => setDirty(true));
    $(id).addEventListener("change", () => setDirty(true));
  }
  $("storageModeLocal").addEventListener("change", syncDraftFromSettingsForm);
  $("storageModeWebdav").addEventListener("change", syncDraftFromSettingsForm);

  $("testWebdavBtn").addEventListener("click", async () => {
    const btn = $("testWebdavBtn");
    setButtonBusy(btn, true, "测试中…");
    $("settingsHint").textContent = "";
    const patch = {
      base_url: $("webdavBaseUrl").value.trim(),
      username: $("webdavUsername").value.trim(),
      password: $("webdavPassword").value || "",
      verify_tls: $("webdavVerifyTls").checked,
      timeout_seconds: Number($("webdavTimeout").value.trim() || 60),
    };
    try {
      const res = await withAuth(() => API.post("/storage/test", { webdav: patch }));
      $("settingsHint").textContent = res.ok ? "WebDAV 连接正常。" : `WebDAV 测试失败：${res.error || ""}`;
      toast(res.ok ? "WebDAV 连接正常。" : `WebDAV 测试失败：${res.error || ""}`, res.ok ? "ok" : "warn");
    } catch (e) {
      $("settingsHint").textContent = `WebDAV 测试失败：${formatError(e)}`;
      toast(`WebDAV 测试失败：${formatError(e)}`, "bad");
    } finally {
      setButtonBusy(btn, false);
    }
  });

  $("saveSettingsBtn").addEventListener("click", async () => {
    const ok = await saveSettings({ busyButtons: [$("saveSettingsBtn")] });
    if (!ok) return;
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
          $("loginError").textContent = "账号或密码错误。";
          return;
        }
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
