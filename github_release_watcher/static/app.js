(() => {
  const runtime = window.GRWAppRuntime;
  const requiredModules = [
    window.GRWApiClient,
    window.GRWFormatters,
    window.GRWLogsView,
    window.GRWRepoController,
    window.GRWSettingsController,
    window.GRWStorageDiagnostics,
    window.GRWBatchSelectors,
    window.GRWBatchActions,
    window.GRWMobileBehavior,
  ];

  if (!runtime || typeof runtime.start !== "function" || requiredModules.some((module) => !module)) {
    throw new Error("Shared frontend modules not loaded");
  }

  runtime.start();
})();
