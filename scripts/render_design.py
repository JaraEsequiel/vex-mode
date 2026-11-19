"""Render the design doc's HTML from its Markdown, so the two never drift apart.

    python3 scripts/render_design.py          # writes docs/specs/2026-11-18-vex-mode-design.html
    python3 scripts/render_design.py --check  # exits 1 if the committed HTML is stale

Covers only the Markdown the design uses: headings, paragraphs, nested lists, tables, fenced code
(```mermaid becomes a diagram), **bold**, *italic*, [links](url), `code`, and source tags written as
`[P-mode:20]`, which become colored links to their row in §13.
"""
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MD = ROOT / "docs/specs/2026-11-18-vex-mode-design.md"
OUT = MD.with_suffix(".html")
TEMPLATE = Path(__file__).resolve().parent / "design_template.html"
PSTACK_BLOB = "https://github.com/cursor/plugins/blob/35a9094/"

TAG = re.compile(r"^(P-[\w-]+|T-[\w-]+|I-\d+|A-[\w-]+|AUD|VEX|MÍA)(:[\w,\-–]+)?$")
CLASSES = {"P": "p", "T": "t", "I": "i", "A": "a", "AUD": "aud", "VEX": "vex", "MÍA": "mia"}
LIST = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")
H2 = re.compile(r"^## (\d+[a-z]?)\.\s+(.*)$")
H3 = re.compile(r"^### (\d+)\.(\d+)\s+(.*)$")


def tag_link(code: str) -> str | None:
    m = TAG.match(code)
    if not m:
        return None
    name = m.group(1)
    cls = CLASSES.get(name) or CLASSES[name.split("-")[0]]
    anchor = "MIA" if name == "MÍA" else name
    return f'<a class="s {cls}" href="#{anchor}">{html.escape(code)}</a>'


def _text(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"(?<![\"'>=])(https?://[^\s<)|]+)", r'<a href="\1">\1</a>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])", r"<i>\1</i>", s)
    return s


def inline(s: str) -> str:
    """Code spans become placeholders first, so **bold** and *italic* may wrap them."""
    codes = []

    def keep(m: re.Match) -> str:
        code = m.group(1)
        bracket = re.fullmatch(r"\[(.+)\]", code)
        codes.append((tag_link(bracket.group(1)) if bracket else None) or f"<code>{html.escape(code)}</code>")
        return f"\x00{len(codes) - 1}\x00"

    text = _text(re.sub(r"`([^`]*)`", keep, s))
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)


def plain(s: str) -> str:
    """Heading text for the table of contents: no source tags, no markup."""
    s = re.sub(r"\s*`\[[^\]]+\]`", "", s)
    return re.sub(r"[`*]", "", s).strip()


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _table(rows: list[str], sources: bool) -> str:
    head, body = _cells(rows[0]), [_cells(r) for r in rows[2:]]
    out = ["<table>", "  <tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr>"]
    for cells in body:
        attr = ""
        if sources and cells and re.fullmatch(r"`[^`]+`", cells[0]):
            code = cells[0][1:-1]
            anchor = "MIA" if code == "MÍA" else code
            attr = f' id="{html.escape(anchor)}"'
            cells = [tag_link(code) or inline(cells[0]), *cells[1:]]
            first = cells[0]
        else:
            first = inline(cells[0]) if cells else ""
        rest = []
        for c in cells[1:]:
            m = re.fullmatch(r"`(pstack/[^`]+)`(.*)", c) if sources else None
            rest.append(f'<a href="{PSTACK_BLOB}{m.group(1)}">{html.escape(m.group(1))}</a>{inline(m.group(2))}' if m
                        else inline(c))
        out.append(f"  <tr{attr}><td>{first}</td>" + "".join(f"<td>{c}</td>" for c in rest) + "</tr>")
    return "\n".join(out + ["</table>"])


def _list(items: list[tuple[int, str, str]]) -> str:
    """items: (indent, marker, text) in order; nesting follows indentation."""
    out, stack = [], []  # stack of (indent, tag)
    for indent, marker, text in items:
        tag = "ol" if marker[0].isdigit() else "ul"
        while stack and indent < stack[-1][0]:
            out.append(f"</li></{stack.pop()[1]}>")
        if not stack or indent > stack[-1][0]:
            out.append(f"<{tag}>")
            stack.append((indent, tag))
        else:
            out.append("</li>")
        out.append(f"<li>{inline(text)}")
    while stack:
        out.append(f"</li></{stack.pop()[1]}>")
    return "\n".join(out)


def render_body(lines: list[str]) -> tuple[str, list[tuple[str, str]]]:
    out, nav, i, section = [], [], 0, None
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.strip() == "---":
            i += 1
            continue
        if m := H2.match(line):
            section = m.group(1)
            nav.append((f"s{section}", f"{section}. {plain(m.group(2))}"))
            out.append(f'<h2 id="s{section}"><span class="n">{section}</span>{inline(m.group(2))}</h2>')
            i += 1
        elif m := H3.match(line):
            out.append(f'<h3 id="s{m.group(1)}-{m.group(2)}">{m.group(1)}.{m.group(2)} {inline(m.group(3))}</h3>')
            i += 1
        elif line.startswith("```"):
            lang, i, code = line[3:].strip(), i + 1, []
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            text = "\n".join(code)
            out.append(f'<div class="mermaid">\n{text}\n</div>' if lang == "mermaid"
                       else f"<pre><code>{html.escape(text)}</code></pre>")
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(lines[i])
                i += 1
            out.append(_table(rows, sources=section == "13"))
        elif LIST.match(line):
            items = []
            while i < len(lines) and (m := LIST.match(lines[i])):
                items.append((len(m.group(1)), m.group(2), m.group(3)))
                i += 1
            out.append(_list(items))
        else:
            para = []
            while i < len(lines) and lines[i].strip() and not (
                    lines[i].startswith(("#", "|", "```")) or LIST.match(lines[i]) or lines[i].strip() == "---"):
                para.append(lines[i].strip())
                i += 1
            out.append(f"<p>{inline(' '.join(para))}</p>")
    return "\n".join(out), nav


def render(md: str, template: str) -> str:
    lines = md.splitlines()
    first_rule = lines.index("---")
    meta = []
    for line in lines[:first_rule]:
        if m := re.match(r"^- \*\*(.+?):\*\*\s*(.*)$", line):
            meta.append(f"    <span><b>{html.escape(m.group(1))}</b> {inline(m.group(2))}</span>")
    body, nav = render_body(lines[first_rule + 1:])
    nav_html = "\n".join(f'  <a href="#{a}">{html.escape(t)}</a>' for a, t in nav)
    return (template.replace("{nav}", nav_html).replace("{meta}", "\n".join(meta)).replace("{body}", body))


def main(argv: list[str]) -> int:
    page = render(MD.read_text(), TEMPLATE.read_text())
    if argv[:1] == ["--check"]:
        if not OUT.exists() or OUT.read_text() != page:
            print(f"{OUT.relative_to(ROOT)} is stale: run python3 scripts/render_design.py")
            return 1
        return 0
    OUT.write_text(page)
    print(OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
