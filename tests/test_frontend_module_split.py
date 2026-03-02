from __future__ import annotations

import unittest
from pathlib import Path


class FrontendModuleSplitTests(unittest.TestCase):
    def test_index_loads_api_and_formatter_modules_before_app(self) -> None:
        html = Path("github_release_watcher/static/index.html").read_text(encoding="utf-8")
        api_pos = html.find('src="/api-client.js"')
        fmt_pos = html.find('src="/formatters.js"')
        app_pos = html.find('src="/app.js"')
        self.assertGreaterEqual(api_pos, 0)
        self.assertGreaterEqual(fmt_pos, 0)
        self.assertGreaterEqual(app_pos, 0)
        self.assertLess(api_pos, app_pos)
        self.assertLess(fmt_pos, app_pos)

    def test_app_uses_shared_global_modules(self) -> None:
        app_js = Path("github_release_watcher/static/app.js").read_text(encoding="utf-8")
        self.assertIn("window.GRWApiClient", app_js)
        self.assertIn("window.GRWFormatters", app_js)
        self.assertNotIn("const API = {", app_js)


if __name__ == "__main__":
    unittest.main()
