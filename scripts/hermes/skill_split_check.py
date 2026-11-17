#!/usr/bin/env python3
"""스킬 분할 검사: 원본(백업 tgz)의 모든 내용 줄이 새 SKILL.md 또는 references/ 어딘가에 남아 있는지 + 크기·링크 규칙.

사용: python3 skill_split_check.py <스킬 이름> [--profile reviewer-bot] [--backup <스킬>.tgz 가 있는 폴더]
  (분할 전에 `COPYFILE_DISABLE=1 tar -C <스킬 상위 폴더> -czf <백업폴더>/<스킬>.tgz <스킬>` 로 백업해 둔다)
통과 조건 (exit 0):
  - 누락 줄 0 (빈 줄·구분선 제외. 제목은 '#' 개수 무시하고 비교. 앞뒤 공백 무시)
  - SKILL.md 전체 24,000자 이하
  - frontmatter(첫 '---' 블록) 원본과 동일
  - references/ 의 모든 파일이 SKILL.md 에서 경로로 언급됨
  - references/ 파일 수 60 이하
경고만: 참조 파일이 다른 참조 파일을 가리킴(한 단계 규칙), 100줄 넘는 참조 파일에 목차 없음
"""
import re
import sys
import tarfile
from pathlib import Path

_a = sys.argv[1:]
_PROFILE = _a[_a.index("--profile") + 1] if "--profile" in _a else "reviewer-bot"
R = Path.home() / ".hermes" / ("skills" if _PROFILE == "default" else f"profiles/{_PROFILE}/skills")
B = Path(_a[_a.index("--backup") + 1]).expanduser() if "--backup" in _a else Path.home() / ".hermes/backups/20261117_skill_split"
LIMIT = 24_000


def norm(line: str) -> str:
    s = line.strip()
    s = re.sub(r"^#{1,6}\s+", "", s)          # 제목 수준 변경 허용
    s = re.sub(r"^[-*]\s+", "- ", s)          # 글머리표 기호 통일
    return s


def content_lines(text: str) -> list[str]:
    out = []
    for l in text.splitlines():
        n = norm(l)
        if not n or re.fullmatch(r"[-=*_|: ]{3,}", n):
            continue
        out.append(n)
    return out


def frontmatter(text: str) -> str:
    m = re.match(r"^---\n.*?\n---\n", text, re.S)
    return m.group(0) if m else ""


def main() -> int:
    name = sys.argv[1]
    d = next(R.rglob(f"{name}/SKILL.md")).parent
    with tarfile.open(B / f"{name}.tgz") as tf:
        orig = {m.name.split("/", 1)[1]: tf.extractfile(m).read().decode("utf-8", "ignore")
                for m in tf.getmembers() if m.isfile() and m.name.endswith(".md") and not m.name.rsplit("/", 1)[-1].startswith("._")}
    new_skill = (d / "SKILL.md").read_text()
    refs = sorted(p for p in (d / "references").rglob("*.md")) if (d / "references").exists() else []
    pool = set()
    others = [p for p in d.rglob("*.md") if p.name != "SKILL.md" and not p.name.startswith("._")]  # templates/ 등도 포함
    for t in [new_skill] + [p.read_text(errors="ignore") for p in others]:
        pool.update(content_lines(t))
    # 원본 SKILL.md 와 원본 references 모두 보존돼야 함
    missing = []
    for fname, t in orig.items():
        for l in content_lines(t):
            if l not in pool:
                missing.append((fname, l))
    ok = True
    print(f"== {name}")
    print(f"SKILL.md {len(new_skill):,}자 / {len(new_skill.splitlines())}줄 (원본 {len(orig.get('SKILL.md','')):,}자), references {len(refs)}개")
    if len(new_skill) > LIMIT:
        ok = False
        print(f"FAIL 크기 {len(new_skill):,} > {LIMIT:,}")
    if frontmatter(new_skill) != frontmatter(orig.get("SKILL.md", "")):
        ok = False
        print("FAIL frontmatter 바뀜")
    if missing:
        ok = False
        print(f"FAIL 누락 줄 {len(missing)}개 (예시):")
        for f, l in missing[:15]:
            print(f"   [{f}] {l[:140]}")
    unlinked = [p.relative_to(d).as_posix() for p in refs if p.relative_to(d).as_posix() not in new_skill and p.name not in new_skill]
    if unlinked:
        ok = False
        print(f"FAIL SKILL.md 가 언급하지 않는 참조 파일: {unlinked}")
    if len(refs) > 60:
        ok = False
        print(f"FAIL 참조 파일 {len(refs)}개 > 60")
    for p in refs:
        t = p.read_text(errors="ignore")
        if re.search(r"references/[\w.-]+\.md", t):
            print(f"WARN {p.name}: 다른 참조 파일을 가리킴")
        if len(t.splitlines()) > 100 and not re.search(r"(?im)^#+\s*(contents|목차)", t):
            print(f"WARN {p.name}: {len(t.splitlines())}줄인데 목차 없음")
    print("PASS" if ok else "NOT PASS")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
