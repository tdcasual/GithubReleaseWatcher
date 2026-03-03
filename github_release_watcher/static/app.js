(() => {
  const bootstrap = window.GRWBootstrapContract;
  const runtime = window.GRWAppRuntime;

  if (!bootstrap || typeof bootstrap.requireModules !== "function") {
    throw new Error("Bootstrap contract not loaded");
  }
  bootstrap.requireModules(
    [
      "GRWApiClient",
      "GRWFormatters",
      "GRWLogsView",
      "GRWRepoController",
      "GRWSettingsController",
      "GRWStorageDiagnostics",
      "GRWBatchSelectors",
      "GRWBatchActions",
      "GRWMobileBehavior",
      "GRWAppRuntime",
    ],
    "app"
  );

  if (!runtime || typeof runtime.start !== "function") {
    throw new Error("Shared frontend modules not loaded");
  }

  runtime.start();
})();
