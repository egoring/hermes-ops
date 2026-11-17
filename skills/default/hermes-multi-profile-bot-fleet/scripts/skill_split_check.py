#!/usr/bin/env python3
"""Gate for splitting an oversized Hermes skill into SKILL.md + references/.

Usage: python3 skill_split_check.py <profile|default> <skill-name> <backup-dir>
  backup-dir holds <skill-name>.tgz made BEFORE the split
  (COPYFILE_DISABLE=1 tar -C <category dir> -czf <backup-dir>/<name>.tgz <name>).

PASS (exit 0) requires:
  - every non-empty line of the original SKILL.md and original references/ exists somewhere in
    the new SKILL.md or references/ (heading level and bullet symbol may change; whitespace ignored;
    separator rows ignored)
  - new SKILL.md <= 24,000 chars (Hermes oversized-body lint threshold)
  - frontmatter (first --- block) unchanged
  - every references/*.md mentioned in SKILL.md; <= 60 reference files
  - every reference file <= 90,000 chars (the 100k cap applies to supporting files too)
Warnings only: a reference pointing at another reference (keep one level deep),
reference > 100 lines without a Contents/목차 heading.
Run it on the untouched skill first: it must report 0 missing lines (only the size FAIL).
"""
import re
import sys
import tarfile
from pathlib import Path

LIMIT = 24_000
REF_LIMIT = 90_000  # headroom under the 100,000-char skill_manage cap


def norm(line: str) -> str:
    s = line.strip()
    s = re.sub(r"^#{1,6}\s+", "", s)
    s = re.sub(r"^[-*]\s+", "- ", s)
    return s


def content_lines(text: str) -> list:
    out = []
    for raw in text.splitlines():
        n = norm(raw)
        if n and not re.fullmatch(r"[-=*_|: ]{3,}", n):
            out.append(n)
    return out


def frontmatter(text: str) -> str:
    m = re.match(r"^---\n.*?\n---\n", text, re.S)
    return m.group(0) if m else ""


def main() -> int:
    profile, name, backup = sys.argv[1], sys.argv[2], Path(sys.argv[3]).expanduser()
    home = Path.home() / ".hermes"
    root = home / "skills" if profile == "default" else home / "profiles" / profile / "skills"
    d = next(p for p in root.rglob(f"{name}/SKILL.md") if ".archive" not in p.parts).parent
    with tarfile.open(backup / f"{name}.tgz") as tf:
        orig = {m.name.split("/", 1)[1]: tf.extractfile(m).read().decode("utf-8", "ignore")
                for m in tf.getmembers()
                if m.isfile() and m.name.endswith(".md") and not m.name.rsplit("/", 1)[-1].startswith("._")}
    skill = (d / "SKILL.md").read_text()
    refs = sorted((d / "references").rglob("*.md")) if (d / "references").exists() else []
    pool = set(content_lines(skill))
    for p in refs:
        pool.update(content_lines(p.read_text(errors="ignore")))
    missing = [(f, l) for f, t in orig.items() for l in content_lines(t) if l not in pool]

    ok = True
    print(f"== {name}: SKILL.md {len(skill):,} chars / {len(skill.splitlines())} lines "
          f"(was {len(orig.get('SKILL.md', '')):,}), references {len(refs)}")
    if len(skill) > LIMIT:
        ok = False
        print(f"FAIL size {len(skill):,} > {LIMIT:,}")
    if frontmatter(skill) != frontmatter(orig.get("SKILL.md", "")):
        ok = False
        print("FAIL frontmatter changed")
    if missing:
        ok = False
        print(f"FAIL {len(missing)} original lines missing, e.g.:")
        for f, l in missing[:15]:
            print(f"   [{f}] {l[:140]}")
    unlinked = [p.relative_to(d).as_posix() for p in refs
                if p.relative_to(d).as_posix() not in skill and p.name not in skill]
    if unlinked:
        ok = False
        print(f"FAIL references not mentioned in SKILL.md: {unlinked}")
    if len(refs) > 60:
        ok = False
        print(f"FAIL {len(refs)} reference files > 60")
    # skill_manage's 100k cap also applies to supporting files: a reference near it blocks the next append
    for p in refs:
        n = len(p.read_text(errors="ignore"))
        if n > REF_LIMIT:
            ok = False
            print(f"FAIL {p.name}: {n:,} chars > {REF_LIMIT:,} (split it sideways into sibling topic files)")
    for p in refs:
        t = p.read_text(errors="ignore")
        if re.search(r"references/[\w.-]+\.md", t):
            print(f"WARN {p.name}: points at another reference")
        if len(t.splitlines()) > 100 and not re.search(r"(?im)^#+\s*(contents|목차)", t):
            print(f"WARN {p.name}: {len(t.splitlines())} lines, no Contents heading")
    print("PASS" if ok else "NOT PASS")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
