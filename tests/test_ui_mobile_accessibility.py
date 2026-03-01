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


if __name__ == "__main__":
    unittest.main()
