#!/usr/bin/env python3
"""Erzeugt die öffentliche Doku der Website (hr3000.de/doku) aus den Markdown-Dateien in docs/.

Einzige Quelle bleibt docs/*.md – nach jeder Änderung an den unten genannten Dateien ausführen
und das Ergebnis (website/doku/) mit committen:

    python3 scripts/build_website_docs.py          # erzeugen
    python3 scripts/build_website_docs.py --check  # prüfen, ob website/doku aktuell ist (rollout.sh)

Nur öffentliche Dokumente: die Handbücher und die Änderungen. betrieb.md und technik.md bleiben
intern (Server-, Backup- und Zugangsdetails). Bewusst nur Standardbibliothek und nur der
Markdown-Umfang, den docs/ nutzt: Überschriften, Absätze, (verschachtelte) Listen, Tabellen,
Codeblöcke, **fett**, `code`, [Links](ziel).
"""

from __future__ import annotations

import html
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OUT = ROOT / "website" / "doku"

# Quelle -> (Pfad auf der Website, Kurztitel für Übersicht/Navigation, Beschreibung)
PAGES = {
    "handbuch-admin.md": ("admin", "Handbuch für Admins, HR und Führungskräfte", "Einrichtung, Tagesgeschäft, Abrechnung und alle Einstellungen."),
    "handbuch-mitarbeiter.md": ("mitarbeiter", "Handbuch für Mitarbeiter", "Stempeln am Tablet und im Browser, „Mein Bereich“."),
    "aenderungen.md": ("aenderungen", "Änderungen", "Was sich wann geändert hat."),
}


# --- Markdown -> HTML (kleiner, bewusst begrenzter Umfang) ---------------------------------


def _slug(text: str) -> str:
    text = text.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _link_target(target: str) -> str | None:
    """Links zwischen Doku-Dateien auf die Website-Pfade umbiegen; interne Dateien -> None."""
    if re.match(r"^(https?:|mailto:|/|#)", target):
        return target
    name, _, anchor = target.partition("#")
    if name in PAGES:
        return f"/doku/{PAGES[name][0]}/" + (f"#{anchor}" if anchor else "")
    return None  # z.B. betrieb.md: nicht öffentlich -> nur Text


def inline(text: str) -> str:
    """Inline-Formatierung; Code-Spans werden vor allem anderen geschützt."""
    parts = re.split(r"(`[^`]+`)", text)
    out = []
    for part in parts:
        if part.startswith("`") and part.endswith("`") and len(part) > 1:
            out.append(f"<code>{html.escape(part[1:-1], quote=False)}</code>")
            continue
        s = html.escape(part, quote=False)

        def repl_link(m: re.Match) -> str:
            label, target = m.group(1), m.group(2)
            href = _link_target(html.unescape(target))
            return f'<a href="{html.escape(href)}">{label}</a>' if href else label

        s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", repl_link, s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        out.append(s)
    return "".join(out)


@dataclass
class _Item:
    indent: int
    kind: str  # "ul" | "ol"
    text: str
    children: list["_Item"] = field(default_factory=list)


_LIST_LINE = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")


def _render_items(items: list[_Item]) -> str:
    html_parts: list[str] = []
    i = 0
    while i < len(items):
        kind = items[i].kind
        group = []
        while i < len(items) and items[i].kind == kind:
            group.append(items[i])
            i += 1
        lis = "".join(f"<li>{inline(it.text)}{_render_items(it.children)}</li>" for it in group)
        html_parts.append(f"<{kind}>{lis}</{kind}>")
    return "".join(html_parts)


def _render_list(lines: list[str]) -> str:
    root: list[_Item] = []
    stack: list[_Item] = []
    for line in lines:
        m = _LIST_LINE.match(line)
        if m:
            indent = len(m.group(1))
            item = _Item(indent, "ol" if m.group(2)[0].isdigit() else "ul", m.group(3).strip())
            while stack and stack[-1].indent >= indent:
                stack.pop()
            (stack[-1].children if stack else root).append(item)
            stack.append(item)
        elif stack:  # umbrochene Zeile eines Listenpunkts
            stack[-1].text += " " + line.strip()
    return _render_items(root)


def _render_table(lines: list[str]) -> str:
    rows = [[c.strip() for c in line.strip().strip("|").split("|")] for line in lines]
    header, body = rows[0], [r for r in rows[1:] if not all(re.fullmatch(r":?-{3,}:?", c) for c in r)]
    thead = "".join(f"<th>{inline(c)}</th>" for c in header)
    tbody = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body)
    return f'<div class="table-wrap"><table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table></div>'


