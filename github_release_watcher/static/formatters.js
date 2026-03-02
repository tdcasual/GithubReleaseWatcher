(function attachFormatters(global) {
  function formatError(e) {
    if (!e) return "未知错误";
    if (e?.code === "unauthorized") return "未登录或登录已过期。";
    if (e?.code === "password_change_required") return "首次登录后请先在设置中修改账号密码。";
    if (e?.code === "rate_limited") return "登录尝试过于频繁，请稍后再试。";
    return String(e?.message || e);
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

  function formatSignedDelta(value) {
    const n = Number(value) || 0;
    if (n > 0) return `+${n}`;
    return String(n);
  }

  function formatRunScope(last) {
    if (!last || typeof last !== "object") return "-";
    const source = String(last?.source || "").trim().toLowerCase();
    const sourceLabel = source === "scheduler" ? "调度" : source === "api" || source === "manual" ? "手动" : "未知";
    const repos = Array.isArray(last?.repos)
      ? last.repos
          .map((x) => String(x || "").trim())
          .filter((x) => !!x)
      : [];
    const repo = String(last?.repo || "").trim();
    if (repos.length) {
      const brief = repos.slice(0, 3).join("、");
      const more = repos.length > 3 ? ` 等 ${repos.length} 个仓库` : "";
      return `批量：${brief}${more} · 来源：${sourceLabel}`;
    }
    if (repo) return `单仓库：${repo} · 来源：${sourceLabel}`;
    if (source === "scheduler") return "调度执行：单仓库轮询";
    return `全量：全部启用仓库 · 来源：${sourceLabel}`;
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  global.GRWFormatters = {
    escapeHtml,
    formatError,
    formatRunScope,
    formatSignedDelta,
    isoToLocal,
  };
})(window);
