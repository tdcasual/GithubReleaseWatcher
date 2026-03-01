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
let releasesCount = null;
let recentDeletedTags = [];
let mustChangePassword = false;
let latestRepoStats = {};

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

function formatApiError(codeOrMessage) {
  const raw = String(codeOrMessage || "");
  if (raw === "rate_limited") return "登录过于频繁，请稍后再试。";
  if (raw === "password_change_required") return "请先在主页面设置中修改默认账号密码。";
  return raw || "未知错误";
}

function formatPercent(numerator, denominator) {
  const den = Number(denominator || 0);
  if (!Number.isFinite(den) || den <= 0) return "-";
  const num = Number(numerator || 0);
  if (!Number.isFinite(num) || num < 0) return "-";
  const pct = (num / den) * 100;
  return `${pct.toFixed(1)}% (${num}/${den})`;
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
  el.innerHTML = '安全限制：当前账号需先修改密码，POST/PUT 操作将被拒绝。<a href="/">前往主页设置</a>。';
  buildBadge("需先改密", "bad");
}

function updateReleaseStatsHint() {
  const el = $("releaseStatsHint");
  if (!el) return;
  const parts = [];
  if (typeof releasesCount === "number") parts.push(`已记录版本：${releasesCount}`);
  if (Array.isArray(recentDeletedTags) && recentDeletedTags.length) {
    parts.push(`最近删除：${recentDeletedTags.join(", ")}`);
  }
  el.textContent = parts.join(" · ");
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
          if (res.error === "rate_limited" || resp.status === 429) {
            $("loginError").textContent = "登录过于频繁，请稍后再试。";
          } else {
            $("loginError").textContent = "账号或密码错误。";
          }
          return;
        }
        mustChangePassword = !!res?.user?.must_change_password;
        renderSecurityBanner();
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
    const me = await API.get("/me");
    mustChangePassword = !!me?.user?.must_change_password;
    renderSecurityBanner();
    return;
  } catch (e) {
    if (e?.code !== "unauthorized") throw e;
  }
  await startLoginFlow();
  const me = await API.get("/me");
  mustChangePassword = !!me?.user?.must_change_password;
  renderSecurityBanner();
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
  latestRepoStats = stats;
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
  $("downloadedReleasesTotal").textContent = String(info.downloaded_releases_total ?? 0);
  $("downloadErrorsTotal").textContent = String(stats.download_errors_total ?? 0);
  $("uploadRetryTotal").textContent = String(stats.upload_retry_total ?? 0);
  $("uploadVerifyFailedTotal").textContent = String(stats.upload_verify_failed_total ?? 0);
  $("uploadQueueDepth").textContent = String(stats.upload_queue_depth ?? 0);
  const checksTotal = Number(stats.checks_total ?? 0);
  const checksOk = Number(stats.checks_ok ?? 0);
  $("checksSuccessRatio").textContent = formatPercent(checksOk, checksTotal);
  const downloadOk = Number(stats.download_assets_total ?? 0);
  const downloadErr = Number(stats.download_errors_total ?? 0);
  $("downloadSuccessRatio").textContent = formatPercent(downloadOk, downloadOk + downloadErr);

  const median = update.median_interval_seconds;
  const mean = update.mean_interval_seconds;
  const sample = update.sample_count ?? 0;
  $("updateHint").textContent = `更新频率统计：median=${secondsToHuman(median)}，mean=${secondsToHuman(mean)}（样本 ${sample}）。`;
  $("uploadHealthHint").textContent = `上传健康：重试 ${stats.upload_retry_total ?? 0}，校验失败 ${stats.upload_verify_failed_total ?? 0}，队列 ${stats.upload_queue_depth ?? 0}`;

  buildBadge(stats.last_check_ok ? "正常" : stats.last_check_ok === false ? "上次有错误" : "未知", stats.last_check_ok ? "ok" : "warn");
  if (mustChangePassword) renderSecurityBanner();

  const lastErr = String(stats.last_error || "").trim();
  if (lastErr) {
    const kind = String(stats.last_error_type || "").trim();
    $("errorHint").textContent = `最近错误${kind ? `（${kind}）` : ""}：${lastErr}`;
  } else {
    $("errorHint").textContent = "";
  }
}

async function loadActivity() {
  const [owner, repo] = repoKey.split("/");
  const data = await API.get(`/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/activity?limit=200`);
  const items = data.items || [];
  const lines = items.map((x) => `${isoToLocal(x.time)} ${x.type || ""} ${x.tag ? `[${x.tag}] ` : ""}${x.message || ""}`.trim());
  $("activity").textContent = lines.join("\n") || "暂无活动。";

  const deleted = [];
  for (const x of items.slice().reverse()) {
    if (x?.type !== "cleanup") continue;
    const tag = String(x?.tag || "").trim();
    if (!tag) continue;
    if (!deleted.includes(tag)) deleted.push(tag);
    if (deleted.length >= 8) break;
  }
  recentDeletedTags = deleted;
  updateReleaseStatsHint();
}

