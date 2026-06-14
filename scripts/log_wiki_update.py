#!/usr/bin/env python3
"""
log_wiki_update.py — incremental, append-only updater for the three session-log
wiki HTMLs (open-tasks / completed-by-subject / lessons-learned).

Design goals (per user spec):
  * NEVER resummarize an existing file. Only splice in new, dated entries.
  * New open tasks  -> appended as `.task` cards (open-tasks.html).
  * Resolved tasks  -> existing card title gets a `DONE <date>:` prefix IN PLACE.
  * New completed / clarifications -> `<li>` prefixed `Edit:` (completed-by-subject.html).
  * New lessons     -> `<li>` appended (lessons-learned.html).

All appends land inside a single per-file "Session Updates" region delimited by
`<!-- THOTH_APPEND_START -->` / `<!-- THOTH_APPEND_END -->`, inserted just before
the file's <footer> the first time this script runs. New items are spliced in
immediately before `<!-- THOTH_ITEM_ANCHOR -->`, so they accumulate chronologically
(newest last). Re-runnable: if a file is ever regenerated from scratch and loses
its anchors, the next run re-creates the region automatically.

Usage:
  log_wiki_update.py --delta /path/to/delta.json [--wiki-dir DIR] [--dry-run]

delta.json schema (all keys optional):
{
  "date": "2026-06-14",
  "todos_new":    [{"title": "...", "meta": "<code>path</code> ...", "body": "free text"}],
  "todos_done":   ["substring that uniquely identifies an existing task <h3>", ...],
  "completed_new":["plain-text entry", ...],
  "lessons_new":  ["plain-text entry", ...]
}
"""
import argparse, html, json, os, re, sys

DEFAULT_WIKI_DIR = os.path.expanduser("~/logs/Claude_logs/wiki")

START = "<!-- THOTH_APPEND_START -->"
END = "<!-- THOTH_APPEND_END -->"
ITEM = "<!-- THOTH_ITEM_ANCHOR -->"

# Per-file config: section wrapper class + the intro line idiom each file uses.
FILES = {
    "todos": {
        "name": "open-tasks.html",
        "section_class": "period",
        "id": "p-session-appends",
        "list_class": None,  # card-based, no <ul>
        "intro": ('<div class="note">New open tasks are appended as cards below by '
                  '<code>/log</code>; resolved tasks get a <code>DONE</code> prefix in '
                  'place above. Not resummarized.</div>'),
    },
    "completed": {
        "name": "completed-by-subject.html",
        "section_class": "subject",
        "id": "s-session-appends",
        "list_class": "done",
        "intro": ('<div class="summary">Incremental entries written by <code>/log</code>, '
                  'each dated and prefixed <code>Edit:</code>. Not resummarized; newest last.</div>'),
    },
    "lessons": {
        "name": "lessons-learned.html",
        "section_class": "theme",
        "id": "t-session-appends",
        "list_class": "lessons",
        "intro": ('<p class="lead">Incremental lessons written by <code>/log</code>, each dated. '
                  'Not resummarized; newest last.</p>'),
    },
}


def esc(s: str) -> str:
    return html.escape(str(s), quote=False)


def ensure_region(doc: str, cfg: dict) -> str:
    """Insert the empty Session-Updates region before <footer> if absent."""
    if START in doc:
        return doc
    if cfg["list_class"]:
        region = (
            f'\n{START}\n'
            f'<section class="{cfg["section_class"]}" id="{cfg["id"]}">\n'
            f'<h2>Session Updates &mdash; live appends</h2>\n'
            f'{cfg["intro"]}\n'
            f'<ul class="{cfg["list_class"]}">\n'
            f'{ITEM}\n'
            f'</ul>\n'
            f'</section>\n'
            f'{END}\n'
        )
    else:
        region = (
            f'\n{START}\n'
            f'<section class="{cfg["section_class"]}" id="{cfg["id"]}">\n'
            f'<h2>Session Updates &mdash; live appends</h2>\n'
            f'{cfg["intro"]}\n'
            f'{ITEM}\n'
            f'</section>\n'
            f'{END}\n'
        )
    # Insert before the LAST <footer (the page footer), else before </body>.
    idx = doc.rfind("<footer")
    if idx == -1:
        idx = doc.rfind("</body>")
    if idx == -1:
        return doc + region  # degenerate file; append at end
    return doc[:idx] + region + doc[idx:]


def splice_before_anchor(doc: str, item_html: str) -> str:
    return doc.replace(ITEM, item_html + ITEM, 1)


