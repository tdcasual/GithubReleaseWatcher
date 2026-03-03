(function attachRepoController(global) {
  function createRepoController(deps) {
    const getConfig = deps.getConfig;
    const getDraft = deps.getDraft;
    const getRepoSummaryByKey = deps.getRepoSummaryByKey;
    const getLastSyncCacheAnomalyRepoKeys = deps.getLastSyncCacheAnomalyRepoKeys;
    const setLastSyncCacheAnomalyRepoKeys = deps.setLastSyncCacheAnomalyRepoKeys;
    const getSelectedRepoKeysSet = deps.getSelectedRepoKeysSet;
    const setSelectedRepoKeysSet = deps.setSelectedRepoKeysSet;
    const getFilterText = deps.getFilterText;
    const getStateFilter = deps.getStateFilter;
    const getSortMode = deps.getSortMode;

    const getRepoConfigByKey = (key) => {
      const config = getConfig();
      if (!config || !Array.isArray(config.repos)) return null;
      for (const repo of config.repos) {
        if (String(repo?.key || "") === String(key || "")) return repo;
      }
      return null;
    };

    const isRepoEnabledForRun = (key) => {
      const repoCfg = getRepoConfigByKey(key);
      if (!repoCfg) return false;
      const draft = getDraft();
      const patch = draft?.repos?.[key] || {};
      if (Object.prototype.hasOwnProperty.call(patch, "enabled")) return !!patch.enabled;
      return !!repoCfg.enabled;
    };

    const isRepoInErrorState = (key) => {
      const summaryByKey = getRepoSummaryByKey();
      const summary = summaryByKey?.get(String(key || ""));
      return summary?.stats?.last_check_ok === false;
    };

    const isRepoInCacheAnomalyState = (key) => {
      const cacheKeys = getLastSyncCacheAnomalyRepoKeys();
      return cacheKeys?.has(String(key || ""));
    };

    const getRepoListView = () => {
      const config = getConfig();
      if (!config || !Array.isArray(config.repos)) {
        return { repos: [], filterText: "", total: 0 };
      }

      const filterText = String(getFilterText() || "")
        .trim()
        .toLowerCase();
      const stateFilter = String(getStateFilter() || "all").trim();
      const sortMode = String(getSortMode() || "default").trim();
      const summaryByKey = getRepoSummaryByKey();

      let repos = Array.from(config.repos);
      if (filterText) {
        repos = repos.filter((r) => {
          const key = String(r?.key || "").toLowerCase();
          const name = String(r?.name || "").toLowerCase();
          return key.includes(filterText) || name.includes(filterText);
        });
      }

      if (stateFilter !== "all") {
        const validRepoKeys = new Set(repos.map((r) => String(r?.key || "")));
        if (stateFilter === "cache_anomaly") {
          const next = new Set();
          for (const key of getLastSyncCacheAnomalyRepoKeys()) {
            if (validRepoKeys.has(key)) next.add(key);
          }
          setLastSyncCacheAnomalyRepoKeys(next);
        }

        repos = repos.filter((r) => {
          const key = String(r?.key || "");
          const enabled = isRepoEnabledForRun(key);
          if (stateFilter === "enabled") return enabled;
          if (stateFilter === "disabled") return !enabled;
          if (stateFilter === "error") return isRepoInErrorState(key);
          if (stateFilter === "network_error") {
            const summary = summaryByKey.get(key);
            return summary?.stats?.last_check_ok === false && summary?.stats?.last_error_type === "network";
          }
          if (stateFilter === "cache_anomaly") {
            return isRepoInCacheAnomalyState(key);
          }
          return true;
        });
      }

      const statusRank = (repoKey) => {
        const summary = summaryByKey.get(repoKey);
        const ok = summary?.stats?.last_check_ok;
        if (ok === false) return summary?.stats?.last_error_type === "network" ? 0 : 1;
        if (ok === true) return 3;
        return 2;
      };
      const nextRank = (repoKey) => {
        const summary = summaryByKey.get(repoKey);
        const iso = summary?.next_run_at;
        const t = iso ? Date.parse(iso) : Number.POSITIVE_INFINITY;
        return Number.isFinite(t) ? t : Number.POSITIVE_INFINITY;
      };

      if (sortMode === "status") {
        repos.sort((a, b) => {
          const ak = String(a.key || "");
          const bk = String(b.key || "");
          const ar = statusRank(ak);
          const br = statusRank(bk);
          if (ar !== br) return ar - br;
          const an = nextRank(ak);
          const bn = nextRank(bk);
          if (an !== bn) return an - bn;
          return ak.localeCompare(bk);
        });
      } else if (sortMode === "next") {
        repos.sort((a, b) => {
          const ak = String(a.key || "");
          const bk = String(b.key || "");
          const an = nextRank(ak);
          const bn = nextRank(bk);
          if (an !== bn) return an - bn;
          return ak.localeCompare(bk);
        });
      }

      return { repos, filterText, stateFilter, total: config.repos.length };
    };

    const getVisibleRepoKeys = () => {
      const view = getRepoListView();
      const keys = [];
      for (const repo of view.repos) {
        const key = String(repo?.key || "");
        if (key) keys.push(key);
      }
      return keys;
    };

    const syncSelectedReposWithConfig = () => {
      const config = getConfig();
      const existing = new Set(Array.isArray(config?.repos) ? config.repos.map((r) => String(r?.key || "")) : []);
      const next = new Set();
      for (const key of getSelectedRepoKeysSet()) {
        if (existing.has(key)) next.add(key);
      }
      setSelectedRepoKeysSet(next);
    };

    const getSelectedRepoKeys = () => {
      syncSelectedReposWithConfig();
      return Array.from(getSelectedRepoKeysSet());
    };

    return {
      getRepoConfigByKey,
      getRepoListView,
      getSelectedRepoKeys,
      getVisibleRepoKeys,
      isRepoEnabledForRun,
      isRepoInCacheAnomalyState,
      isRepoInErrorState,
      syncSelectedReposWithConfig,
    };
  }

  global.GRWRepoController = { createRepoController };
})(window);