async function loadReleases() {
  const [owner, repo] = repoKey.split("/");
  const data = await API.get(`/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/releases?limit=200`);
  const items = Array.isArray(data.items) ? data.items : [];
  releasesCount = items.length;
  updateReleaseStatsHint();

  const lines = items.map((x) => {
    const tag = String(x?.tag || "-");
    const assetsCount = Number(x?.downloaded_assets_count ?? (Array.isArray(x?.downloaded_assets) ? x.downloaded_assets.length : 0));
    const published = x?.published_at ? isoToLocal(x.published_at) : x?.created_at ? isoToLocal(x.created_at) : "-";
    const processed = x?.processed_at ? isoToLocal(x.processed_at) : "-";
    return `${tag} · 资产:${Number.isFinite(assetsCount) ? assetsCount : 0} · 发布:${published} · 处理:${processed}`;
  });
  $("releases").textContent = lines.join("\n") || "暂无版本记录。";
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

function initSectionToggles() {
  const isMobile = window.matchMedia("(max-width: 640px)").matches;
  for (const btn of document.querySelectorAll(".section-toggle")) {
    const targetId = btn.getAttribute("data-target");
    if (!targetId) continue;
    const body = document.getElementById(targetId);
    if (!body) continue;
    btn.setAttribute("aria-controls", targetId);
    if (isMobile && (targetId === "releasesBody" || targetId === "activityBody")) {
      body.classList.add("hidden");
      btn.textContent = "展开";
      btn.setAttribute("aria-expanded", "false");
    } else {
      body.classList.remove("hidden");
      btn.textContent = "折叠";
      btn.setAttribute("aria-expanded", "true");
    }
    btn.addEventListener("click", () => {
      const collapsed = body.classList.toggle("hidden");
      btn.textContent = collapsed ? "展开" : "折叠";
      btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
    });
  }
}

function setupMobileSectionNav() {
  const nav = document.querySelector(".mobile-nav");
  if (!nav) return;
  const links = Array.from(nav.querySelectorAll('.mobile-nav-item[href^="#"]'));
  if (!links.length) return;

  const items = links
    .map((link) => {
      const raw = String(link.getAttribute("href") || "");
      const id = raw.startsWith("#") ? raw.slice(1) : "";
      const section = id ? document.getElementById(id) : null;
      return section ? { id, section, link } : null;
    })
    .filter(Boolean);
  if (!items.length) return;
  items.sort((a, b) => a.section.offsetTop - b.section.offsetTop);

  const topOffset = () => {
    const topbar = document.querySelector(".topbar");
    return Math.ceil((topbar?.getBoundingClientRect().height || 0) + 16);
  };

  const setActive = (id) => {
    for (const item of items) {
      const active = item.id === id;
      item.link.classList.toggle("active", active);
      if (active) item.link.setAttribute("aria-current", "page");
      else item.link.removeAttribute("aria-current");
    }
  };

  const scrollToSection = (id) => {
    const target = document.getElementById(id);
    if (!target) return;
    const targetY = window.scrollY + target.getBoundingClientRect().top - topOffset();
    window.scrollTo({ top: Math.max(0, targetY), behavior: "smooth" });
    if (history.replaceState) history.replaceState(null, "", `#${id}`);
  };

  for (const item of items) {
    item.link.addEventListener("click", (e) => {
      e.preventDefault();
      setActive(item.id);
      scrollToSection(item.id);
    });
  }

  let ticking = false;
  const updateByScroll = () => {
    ticking = false;
    const probeY = topOffset() + 24;
    let current = items[0];
    for (const item of items) {
      if (item.section.getBoundingClientRect().top <= probeY) current = item;
      else break;
    }
    setActive(current.id);
  };
  const requestUpdate = () => {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(updateByScroll);
  };

  window.addEventListener("scroll", requestUpdate, { passive: true });
  window.addEventListener("resize", requestUpdate);
  window.addEventListener("hashchange", () => {
    const id = (location.hash || "").replace(/^#/, "");
    if (!id) return;
    const item = items.find((x) => x.id === id);
    if (item) setActive(item.id);
  });

  const currentHashId = (location.hash || "").replace(/^#/, "");
  if (currentHashId) {
    const current = items.find((x) => x.id === currentHashId);
    if (current) setActive(current.id);
    else requestUpdate();
  } else {
    requestUpdate();
  }
}

async function runRepoNow() {
  const hint = $("runFeedbackHint");
  if (hint) {
    hint.className = "hint";
    hint.textContent = "";
  }
  if (mustChangePassword) {
    renderSecurityBanner();
    if (hint) {
      hint.className = "hint danger";
      hint.textContent = "当前账号需先修改密码，已阻止触发。";
    }
    toast("当前账号需先修改密码，请先返回主页设置。", "warn");
    return;
  }
  const btn = $("runRepoBtn");
  setButtonBusy(btn, true, "检查中…");
  try {
    const res = await withAuth(() => API.post("/run", { repo: repoKey }));
    if (res.error) {
      if (hint) {
        hint.className = "hint danger";
        hint.textContent = `触发失败：${formatApiError(res.error)}`;
      }
      toast(`触发失败：${formatApiError(res.error)}`, "bad");
    } else {
      if (hint) {
        hint.className = "hint";
        hint.textContent = res.queued
          ? `已加入队列：${new Date().toLocaleTimeString()}`
          : `任务已在运行/队列中：${new Date().toLocaleTimeString()}`;
      }
      toast(res.queued ? "已加入队列。" : "任务已在运行/队列中。", "ok");
    }
  } catch (e) {
    if (hint) {
      hint.className = "hint danger";
      hint.textContent = `触发失败：${formatApiError(e?.message || e)}`;
    }
    toast(formatApiError(e?.message || e), "bad");
  } finally {
    setButtonBusy(btn, false);
  }
}

function buildDiagnosticBundle() {
  const stats = latestRepoStats || {};
  const activityLines = String($("activity").textContent || "")
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean)
    .slice(0, 30);
  const releasesLines = String($("releases").textContent || "")
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean)
    .slice(0, 20);
  return [
    `仓库: ${repoKey}`,
    `生成时间: ${new Date().toLocaleString()}`,
    `状态徽章: ${$("statusBadge").textContent || "-"}`,
    `当前版本: ${$("currentTag").textContent || "-"}`,
    `下次检查: ${$("nextRunAt").textContent || "-"}`,
    `上次检查: ${$("lastCheckAt").textContent || "-"}`,
    `推荐检查间隔: ${$("recommendedInterval").textContent || "-"}`,
    `检查成功率: ${$("checksSuccessRatio").textContent || "-"}`,
    `下载成功率: ${$("downloadSuccessRatio").textContent || "-"}`,
    `最近错误: ${$("errorHint").textContent || "无"}`,
    `上传健康: ${$("uploadHealthHint").textContent || "-"}`,
    `统计快照: checks_total=${stats.checks_total ?? 0}, checks_ok=${stats.checks_ok ?? 0}, checks_network_failed=${
      stats.checks_network_failed ?? 0
    }, download_assets_total=${stats.download_assets_total ?? 0}, download_errors_total=${stats.download_errors_total ?? 0}, upload_retry_total=${
      stats.upload_retry_total ?? 0
    }, upload_verify_failed_total=${stats.upload_verify_failed_total ?? 0}, upload_queue_depth=${stats.upload_queue_depth ?? 0}`,
    "",
    "[最近版本 20 条]",
    ...(releasesLines.length ? releasesLines : ["(无)"]),
    "",
    "[最近活动 30 条]",
    ...(activityLines.length ? activityLines : ["(无)"]),
  ].join("\n");
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
  renderSecurityBanner();

  $("runRepoBtn").addEventListener("click", runRepoNow);
  initSectionToggles();
  setupMobileSectionNav();
  $("copyActivityBtn").addEventListener("click", async () => {
    const ok = await copyText($("activity").textContent || "");
    toast(ok ? "已复制活动。" : "复制失败，请手动选择复制。", ok ? "ok" : "warn");
  });
  $("copyReleasesBtn").addEventListener("click", async () => {
    const ok = await copyText($("releases").textContent || "");
    toast(ok ? "已复制版本列表。" : "复制失败，请手动选择复制。", ok ? "ok" : "warn");
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
      `已保存版本数: ${$("downloadedReleasesTotal").textContent || "0"}`,
      `下载失败次数: ${$("downloadErrorsTotal").textContent || "0"}`,
      `上传重试次数: ${$("uploadRetryTotal").textContent || "0"}`,
      `上传校验失败: ${$("uploadVerifyFailedTotal").textContent || "0"}`,
      `上传队列深度: ${$("uploadQueueDepth").textContent || "0"}`,
    ].join("\n");
    const ok = await copyText(summary);
    toast(ok ? "已复制摘要。" : "复制失败。", ok ? "ok" : "warn");
  });
  $("copyDiagBtn").addEventListener("click", async () => {
    const payload = buildDiagnosticBundle();
    const ok = await copyText(payload);
    toast(ok ? "已复制诊断包。" : "复制失败。", ok ? "ok" : "warn");
  });

  await requireLogin();
  await loadSummary();
  await loadReleases();
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
      await withAuth(loadReleases);
    } catch {}
  }, 15000);
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
