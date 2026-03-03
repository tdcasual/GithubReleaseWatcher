(function attachBatchActions(global) {
  function createBatchActionsController(deps) {
    const getSelectedRepoKeys = deps.getSelectedRepoKeys;
    const setBatchActionHint = deps.setBatchActionHint;
    const toast = deps.toast;
    const queueStatusFeedback = deps.queueStatusFeedback;
    const repoDraft = deps.repoDraft;
    const setDirty = deps.setDirty;
    const renderRepos = deps.renderRepos;
    const saveSettings = deps.saveSettings;
    const isRepoEnabledForRun = deps.isRepoEnabledForRun;
    const getMustChangePassword = deps.getMustChangePassword;
    const renderSecurityBanner = deps.renderSecurityBanner;
    const setButtonBusy = deps.setButtonBusy;
    const withAuth = deps.withAuth;
    const apiPost = deps.apiPost;
    const formatError = deps.formatError;
    const refreshStatusSafe = deps.refreshStatusSafe;
    const updateBatchControlsUI = deps.updateBatchControlsUI;

    const batchSetEnabled = async (enabled, triggerBtn) => {
      const selected = getSelectedRepoKeys();
      if (!selected.length) {
        setBatchActionHint("请先选择至少一个仓库。", "danger");
        toast("请先选择至少一个仓库。", "warn");
        return;
      }
      setBatchActionHint("", "");
      for (const key of selected) {
        repoDraft(key).enabled = !!enabled;
      }
      setDirty(true);
      renderRepos();
      const ok = await saveSettings({ busyButtons: triggerBtn ? [triggerBtn] : [] });
      if (!ok) {
        setBatchActionHint(`批量${enabled ? "启用" : "停用"}失败。`, "danger");
        return;
      }
      const msg = `批量${enabled ? "启用" : "停用"}完成：${selected.length} 个仓库。`;
      setBatchActionHint(msg, "");
      toast(msg, "ok");
    };

    const batchRunSelected = async (triggerBtn) => {
      const selected = getSelectedRepoKeys();
      if (!selected.length) {
        setBatchActionHint("请先选择至少一个仓库。", "danger");
        toast("请先选择至少一个仓库。", "warn");
        return;
      }
      const runnableSelected = selected.filter((key) => isRepoEnabledForRun(key));
      if (!runnableSelected.length) {
        setBatchActionHint("所选仓库均为停用状态，无法批量检查。", "danger");
        toast("所选仓库均为停用状态，请先启用后再批量检查。", "warn");
        return;
      }
      if (getMustChangePassword()) {
        renderSecurityBanner();
        setBatchActionHint("当前账号需先修改密码，已阻止批量触发。", "danger");
        toast("当前账号需先修改密码，请先在设置中更新账号密码。", "warn");
        return;
      }
      const skipped = selected.length - runnableSelected.length;
      const skippedSuffix = skipped > 0 ? `（跳过 ${skipped} 个停用仓库）` : "";
      setBatchActionHint("", "");
      setButtonBusy(triggerBtn, true, "触发中…");
      try {
        const res = await withAuth(() => apiPost("/run", { repos: runnableSelected }));
        if (res.error) {
          const msg = `批量触发失败：${res.error}`;
          setBatchActionHint(msg, "danger");
          toast(msg, "bad");
          return;
        }
        const feedback = queueStatusFeedback(res.queue_status);
        let msg = feedback.message;
        if (feedback.status === "accepted") {
          msg = `批量检查已入队：${runnableSelected.length} 个仓库。${skippedSuffix}`;
        } else if (feedback.status === "deduplicated") {
          msg = "已有任务在运行或队列中，本次批量请求被去重。";
        } else if (feedback.status === "rejected_overflow") {
          msg = "运行队列已满，批量请求被拒绝，请稍后重试。";
        }
        setBatchActionHint(msg, feedback.tone === "bad" ? "danger" : "");
        toast(msg, feedback.tone);
      } catch (e) {
        const msg = `批量触发失败：${formatError(e)}`;
        setBatchActionHint(msg, "danger");
        toast(msg, "bad");
      } finally {
        setButtonBusy(triggerBtn, false);
        await refreshStatusSafe().catch(() => {});
        updateBatchControlsUI();
      }
    };

    return {
      batchSetEnabled,
      batchRunSelected,
    };
  }

  global.GRWBatchActions = { createBatchActionsController };
})(window);
