#!/usr/bin/env python3
"""운영용 자작 스킬과 봇 SOUL.md를 ~/.hermes 에서 복사하고, 저장소 전체를 개인정보 검사한다.

원본은 항상 ~/.hermes 쪽이다 (Hermes가 스킬을 계속 고치므로). 저장소 쪽은 스냅샷.
사용:
  python3 scripts/sync_skills.py          # 복사 + 검사
  python3 scripts/sync_skills.py --check  # 검사만 (복사 안 함)
검사에 걸리면 exit 1 → 커밋/푸시하지 말고 원본을 고치거나 PII_ALLOW에 사유와 함께 추가.
"""
import re
import shutil
import sys
from pathlib import Path

HERMES = Path.home() / ".hermes"
REPO = Path(__file__).resolve().parent.parent
DEST = REPO / "skills"

# (저장소 안 경로, 원본 경로). 특정 프로젝트 전용 스킬은 넣지 않는다.
SKILLS = [
    ("default/hermes-multi-profile-bot-fleet", "skills/devops/hermes-multi-profile-bot-fleet"),
    ("reviewer-bot/kanban-verified-analysis", "profiles/reviewer-bot/skills/software-development/kanban-verified-analysis"),
    ("reviewer-bot/kanban-orchestration", "profiles/reviewer-bot/skills/software-development/kanban-orchestration"),
    ("reviewer-bot/kanban-work-delegation", "profiles/reviewer-bot/skills/software-development/kanban-work-delegation"),
    ("reviewer-bot/kanban-task-orchestration", "profiles/reviewer-bot/skills/autonomous-ai-agents/kanban-task-orchestration"),
    ("coder-bot/shared-thread-scope-discipline", "profiles/coder-bot/skills/autonomous-ai-agents/shared-thread-scope-discipline"),
]

# 올리면 안 되는 패턴: Discord/긴 숫자 ID, 절대 홈 경로, 키·토큰 형태
# 개인 계정명 같은 추가 금지어는 scripts/pii_local.txt (한 줄에 하나, git 제외)에 둔다.
_LOCAL = Path(__file__).with_name("pii_local.txt")
_EXTRA = [re.escape(w.strip()) for w in (_LOCAL.read_text().splitlines() if _LOCAL.exists() else []) if w.strip()]
PII = re.compile(
    r"\b\d{17,20}\b|/Users/[A-Za-z0-9_.-]+"
    r"|sk-ant-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{20,}|xox[bp]-|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|[MN][A-Za-z0-9_-]{23,25}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}"
    + "".join("|" + w for w in _EXTRA),
    re.I,
)
# SOUL.md: 복사할 때 개인 ID를 자리표시자로 바꾼다 (원본은 그대로)
SOULS = ["reviewer-bot", "coder-bot", "helper-bot"]
SOUL_DEST = REPO / "souls"
_REDACT_LOCAL = Path(__file__).with_name("redact_local.txt")  # "원문<TAB>치환" 한 줄씩, git 제외


def _redact(text: str) -> str:
    text = re.sub(r"<@\d{17,20}>", "<@USER_ID>", text)
    text = re.sub(r"\b\d{17,20}\b", "<ID>", text)
    if _REDACT_LOCAL.exists():
        for line in _REDACT_LOCAL.read_text().splitlines():
            if "\t" in line:
                a, b = line.split("\t", 1)
                text = text.replace(a, b)
    return text


# 공개 저장소용: 진행 중인 프로젝트 내용이 드러나는 파일은 안내문으로 대체하고, 특정 문구는 일반화한다.
# 원본(~/.hermes)은 그대로 둔다. 프로젝트 종료 후 WITHHOLD에서 빼면 원문이 올라간다.
WITHHOLD = {
    "reviewer-bot/kanban-work-delegation/references/measuring-what-matters.md":
        "진행 중인 프로젝트의 분석 사례가 많이 들어 있어 프로젝트 종료 후 공개한다.",
}
# 공개용 문구 치환 목록은 scripts/public_subs_local.txt (git 제외)에 둔다 — 원문을 저장소에 적지 않기 위해.
# 형식: 한 줄에 "원문<TAB>치환", 줄바꿈은 \n 으로 적는다.
_SUBS_LOCAL = Path(__file__).with_name("public_subs_local.txt")
PUBLIC_SUBS = [
    tuple(part.replace("\\n", "\n") for part in line.split("\t", 1))
    for line in (_SUBS_LOCAL.read_text().splitlines() if _SUBS_LOCAL.exists() else [])
    if "\t" in line
]
_STUB = "# (비공개 보류)\n\n{reason}\n원본: `~/.hermes/profiles/…/{rel}`\n"

IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "*.bak*", ".*")


def copy() -> None:
    if DEST.exists():
        shutil.rmtree(DEST)  # 원본에서 지운 파일이 남지 않게 매번 새로 만든다
    for rel, src in SKILLS:
        s = HERMES / src
        if not (s / "SKILL.md").exists():
            print(f"!! 원본 없음: {s}")
            sys.exit(1)
        shutil.copytree(s, DEST / rel, ignore=IGNORE)
    for rel, reason in WITHHOLD.items():
        f = DEST / rel
        if f.exists():
            f.write_text(_STUB.format(reason=reason, rel=rel.split("/", 1)[1]))
    for f in DEST.rglob("*.md"):
        t = f.read_text()
        for a, b in PUBLIC_SUBS:
            t = t.replace(a, b)
        f.write_text(t)
    print(f"복사: {len(SKILLS)}개 스킬 → {DEST.relative_to(REPO)}/ (보류 {len(WITHHOLD)}개)")
    SOUL_DEST.mkdir(exist_ok=True)
    for bot in SOULS:
        src = HERMES / "profiles" / bot / "SOUL.md"
        (SOUL_DEST / f"{bot}.md").write_text(_redact(src.read_text()))
    print(f"복사: SOUL {len(SOULS)}개 → souls/ (ID 치환)")


_SKIP = {Path(__file__).resolve(), _LOCAL.resolve(), _REDACT_LOCAL.resolve(), _SUBS_LOCAL.resolve()}


def _files():
    for f in sorted(REPO.rglob("*")):
        if f.is_file() and ".git" not in f.relative_to(REPO).parts and f.resolve() not in _SKIP \
                and f.name != "변경이력.md":  # 로컬 전용(.gitignore)
            yield f


def check() -> int:
    hits = 0
    for f in _files():
        for i, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
            for m in PII.finditer(line):
                hits += 1
                print(f"PII {f.relative_to(REPO)}:{i}: {m.group(0)}")
    n = sum(1 for _ in _files())
    print(f"검사: 파일 {n}개, 걸린 것 {hits}건")
    return 1 if hits else 0


if __name__ == "__main__":
    if "--check" not in sys.argv:
        copy()
    sys.exit(check())