def mark_done(doc: str, substrings, date: str):
    """Prepend 'DONE <date>: ' to the inner text of any <h3> matching a substring."""
    marked, missed = [], []
    for sub in substrings:
        sub_l = sub.lower()

        def repl(m, _sub_l=sub_l, _sub=sub):
            inner = m.group(1)
            plain = re.sub(r"<[^>]+>", "", inner)  # strip tags for matching
            if _sub_l not in plain.lower():
                return m.group(0)
            if plain.lstrip().upper().startswith("DONE"):
                return m.group(0)  # already marked
            return f"<h3>DONE {esc(date)}: {inner}</h3>"

        new_doc, n = re.subn(r"<h3>(.*?)</h3>", repl, doc, flags=re.DOTALL)
        # count whether this particular substring actually hit
        if new_doc != doc:
            doc = new_doc
            marked.append(sub)
        else:
            missed.append(sub)
    return doc, marked, missed


def task_card(item: dict, date: str) -> str:
    title = esc(item.get("title", "(untitled task)"))
    meta = item.get("meta", "")  # may contain intentional <code> markup
    body = esc(item.get("body", ""))
    parts = [f'<div class="task">', f'  <h3>{title}</h3>']
    parts.append(f'  <div class="meta"><span class="d">{esc(date)}</span> &middot; {meta}</div>'
                 if meta else f'  <div class="meta"><span class="d">{esc(date)}</span></div>')
    if body:
        parts.append(f'  <p>{body}</p>')
    parts.append('</div>')
    return "\n".join(parts) + "\n"


def li_entry(text: str, date: str, prefix: str = "") -> str:
    body = esc(text)
    pfx = f"{prefix} " if prefix else ""
    return f'<li><span class="d">{esc(date)}</span> {pfx}{body}</li>\n'


def process(wiki_dir, delta, dry_run):
    date = delta.get("date") or ""
    report = []

    def load(cfg):
        path = os.path.join(wiki_dir, cfg["name"])
        if not os.path.isfile(path):
            return None, None
        with open(path, encoding="utf-8") as f:
            return path, f.read()

    def save(path, doc):
        if dry_run:
            return
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(doc)
        os.replace(tmp, path)

    # --- open-tasks.html: DONE marking (in place) + new task cards ---
    cfg = FILES["todos"]
    path, doc = load(cfg)
    if doc is not None:
        orig = doc
        done = delta.get("todos_done") or []
        if done:
            doc, marked, missed = mark_done(doc, done, date)
            if marked:
                report.append(f"  DONE-marked {len(marked)} task(s): {', '.join(marked)}")
            if missed:
                report.append(f"  WARN: no <h3> matched for: {', '.join(missed)}")
        new = delta.get("todos_new") or []
        if new:
            doc = ensure_region(doc, cfg)
            cards = "".join(task_card(t, date) for t in new)
            doc = splice_before_anchor(doc, cards)
            report.append(f"  appended {len(new)} new task card(s)")
        if doc != orig:
            save(path, doc)
        else:
            report.append("  open-tasks.html: no changes")
    else:
        report.append(f"  MISSING: {cfg['name']}")

    # --- completed-by-subject.html: Edit: entries ---
    cfg = FILES["completed"]
    path, doc = load(cfg)
    if doc is not None:
        items = delta.get("completed_new") or []
        if items:
            doc = ensure_region(doc, cfg)
            lis = "".join(li_entry(t, date, prefix="Edit:") for t in items)
            doc = splice_before_anchor(doc, lis)
            save(path, doc)
            report.append(f"  appended {len(items)} Edit: entry(ies) to completed-by-subject.html")
    else:
        report.append(f"  MISSING: {cfg['name']}")

    # --- lessons-learned.html: new lessons ---
    cfg = FILES["lessons"]
    path, doc = load(cfg)
    if doc is not None:
        items = delta.get("lessons_new") or []
        if items:
            doc = ensure_region(doc, cfg)
            lis = "".join(li_entry(t, date) for t in items)
            doc = splice_before_anchor(doc, lis)
            save(path, doc)
            report.append(f"  appended {len(items)} lesson(s) to lessons-learned.html")
    else:
        report.append(f"  MISSING: {cfg['name']}")

    return report


def main():
    ap = argparse.ArgumentParser(description="Incremental updater for the 3 session-log wiki HTMLs.")
    ap.add_argument("--delta", required=True, help="path to delta.json")
    ap.add_argument("--wiki-dir", default=DEFAULT_WIKI_DIR)
    ap.add_argument("--dry-run", action="store_true", help="compute and report, write nothing")
    args = ap.parse_args()

    with open(args.delta, encoding="utf-8") as f:
        delta = json.load(f)
    if not delta.get("date"):
        print("WARN: delta has no 'date'; entries will be undated.", file=sys.stderr)

    report = process(os.path.expanduser(args.wiki_dir), delta, args.dry_run)
    tag = "[dry-run] " if args.dry_run else ""
    print(f"{tag}wiki update:")
    print("\n".join(report) if report else "  (nothing to do)")


if __name__ == "__main__":
    main()
