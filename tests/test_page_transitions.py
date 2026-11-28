import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HELPERS = ("dvNavigate", "dvSubmitForm")
TRANSITIONS = "js/page-transitions.js"


class PageTransitionsContractTest(unittest.TestCase):
    """Scripts that redirect through window.dvNavigate / dvSubmitForm crash
    without page-transitions.js, so every page using them must load it first."""

    def test_pages_load_transitions_before_scripts_that_need_them(self):
        dependent = {
            f"js/{path.name}"
            for path in (ROOT / "static/js").glob("*.js")
            if path.name != "page-transitions.js" and any(h in path.read_text(encoding="utf-8") for h in HELPERS)
        }
        self.assertIn("js/lobby.js", dependent)
        for template in sorted((ROOT / "templates").glob("*.html")):
            html = template.read_text(encoding="utf-8-sig")
            scripts = re.findall(r"filename='(js/[\w.-]+\.js)'", html)
            needs = [s for s in scripts if s in dependent]
            inline = any(h in re.sub(r"<script[^>]*src=[^>]*></script>", "", html) for h in HELPERS)
            if not needs and not inline:
                continue
            with self.subTest(template=template.name):
                self.assertIn(TRANSITIONS, scripts, f"{template.name} uses {needs or 'an inline helper'} without {TRANSITIONS}")
                for script in needs:
                    self.assertLess(scripts.index(TRANSITIONS), scripts.index(script), f"{TRANSITIONS} must load before {script}")


if __name__ == "__main__":
    unittest.main()
