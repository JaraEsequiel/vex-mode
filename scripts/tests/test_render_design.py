import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import render_design as rd

TEMPLATE = "<nav>{nav}</nav><div>{meta}</div><main>{body}</main>"
DOC = """# Title

- **Fecha:** 2026-11-19
- **Estado:** listo

---

## 1. Intención `[VEX]`

Texto con **negrita y `código`** y *cursiva* `[P-mode:20]` y `[MÍA]`.

- uno
  - anidado `[I-726]`
- dos

1. primero
2. segundo

```mermaid
flowchart LR
  A --> B
```

## 13. Fuentes

| Código | Fuente |
|---|---|
| `P-mode` | `pstack/skills/poteto-mode/SKILL.md` |
| `MÍA` | Propuesta mía |
"""


class RenderTest(unittest.TestCase):
    def page(self):
        return rd.render(DOC, TEMPLATE)

    def test_source_tags_link_to_their_row(self):
        page = self.page()
        self.assertIn('<a class="s p" href="#P-mode">P-mode:20</a>', page)
        self.assertIn('<a class="s mia" href="#MIA">MÍA</a>', page)
        self.assertIn('<tr id="P-mode">', page)
        self.assertIn('<tr id="MIA">', page)

    def test_bold_may_wrap_code(self):
        self.assertIn("<b>negrita y <code>código</code></b>", self.page())
        self.assertIn("<i>cursiva</i>", self.page())

    def test_lists_nest_and_number(self):
        page = self.page()
        self.assertIn("<li>uno\n<ul>\n<li>anidado", page)
        self.assertIn("<ol>\n<li>primero", page)

    def test_mermaid_and_pstack_links(self):
        page = self.page()
        self.assertIn('<div class="mermaid">\nflowchart LR\n  A --> B\n</div>', page)
        self.assertIn(f'<a href="{rd.PSTACK_BLOB}pstack/skills/poteto-mode/SKILL.md">', page)

    def test_toc_and_meta(self):
        page = self.page()
        self.assertIn('<a href="#s1">1. Intención</a>', page)
        self.assertIn("<b>Fecha</b> 2026-11-19", page)
        self.assertIn('<h2 id="s13">', page)

    def test_committed_html_is_current(self):
        self.assertEqual(rd.main(["--check"]), 0, "run python3 scripts/render_design.py")


if __name__ == "__main__":
    unittest.main()
