#!/opt/anaconda3/bin/python3
"""cc_kit 실행기: 'Hermes 설계 → Claude Code 구현' 키트 A/B 시행(헤드리스 Claude Code, 구독 로그인).

  cc_run.py design --tasks v3_07_run_compare[,..|all]       reviewer-bot 한 번 호출로 설계 문서를 만든다(과제별 캐시)
  cc_run.py run --run-id ID [--tasks all] [--conditions A,B] [--reps 1] [--seed S] [--dry-run] [--keep]
  cc_run.py probe-env                                       시행 설정(샌드박스·권한·인증) 확인용 설정 파일만 찍는다

조건 A: 프롬프트 = effort 실험 하네스의 build_prompt_synthetic(카드 제목+본문+고정 안내) 그대로, 작업 폴더 = repo/ 사본(git init + add, 커밋 0).
조건 B: A + docs/handoff/{current.md(reviewer-bot 설계), protected.txt, acceptance.json} + CLAUDE.md(@docs/handoff/current.md 가져오기)
        + .claude/settings.json 훅(PreToolUse 보호 파일 차단, Stop 합격 명령 확인 최대 3번, 기록 훅).
공통: claude-sonnet-5-5 · effort high · 샌드박스(쓰기 = 작업 폴더·시행 tmp, 네트워크 0) · acceptEdits + 묻기 없음(--permission-prompts none)
      · 사용자 설정·플러그인·MCP·전역 CLAUDE.md 제외(--setting-sources project,local · --strict-mcp-config · claudeMdExcludes)
      · ~/.hermes·~/.claude 읽기 거부 · ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN/HERMES_EVAL_ANTHROPIC_API_KEY 없는 환경.
채점: effort 하네스와 같은 함수(effort_common.run_checks + taskset.run_hidden), clean = 보이는 합격 명령 전부 + 숨은 rate 1.0.
작업 폴더는 /private/tmp/cc_kit/<run>/ (~/.hermes 밖) — 숨은 시험은 에이전트가 끝난 뒤에만 시행 폴더에 복사된다.
effort 실험 폴더(~/.hermes/evals/effort)는 읽기만 한다(바이트코드도 쓰지 않는다).
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
EFFORT_BIN = Path.home() / ".hermes" / "evals" / "effort" / "bin"
sys.path.insert(0, str(EFFORT_BIN))
import effort_common as C  # noqa: E402
import effort_run as ER  # noqa: E402  (build_prompt_synthetic·SUFFIX 를 그대로 쓴다)
import taskset as TS  # noqa: E402

KIT = Path(__file__).resolve().parent.parent          # ~/.hermes/evals/cc_kit
HOOK_SRC = KIT / "bin" / "kit_hook.py"
TEMPLATES = KIT / "kit" / "templates"
DESIGNS = KIT / "designs"
RESULTS = KIT / "results"
TRIAL_BASE = Path("/private/tmp/cc_kit")
PY = "/opt/anaconda3/bin/python3"
MODEL = "claude-sonnet-5-5"
EFFORT = os.environ.get("CC_KIT_EFFORT", "high")  # 실행 때 CC_KIT_EFFORT=medium 으로 바꿀 수 있다(11-26)
assert EFFORT in ("low", "medium", "high", "xhigh", "max"), EFFORT
TIMEOUT_S = 1500
HIDDEN_TIMEOUT = 300
CHECK_TIMEOUT = 600
SECRET_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "HERMES_EVAL_ANTHROPIC_API_KEY")
KIT_FILES = ("CLAUDE.md", ".claude/**", "docs/handoff/**")
HERMES_MARKS = (".hermes", "/evals/effort", "hidden_run", "test_hidden_")
DESIGN_SECTIONS = ("목표", "안 할 것", "바꿀 파일", "README와 코드 대조 체크리스트", "수용 기준", "합격 명령")


def claude_bin() -> str:
    cands = sorted(glob.glob(str(Path.home() / ".vscode/extensions/anthropic.claude-code-*-darwin-arm64/resources/native-binary/claude")),
                   key=lambda p: [int(x) for x in re.findall(r"claude-code-(\d+)\.(\d+)\.(\d+)", p)[0]])
    if not cands:
        raise SystemExit("claude 바이너리를 찾지 못했다")
    return cands[-1]


def clean_env(extra: dict | None = None) -> dict:
    keep = ("HOME", "USER", "LOGNAME", "SHELL", "LANG", "TERM")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env["PATH"] = "/opt/anaconda3/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    env["LANG"] = env.get("LANG") or "en_US.UTF-8"
    env["DISABLE_AUTOUPDATER"] = "1"
    env.update(extra or {})
    for k in SECRET_ENV:
        env.pop(k, None)
    assert not any(k in env for k in SECRET_ENV)
    return env


# ---------------------------------------------------------------- 과제·보호 목록


def load_tasks(sel: str) -> list[dict]:
    tasks = TS.load_tasks(taskset="synthetic_v3")
    if sel in ("all", "", None):
        return tasks
    want = [s.strip() for s in sel.split(",") if s.strip()]
    out = [t for t in tasks if t["id"] in want or any(t["id"].startswith(w) for w in want)]
    if not out:
        raise SystemExit(f"과제 없음: {sel}")
    return out


def protected_from_card(card: dict) -> list[str]:
    """카드 '## 범위' 절에서 '바꾸지 않는다' 줄의 백틱 경로 → glob(폴더면 dir/**). 카드 문장만 쓴다(숨은 시험·정답 안 봄)."""
    body = card["body"]
    m = re.search(r"^## 범위\s*$(.*?)(?=^## )", body, flags=re.M | re.S)
    sec = m.group(1) if m else ""
    out = []
    for ln in sec.splitlines():
        if "바꾸지 않는다" not in ln:
            continue
        for p in re.findall(r"`([^`]+)`", ln):
            p = p.strip()
            if " " in p or p.startswith("-") or not ("/" in p or "." in p):
                continue
            out.append(p.rstrip("/") + "/**" if p.endswith("/") else p)
    return out


def sha_protected(ws: Path, pats: list[str]) -> dict[str, str]:
    sys.path.insert(0, str(HOOK_SRC.parent))
    import kit_hook as KH  # noqa: PLC0415
    out = {}
    for p in sorted(Path(ws).rglob("*")):
        if p.is_file() and ".git" not in p.parts:
            rel = p.relative_to(ws).as_posix()
            if KH.is_protected(rel, pats):
                out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


# ---------------------------------------------------------------- 설계 문서 (reviewer-bot)

DESIGN_PROMPT = """너는 설계 담당(reviewer)이다. 구현은 다른 에이전트(Claude Code)가 한다. 아래 카드와 현재 폴더(작업 폴더 사본)의 코드·README·tests 만 읽고,
구현자가 그대로 따라 할 **설계 문서**를 한국어 마크다운으로 써라.

규칙:
- 파일을 만들거나 고치지 않는다. 읽기만 한다. 현재 폴더 밖은 읽지 않는다.
- 최종 답 = 설계 문서 본문만(앞뒤 인사·설명 없이). 첫 줄은 `# 설계: <한 줄 제목>`.
- 반드시 아래 절을 이 이름·순서로 둔다:
  ## 목표
  ## 안 할 것
  ## 바꿀 파일 / 바꾸면 안 되는 파일
  ## README와 코드 대조 체크리스트
     (README 의 규칙을 문장 단위로 훑어 코드와 하나씩 대조한 표: README 문장 | 코드 위치(파일:함수) | 지금 동작 | 맞음/어긋남 | 고칠 내용.
      증상과 무관해 보여도 README 와 어긋나는 곳은 모두 찾아 '어긋남'으로 적고 고치게 한다. 공개 시험이 없는 동작도 포함.
      직접 확인하지 못한 항목은 '확인 필요'로 적는다 — 추측으로 맞음이라고 쓰지 않는다.)
  ## 요구사항별 수용 기준
     (카드 요구사항 번호마다: 바꿀 코드 위치, 더할 시험 이름, 관찰 가능한 기대 결과)
  ## 합격 명령
     (카드의 합격 명령을 그대로, 그리고 `/opt/anaconda3/bin/python3 -m pytest -q tests`)

=== 카드 ===
{card}
"""


def reviewer_tool_calls(sid: str | None) -> dict:
    """reviewer-bot state.db(읽기 전용)에서 이 세션의 도구 호출 경로를 보고 평가 폴더 접근 표시를 센다."""
    import sqlite3  # noqa: PLC0415
    db = Path.home() / ".hermes" / "profiles" / "reviewer-bot" / "state.db"
    if not sid or not db.is_file():
        return {"error": "no session/db"}
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        calls = []
        for (tc,) in con.execute("select tool_calls from messages where session_id=? and role='assistant'", (sid,)):
            for c in json.loads(tc or "[]"):
                f = c.get("function") or {}
                calls.append([f.get("name"), (f.get("arguments") or "")[:200]])
        s = con.execute("select model, estimated_cost_usd, api_call_count from sessions where id=?", (sid,)).fetchone()
    finally:
        con.close()
    blob = json.dumps(calls, ensure_ascii=False)
    return {"n": len(calls), "calls": calls, "marks": [m for m in (".hermes", "/hidden", "solution/", "wrong/") if m in blob],
            "model": s[0] if s else None, "hermes_estimated_cost_usd": s[1] if s else None, "api_calls": s[2] if s else None}


def run_design(task: dict, force: bool = False) -> dict:
    out = DESIGNS / task["id"]
    if (out / "current.md").is_file() and not force:
        return json.loads((out / "meta.json").read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    root = TRIAL_BASE / "design" / f"{task['id']}-{os.urandom(3).hex()}"
    copy = TS.materialize(task, root / task["ws_name"])
    before = {p.relative_to(copy).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in copy.rglob("*") if p.is_file()}
    qf = root / "query.md"
    qf.write_text(DESIGN_PROMPT.format(card=f"# {task['title']}\n\n{task['body']}"), encoding="utf-8")
    hermes = shutil.which("hermes") or str(Path.home() / ".hermes/hermes-agent/.hermes/bin/hermes")
    argv = [hermes, "-p", "reviewer-bot", "chat", "-Q", "--query-file", str(qf), "--in", str(copy), "--source", "tool",
            "-t", "file", "--max-turns", "60", "--run-budget", "900"]
    t0 = time.monotonic()
    p = subprocess.run(argv, cwd=str(copy), env=clean_env({"HOME": str(Path.home())}), capture_output=True, text=True, timeout=1200,
                       stdin=subprocess.DEVNULL)
    wall = round(time.monotonic() - t0, 1)
    (out / "reviewer_stdout.txt").write_text(p.stdout, encoding="utf-8")
    (out / "reviewer_stderr.txt").write_text(p.stderr[-20000:], encoding="utf-8")
    text = p.stdout
    i = text.find("# 설계")
    doc = text[i:] if i >= 0 else text
    doc = re.split(r"\n(?:session_id|Session:|Resume this session)", doc)[0].rstrip() + "\n"
    after = {p_.relative_to(copy).as_posix(): hashlib.sha256(p_.read_bytes()).hexdigest() for p_ in copy.rglob("*") if p_.is_file()}
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k) and "__pycache__" not in k and ".pytest_cache" not in k)
    prot = protected_from_card(task)
    (out / "current.md").write_text(doc, encoding="utf-8")
    (out / "protected.txt").write_text(
        "# 카드 '범위' 절의 '바꾸지 않는다' 에서 기계적으로 뽑은 목록 + 키트 파일. 한 줄에 glob 하나(작업 폴더 기준).\n"
        + "\n".join(prot + list(KIT_FILES)) + "\n", encoding="utf-8")
    (out / "acceptance.json").write_text(json.dumps([{"cmd": a["cmd"], "expect": a["expect"]} for a in task["acceptance"]],
                                                    ensure_ascii=False, indent=1), encoding="utf-8")
    sid = (re.findall(r"session_id:\s*(\S+)", p.stderr + p.stdout) or [None])[-1]
    meta = {"task": task["id"], "rc": p.returncode, "wall_s": wall, "chars": len(doc), "session_id": sid,
            "reviewer_tool_calls": reviewer_tool_calls(sid),
            "sections_present": {s: (s in doc) for s in DESIGN_SECTIONS}, "copy_changed_files": changed,
            "protected_from_card": prot, "made_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "eval_dir_marks_in_stdout": [m for m in (".hermes/evals", "hidden/", "solution/") if m in p.stdout]}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.rmtree(root, ignore_errors=True)
    return meta


# ---------------------------------------------------------------- 시행 준비


def base_settings(trial: Path) -> dict:
    """A·B 공통(--settings = flag 출처). 작업 폴더 밖에 둔다."""
    home = str(Path.home())
    return {
        "model": MODEL,
        "effortLevel": EFFORT,
        "autoMemoryEnabled": False,
        "includeCoAuthoredBy": False,
        "claudeMdExcludes": [f"{home}/.claude/CLAUDE.md", f"{home}/.claude/rules/**"],
        "permissions": {
            "defaultMode": "acceptEdits",
            # 샌드박스 안 Bash 는 전부 허용: autoAllowBashIfSandboxed 만으로는 `test "$(…)"`·for 문처럼 미리 검사할 수 없는 명령이
            # '승인 필요' → --permission-prompts none 에서 자동 거부된다(pilot_v0 에서 A·B 각 3회). 쓰기·네트워크는 샌드박스가 막는다.
            "allow": ["Bash"],
            "deny": ["Read(~/.hermes/**)", "Edit(~/.hermes/**)", "Read(~/.claude/**)", "Edit(~/.claude/**)", "WebFetch", "WebSearch"],
            "blockReadsOutsideWorkingDirectories": True,
            "blockWritesOutsideWorkingDirectories": True,
        },
        "sandbox": {
            "enabled": True,
            "failIfUnavailable": True,
            "autoAllowBashIfSandboxed": True,
            "allowUnsandboxedCommands": False,
            "filesystem": {"denyRead": [f"{home}/.hermes", f"{home}/.claude"]},
            "network": {"allowedDomains": [], "strictAllowlist": True},
        },
    }


def hook_cmd(mode: str, trial: Path, ws: Path) -> str:
    return (f"{PY} {trial / 'kit' / 'kit_hook.py'} {mode} --ws {ws} --state {trial / 'state'} --log {trial / 'hooks.log'}")


def kit_settings(trial: Path, ws: Path) -> dict:
    ev = [{"hooks": [{"type": "command", "command": hook_cmd("event", trial, ws), "timeout": 20}]}]
    return {"hooks": {
        "PreToolUse": [{"matcher": "Edit|Write|MultiEdit|NotebookEdit|Bash",
                        "hooks": [{"type": "command", "command": hook_cmd("pre", trial, ws), "timeout": 30, "onFailure": "block"}]}],
        "Stop": [{"hooks": [{"type": "command", "command": hook_cmd("stop", trial, ws), "timeout": 900}]}],
        "InstructionsLoaded": ev,
        "SessionStart": ev,
    }}


def install_kit(task: dict, ws: Path, trial: Path) -> dict:
    d = DESIGNS / task["id"]
    if not (d / "current.md").is_file():
        raise RuntimeError(f"설계 문서 없음: {d} — 먼저 `cc_run.py design --tasks {task['id']}`")
    (ws / "docs" / "handoff").mkdir(parents=True, exist_ok=True)
    for f in ("current.md", "protected.txt", "acceptance.json"):
        shutil.copy2(d / f, ws / "docs" / "handoff" / f)
    shutil.copy2(TEMPLATES / "CLAUDE.md", ws / "CLAUDE.md")
    (ws / ".claude").mkdir(exist_ok=True)
    (ws / ".claude" / "settings.json").write_text(json.dumps(kit_settings(trial, ws), ensure_ascii=False, indent=1), encoding="utf-8")
    pats = [ln.strip() for ln in (d / "protected.txt").read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    (trial / "state" / "protected.sha256").write_text(json.dumps(sha_protected(ws, pats), indent=1), encoding="utf-8")
    return {"protected": pats}


def claude_argv(cl: str, prompt: str, settings: Path) -> list[str]:
    return [cl, "-p", prompt, "--output-format", "stream-json", "--verbose", "--model", MODEL, "--effort", EFFORT,
            "--settings", str(settings), "--setting-sources", "project,local", "--strict-mcp-config",
            "--permission-mode", "acceptEdits", "--permission-prompts", "none", "--no-session-persistence"]


def run_proc(argv: list[str], cwd: Path, env: dict, timeout: float, out_path: Path) -> dict:
    t0 = time.monotonic()
    with open(out_path, "w", encoding="utf-8") as fo, open(str(out_path) + ".stderr", "w", encoding="utf-8") as fe:
        p = subprocess.Popen(argv, cwd=str(cwd), env=env, stdout=fo, stderr=fe, stdin=subprocess.DEVNULL, start_new_session=True)
        to = False
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            to = True
            os.killpg(p.pid, signal.SIGTERM)
            try:
                p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait()
    return {"rc": p.returncode, "timeout": to, "wall_s": round(time.monotonic() - t0, 1)}


def parse_stream(path: Path) -> dict:
    init, result, tool_uses, denials = None, None, [], 0
    for ln in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            ev = json.loads(ln)
        except ValueError:
            continue
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            init = ev
        elif ev.get("type") == "result":
            result = ev
        elif ev.get("type") == "assistant":
            for c in (ev.get("message") or {}).get("content") or []:
                if c.get("type") == "tool_use":
                    tool_uses.append({"name": c.get("name"), "input": c.get("input")})
    if result:
        denials = len(result.get("permission_denials") or [])
    blob = json.dumps([t["input"] for t in tool_uses], ensure_ascii=False)
    marks = sorted({m for m in HERMES_MARKS if m in blob})
    return {"init": init, "result": result, "tool_uses": tool_uses, "permission_denials": denials, "hermes_marks": marks}


def hook_log_summary(path: Path) -> dict:
    if not path.is_file():
        return {"lines": 0}
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    out = {"lines": len(rows), "pre_allow": 0, "pre_block": 0, "stop_block": 0, "stop_allow": [], "instructions_loaded": [], "hook_errors": 0}
    for r in rows:
        e, d = r.get("event"), r.get("decision")
        if e == "PreToolUse":
            out["pre_allow" if d == "allow" else "pre_block"] += 1
        elif e == "Stop":
            if d == "block":
                out["stop_block"] += 1
            else:
                out["stop_allow"].append(r.get("why"))
        elif e == "InstructionsLoaded":
            out["instructions_loaded"].append(r.get("file_path"))
        if d == "hook_error":
            out["hook_errors"] += 1
    return out


# ---------------------------------------------------------------- 시행


def run_trial(t: dict, task: dict, run_id: str, cl: str, keep: bool = False) -> dict:
    tid = t["trial_id"]
    res_dir = RESULTS / run_id / "trials" / tid
    res_dir.mkdir(parents=True, exist_ok=True)
    trial = TRIAL_BASE / run_id / f"{t['seq']:03d}-{os.urandom(3).hex()}"
    for d in ("ws", "tmp", "kit", "state"):
        (trial / d).mkdir(parents=True)
    row = {"trial_id": tid, "task": task["id"], "condition": t["condition"], "rep": t["rep"], "seq": t["seq"], "model": MODEL,
           "effort": EFFORT, "claude_bin": cl, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    try:
        ws = TS.materialize(task, trial / "ws" / task["ws_name"])
        shutil.copy2(HOOK_SRC, trial / "kit" / "kit_hook.py")
        prot_card = protected_from_card(task)
        if t["condition"] == "B":
            row["kit"] = install_kit(task, ws, trial)
        C.scratch_git_baseline(ws, TRIAL_BASE)
        prompt = ER.build_prompt_synthetic(task, str(ws))
        (res_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
        settings = trial / "kit" / "settings.base.json"
        settings.write_text(json.dumps(base_settings(trial), ensure_ascii=False, indent=1), encoding="utf-8")
        shutil.copy2(settings, res_dir / "settings.base.json")
        if t["condition"] == "B":
            shutil.copy2(ws / ".claude" / "settings.json", res_dir / "settings.project.json")
        env = clean_env({"TMPDIR": str(trial / "tmp"), "GIT_CEILING_DIRECTORIES": str(trial)})
        r = run_proc(claude_argv(cl, prompt, settings), ws, env, TIMEOUT_S, res_dir / "stream.jsonl")
        row.update({"rc": r["rc"], "timeout": r["timeout"], "wall_s": r["wall_s"]})
        st = parse_stream(res_dir / "stream.jsonl")
        res = st["result"] or {}
        init = st["init"] or {}
        row.update({"num_turns": res.get("num_turns"), "total_cost_usd": res.get("total_cost_usd"), "duration_ms": res.get("duration_ms"),
                    "result_subtype": res.get("subtype"), "is_error": res.get("is_error"), "usage": res.get("usage"),
                    "model_usage": res.get("modelUsage"), "permission_denials": st["permission_denials"],
                    "tool_calls": len(st["tool_uses"]), "hermes_marks": st["hermes_marks"],
                    "init": {k: init.get(k) for k in ("model", "permissionMode", "apiKeySource", "cwd", "mcp_servers", "plugins", "claude_code_version")},
                    "init_tools": init.get("tools")})
        (res_dir / "answer.txt").write_text(str(res.get("result") or ""), encoding="utf-8")
        # 채점(effort 하네스와 같은 함수·같은 정의)
        acc = C.run_checks(task["acceptance"], ws, C.check_env(ws, trial), timeout=CHECK_TIMEOUT)
        row["acceptance"] = [{k: a[k] for k in ("cmd", "expect", "rc", "pass", "timeout", "secs")} for a in acc]
        row["visible_all_pass"] = all(a["pass"] for a in acc) if acc else True
        hid = TS.run_hidden(task, ws, trial, timeout=HIDDEN_TIMEOUT)
        row["hidden"] = {k: hid.get(k) for k in ("passed", "expected", "total", "rate", "rc", "timeout", "secs")}
        row["hidden"]["failed"] = hid["failed"][:40]
        row["clean"] = bool(row["visible_all_pass"] and hid["rate"] == 1.0)
        # 보호 파일(카드 범위) 변경: repo/ 원본과 비교
        orig = TS.materialize(task, trial / "orig" / task["ws_name"])
        a_sha, b_sha = sha_protected(orig, prot_card), sha_protected(ws, prot_card)
        row["protected_changed"] = sorted(k for k in set(a_sha) | set(b_sha) if a_sha.get(k) != b_sha.get(k))
        if t["condition"] == "B":
            for f in ("CLAUDE.md", ".claude", "docs"):
                src = ws / f
                if src.is_dir():
                    shutil.copytree(src, orig / f, dirs_exist_ok=True)
            kd = DESIGNS / task["id"]
            kit_now = {f: hashlib.sha256((ws / "docs" / "handoff" / f).read_bytes()).hexdigest() == hashlib.sha256((kd / f).read_bytes()).hexdigest()
                       for f in ("current.md", "protected.txt", "acceptance.json") if (ws / "docs" / "handoff" / f).is_file()}
            row["kit_files_intact"] = kit_now
            # orig 쪽 키트 파일은 설치 때 값으로(에이전트가 바꿨다면 diff 에 보이게)
            shutil.copy2(TEMPLATES / "CLAUDE.md", orig / "CLAUDE.md")
            for f in ("current.md", "protected.txt", "acceptance.json"):
                shutil.copy2(kd / f, orig / "docs" / "handoff" / f)
            (orig / ".claude" / "settings.json").write_text(json.dumps(kit_settings(trial, ws), ensure_ascii=False, indent=1), encoding="utf-8")
        df = C.diff_trees(trial / "orig", trial / "ws")
        row["diff_chars"], row["diff_files"] = df["chars"], df["files"]
        (res_dir / "diff.patch").write_text(df["diff"], encoding="utf-8")
        (res_dir / "acceptance.json").write_text(json.dumps(acc, ensure_ascii=False, indent=1), encoding="utf-8")
        (res_dir / "hidden.json").write_text(json.dumps(hid, ensure_ascii=False, indent=1), encoding="utf-8")
        if (trial / "hooks.log").is_file():
            shutil.copy2(trial / "hooks.log", res_dir / "hooks.log")
        row["hooks"] = hook_log_summary(trial / "hooks.log")
        if r["timeout"]:
            row["status"] = "timeout"
        elif st["hermes_marks"]:
            row["status"] = "eval_dir_access"
        elif r["rc"] != 0 or res.get("is_error"):
            row["status"] = "agent_error"
        else:
            row["status"] = "done"
    except Exception as e:  # noqa: BLE001
        row["status"] = "runner_error"
        row["error"] = f"{type(e).__name__}: {str(e)[:300]}"
    finally:
        if not keep:
            C.safe_rmtree(trial, TRIAL_BASE)
        else:
            row["trial_dir"] = str(trial)
    with open(RESULTS / run_id / "trials.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def plan(tasks: list[dict], conditions: list[str], reps: int, seed: int) -> list[dict]:
    """(과제, 반복) 블록마다 조건을 섞어 연달아 넣는다(effort 하네스와 같은 블록 무작위화)."""
    rng = random.Random(seed)
    out = []
    for r in range(1, reps + 1):
        order = list(tasks)
        rng.shuffle(order)
        for tk in order:
            cs = list(conditions)
            rng.shuffle(cs)
            out += [{"trial_id": f"{tk['id']}.{c}.r{r}", "task": tk["id"], "condition": c, "rep": r} for c in cs]
    for i, t in enumerate(out, 1):
        t["seq"] = i
    return out


def done_ids(run_id: str) -> set[str]:
    p = RESULTS / run_id / "trials.jsonl"
    if not p.is_file():
        return set()
    return {json.loads(x)["trial_id"] for x in p.read_text(encoding="utf-8").splitlines() if x.strip()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("design")
    d.add_argument("--tasks", default="all")
    d.add_argument("--force", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("--run-id", required=True)
    r.add_argument("--tasks", default="all")
    r.add_argument("--conditions", default="A,B")
    r.add_argument("--reps", type=int, default=1)
    r.add_argument("--seed", type=int, default=20261126)
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--keep", action="store_true", help="시행 폴더를 지우지 않는다(디버그)")
    r.add_argument("--make-design", action="store_true", help="설계 문서가 없는 과제는 먼저 reviewer-bot 으로 만든다")
    sub.add_parser("probe-env")
    a = ap.parse_args(argv)
    if a.cmd == "probe-env":
        print(json.dumps(base_settings(Path("/x")), ensure_ascii=False, indent=1))
        print(claude_bin())
        return 0
    if a.cmd == "design":
        for tk in load_tasks(a.tasks):
            print(json.dumps(run_design(tk, force=a.force), ensure_ascii=False))
        return 0
    tasks = {t["id"]: t for t in load_tasks(a.tasks)}
    conds = [c.strip() for c in a.conditions.split(",") if c.strip()]
    pl = plan(list(tasks.values()), conds, a.reps, a.seed)
    left = [t for t in pl if t["trial_id"] not in done_ids(a.run_id)]
    missing_design = sorted({t["task"] for t in left if t["condition"] == "B" and not (DESIGNS / t["task"] / "current.md").is_file()})
    est = sum(240 if t["condition"] == "A" else 360 for t in left)
    print(json.dumps({"run_id": a.run_id, "planned": len(pl), "pending": len(left), "missing_design": missing_design,
                      "est_wall_min_sequential": round(est / 60), "first": [t["trial_id"] for t in left[:6]]}, ensure_ascii=False))
    if a.dry_run:
        for t in left:
            print(t["seq"], t["trial_id"])
        return 0
    if missing_design and not a.make_design:
        print("설계 문서 없는 과제가 있다: --make-design 을 붙이거나 먼저 design 을 돌려라", file=sys.stderr)
        return 2
    for tk in missing_design:
        print(json.dumps(run_design(tasks[tk]), ensure_ascii=False))
    (RESULTS / a.run_id).mkdir(parents=True, exist_ok=True)
    (RESULTS / a.run_id / "plan.json").write_text(json.dumps(pl, ensure_ascii=False, indent=1), encoding="utf-8")
    cl = claude_bin()
    for t in left:
        if (KIT / "STOP").exists():
            print("STOP 파일 — 멈춘다")
            break
        row = run_trial(t, tasks[t["task"]], a.run_id, cl, keep=a.keep)
        print(json.dumps({k: row.get(k) for k in ("trial_id", "status", "clean", "wall_s", "num_turns", "total_cost_usd")}
                         | {"hidden": (row.get("hidden") or {}).get("passed")}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