def markdown_to_html(text: str) -> tuple[str, str, list[tuple[str, str]]]:
    """-> (Titel aus der ersten H1, HTML ohne die H1, Inhaltsverzeichnis [(id, H2-Text)])."""
    lines = text.splitlines()
    out: list[str] = []
    toc: list[tuple[str, str]] = []
    title = ""
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("```"):
            code = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            out.append(f"<pre><code>{html.escape(chr(10).join(code), quote=False)}</code></pre>")
            continue
        m = re.match(r"^(#{1,3})\s+(.*)$", line)
        if m:
            level, content = len(m.group(1)), m.group(2).strip()
            if level == 1 and not title:
                title = content
            else:
                anchor = _slug(content)
                if level == 2:
                    toc.append((anchor, content))
                out.append(f'<h{level} id="{anchor}">{inline(content)}</h{level}>')
            i += 1
            continue
        if line.lstrip().startswith("|"):
            block = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                block.append(lines[i])
                i += 1
            out.append(_render_table(block))
            continue
        if _LIST_LINE.match(line):
            block = []
            while i < len(lines) and lines[i].strip() and (_LIST_LINE.match(lines[i]) or lines[i].startswith(" ")):
                block.append(lines[i])
                i += 1
            out.append(_render_list(block))
            continue
        para = []
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,3}\s|\||```)", lines[i]) and not _LIST_LINE.match(lines[i]):
            para.append(lines[i].strip())
            i += 1
        out.append(f"<p>{inline(' '.join(para))}</p>")
    return title, "\n".join(out), toc


# --- Seiten ------------------------------------------------------------------------------

_HEAD = """<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} – HR3000</title>
  <meta name="description" content="{description}">
  <meta name="theme-color" content="#4f46e5">
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="/assets/style.css">
</head>
<body>
  <header class="site-header">
    <div class="container">
      <a class="brand" href="/"><img src="/assets/logo.svg" alt="" width="32" height="32">HR3000</a>
      <nav class="site-nav" aria-label="Hauptnavigation">
        <a class="nav-section" href="/doku/">Doku</a>
        <a class="btn btn-ghost btn-small" href="/login/">Anmelden</a>
      </nav>
    </div>
  </header>
"""

_FOOT = """
  <footer class="site-footer">
    <div class="container">
      <span>© 2026 HR3000 · Lassners IT Factory</span>
      <nav aria-label="Rechtliches">
        <a href="/">Startseite</a>
        <a href="/doku/">Doku</a>
        <a href="https://github.com/EEaglEEyEE/hr3000" rel="noopener">Quellcode</a>
        <a href="/agb/">Nutzungsbedingungen</a>
        <a href="/avv/">AV-Vertrag</a>
        <a href="/impressum/">Impressum</a>
        <a href="/datenschutz/">Datenschutz</a>
      </nav>
    </div>
  </footer>
</body>
</html>
"""

_GENERATED = "<!-- Erzeugt von scripts/build_website_docs.py aus docs/{source} – nicht von Hand ändern. -->\n"


def _page(source: str) -> str:
    slug, short, description = PAGES[source]
    title, body, toc = markdown_to_html((DOCS / source).read_text(encoding="utf-8"))
    title = re.sub(r"^HR3000\s*[–-]\s*", "", title)
    toc_html = ""
    if len(toc) > 2:
        links = "".join(f'<li><a href="#{a}">{inline(t)}</a></li>' for a, t in toc)
        toc_html = f'<nav class="doc-toc" aria-label="Inhalt"><strong>Inhalt</strong><ul>{links}</ul></nav>'
    return (
        _GENERATED.format(source=source)
        + _HEAD.format(title=html.escape(title or short), description=html.escape(description))
        + f'  <main class="container legal doc">\n    <p class="doc-crumbs"><a href="/doku/">Doku</a> › {html.escape(short)}</p>\n'
        + f"    <h1>{inline(title or short)}</h1>\n    {toc_html}\n{body}\n  </main>\n"
        + _FOOT
    )


def _index() -> str:
    cards = "".join(
        f'<a class="card doc-card" href="/doku/{slug}/"><h3>{html.escape(short)}</h3><p>{html.escape(desc)}</p></a>'
        for slug, short, desc in PAGES.values()
    )
    return (
        _GENERATED.format(source="*.md")
        + _HEAD.format(title="Dokumentation", description="Handbücher und Änderungen von HR3000.")
        + '  <main class="container legal doc">\n    <h1>Dokumentation</h1>\n'
        + "    <p class=\"muted\">Alles zur Einrichtung und Bedienung von HR3000. Die Doku wird mit jeder Änderung aktualisiert.</p>\n"
        + f'    <div class="grid doc-grid">{cards}</div>\n  </main>\n'
        + _FOOT
    )


def build() -> dict[Path, str]:
    files = {OUT / "index.html": _index()}
    for source, (slug, _, _) in PAGES.items():
        files[OUT / slug / "index.html"] = _page(source)
    return files


def main(argv: list[str]) -> int:
    files = build()
    if "--check" in argv:
        stale = [p for p, content in files.items() if not p.exists() or p.read_text(encoding="utf-8") != content]
        for p in stale:
            print(f"veraltet: {p.relative_to(ROOT)}")
        if stale:
            print("Website-Doku ist nicht aktuell – python3 scripts/build_website_docs.py ausführen und committen.")
            return 1
        print("Website-Doku ist aktuell.")
        return 0
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"geschrieben: {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
