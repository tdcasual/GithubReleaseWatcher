import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "github_release_watcher" / "static"


def contrast_ratio(hex_a: str, hex_b: str) -> float:
    def channel_to_linear(v: int) -> float:
        s = v / 255.0
        if s <= 0.03928:
            return s / 12.92
        return ((s + 0.055) / 1.055) ** 2.4

    def luminance(hex_color: str) -> float:
        h = hex_color.lstrip("#")
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
        return (
            0.2126 * channel_to_linear(r)
            + 0.7152 * channel_to_linear(g)
            + 0.0722 * channel_to_linear(b)
        )

    la = luminance(hex_a)
    lb = luminance(hex_b)
    lighter = max(la, lb)
    darker = min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


class UIMobileAccessibilityTests(unittest.TestCase):
    def test_mobile_meta_viewport_uses_viewport_fit_cover(self) -> None:
        for name in ("index.html", "repo.html"):
            content = (STATIC_DIR / name).read_text(encoding="utf-8")
            # iOS safe-area support requires viewport-fit=cover.
            self.assertRegex(
                content,
                r'<meta\s+name="viewport"\s+content="[^"]*viewport-fit=cover[^"]*"',
                msg=f"{name} is missing viewport-fit=cover in viewport meta tag",
            )

    def test_light_theme_muted_text_has_minimum_contrast(self) -> None:
        content = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
        muted = re.search(r"--muted:\s*(#[0-9a-fA-F]{6})\s*;", content)
        card = re.search(r"--card:\s*(#[0-9a-fA-F]{6})\s*;", content)
        self.assertIsNotNone(muted, "Could not locate light theme --muted color.")
        self.assertIsNotNone(card, "Could not locate light theme --card color.")
        ratio = contrast_ratio(muted.group(1), card.group(1))
        self.assertGreaterEqual(
            ratio,
            4.5,
            f"Muted text contrast ratio is {ratio:.2f}, expected at least 4.5 on light card background.",
        )

    def test_layout_and_mobile_toast_regression_guards(self) -> None:
        content = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
        index_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn(
            "#securityBanner {\n    grid-column: 1 / -1;\n  }",
            content,
            "security banner should span both desktop columns to avoid large blank areas.",
        )
        self.assertIn("pointer-events: none;", content, "toast should not block taps/clicks.")
        self.assertRegex(
            content,
            r"@media\s*\(max-width:\s*640px\)\s*\{[\s\S]*?\.toast\s*\{[\s\S]*?bottom:\s*calc\(18px\s*\+\s*env\(safe-area-inset-bottom\)\)",
            "mobile toast should stay near bottom safe-area and avoid covering content cards.",
        )
        self.assertIn("grid-template-columns: minmax(0, 1fr);", content, "grid should clamp single-column width on mobile.")
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", content, "desktop grid should also use clamped tracks.")
        self.assertIn(".grid > * {\n  min-width: 0;\n}", content, "grid children should allow shrinking to viewport width.")
        self.assertRegex(
            content,
            r"@media\s*\(max-width:\s*640px\)\s*\{[\s\S]*?\.card-head\s*\{[\s\S]*?flex-wrap:\s*wrap;",
            "mobile card header should wrap to prevent horizontal overflow.",
        )
        self.assertIn('id="batchToolsToggleBtn"', index_html, "mobile batch tools should provide a collapse toggle button.")
        self.assertIn('aria-controls="batchToolsPanel"', index_html, "batch tools toggle should reference its controlled panel.")
        self.assertIn('.batch-tools-wrap[data-expanded="false"] .batch-tools', content, "collapsed batch tools rule should exist on mobile.")

    def test_logs_panel_uses_structured_readable_layout(self) -> None:
        content = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
        index_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        logs_view_js = (STATIC_DIR / "logs-view.js").read_text(encoding="utf-8")
        logs_source = f"{app_js}\n{logs_view_js}"
        self.assertIn('id="logs"', index_html, "logs container should exist.")
        self.assertIn('class="logs logs-feed"', index_html, "logs container should use feed layout class.")
        self.assertIn('role="log"', index_html, "logs container should expose log role for assistive tools.")
        self.assertIn(".log-entry", content, "structured log row style should exist.")
        self.assertIn(".log-time", content, "structured log time style should exist.")
        self.assertIn(".log-summary", content, "structured log summary style should exist.")
        self.assertIn(".log-details", content, "error details style should exist.")
        self.assertIn(".log-details[hidden]", content, "error details should support collapsed hidden state.")
        self.assertIn(".log-count-badge", content, "repeated log groups should show compact count badge style.")
        self.assertIn(".log-detail-advanced-toggle", content, "error details should use a single advanced-details toggle.")
        self.assertIn(".log-detail-advanced", content, "error details should include advanced details panel.")
        self.assertIn(".log-detail-advanced-row", content, "advanced details panel should render structured rows.")
        self.assertIn(".log-detail-advanced-toggle.is-critical", content, "critical errors should have emphasized advanced-details toggle style.")
        self.assertIn('tone === "bad"', logs_source, "only error-toned logs should render detailed blocks.")
        self.assertIn("details.hidden = !expanded", logs_source, "error details should toggle expanded/collapsed state.")
        self.assertIn("buildDisplayLogGroups", logs_source, "log rendering should aggregate repeated events before display.")
        self.assertIn("formatLogPathTail", logs_source, "error details should show condensed path tail by default.")
        self.assertIn("summarizeLogDetailMessage", logs_source, "error details should show a concise message summary by default.")
        self.assertIn("shouldAutoExpandAdvancedDetails", logs_source, "critical errors should auto-expand advanced details.")
        self.assertIn("detailPanel.hidden = !autoExpandAdvanced", logs_source, "advanced details panel should initialize by severity policy.")
        self.assertIn("detailToggle.textContent = next ? \"收起细节\" : \"技术细节\"", logs_source, "advanced details toggle should update label.")


if __name__ == "__main__":
    unittest.main()
