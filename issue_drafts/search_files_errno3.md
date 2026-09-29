# [macOS] `search_files` intermittently fails with `[Errno 3] No such process` (race in native rg kill)

## Environment
- Hermes Agent v0.21.4 (2026.9.21), upstream `d2ef7db7`
- macOS 26.6.2, Apple Silicon, local terminal backend
- Seen in gateway-served profiles, kanban workers and one-shot `hermes chat -q`

## Symptom
`search_files` returns `{"error": "[Errno 3] No such process"}` after 0.01–0.4 s, with no results. Retrying the same call sometimes works.

`errors.log` across 3 profiles, 2026-09-14 → 09-29: **55** `Tool search_files returned error … [Errno 3] No such process` warnings — every `Errno 3` tool error on this host is `search_files`. Per active day: 2, 16, 14, 4, 5, 5, 1, 1, 2, 5.

Agents handle it differently: some retry, some conclude "file not found" (a false negative), which changes the answer.

## Likely cause (from reading the code, not yet reproduced in isolation)
`tools/file_operations_search.py::_run_rg_native`:

```python
if proc.poll() is None:
    _kill_process_group_posix(proc)
```

`tools/environments/local.py::_kill_process_group_posix`:

```python
try:
    pgid = os.getpgid(proc.pid)
except ProcessLookupError:
    if (pgid := getattr(proc, "_hermes_pgid", None)) is None:
        raise
```

When the drain thread stops at `fetch_limit` (or the deadline hits), rg can exit between `proc.poll()` and `os.getpgid()`. `_run_rg_native` spawns with `subprocess.Popen` directly and never sets `proc._hermes_pgid` (only the terminal path at `local.py:949` does), so the `ProcessLookupError` is re-raised and surfaces as the tool error.

## Suggested fix
- In `_run_rg_native`, record `proc._hermes_pgid = os.getpgid(proc.pid)` right after `Popen` (it is `start_new_session=True`, so pgid == pid), **or**
- treat `ProcessLookupError` in `_kill_process_group_posix` as "already gone" when the caller's process has exited (`proc.poll() is not None`).

## Related
- Kanban worker crashes on the same host show `search_files … [Errno 3]` shortly before the worker died in 1 of 8 cases; not claimed as the cause.

---
<!-- 제출됨: https://github.com/NousResearch/hermes-agent/issues/127652 (2026-09-29). 이후 수정은 GitHub 쪽에서. -->
