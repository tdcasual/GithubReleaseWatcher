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

let config = null;
let draft = null;
let dirty = false;
let currentUser = null;
let loginPromise = null;

const $ = (id) => document.getElementById(id);

function setDirty(v) {
  dirty = v;
  $("saveBtn").disabled = !dirty;
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

function buildBadge(text, cls) {
  const el = $("statusBadge");
  el.textContent = text;
  el.className = `badge ${cls ?? ""}`.trim();
}

function setUser(username) {
  currentUser = username || null;
  $("userBadge").textContent = currentUser ? currentUser : "未登录";
  $("logoutBtn").disabled = !currentUser;
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
  container.innerHTML = "";
  for (const t of PRESET_TYPES) {
    const label = document.createElement("label");
    label.className = "chip";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = selected.includes(t.key);
    input.addEventListener("change", () => onChange(t.key, input.checked));
    label.appendChild(input);
    const span = document.createElement("span");
    span.textContent = t.label;
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
      try {
        const res = await API.post("/run", { repo: repo.key });
        if (res.error) alert(`触发失败：${res.error}`);
      } catch (e) {
        if (e?.code === "unauthorized") await requireLogin();
        else alert(String(e?.message || e));
      }
      await refreshStatusSafe();
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
      runBtn.disabled = !enabled.checked;
      setDirty(true);
    });
    const slider = document.createElement("span");
    slider.className = "slider";
    sw.appendChild(enabled);
    sw.appendChild(slider);
    enabledWrap.appendChild(enabledLabel);
    enabledWrap.appendChild(sw);

    head.appendChild(title);
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
    const initialTypes = repo.asset_types_effective || [];
    renderTypeChips(chips, initialTypes, (key, checked) => {
      const current = new Set(repoDraft(repo.key).asset_types ?? initialTypes);
      if (checked) current.add(key);
      else current.delete(key);
      repoDraft(repo.key).asset_types = Array.from(current);
      setDirty(true);
    });
    typesBox.appendChild(typesLabel);
    typesBox.appendChild(chips);

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
  draft.storage.local_dir = $("localDirInput").value.trim() || draft.storage.local_dir;
  draft.storage.webdav.base_url = $("webdavBaseUrl").value.trim();
  draft.storage.webdav.username = $("webdavUsername").value.trim();
  draft.storage.webdav.verify_tls = $("webdavVerifyTls").checked;
  draft.storage.webdav.timeout_seconds = Number($("webdavTimeout").value.trim() || 60);
  $("webdavFields").classList.toggle("hidden", mode !== "webdav");
}

