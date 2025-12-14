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
};

const $ = (id) => document.getElementById(id);

let toastTimer = null;
let loginPromise = null;
let repoKey = null;

function isoToLocal(iso) {
  if (!iso) return "-";
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

function secondsToHuman(seconds) {
  const s = Number(seconds);
  if (!Number.isFinite(s) || s <= 0) return "-";
  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  if (days > 0) return `${days}天${hours ? `${hours}小时` : ""}`;
  const minutes = Math.floor((s % 3600) / 60);
  if (hours > 0) return `${hours}小时${minutes ? `${minutes}分钟` : ""}`;
  return `${minutes}分钟`;
}

function buildBadge(text, cls) {
  const el = $("statusBadge");
  el.textContent = text;
  el.className = `badge ${cls ?? ""}`.trim();
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
  toastTimer = setTimeout(() => el.classList.add("hidden"), 2400);
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

async function startLoginFlow(message) {
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

    const onDone = () => {
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
        onDone();
      } catch (err) {
        $("loginError").textContent = String(err?.message || err);
      }
    };
  });
  return loginPromise;
}

async function requireLogin() {
  try {
    await API.get("/me");
    return;
  } catch (e) {
    if (e?.code !== "unauthorized") throw e;
  }
  await startLoginFlow();
}

function parseRepoKey() {
  const url = new URL(window.location.href);
  const raw = (url.searchParams.get("repo") || "").trim();
  if (!raw) return null;
  const parts = raw.split("/");
  if (parts.length !== 2 || !parts[0] || !parts[1]) return null;
  return raw;
}

async function loadSummary() {
  const [owner, repo] = repoKey.split("/");
  const data = await API.get(`/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`);
  const info = data.repo || {};
  const stats = info.stats || {};
  const update = info.update || {};

  const current = stats.current_tag || stats.latest_release_tag || "-";
  $("currentTag").textContent = current;
  $("nextRunAt").textContent = info.next_run_at ? isoToLocal(info.next_run_at) : "-";
  $("lastCheckAt").textContent = stats.last_check_finished_at ? isoToLocal(stats.last_check_finished_at) : "-";
  $("recommendedInterval").textContent = secondsToHuman(info.recommended_interval_seconds);

  $("checksTotal").textContent = String(stats.checks_total ?? 0);
  $("checksNetworkFailed").textContent = String(stats.checks_network_failed ?? 0);
  $("downloadsTotal").textContent = String(stats.download_assets_total ?? 0);
  $("cleanupTotal").textContent = String(stats.cleanup_tags_total ?? 0);

  const median = update.median_interval_seconds;
  const mean = update.mean_interval_seconds;
  const sample = update.sample_count ?? 0;
  $("updateHint").textContent = `更新频率统计：median=${secondsToHuman(median)}，mean=${secondsToHuman(mean)}（样本 ${sample}）。`;

  buildBadge(stats.last_check_ok ? "正常" : stats.last_check_ok === false ? "上次有错误" : "未知", stats.last_check_ok ? "ok" : "warn");
}

async function loadActivity() {
  const [owner, repo] = repoKey.split("/");
  const data = await API.get(`/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/activity?limit=200`);
  const items = data.items || [];
  const lines = items.map((x) => `${isoToLocal(x.time)} ${x.type || ""} ${x.tag ? `[${x.tag}] ` : ""}${x.message || ""}`.trim());
  $("activity").textContent = lines.join("\n") || "暂无活动。";
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

async function runRepoNow() {
  const btn = $("runRepoBtn");
  setButtonBusy(btn, true, "检查中…");
  try {
    const res = await withAuth(() => API.post("/run", { repo: repoKey }));
    if (res.error) toast(`触发失败：${res.error}`, "bad");
    else toast(res.queued ? "已加入队列。" : "任务已在运行/队列中。", "ok");
  } catch (e) {
    toast(String(e?.message || e), "bad");
  } finally {
    setButtonBusy(btn, false);
  }
}

async function main() {
  repoKey = parseRepoKey();
  if (!repoKey) {
    buildBadge("参数错误", "bad");
    $("activity").textContent = "缺少 repo 参数，例如：/repo.html?repo=owner/repo";
    $("runRepoBtn").disabled = true;
    return;
  }

  $("repoTitle").textContent = repoKey;
  $("repoSubtitle").textContent = "活动与统计";

  $("runRepoBtn").addEventListener("click", runRepoNow);
  $("copyActivityBtn").addEventListener("click", async () => {
    const ok = await copyText($("activity").textContent || "");
    toast(ok ? "已复制活动。" : "复制失败，请手动选择复制。", ok ? "ok" : "warn");
  });
  $("copySummaryBtn").addEventListener("click", async () => {
    const summary = [
      `仓库: ${repoKey}`,
      `当前版本: ${$("currentTag").textContent || "-"}`,
      `下次检查: ${$("nextRunAt").textContent || "-"}`,
      `上次检查: ${$("lastCheckAt").textContent || "-"}`,
      `推荐检查间隔: ${$("recommendedInterval").textContent || "-"}`,
      `检查次数: ${$("checksTotal").textContent || "0"}`,
      `网络失败次数: ${$("checksNetworkFailed").textContent || "0"}`,
      `下载次数(资产): ${$("downloadsTotal").textContent || "0"}`,
      `删除旧版本次数: ${$("cleanupTotal").textContent || "0"}`,
    ].join("\n");
    const ok = await copyText(summary);
    toast(ok ? "已复制摘要。" : "复制失败。", ok ? "ok" : "warn");
  });

  await requireLogin();
  await loadSummary();
  await loadActivity();

  setInterval(async () => {
    if (document.hidden) return;
    try {
      await withAuth(loadSummary);
    } catch {}
  }, 5000);
  setInterval(async () => {
    if (document.hidden) return;
    try {
      await withAuth(loadActivity);
    } catch {}
  }, 7000);
}

main().catch((e) => {
  buildBadge("初始化失败", "bad");
  $("activity").textContent = String(e?.stack || e);
});
