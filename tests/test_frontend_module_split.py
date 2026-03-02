from __future__ import annotations

import unittest
from pathlib import Path


class FrontendModuleSplitTests(unittest.TestCase):
    def test_index_loads_api_and_formatter_modules_before_app(self) -> None:
        html = Path("github_release_watcher/static/index.html").read_text(encoding="utf-8")
        api_pos = html.find('src="/api-client.js"')
        fmt_pos = html.find('src="/formatters.js"')
        logs_pos = html.find('src="/logs-view.js"')
        repos_pos = html.find('src="/repos-controller.js"')
        settings_pos = html.find('src="/settings-controller.js"')
        storage_diag_pos = html.find('src="/storage-diagnostics.js"')
        batch_selectors_pos = html.find('src="/batch-selectors.js"')
        app_pos = html.find('src="/app.js"')
        self.assertGreaterEqual(api_pos, 0)
        self.assertGreaterEqual(fmt_pos, 0)
        self.assertGreaterEqual(logs_pos, 0)
        self.assertGreaterEqual(repos_pos, 0)
        self.assertGreaterEqual(settings_pos, 0)
        self.assertGreaterEqual(storage_diag_pos, 0)
        self.assertGreaterEqual(batch_selectors_pos, 0)
        self.assertGreaterEqual(app_pos, 0)
        self.assertLess(api_pos, app_pos)
        self.assertLess(fmt_pos, app_pos)
        self.assertLess(logs_pos, app_pos)
        self.assertLess(repos_pos, app_pos)
        self.assertLess(settings_pos, app_pos)
        self.assertLess(storage_diag_pos, app_pos)
        self.assertLess(batch_selectors_pos, app_pos)

    def test_app_uses_shared_global_modules(self) -> None:
        app_js = Path("github_release_watcher/static/app.js").read_text(encoding="utf-8")
        self.assertIn("window.GRWApiClient", app_js)
        self.assertIn("window.GRWFormatters", app_js)
        self.assertIn("window.GRWLogsView", app_js)
        self.assertIn("window.GRWRepoController", app_js)
        self.assertIn("window.GRWSettingsController", app_js)
        self.assertIn("window.GRWStorageDiagnostics", app_js)
        self.assertIn("window.GRWBatchSelectors", app_js)
        self.assertNotIn("const API = {", app_js)
        self.assertNotIn("function renderStructuredLogs(", app_js)
        self.assertNotIn("function getRepoListView(", app_js)
        self.assertNotIn("function validateIntField(", app_js)
        self.assertNotIn("function formatStorageHealthTopRepos(", app_js)
        self.assertNotIn("function refreshStorageDiagnostics(", app_js)
        self.assertNotIn("function batchSelectVisible(", app_js)


if __name__ == "__main__":
    unittest.main()
