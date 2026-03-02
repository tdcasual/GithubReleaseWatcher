(function attachLogsView(global) {
  const isoToLocal = global.GRWFormatters?.isoToLocal;
  if (!isoToLocal) {
    throw new Error("GRWFormatters.isoToLocal is required for logs view");
  }

  function classifyLogTone(item) {
    const level = String(item?.level || "")
      .trim()
      .toUpperCase();
    const type = String(item?.type || "")
      .trim()
      .toLowerCase();
    const message = String(item?.message || "")
      .trim();
    if (level === "ERROR" || /失败|错误|exception|traceback|denied/i.test(message)) return "bad";
    if (level === "WARNING" || level === "WARN" || /重试|retry|rate limit|429|timeout|超时/i.test(message)) return "warn";
    if (type === "cleanup") return "warn";
    return "info";
  }

  function formatLogTimeCompact(iso) {
    if (!iso) return "-";
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
    } catch {
      return isoToLocal(iso);
    }
  }

  function toLogTypeLabel(type) {
    const key = String(type || "")
      .trim()
      .toLowerCase();
    const map = {
      download: "下载",
      download_error: "下载",
      download_failed: "下载",
      cleanup: "清理",
      cleanup_error: "清理",
      check: "检查",
      check_error: "检查",
      network_error: "网络",
      run: "执行",
      scheduler: "调度",
      startup: "启动",
      reload: "重载",
    };
    return map[key] || (key ? key : "操作");
  }

  function normalizeRepoLabel(repo) {
    const text = String(repo || "").trim();
    if (!text) return "全局";
    return text.length > 36 ? `${text.slice(0, 33)}...` : text;
  }

  function extractErrorKeyword(message) {
    const text = String(message || "")
      .trim()
      .toLowerCase();
    if (!text) return "";
    if (/429|rate limit|限流/.test(text)) return "限流";
    if (/timeout|timed out|超时/.test(text)) return "超时";
    if (/403|forbidden/.test(text)) return "403";
    if (/404|not found/.test(text)) return "404";
    if (/network|连接|dns|socket/.test(text)) return "网络";
    return "";
  }

  function summarizeLog(item, tone) {
    const repo = normalizeRepoLabel(item?.repo);
    const action = toLogTypeLabel(item?.type);
    if (tone === "bad") {
      const keyword = extractErrorKeyword(item?.message);
      return keyword ? `${repo} ${action}失败（${keyword}）` : `${repo} ${action}失败`;
    }
    if (tone === "warn") return `${repo} ${action}完成（需关注）`;
    return `${repo} ${action}完成`;
  }

  function formatLogPathTail(pathValue) {
    const raw = String(pathValue || "").trim();
    if (!raw) return "-";
    const parts = raw.split(/[\\/]/).filter(Boolean);
    if (parts.length <= 2) return raw;
    return `.../${parts.slice(-2).join("/")}`;
  }

  function summarizeLogDetailMessage(message) {
    const raw = String(message || "").trim();
    if (!raw) return "-";
    const singleLine = raw.replace(/\s+/g, " ").trim();
    if (!singleLine) return "-";
    const sentenceMatch = singleLine.match(/^(.{1,64}?[。！？.!?])(\s|$)/);
    if (sentenceMatch && sentenceMatch[1]) return sentenceMatch[1].trim();
    if (singleLine.length <= 54) return singleLine;
    return `${singleLine.slice(0, 54)}...`;
  }

  function shouldAutoExpandAdvancedDetails(item, rawMessage) {
    const level = String(item?.level || "")
      .trim()
      .toUpperCase();
    const type = String(item?.type || "")
      .trim()
      .toLowerCase();
    const text = String(rawMessage || "")
      .trim()
      .toLowerCase();
    if (level === "CRITICAL" || level === "FATAL") return true;
    if (!text) return false;

    // Severe diagnostics or auth/storage integrity failures should surface immediately.
    if (/traceback|stack trace|panic|fatal|uncaught|segmentation|exception/.test(text)) return true;
    if (/denied|forbidden|unauthorized|401|403|权限|认证|凭证|token|password|登录/.test(text)) return true;
    if (/checksum|hash mismatch|verify failed|corrupt|损坏|完整性|磁盘已满|no space|quota|只读/.test(text)) return true;
    if (/(upload|webdav|sync)/.test(type) && /failed|失败|error|错误/.test(text)) return true;
    return false;
  }

  function appendLogDetailLine(container, label, value) {
    const row = document.createElement("div");
    row.className = "log-detail-row";

    const key = document.createElement("span");
    key.className = "log-detail-key";
    key.textContent = `${label}:`;
    row.appendChild(key);

    const text = String(value || "-").trim() || "-";
    const val = document.createElement("span");
    val.className = "log-detail-value";
    val.textContent = text;
    val.title = text;
    row.appendChild(val);

    container.appendChild(row);
    return row;
  }

  function normalizeLogGroupToken(value) {
    return String(value || "")
      .trim()
      .toLowerCase();
  }

  function buildDisplayLogGroupKey(item, tone, summary) {
    return [
      normalizeLogGroupToken(tone),
      normalizeLogGroupToken(item?.type),
      normalizeLogGroupToken(item?.repo),
      normalizeLogGroupToken(summary),
    ].join("|");
  }

  function buildDisplayLogGroups(items) {
    const groups = [];
    for (const item of items) {
      const tone = classifyLogTone(item);
      const summary = summarizeLog(item, tone);
      const key = buildDisplayLogGroupKey(item, tone, summary);
      const last = groups[groups.length - 1];
      if (last && last.key === key) {
        last.count += 1;
        last.items.push(item);
        continue;
      }
      groups.push({
        key,
        tone,
        summary,
        count: 1,
        items: [item],
        latest: item,
      });
    }
    return groups;
  }

  function formatLogCopyLine(item) {
    const time = isoToLocal(item?.time);
    const level = String(item?.level || "")
      .trim()
      .toUpperCase();
    const type = String(item?.type || "").trim();
    const repo = String(item?.repo || "").trim();
    const tag = String(item?.tag || "").trim();
    const message = String(item?.message || "").trim();
    const parts = [time];
    if (level) parts.push(`[${level}]`);
    if (type) parts.push(type);
    if (repo) parts.push(repo);
    if (tag) parts.push(`[${tag}]`);
    if (message) parts.push(message);
    return parts.join(" ").trim();
  }

  function renderStructuredLogs(logsEl, items) {
    const nextText = items.map((x) => formatLogCopyLine(x)).join("\n") || "暂无活动。";
    const prevText = logsEl.dataset.rawText || logsEl.textContent || "";
    if (prevText === nextText) return;

    const prevScrollTop = logsEl.scrollTop;
    const nearBottom = logsEl.scrollHeight - logsEl.clientHeight - logsEl.scrollTop <= 24;
    logsEl.dataset.rawText = nextText;
    logsEl.textContent = "";

    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "log-empty";
      empty.textContent = "暂无活动。";
      logsEl.appendChild(empty);
    } else {
      const groups = buildDisplayLogGroups(items.slice().reverse());
      const frag = document.createDocumentFragment();
      for (const group of groups) {
        const item = group.latest;
        const row = document.createElement("article");
        const tone = group.tone;
        row.className = "log-entry";
        row.dataset.level = tone;
        const hasDetails = tone === "bad";

        const meta = document.createElement("div");
        meta.className = "log-meta";

        const time = document.createElement("span");
        time.className = "log-time";
        const fullTime = isoToLocal(item?.time);
        time.textContent = formatLogTimeCompact(item?.time);
        time.title = fullTime;
        meta.appendChild(time);

        const toneBadge = document.createElement("span");
        toneBadge.className = "log-chip level";
        toneBadge.textContent = tone === "bad" ? "错误" : tone === "warn" ? "提醒" : "正常";
        meta.appendChild(toneBadge);

        const typeBadge = document.createElement("span");
        typeBadge.className = "log-chip";
        typeBadge.textContent = toLogTypeLabel(item?.type);
        meta.appendChild(typeBadge);

        if (group.count > 1) {
          const countBadge = document.createElement("span");
          countBadge.className = "log-count-badge";
          countBadge.textContent = `x${group.count}`;
          countBadge.title = `重复 ${group.count} 次`;
          meta.appendChild(countBadge);
        }

        const summary = document.createElement("div");
        summary.className = "log-summary";
        summary.textContent = group.summary;

        row.appendChild(meta);
        row.appendChild(summary);

        if (hasDetails) {
          row.classList.add("has-details");
          row.tabIndex = 0;
          row.setAttribute("role", "button");
          row.setAttribute("aria-expanded", "false");
          row.title = "点击展开错误详情";

          const expandHint = document.createElement("span");
          expandHint.className = "log-expand-hint";
          expandHint.textContent = "详情";
          meta.appendChild(expandHint);

          const details = document.createElement("div");
          details.className = "log-details";
          const earliest = group.items[group.items.length - 1];
          const earliestTime = isoToLocal(earliest?.time);
          const rawType = String(item?.type || "-").trim() || "-";
          const typeLabel = toLogTypeLabel(rawType);
          const typeText = typeLabel && typeLabel !== rawType ? `${typeLabel} (${rawType})` : typeLabel || rawType;
          const rawPath = String(item?.path || "").trim();
          const pathTail = formatLogPathTail(rawPath);

          appendLogDetailLine(details, "时间", fullTime);
          appendLogDetailLine(details, "重复", `${group.count} 次`);
          appendLogDetailLine(details, "首次", earliestTime);
          appendLogDetailLine(details, "仓库", String(item?.repo || "-").trim() || "-");
          appendLogDetailLine(details, "类型", typeText);
          appendLogDetailLine(details, "标签", String(item?.tag || "-").trim() || "-");
          appendLogDetailLine(details, "路径", pathTail);

          const rawMessage = String(item?.message || "").trim();
          const messageSummary = summarizeLogDetailMessage(rawMessage);
          appendLogDetailLine(details, "详情", messageSummary);
          const hasFullPath = rawPath && rawPath !== "-" && rawPath !== pathTail;
          const hasFullMessage = rawMessage && rawMessage !== "-" && rawMessage !== messageSummary;
          if (hasFullPath || hasFullMessage) {
            const autoExpandAdvanced = shouldAutoExpandAdvancedDetails(item, rawMessage);
            const detailToggle = document.createElement("button");
            detailToggle.type = "button";
            detailToggle.className = "log-detail-advanced-toggle";
            detailToggle.textContent = autoExpandAdvanced ? "收起细节" : "技术细节";
            detailToggle.setAttribute("aria-expanded", autoExpandAdvanced ? "true" : "false");
            if (autoExpandAdvanced) detailToggle.classList.add("is-critical");

            const detailPanel = document.createElement("div");
            detailPanel.className = "log-detail-advanced";
            detailPanel.hidden = !autoExpandAdvanced;

            if (hasFullPath) {
              const pathRow = document.createElement("div");
              pathRow.className = "log-detail-advanced-row";

              const pathKey = document.createElement("span");
              pathKey.className = "log-detail-advanced-key";
              pathKey.textContent = "全路径:";
              pathRow.appendChild(pathKey);

              const pathVal = document.createElement("span");
              pathVal.className = "log-detail-advanced-value";
              pathVal.textContent = rawPath;
              pathVal.title = rawPath;
              pathRow.appendChild(pathVal);

              detailPanel.appendChild(pathRow);
            }

            if (hasFullMessage) {
              const msgRow = document.createElement("div");
              msgRow.className = "log-detail-advanced-row";

              const msgKey = document.createElement("span");
              msgKey.className = "log-detail-advanced-key";
              msgKey.textContent = "完整详情:";
              msgRow.appendChild(msgKey);

              const msgVal = document.createElement("span");
              msgVal.className = "log-detail-advanced-value log-detail-advanced-message";
              msgVal.textContent = rawMessage;
              msgVal.title = rawMessage;
              msgRow.appendChild(msgVal);

              detailPanel.appendChild(msgRow);
            }

            const toggleAdvancedDetails = (e) => {
              e.preventDefault();
              e.stopPropagation();
              const expanded = detailToggle.getAttribute("aria-expanded") === "true";
              const next = !expanded;
              detailToggle.setAttribute("aria-expanded", next ? "true" : "false");
              detailToggle.textContent = next ? "收起细节" : "技术细节";
              detailPanel.hidden = !next;
            };

            detailToggle.addEventListener("click", toggleAdvancedDetails);
            detailToggle.addEventListener("keydown", (e) => {
              if (e.key === "Enter" || e.key === " ") e.stopPropagation();
            });

            details.appendChild(detailToggle);
            details.appendChild(detailPanel);
          }
          details.hidden = true;
          row.appendChild(details);

          const toggleExpanded = () => {
            const expanded = row.classList.toggle("expanded");
            row.setAttribute("aria-expanded", expanded ? "true" : "false");
            details.hidden = !expanded;
            expandHint.textContent = expanded ? "收起" : "详情";
          };
          row.addEventListener("click", toggleExpanded);
          row.addEventListener("keydown", (e) => {
            if (e.key !== "Enter" && e.key !== " ") return;
            e.preventDefault();
            toggleExpanded();
          });
        }

        frag.appendChild(row);
      }
      logsEl.appendChild(frag);
    }

    if (nearBottom) {
      logsEl.scrollTop = logsEl.scrollHeight;
    } else {
      const maxTop = Math.max(0, logsEl.scrollHeight - logsEl.clientHeight);
      logsEl.scrollTop = Math.min(prevScrollTop, maxTop);
    }
  }

  global.GRWLogsView = { renderStructuredLogs };
})(window);
