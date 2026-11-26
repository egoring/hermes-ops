#!/opt/anaconda3/bin/python3
"""cc_kit 훅(조건 B). Claude Code 가 stdin 으로 JSON 을 준다. 모든 호출을 로그 파일에 한 줄(JSON)씩 남긴다.

  kit_hook.py pre   --ws WS --state DIR --log FILE        PreToolUse(Edit|Write|MultiEdit|NotebookEdit|Bash)
  kit_hook.py stop  --ws WS --state DIR --log FILE        Stop
  kit_hook.py event --ws WS --state DIR --log FILE        기록만(InstructionsLoaded·SessionStart 등)

pre : 보호 파일(<ws>/docs/handoff/protected.txt 의 glob, 줄마다 하나)을 고치려는 도구 호출 → exit 2 + stderr 이유.
      Bash 는 리다이렉션(>, >>, tee) 대상과 파일을 바꾸는 명령(sed -i, mv, cp, rm, truncate, git checkout/restore …)의
      인자에 보호 파일이 나오면 막는다(휴리스틱 — 최종 방어선은 stop 의 보호 파일 무결성 검사).
stop: <ws>/docs/handoff/acceptance.json 의 합격 명령(카드의 `# expect:` 줄)을 돌리고, 보호 파일이 바뀌었는지(state/protected.sha256)
      본다. 실패하면 {"decision":"block","reason":…} 로 멈춤을 막는다. 최대 3번(state/stop_blocks). stop_hook_active 가 참이고
      실패 내용이 지난번 막을 때와 같으면(진전 없음) 멈춤을 허용한다(무한 반복 방지).
합격 명령은 macOS sandbox-exec 로 쓰기를 작업 폴더·state/tmp 로 가둔 채 돌린다(훅은 Claude Code 샌드박스 밖에서 돈다).
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

MAX_BLOCKS = 3
CHECK_TIMEOUT = 300
SANDBOX_EXEC = "/usr/bin/sandbox-exec"


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def log(path: Path, rec: dict) -> None:
    rec = {"ts": now(), **rec}
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_protected(ws: Path) -> list[str]:
    p = ws / "docs" / "handoff" / "protected.txt"
    if not p.is_file():
        return []
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            out.append(ln)
    return out


def rel_in_ws(ws: Path, path: str, cwd: str | None) -> str | None:
    """path 를 작업 폴더 기준 posix 상대 경로로. 작업 폴더 밖이면 None."""
    if not path:
        return None
    p = Path(os.path.expanduser(path))
    if not p.is_absolute():
        p = Path(cwd or ws) / p
    rp = os.path.realpath(p)
    rws = os.path.realpath(ws)
    if rp == rws:
        return "."
    if not rp.startswith(rws + os.sep):
        return None
    return Path(os.path.relpath(rp, rws)).as_posix()


def is_protected(rel: str | None, pats: list[str]) -> str | None:
    if rel is None:
        return None
    for pat in pats:
        if pat.endswith("/**"):
            base = pat[:-3]
            if rel == base or rel.startswith(base + "/"):
                return pat
        elif fnmatch.fnmatchcase(rel, pat) or rel == pat.rstrip("/"):
            return pat
    return None


REDIR_RE = re.compile(r"(?:^|[^0-9&<>])(?:[0-9]?>>?|&>>?)\s*(?!&)([^\s;|&<>]+)")
TEE_RE = re.compile(r"\btee\s+(?:-[a-zA-Z]+\s+)*([^\s;|&<>]+)")
DEST_LAST = {"cp", "install", "ln", "rsync"}                      # 마지막 인자만 바뀐다(원본은 읽기)
ALL_ARGS = {"mv", "rm", "truncate", "touch", "chmod", "chown", "unlink", "shred", "patch", "dd"}
GIT_MUT = {"checkout", "restore", "rm", "mv", "apply", "stash", "reset", "clean"}
PYWRITE = re.compile(r"(open\([^)]*['\"][wax+]|write_text|write_bytes|shutil\.|os\.remove|os\.unlink|\.unlink\(|os\.rename|"
                     r"os\.replace|json\.dump\()")
SEG_SPLIT = re.compile(r"&&|\|\||[;|\n]")


def _words(seg: str) -> list[str]:
    try:
        w = shlex.split(seg, posix=True)
    except ValueError:
        w = seg.split()
    while w and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w[0]):  # VAR=값 앞붙이기
        w = w[1:]
    return w


def bash_targets(cmd: str) -> list[tuple[str, str]]:
    """(종류, 경로 글자) 목록: 리다이렉션·tee 대상 + 파일을 바꾸는 명령의 대상 인자(cp 류는 마지막 인자만)."""
    out = [("redirect", m.group(1)) for m in REDIR_RE.finditer(cmd)]
    out += [("tee", m.group(1)) for m in TEE_RE.finditer(cmd)]
    sub = ""  # 앞 조각의 `cd X` 를 따라간다(작업 폴더 기준 상대)
    for seg in SEG_SPLIT.split(cmd):
        w = _words(seg.strip().lstrip("("))
        if not w:
            continue
        head = os.path.basename(w[0])
        if head == "cd" and len(w) > 1:
            sub = w[1] if w[1].startswith("/") else os.path.join(sub, w[1])
            continue
        args = [os.path.join(sub, x) if sub and not x.startswith(("/", "~")) else x for x in w[1:] if not x.startswith("-")]
        if head in DEST_LAST and args:
            out.append((head, args[-1]))
        elif head in ALL_ARGS:
            out += [(head, x.split("=", 1)[-1]) for x in args]
        elif head in ("sed", "perl") and any(x.startswith("-i") or x == "--in-place" for x in w[1:]):
            out += [(head + " -i", x) for x in args]
        elif head == "git" and len(w) > 1 and w[1] in GIT_MUT:
            out += [("git " + w[1], x) for x in args[1:]]
        elif head.startswith("python") and PYWRITE.search(seg):
            for x in w[1:]:
                out += [("python-write", p) for p in re.split(r"[\"'(),=\s]+", x) if p and ("/" in p or "." in p)]
    return [(k, v.strip("\"'")) for k, v in out if v and v not in ("/dev/null", "/dev/stderr", "/dev/stdout")]


def cmd_pre(a, data: dict) -> int:
    ws = Path(a.ws)
    pats = load_protected(ws)
    tool = data.get("tool_name")
    ti = data.get("tool_input") or {}
    cwd = data.get("cwd")
    rec = {"event": "PreToolUse", "tool": tool, "effort": (data.get("effort") or {}).get("level"),
           "permission_mode": data.get("permission_mode")}
    hits: list[tuple[str, str, str]] = []
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        target = ti.get("file_path") or ti.get("notebook_path") or ""
        rec["target"] = target
        rel = rel_in_ws(ws, target, cwd)
        pat = is_protected(rel, pats)
        if pat:
            hits.append(("file_tool", rel, pat))
    elif tool == "Bash":
        cmd = str(ti.get("command") or "")
        rec["command"] = cmd[:400]
        for kind, t in bash_targets(cmd):
            rel = rel_in_ws(ws, t, cwd)
            pat = is_protected(rel, pats)
            if pat:
                hits.append((kind, rel, pat))
    if hits:
        reason = ("[cc_kit 보호 파일 훅] 이 호출은 바꾸면 안 되는 파일을 건드린다: "
                  + ", ".join(f"{r} (규칙 {p}, {k})" for k, r, p in hits)
                  + ". docs/handoff/protected.txt 의 파일은 카드 범위상 수정 금지다. 다른 방법으로 진행하라(읽기는 된다).")
        log(Path(a.log), {**rec, "decision": "block", "hits": hits})
        print(reason, file=sys.stderr)
        return 2
    log(Path(a.log), {**rec, "decision": "allow"})
    return 0


def sha_map(ws: Path, pats: list[str]) -> dict[str, str]:
    out = {}
    for p in sorted(ws.rglob("*")):
        if not p.is_file() or ".git" in p.parts:
            continue
        rel = p.relative_to(ws).as_posix()
        if is_protected(rel, pats):
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def sandbox_profile(ws: Path, tmp: Path) -> str:
    allow = [os.path.realpath(ws), os.path.realpath(tmp), "/private/var/folders", "/private/tmp/cc_kit_null"]
    subs = " ".join(f'(subpath "{x}")' for x in allow)
    return f'(version 1)(allow default)(deny file-write*)(allow file-write* {subs} (literal "/dev/null") (regex #"^/dev/tty"))'


def run_checks(ws: Path, state: Path) -> list[dict]:
    acc = json.loads((ws / "docs" / "handoff" / "acceptance.json").read_text(encoding="utf-8"))
    tmp = state / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    env = {"PATH": "/opt/anaconda3/bin:/usr/bin:/bin:/usr/sbin:/sbin", "HOME": os.environ.get("HOME", ""), "LANG": "en_US.UTF-8",
           "LC_ALL": "en_US.UTF-8", "GIT_CEILING_DIRECTORIES": str(ws.parent), "GIT_CONFIG_NOSYSTEM": "1",
           "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": str(tmp)}
    out = []
    use_sb = os.path.exists(SANDBOX_EXEC)
    for k in acc:
        argv = ["/bin/bash", "-c", k["cmd"]]
        if use_sb:
            argv = [SANDBOX_EXEC, "-p", sandbox_profile(ws, tmp)] + argv
        t0 = time.monotonic()
        try:
            p = subprocess.run(argv, cwd=str(ws), env=env, capture_output=True, timeout=CHECK_TIMEOUT, stdin=subprocess.DEVNULL)
            rc, tail = p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")[-1500:]
        except subprocess.TimeoutExpired:
            rc, tail = None, "(timeout)"
        out.append({"cmd": k["cmd"], "expect": k["expect"], "rc": rc, "pass": rc == k["expect"], "tail": tail,
                    "secs": round(time.monotonic() - t0, 2), "sandboxed": use_sb})
    return out


def cmd_stop(a, data: dict) -> int:
    ws, state = Path(a.ws), Path(a.state)
    state.mkdir(parents=True, exist_ok=True)
    cnt_f, sig_f = state / "stop_blocks", state / "last_block_sig"
    n = int(cnt_f.read_text().strip() or 0) if cnt_f.is_file() else 0
    active = bool(data.get("stop_hook_active"))
    checks = run_checks(ws, state)
    pats = load_protected(ws)
    base = json.loads((state / "protected.sha256").read_text(encoding="utf-8")) if (state / "protected.sha256").is_file() else {}
    cur = sha_map(ws, pats)
    changed = sorted(k for k in set(base) | set(cur) if base.get(k) != cur.get(k))
    failed = [c for c in checks if not c["pass"]]
    rec = {"event": "Stop", "stop_hook_active": active, "blocks_before": n, "effort": (data.get("effort") or {}).get("level"),
           "checks": [{"cmd": c["cmd"][:120], "rc": c["rc"], "expect": c["expect"], "pass": c["pass"], "secs": c["secs"]} for c in checks],
           "protected_changed": changed}
    if not failed and not changed:
        log(Path(a.log), {**rec, "decision": "allow", "why": "all_pass"})
        return 0
    sig = hashlib.sha256(json.dumps([[c["cmd"], c["rc"], c["tail"][-400:]] for c in failed] + changed, ensure_ascii=False).encode()).hexdigest()
    if n >= MAX_BLOCKS:
        log(Path(a.log), {**rec, "decision": "allow", "why": f"cap_{MAX_BLOCKS}"})
        return 0
    if active and sig_f.is_file() and sig_f.read_text().strip() == sig:
        log(Path(a.log), {**rec, "decision": "allow", "why": "stop_hook_active_no_progress"})
        return 0
    n += 1
    cnt_f.write_text(str(n))
    sig_f.write_text(sig)
    parts = [f"[cc_kit Stop 훅 {n}/{MAX_BLOCKS}] 합격 명령이 아직 통과하지 않았다. 멈추지 말고 고쳐라(README 가 기준)."]
    for c in failed:
        parts.append(f"\n$ {c['cmd']}\n  기대 종료 코드 {c['expect']}, 실제 {c['rc']}\n{c['tail'][-1200:]}")
    if changed:
        parts.append("\n보호 파일이 바뀌었다(원래대로 되돌려라): " + ", ".join(changed))
    reason = "\n".join(parts)[:6000]
    log(Path(a.log), {**rec, "decision": "block", "n": n})
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return 0


def cmd_event(a, data: dict) -> int:
    keep = {k: data.get(k) for k in ("hook_event_name", "file_path", "memory_type", "load_reason", "source", "model") if k in data}
    log(Path(a.log), {"event": data.get("hook_event_name"), **keep})
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("pre", "stop", "event"))
    ap.add_argument("--ws", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--log", required=True)
    a = ap.parse_args()
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except ValueError:
        data = {}
    try:
        return {"pre": cmd_pre, "stop": cmd_stop, "event": cmd_event}[a.mode](a, data)
    except Exception as e:  # noqa: BLE001 - 훅 오류도 기록한다
        log(Path(a.log), {"event": a.mode, "decision": "hook_error", "error": f"{type(e).__name__}: {e}"[:300]})
        if a.mode == "pre":
            print(f"[cc_kit 훅 오류] {type(e).__name__}: {e}", file=sys.stderr)
            return 2  # 보호 훅은 실패하면 막는 쪽(fail closed)
        return 0


if __name__ == "__main__":
    sys.exit(main())
