(() => {
  function createSettingsDialogController(options = {}) {
    const getEl = typeof options.getEl === "function" ? options.getEl : (id) => document.getElementById(id);
    const getDraft = typeof options.getDraft === "function" ? options.getDraft : () => null;
    const getSettingsDialogDraftSnapshot =
      typeof options.getSettingsDialogDraftSnapshot === "function" ? options.getSettingsDialogDraftSnapshot : () => null;
    const stableStringify = typeof options.stableStringify === "function" ? options.stableStringify : (value) => JSON.stringify(value);
    const getLastWebdavTest = typeof options.getLastWebdavTest === "function" ? options.getLastWebdavTest : () => null;
    const setLastWebdavTest = typeof options.setLastWebdavTest === "function" ? options.setLastWebdavTest : () => {};
    const revealHintIfNeeded = typeof options.revealHintIfNeeded === "function" ? options.revealHintIfNeeded : () => {};

    const $ = (id) => getEl(id);

    function hasSettingsDialogUnsavedChanges() {
      const draft = getDraft();
      const snapshot = getSettingsDialogDraftSnapshot();
      if (!snapshot || !draft) return false;
      try {
        return stableStringify(draft) !== stableStringify(snapshot);
      } catch {
        return false;
      }
    }

    function renderWebdavTestHint() {
      const el = $("webdavTestHint");
      if (!el) return;
      const lastWebdavTest = getLastWebdavTest();
      if (!lastWebdavTest) {
        el.className = "hint";
        el.textContent = "上次测试：未测试";
        revealHintIfNeeded(el);
        return;
      }
      el.className = lastWebdavTest.ok ? "hint" : "hint danger";
      el.textContent = `上次测试：${lastWebdavTest.time} · ${lastWebdavTest.ok ? "连接正常" : `失败：${lastWebdavTest.message}`}`;
      revealHintIfNeeded(el);
    }

    function invalidateWebdavTest() {
      setLastWebdavTest(null);
      renderWebdavTestHint();
    }

    function syncSettingsFormFromDraft() {
      const draft = getDraft();
      const mode = draft?.storage?.mode || "local";
      const storageModeLocal = $("storageModeLocal");
      const storageModeWebdav = $("storageModeWebdav");
      const webdavFields = $("webdavFields");

      if (storageModeLocal) storageModeLocal.checked = mode === "local";
      if (storageModeWebdav) storageModeWebdav.checked = mode === "webdav";

      const localDirInput = $("localDirInput");
      const webdavBaseUrl = $("webdavBaseUrl");
      const webdavUsername = $("webdavUsername");
      const webdavTimeout = $("webdavTimeout");
      const webdavVerifyTls = $("webdavVerifyTls");
      const webdavUploadConcurrency = $("webdavUploadConcurrency");
      const webdavMaxRetries = $("webdavMaxRetries");
      const webdavRetryBackoffSeconds = $("webdavRetryBackoffSeconds");
      const webdavVerifyAfterUpload = $("webdavVerifyAfterUpload");
      const webdavUploadTempSuffix = $("webdavUploadTempSuffix");
      const webdavCleanupMode = $("webdavCleanupMode");

      if (localDirInput) localDirInput.value = draft?.storage?.local_dir || "";
      if (webdavBaseUrl) webdavBaseUrl.value = draft?.storage?.webdav?.base_url || "";
      if (webdavUsername) webdavUsername.value = draft?.storage?.webdav?.username || "";
      if (webdavTimeout) webdavTimeout.value = String(draft?.storage?.webdav?.timeout_seconds ?? 60);
      if (webdavVerifyTls) webdavVerifyTls.checked = !!(draft?.storage?.webdav?.verify_tls ?? true);
      if (webdavUploadConcurrency) webdavUploadConcurrency.value = String(draft?.storage?.webdav?.upload_concurrency ?? 2);
      if (webdavMaxRetries) webdavMaxRetries.value = String(draft?.storage?.webdav?.max_retries ?? 3);
      if (webdavRetryBackoffSeconds) webdavRetryBackoffSeconds.value = String(draft?.storage?.webdav?.retry_backoff_seconds ?? 2);
      if (webdavVerifyAfterUpload) webdavVerifyAfterUpload.checked = !!(draft?.storage?.webdav?.verify_after_upload ?? true);
      if (webdavUploadTempSuffix) webdavUploadTempSuffix.value = String(draft?.storage?.webdav?.upload_temp_suffix || ".uploading");
      if (webdavCleanupMode) webdavCleanupMode.value = String(draft?.storage?.webdav?.cleanup_mode || "delete");
      if (webdavFields) webdavFields.classList.toggle("hidden", mode !== "webdav");

      renderWebdavTestHint();
    }

    function syncDraftFromSettingsForm() {
      const draft = getDraft();
      if (!draft?.storage?.webdav) return;

      const mode = $("storageModeWebdav")?.checked ? "webdav" : "local";
      draft.storage.mode = mode;
      draft.storage.local_dir = $("localDirInput")?.value?.trim() || "";
      draft.storage.webdav.base_url = $("webdavBaseUrl")?.value?.trim() || "";
      draft.storage.webdav.username = $("webdavUsername")?.value?.trim() || "";
      draft.storage.webdav.verify_tls = !!$("webdavVerifyTls")?.checked;
      draft.storage.webdav.timeout_seconds = Number($("webdavTimeout")?.value?.trim() || 60);
      draft.storage.webdav.upload_concurrency = Number($("webdavUploadConcurrency")?.value?.trim() || 2);
      draft.storage.webdav.max_retries = Number($("webdavMaxRetries")?.value?.trim() || 3);
      draft.storage.webdav.retry_backoff_seconds = Number($("webdavRetryBackoffSeconds")?.value?.trim() || 2);
      draft.storage.webdav.verify_after_upload = !!$("webdavVerifyAfterUpload")?.checked;
      draft.storage.webdav.upload_temp_suffix = String($("webdavUploadTempSuffix")?.value || ".uploading").trim();
      draft.storage.webdav.cleanup_mode = String($("webdavCleanupMode")?.value || "delete").trim();
      $("webdavFields")?.classList.toggle("hidden", mode !== "webdav");
    }

    return {
      hasSettingsDialogUnsavedChanges,
      renderWebdavTestHint,
      invalidateWebdavTest,
      syncSettingsFormFromDraft,
      syncDraftFromSettingsForm,
    };
  }

  window.GRWAppSettingsDialog = {
    createSettingsDialogController,
  };
})();
