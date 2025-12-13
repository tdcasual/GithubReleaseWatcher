const API = {
  async get(path) {
    const res = await fetch(`/api/v1${path}`, { headers: { Accept: "application/json" } });
    return await res.json();
  },
  async post(path, body) {
    const res = await fetch(`/api/v1${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body ?? {}),
    });
    return await res.json();
  },
  async put(path, body) {
    const res = await fetch(`/api/v1${path}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body ?? {}),
    });
    return await res.json();
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
      setDirty(true);
    });
    const slider = document.createElement("span");
    slider.className = "slider";
    sw.appendChild(enabled);
    sw.appendChild(slider);
    enabledWrap.appendChild(enabledLabel);
    enabledWrap.appendChild(sw);

    head.appendChild(title);
    head.appendChild(enabledWrap);
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
  draft = { app: {}, repos: {} };
  draft.app.keep_last = config.app.keep_last;
  draft.app.interval_seconds = config.app.interval_seconds;
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

async function loadAll() {
  const status = await API.get("/status");
  config = status.config;
  if (!config) {
    buildBadge("配置未加载", "bad");
    $("configHint").textContent = status.config_error ? `配置错误：${status.config_error}` : "配置未加载。";
    return;
  }
  $("configHint").textContent = `配置文件：${status.config_path}（覆盖文件：${status.overrides_path}）`;

  materializeDraftFromConfig();
  setDirty(false);

  $("keepLastInput").value = String(config.app.keep_last);
  $("intervalInput").value = String(Math.max(1, Math.round(config.app.interval_seconds / 60)));

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

async function refreshLogs() {
  const data = await API.get("/logs?limit=200");
  const items = data.items || [];
  const lines = items.map((x) => `${isoToLocal(x.time)} ${x.level} ${x.message}`);
  $("logs").textContent = lines.join("\n") || "暂无日志。";
}

async function runNow() {
  await API.post("/run", {});
  await refreshStatus();
}

async function saveSettings() {
  draft.app.keep_last = Number($("keepLastInput").value.trim() || 1);
  draft.app.interval_seconds = Number($("intervalInput").value.trim() || 10) * 60;
  const res = await API.put("/settings", draft);
  if (res.error) {
    alert(`保存失败：${res.error}`);
    return;
  }
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
}

async function main() {
  wireEvents();
  await loadAll();
  await refreshLogs();
  setInterval(refreshStatus, 2000);
  setInterval(refreshLogs, 3000);
}

main().catch((e) => {
  buildBadge("初始化失败", "bad");
  $("logs").textContent = String(e?.stack || e);
});

