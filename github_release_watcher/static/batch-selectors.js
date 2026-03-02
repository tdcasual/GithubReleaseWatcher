(function attachBatchSelectors(global) {
  function createBatchSelectorsController(deps) {
    const getVisibleRepoKeys = deps.getVisibleRepoKeys;
    const getSelectedRepoKeysSet = deps.getSelectedRepoKeysSet;
    const setSelectedRepoKeysSet = deps.setSelectedRepoKeysSet;
    const setBatchActionHint = deps.setBatchActionHint;
    const renderRepos = deps.renderRepos;
    const isRepoEnabledForRun = deps.isRepoEnabledForRun;
    const isRepoInErrorState = deps.isRepoInErrorState;
    const isRepoInCacheAnomalyState = deps.isRepoInCacheAnomalyState;
    const isWebdavStorageMode = deps.isWebdavStorageMode;
    const getHasSyncCacheSnapshot = deps.getHasSyncCacheSnapshot;

    const ensureSelectedRepoKeys = () => {
      const existing = getSelectedRepoKeysSet();
      if (existing instanceof Set) return existing;
      const next = new Set();
      setSelectedRepoKeysSet(next);
      return next;
    };

    const batchSelectByFilter = (predicate, successMessage, emptyMessage) => {
      const visible = getVisibleRepoKeys();
      if (!visible.length) {
        setBatchActionHint("当前筛选结果为空，无可选仓库。", "danger");
        return;
      }
      const selectedRepoKeys = ensureSelectedRepoKeys();
      let selectedNow = 0;
      for (const key of visible) {
        if (!predicate(key)) continue;
        if (selectedRepoKeys.has(key)) continue;
        selectedRepoKeys.add(key);
        selectedNow += 1;
      }
      if (selectedNow <= 0) {
        setBatchActionHint(emptyMessage, "danger");
        renderRepos();
        return;
      }
      setBatchActionHint(successMessage(selectedNow), "");
      renderRepos();
    };

    const batchSelectVisible = () => {
      const visible = getVisibleRepoKeys();
      if (!visible.length) {
        setBatchActionHint("当前筛选结果为空，无可选仓库。", "danger");
        return;
      }
      const selectedRepoKeys = ensureSelectedRepoKeys();
      let added = 0;
      for (const key of visible) {
        if (selectedRepoKeys.has(key)) continue;
        selectedRepoKeys.add(key);
        added += 1;
      }
      const msg = added > 0 ? `已新增选择 ${added} 个仓库。` : `当前筛选内 ${visible.length} 个仓库已全部选中。`;
      setBatchActionHint(msg, "");
      renderRepos();
    };

    const batchInvertVisible = () => {
      const visible = getVisibleRepoKeys();
      if (!visible.length) {
        setBatchActionHint("当前筛选结果为空，无法反选。", "danger");
        return;
      }
      const selectedRepoKeys = ensureSelectedRepoKeys();
      let selectedNow = 0;
      let unselectedNow = 0;
      for (const key of visible) {
        if (selectedRepoKeys.has(key)) {
          selectedRepoKeys.delete(key);
          unselectedNow += 1;
        } else {
          selectedRepoKeys.add(key);
          selectedNow += 1;
        }
      }
      const msg = `反选完成：选中 ${selectedNow} 个，取消 ${unselectedNow} 个。`;
      setBatchActionHint(msg, "");
      renderRepos();
    };

    const batchSelectEnabledVisible = () => {
      batchSelectByFilter(
        (key) => isRepoEnabledForRun(key),
        (count) => `已选中 ${count} 个启用仓库。`,
        "当前筛选结果中没有可新增的启用仓库。"
      );
    };

    const batchSelectErrorVisible = () => {
      batchSelectByFilter(
        (key) => isRepoInErrorState(key),
        (count) => `已选中 ${count} 个异常仓库。`,
        "当前筛选结果中没有可新增的异常仓库。"
      );
    };

    const batchSelectCacheAnomalyVisible = () => {
      if (!isWebdavStorageMode()) {
        setBatchActionHint("当前存储模式不是 WebDAV，无法选择缓存异常仓库。", "danger");
        return;
      }
      if (!getHasSyncCacheSnapshot()) {
        setBatchActionHint("请先在设置中执行一次“同步缓存”，再选择缓存异常仓库。", "danger");
        return;
      }
      batchSelectByFilter(
        (key) => isRepoInCacheAnomalyState(key),
        (count) => `已选中 ${count} 个缓存异常仓库。`,
        "当前筛选结果中没有可新增的缓存异常仓库。"
      );
    };

    return {
      batchSelectVisible,
      batchInvertVisible,
      batchSelectEnabledVisible,
      batchSelectErrorVisible,
      batchSelectCacheAnomalyVisible,
    };
  }

  global.GRWBatchSelectors = { createBatchSelectorsController };
})(window);
