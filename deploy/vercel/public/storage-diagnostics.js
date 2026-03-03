(function attachStorageDiagnostics(global) {
  function createStorageDiagnosticsController(deps) {
    const getEl = deps.getEl;
    const getStorageMode = deps.getStorageMode;
    const withAuth = deps.withAuth;
    const apiGet = deps.apiGet;
    const formatError = deps.formatError;
    const secondsToElapsedText = deps.secondsToElapsedText;
    const formatSignedDelta = deps.formatSignedDelta;
    const escapeHtml = deps.escapeHtml;
    const revealHintIfNeeded = deps.revealHintIfNeeded;
    const renderRepos = deps.renderRepos;
    const updateBatchControlsUI = deps.updateBatchControlsUI;

    const getLastStorageHealthTotals = deps.getLastStorageHealthTotals;
    const setLastStorageHealthTotals = deps.setLastStorageHealthTotals;
    const getLastStorageHealthAt = deps.getLastStorageHealthAt;
    const setLastStorageHealthAt = deps.setLastStorageHealthAt;
    const setHasSyncCacheSnapshot = deps.setHasSyncCacheSnapshot;
    const setLastSyncCacheAnomalyRepoKeys = deps.setLastSyncCacheAnomalyRepoKeys;

    const formatStorageHealthTopRepos = (repos, limit = 3) => {
      const list = Array.isArray(repos) ? repos : [];
      return list
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
    };

    const formatSyncCacheTopRepos = (items, limit = 3) => {
      const list = Array.isArray(items) ? items : [];
      return list
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
    };

    const refreshStorageDiagnostics = async () => {
      const capsEl = getEl("webdavCapabilitiesHint");
      const healthEl = getEl("storageHealthHint");
      if (!capsEl || !healthEl) return;

      const mode = String(getStorageMode() || "local");
      if (mode !== "webdav") {
        setLastStorageHealthTotals(null);
        setLastStorageHealthAt(0);
        setHasSyncCacheSnapshot(false);
        setLastSyncCacheAnomalyRepoKeys(new Set());
        const stateSelect = getEl("repoStateFilterSelect");
        if (stateSelect?.value === "cache_anomaly") {
          stateSelect.value = "all";
          renderRepos();
        } else {
          updateBatchControlsUI();
        }
        capsEl.className = "hint";
        capsEl.textContent = "当前为本地存储模式。";
        revealHintIfNeeded(capsEl);
        healthEl.className = "hint";
        healthEl.textContent = "";
        return;
      }

      try {
        const caps = await withAuth(() => apiGet("/storage/capabilities"));
        if (caps.error || caps.ok === false) {
          capsEl.className = "hint danger";
          capsEl.textContent = `能力探测失败：${caps.error || "未知错误"}`;
          revealHintIfNeeded(capsEl);
        } else {
          const enabled = Object.entries(caps.capabilities || {})
            .filter(([, v]) => !!v)
            .map(([k]) => k.toUpperCase());
          capsEl.className = "hint";
          capsEl.textContent = `WebDAV 能力：${enabled.length ? enabled.join(", ") : "未探测到"}`;
          revealHintIfNeeded(capsEl);
        }
      } catch (e) {
        capsEl.className = "hint danger";
        capsEl.textContent = `能力探测失败：${formatError(e)}`;
        revealHintIfNeeded(capsEl);
      }

      try {
        const health = await withAuth(() => apiGet("/storage/health"));
        const totals = health.totals || {};
        const current = {
          retry: Number(totals.upload_retry_total || 0),
          verify_failed: Number(totals.upload_verify_failed_total || 0),
          queue: Number(totals.upload_queue_depth || 0),
        };
        let trendText = "趋势：首次采样。";
        const now = Date.now();
        const lastTotals = getLastStorageHealthTotals();
        const lastAt = getLastStorageHealthAt();
        if (lastTotals && lastAt > 0) {
          const elapsed = secondsToElapsedText((now - lastAt) / 1000);
          trendText = `趋势（较 ${elapsed} 前）：重试 ${formatSignedDelta(
            current.retry - (lastTotals.retry || 0)
          )}，校验失败 ${formatSignedDelta(
            current.verify_failed - (lastTotals.verify_failed || 0)
          )}，队列 ${formatSignedDelta(current.queue - (lastTotals.queue || 0))}`;
        }
        setLastStorageHealthTotals(current);
        setLastStorageHealthAt(now);

        const topRepos = formatStorageHealthTopRepos(health.repos || [], 3);
        healthEl.className = "hint";
        const mainText = `上传健康：重试 ${current.retry} 次，校验失败 ${current.verify_failed} 次，队列深度 ${current.queue}。${trendText}`;
        if (!topRepos.length) {
          healthEl.textContent = `${mainText} 重点仓库：暂无异常。`;
          revealHintIfNeeded(healthEl);
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
        revealHintIfNeeded(healthEl);
      } catch (e) {
        healthEl.className = "hint danger";
        healthEl.textContent = `上传健康读取失败：${formatError(e)}`;
        revealHintIfNeeded(healthEl);
      }
    };

    return {
      formatStorageHealthTopRepos,
      formatSyncCacheTopRepos,
      refreshStorageDiagnostics,
    };
  }

  global.GRWStorageDiagnostics = { createStorageDiagnosticsController };
})(window);