async function loadAll() {
  const status = await API.get("/status");
  config = status.config;
  if (!config) {
    buildBadge("配置未加载", "bad");
    $("configHint").textContent = status.config_error ? `配置错误：${status.config_error}` : "配置未加载。";
    return;
  }
  $("settingsBtn").disabled = false;
  $("configHint").textContent = `配置文件：${status.config_path}（覆盖文件：${status.overrides_path}）`;
  if (status.auth?.username) {
    setUser(status.auth.username);
    $("authUsername").value = status.auth.username;
  }

  materializeDraftFromConfig();
  setDirty(false);

  $("keepLastInput").value = String(config.app.keep_last);
  $("intervalInput").value = String(Math.max(1, Math.round(config.app.interval_seconds / 60)));
  syncSettingsFormFromDraft();

  renderRepos();
  await refreshStatus();
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

async function runNow() {
  await API.post("/run", {});
  await refreshStatusSafe();
}

async function saveSettings() {
  syncDraftFromSettingsForm();
  draft.app.keep_last = Number($("keepLastInput").value.trim() || 1);
  draft.app.interval_seconds = Number($("intervalInput").value.trim() || 10) * 60;

  const payload = cloneDeep(draft);
  const webdavPassword = $("webdavPassword").value || "";
  if (webdavPassword) {
    payload.storage = payload.storage || {};
    payload.storage.webdav = payload.storage.webdav || {};
    payload.storage.webdav.password = webdavPassword;
  }

  const newUsername = ($("authUsername").value || "").trim();
  const newPassword = $("authPassword").value || "";
  if (newPassword) {
    payload.auth = { username: newUsername, password: newPassword };
  }

  const res = await API.put("/settings", payload);
  if (res.error) {
    alert(`保存失败：${res.error}`);
    return;
  }
  $("webdavPassword").value = "";
  $("authPassword").value = "";
  $("settingsHint").textContent = "";
  await loadAll();
}

async function setScheduler(enabled) {
  await API.put("/scheduler", { enabled });
  await refreshStatus();
}

function openRepoDialog() {
  const dlg = $("repoDialog");
  $("newRepoName").value = "";
  const typesWrap = $("newRepoTypes");
  const selected = new Set(["exe", "apk"]);
  renderTypeChips(typesWrap, Array.from(selected), (key, checked) => {
    if (checked) selected.add(key);
    else selected.delete(key);
  });

  $("addTypeBtn").onclick = () => {
    const raw = $("newTypeInput").value.trim();
    if (!raw) return;
    selected.add(raw.replace(/^\./, "").toLowerCase());
    $("newTypeInput").value = "";
    renderTypeChips(typesWrap, Array.from(selected), (key, checked) => {
      if (checked) selected.add(key);
      else selected.delete(key);
    });
  };

  $("createRepoBtn").onclick = async (e) => {
    e.preventDefault();
    const name = $("newRepoName").value.trim();
    if (!name) {
      alert("请输入仓库名");
      return;
    }
    const patch = { name, enabled: true, asset_types: Array.from(selected) };
    draft.repos[name] = patch;
    setDirty(true);
    dlg.close();
    await saveSettings();
  };

  dlg.showModal();
}

function copyLogs() {
  const text = $("logs").textContent || "";
  navigator.clipboard?.writeText(text);
}

function wireEvents() {
  $("runNowBtn").addEventListener("click", runNow);
  $("settingsBtn").addEventListener("click", () => {
    if (!draft) {
      alert("配置未加载。");
      return;
    }
    $("settingsHint").textContent = "";
    syncSettingsFormFromDraft();
    $("settingsDialog").showModal();
  });
  $("logoutBtn").addEventListener("click", async () => {
    try {
      await API.post("/logout", {});
    } catch {}
    setUser(null);
    await requireLogin();
    await loadAll();
  });
  $("reloadBtn").addEventListener("click", async () => {
    await API.post("/reload", {});
    await loadAll();
  });
  $("saveBtn").addEventListener("click", saveSettings);
  $("schedulerToggle").addEventListener("change", (e) => setScheduler(e.target.checked));
  $("keepLastInput").addEventListener("input", () => setDirty(true));
  $("intervalInput").addEventListener("input", () => setDirty(true));
  $("addRepoBtn").addEventListener("click", openRepoDialog);
  $("copyLogsBtn").addEventListener("click", copyLogs);

  const settingsForm = $("settingsDialog").querySelector("form");
  settingsForm?.addEventListener("submit", (e) => e.preventDefault());
  for (const id of [
    "storageModeLocal",
    "storageModeWebdav",
    "localDirInput",
    "webdavBaseUrl",
    "webdavUsername",
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
    $("settingsHint").textContent = "";
    const patch = {
      base_url: $("webdavBaseUrl").value.trim(),
      username: $("webdavUsername").value.trim(),
      password: $("webdavPassword").value || "",
      verify_tls: $("webdavVerifyTls").checked,
      timeout_seconds: Number($("webdavTimeout").value.trim() || 60),
    };
    try {
      const res = await API.post("/storage/test", { webdav: patch });
      $("settingsHint").textContent = res.ok ? "WebDAV 连接正常。" : `WebDAV 测试失败：${res.error || ""}`;
    } catch (e) {
      if (e?.code === "unauthorized") await requireLogin();
      else $("settingsHint").textContent = `WebDAV 测试失败：${String(e?.message || e)}`;
    }
  });

  $("saveSettingsBtn").addEventListener("click", async () => {
    await saveSettings();
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
  $("settingsBtn").disabled = true;
  $("logoutBtn").disabled = true;
  setUser(null);
  await requireLogin();
  await loadAll();
  await refreshLogs();
  setInterval(() => refreshStatusSafe(), 2000);
  setInterval(async () => {
    try {
      await refreshLogs();
    } catch (e) {
      if (e?.code === "unauthorized") await requireLogin();
      else throw e;
    }
  }, 3000);
}

main().catch((e) => {
  buildBadge("初始化失败", "bad");
  $("logs").textContent = String(e?.stack || e);
});
