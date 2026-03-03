(() => {
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

  function createAppEventsController(options = {}) {
    const getEl = typeof options.getEl === "function" ? options.getEl : (id) => document.getElementById(id);
    const $ = (id) => getEl(id);

    const api = options.api;
    const runNow = options.runNow;
    const openSettingsDialog = options.openSettingsDialog;
    const setButtonBusy = options.setButtonBusy;
    const setUser = options.setUser;
    const requireLogin = options.requireLogin;
    const withAuth = options.withAuth;
    const loadAll = options.loadAll;
    const toast = options.toast;
    const getCurrentUser = options.getCurrentUser;
    const formatError = options.formatError;
    const saveSettings = options.saveSettings;
    const setScheduler = options.setScheduler;
    const setDirty = options.setDirty;
    const renderRepos = options.renderRepos;
    const openRepoDialog = options.openRepoDialog;
    const batchSelectVisible = options.batchSelectVisible;
    const batchInvertVisible = options.batchInvertVisible;
    const batchSelectEnabledVisible = options.batchSelectEnabledVisible;
    const batchSelectErrorVisible = options.batchSelectErrorVisible;
    const batchSelectCacheAnomalyVisible = options.batchSelectCacheAnomalyVisible;
    const batchRunSelected = options.batchRunSelected;
    const batchSetEnabled = options.batchSetEnabled;
    const isCompactMobileViewport = options.isCompactMobileViewport;
    const getBatchToolsExpanded = options.getBatchToolsExpanded;
    const setBatchToolsExpanded = options.setBatchToolsExpanded;
    const syncBatchToolsPresentation = options.syncBatchToolsPresentation;
    const getSelectedRepoKeys = options.getSelectedRepoKeys;
    const clearSelectedRepoKeys = options.clearSelectedRepoKeys;
    const setBatchActionHint = options.setBatchActionHint;
    const hasSettingsDialogUnsavedChanges = options.hasSettingsDialogUnsavedChanges;
    const getSettingsDialogReturnFocusEl = options.getSettingsDialogReturnFocusEl;
    const setSettingsDialogReturnFocusEl = options.setSettingsDialogReturnFocusEl;
    const getSettingsDialogSaved = options.getSettingsDialogSaved;
    const setSettingsDialogSaved = options.setSettingsDialogSaved;
    const getSettingsDialogDraftSnapshot = options.getSettingsDialogDraftSnapshot;
    const setSettingsDialogDraftSnapshot = options.setSettingsDialogDraftSnapshot;
    const getSettingsDialogDirtyBefore = options.getSettingsDialogDirtyBefore;
    const getSettingsDialogAuthUsernameBefore = options.getSettingsDialogAuthUsernameBefore;
    const setSettingsDialogAuthUsernameBefore = options.setSettingsDialogAuthUsernameBefore;
    const getDraft = options.getDraft;
    const setDraft = options.setDraft;
    const getDirty = options.getDirty;
    const syncSettingsFormFromDraft = options.syncSettingsFormFromDraft;
    const focusIfPossible = options.focusIfPossible;
    const syncDialogOpenState = options.syncDialogOpenState;
    const getRepoDialogReturnFocusEl = options.getRepoDialogReturnFocusEl;
    const setRepoDialogReturnFocusEl = options.setRepoDialogReturnFocusEl;
    const invalidateWebdavTest = options.invalidateWebdavTest;
    const syncDraftFromSettingsForm = options.syncDraftFromSettingsForm;
    const recordWebdavTestResult = options.recordWebdavTestResult;
    const renderWebdavTestHint = options.renderWebdavTestHint;
    const refreshStorageDiagnostics = options.refreshStorageDiagnostics;
    const revealHintIfNeeded = options.revealHintIfNeeded;
    const formatSyncCacheTopRepos = options.formatSyncCacheTopRepos;
    const setLastSyncCacheAnomalyRepoKeys = options.setLastSyncCacheAnomalyRepoKeys;
    const setHasSyncCacheSnapshot = options.setHasSyncCacheSnapshot;
    const updateBatchControlsUI = options.updateBatchControlsUI;
    const escapeHtml = options.escapeHtml;

    async function copyLogs() {
      const logsEl = $("logs");
      const text = logsEl?.dataset?.rawText || logsEl?.textContent || "";
      const ok = await copyText(text);
      toast(ok ? "已复制活动。" : "复制失败，请手动选择复制。", ok ? "ok" : "warn");
    }

    function wireEvents() {
      $("runNowBtn").addEventListener("click", runNow);
      $("settingsBtn").addEventListener("click", () => openSettingsDialog({ focusAuthPassword: false }));
      $("logoutBtn").addEventListener("click", async () => {
        const btn = $("logoutBtn");
        setButtonBusy(btn, true, "退出中…");
        try {
          await api.post("/logout", {});
        } catch {}
        setUser(null);
        try {
          await requireLogin();
          await withAuth(() => loadAll());
          toast("已重新登录。", "ok");
        } finally {
          setButtonBusy(btn, false);
          setUser(getCurrentUser());
        }
      });
      $("reloadBtn").addEventListener("click", async () => {
        const btn = $("reloadBtn");
        setButtonBusy(btn, true, "加载中…");
        try {
          await withAuth(() => api.post("/reload", {}));
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
      $("batchToolsToggleBtn").addEventListener("click", () => {
        if (!isCompactMobileViewport()) return;
        setBatchToolsExpanded(!getBatchToolsExpanded());
        syncBatchToolsPresentation(getSelectedRepoKeys().length);
      });
      $("batchClearBtn").addEventListener("click", () => {
        clearSelectedRepoKeys();
        setBatchActionHint("已清空选择。", "");
        renderRepos();
      });
      window.addEventListener("resize", () => {
        syncBatchToolsPresentation(getSelectedRepoKeys().length);
      });

      const settingsForm = $("settingsDialog").querySelector("form");
      settingsForm?.addEventListener("submit", (e) => e.preventDefault());
      const repoForm = $("repoDialog").querySelector("form");
      repoForm?.addEventListener("submit", (e) => e.preventDefault());

      const settingsDialog = $("settingsDialog");
      for (const btn of settingsDialog.querySelectorAll('button[value="cancel"]')) {
        btn.addEventListener("click", (e) => {
          e.preventDefault();
          setSettingsDialogSaved(false);
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
        setSettingsDialogSaved(false);
        if (!hasSettingsDialogUnsavedChanges()) return;
        const ok = window.confirm("设置未保存，确定取消并丢弃本次修改吗？");
        if (!ok) e.preventDefault();
      });
      settingsDialog.addEventListener("close", () => {
        const returnFocusEl = getSettingsDialogReturnFocusEl();
        setSettingsDialogReturnFocusEl(null);
        const saved = getSettingsDialogSaved();
        setSettingsDialogSaved(false);

        if ($("webdavPassword")) $("webdavPassword").value = "";
        if ($("authPassword")) $("authPassword").value = "";
        $("settingsHint").textContent = "";

        const settingsDialogDraftSnapshot = getSettingsDialogDraftSnapshot();
        if (!saved && settingsDialogDraftSnapshot) {
          setDraft(settingsDialogDraftSnapshot);
          setDirty(getSettingsDialogDirtyBefore());
          if ($("authUsername")) $("authUsername").value = getSettingsDialogAuthUsernameBefore() || $("authUsername").value;
          syncSettingsFormFromDraft();
          renderRepos();
        }

        setSettingsDialogDraftSnapshot(null);
        setSettingsDialogAuthUsernameBefore("");
        syncDialogOpenState();
        if (!focusIfPossible(returnFocusEl)) focusIfPossible($("settingsBtn"));
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
      repoDialog.addEventListener("close", () => {
        const returnFocusEl = getRepoDialogReturnFocusEl();
        setRepoDialogReturnFocusEl(null);
        syncDialogOpenState();
        if (!focusIfPossible(returnFocusEl)) focusIfPossible($("addRepoBtn"));
      });
      const loginDialog = $("loginDialog");
      loginDialog?.addEventListener("close", () => {
        syncDialogOpenState();
      });
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
          const res = await withAuth(() => api.post("/storage/test", { webdav: patch }));
          recordWebdavTestResult({
            time: new Date().toLocaleString(),
            ok: !!res.ok,
            message: String(res.error || ""),
          });
          renderWebdavTestHint();
          toast(res.ok ? "WebDAV 连接正常。" : `WebDAV 测试失败：${res.error || ""}`, res.ok ? "ok" : "warn");
        } catch (e) {
          recordWebdavTestResult({ time: new Date().toLocaleString(), ok: false, message: formatError(e) });
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
          const data = await withAuth(() => api.post("/cleanup/preview", {}));
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
          revealHintIfNeeded(hint);
          toast("清理预演完成。", "ok");
        } catch (e) {
          hint.className = "hint danger";
          hint.textContent = `清理预演失败：${formatError(e)}`;
          revealHintIfNeeded(hint);
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
          const data = await withAuth(() => api.post("/storage/sync-cache", { prune }));
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
          setLastSyncCacheAnomalyRepoKeys(new Set(anomalyRepos));
          setHasSyncCacheSnapshot(true);
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
          revealHintIfNeeded(hint);
          if ($("repoStateFilterSelect")?.value === "cache_anomaly") renderRepos();
          if (prune) {
            toast(`缓存同步完成，已清理 ${pruned} 个。`, "ok");
          } else {
            toast("缓存同步完成。", "ok");
          }
        } catch (e) {
          hint.className = "hint danger";
          hint.textContent = `缓存同步失败：${formatError(e)}`;
          revealHintIfNeeded(hint);
          toast(`缓存同步失败：${formatError(e)}`, "bad");
        } finally {
          setButtonBusy(btn, false);
          updateBatchControlsUI();
        }
      });

      $("saveSettingsBtn").addEventListener("click", async () => {
        const ok = await saveSettings({ busyButtons: [$("saveSettingsBtn")] });
        if (!ok) return;
        setSettingsDialogSaved(true);
        try {
          $("settingsDialog").close();
        } catch {}
      });
    }

    return {
      wireEvents,
    };
  }

  window.GRWAppEvents = {
    createAppEventsController,
  };
})();
