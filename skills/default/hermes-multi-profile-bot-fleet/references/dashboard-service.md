# Web dashboard as a service

## The inherited-web-dist trap

When the Electron desktop app is running it exports `HERMES_WEB_DIST` pointing at its own packaged
renderer bundle (`.../app.asar.unpacked/dist`). A `hermes dashboard` started from that shell
inherits the variable and serves the DESKTOP frontend to the browser, which then fails looking for
an Electron IPC bridge that does not exist in a browser tab. `curl` returns HTTP 200 the whole
time, so the server looks healthy while every page is broken.

Start it with the variable stripped:

```bash
env -u HERMES_WEB_DIST hermes dashboard --isolated --no-open --port 9119
```

Do NOT pass `--skip-build` while diagnosing this: the real dashboard bundle may never have been
built, and skipping the build leaves the wrong bundle in place and hides the cause.

## Verify the served bundle, not just the status code

HTTP 200 proves a server answered, not that it answered with the right app:

```bash
curl -s http://127.0.0.1:9119/ > /tmp/dash.html
grep -o "<title>[^<]*</title>" /tmp/dash.html      # expect the Dashboard title
grep -c "app.asar\|TRANSPARENT_WINDOWS" /tmp/dash.html   # expect 0
```

A non-zero count on the second grep means the Electron bundle is being served.

## Watching fleet work live

When the user wants to "see progress live", point at what already exists before building anything:

| Surface | Shows | Live? |
|---|---|---|
| Dashboard **Kanban** tab (`http://127.0.0.1:9119`, launchd `ai.hermes.dashboard`) | every board's cards, who runs what, comments, runs, worker log | cards/events live (the kanban plugin tails `task_events` over its `/events` WebSocket); the worker-log pane loads once with a refresh button |
| `hermes kanban watch --interval 2` | event stream across boards (create/claim/review/complete/crash) | live |
| `hermes kanban --board <b> tail <task_id>` | one worker's tool calls and output | live (tail -f); `log <id> --tail N` for a snapshot |
| The Discord thread itself | tool-call progress bubbles | live when `display.tool_progress` is non-`off` |

For this user (Ghostty + tmux) recommend a split: `tmux new-session -d -s kb 'hermes kanban watch
--interval 2' \; split-window -h 'hermes kanban --board <b> tail <id>' \; attach -t kb`. The
dashboard binds 127.0.0.1 — viewing it from a phone needs a tunnel with its own auth; recommend the
Discord app instead. Find the running task with `sqlite3 <board>/kanban.db "select id from tasks
where status='running'"`. When testing `watch` non-interactively, bound it with
`perl -e 'alarm 10; exec @ARGV' hermes kanban watch …` (no `timeout` on macOS; `&` is rejected).

## Autostart via launchd

A dashboard started by hand dies with its shell. For a persistent one, model the LaunchAgent on
the existing gateway plists (`RunAtLoad`, `KeepAlive`, `ThrottleInterval` 30, explicit `PATH`,
`VIRTUAL_ENV`, `HERMES_HOME`, log paths).

**Omit `HERMES_WEB_DIST` from `EnvironmentVariables`.** launchd does not inherit the login shell's
exports, so leaving it out is the whole fix — no `env -u` wrapper needed.

After `launchctl load`, an exit status of 75 with `BACKEND_PORT_IN_USE` in the log means a
manually started instance still holds the port. Stop that process; KeepAlive brings the managed
one up on the next throttle window (~30 s), so wait before declaring failure. Confirm stability by
checking the PID twice a minute apart — a changing PID is a crash loop, an unchanged one is
healthy, and a stale non-zero exit code from the first failed attempt is not a live error.

## Building a project-centric view on top of Hermes data

The stock dashboard is a management console (sessions, skills, cron, kanban). When the user wants
"organized" views — per-project status, which rules apply where, per-thread summaries — offer the
options in order of weight and let them pick:
1. **Dashboard plugin tab** (lightest): `~/.hermes/plugins/<name>/dashboard/` with `manifest.json`
   (`tab.path`, `position`), a plain-IIFE `dist/index.js` using `window.__HERMES_PLUGIN_SDK__`
   (React + card components, no build step, theme-aware), and an optional `plugin_api.py`
   FastAPI `router` mounted at `/api/plugins/<name>/` behind dashboard auth. Survives Hermes
   updates. Reference: `website/docs/user-guide/features/extending-the-dashboard.md`. It runs
   inside the dashboard process — open DBs read-only and keep handlers light.
2. **Separate app** (when the user wants it decoupled from the console, e.g. their own stack or
   containers). Design doc first (`fleet-design-doc.md` conventions), then build in phases.

Rules for any separate app that reads Hermes state:
- **Never bind-mount the live Hermes SQLite DBs into containers.** `state.db` and `kanban.db` run
  in WAL mode (`pragma journal_mode` → `wal`); WAL readers coordinate through the `-shm`
  memory map, which is not shared between the macOS host and Docker Desktop's Linux VM, so even a
  read-only mount can misread or corrupt. Put a small host-side reader (launchd, 127.0.0.1, bearer
  token) in front: it opens `file:<db>?mode=ro` + `PRAGMA query_only=1` per request, masks
  secrets and Discord IDs, never opens `.env`/`auth.json`/credential dirs, and serves JSON to the
  containers via `host.docker.internal`.
- Stored session prompts are content-addressed: join `sessions.system_prompt_hash` to
  `system_prompts(hash, prompt)` (the `sessions.system_prompt` column is NULL).
- Summaries of chat threads run as a separate batch (hourly in working hours — daily is too stale
  for the user; cheap model, user/assistant text only, per-session cursor for idempotence, per-run
  token cap), never inside the gateway process — the
  shared gateway already stalls Discord heartbeats under load.
- Keep it 127.0.0.1-only (ClusterIP + `kubectl port-forward --address 127.0.0.1`); the views show
  project text.
- Pin versions from live lookups, not memory: `npm view <pkg> version`, PyPI JSON
  (`https://pypi.org/pypi/<pkg>/json`), support windows from
  `https://endoflife.date/api/<product>.json`. Prefer the newest LTS / one-behind runtime when the
  newest is days old (thin wheel coverage), state why in the version table, and flag unverified
  toolchain combos as a Phase-0 check.
- Check the cluster exists before designing deploy steps (`kubectl config get-contexts -o name`
  empty → the user must enable Docker Desktop Kubernetes), and list the control plane's standing
  RAM as a risk when the fleet already shows load-related disconnects.
- Batch all version/environment probes into one `execute_code` call; long `node`/`docker` chains
  in `terminal` can be rejected as long-lived server commands.
- Bootstrap order once the design is approved: (1) record the user's open decisions in the
  design doc's risk/decision table and bump its status line, add it to the ops repo README index,
  run the PII gate, commit + push; (2) scaffold a SEPARATE private app repo (`gh repo create
  <owner>/<app> --private --source=. --push`, noreply author, `.gitignore` covering
  node_modules/.next/.venv/*.db*/secrets, a copy of the design doc, empty skeleton dirs with
  `.gitkeep`), verify `gh repo view --json visibility` = PRIVATE; (3) run the Phase-0 checks that
  need no cluster and record each with its evidence in `phase0/결과.md`.
- Phase-0 checks that work without Kubernetes (both verified on Docker Desktop for Mac):
  - Host reachability: run a throwaway `python3 -m http.server <port> --bind 127.0.0.1` as a
    background terminal process, then `docker run --rm curlimages/curl -s -o /dev/null -w
    '%{http_code}' http://host.docker.internal:<port>/` → 200 means the host reader can stay
    127.0.0.1-only. Kill the background process afterwards (`process_manage kill`).
  - Frontend toolchain combo: write a 3-file Next app (package.json with exact versions,
    `app/layout.tsx`, `app/page.tsx`, `next.config.ts` with `output: "standalone"`) and build it
    inside `node:<lts>-slim` with the dir bind-mounted — nothing installs on the Mac; pass =
    `next build` succeeds and `.next/standalone/server.js` exists. Gitignore its node_modules.
  - Cluster-dependent checks (local image use, NetworkPolicy enforcement, pod →
    host.docker.internal) stay "pending" until the user enables Kubernetes. Once it is on, run
    them in a throwaway namespace (delete the namespace + test image afterwards):
    - Local image: `docker build -t <x>:test` then a pod with `imagePullPolicy: Never` — Docker
      Desktop's kubeadm cluster runs local images directly, so no registry and no load step.
    - Pod → host: `kubectl exec <pod> -- wget -q -O- http://host.docker.internal:<port>/` against
      the same background 127.0.0.1 server.
    - NetworkPolicy: server pod + Service + client pod; fetch before and 8 s after applying a
      default-deny Ingress policy. Docker Desktop ships no policy engine, so expect it to still
      connect (not enforced) — keep the manifest as documentation and rely on 127.0.0.1 binding +
      bearer token + ClusterIP. Plain `alpine` has no `httpd`; use `apk add busybox-extras`, or the
      server pod never becomes Ready and the "before" fetch already fails, making the test void.
    - Write the before/after results into `phase0/결과.md` and the design doc in the same pass.
- Enabling Kubernetes is a user GUI step. Bring the app forward with `open -a "Docker Desktop"`,
  then give the clicks: Settings (⚙️) → Kubernetes → Enable Kubernetes (kubeadm, 1 node default)
  → Apply & restart → Install → wait for the green "Kubernetes running"; verify with
  `kubectl config get-contexts` showing `docker-desktop`. Warn that Docker restarts during this,
  killing running containers (e.g. a project's sandbox jobs) — do it when none run.
- Phase 1 (read-only views) build order that worked: host reader → api → web → k8s → launchd.
  - Host reader: reimplement the AGENTS.md chain rule (git root → cwd; per dir first NON-EMPTY of
    `AGENTS.override.md`/`AGENTS.md`/`agents.md`) instead of importing Hermes, then prove parity
    with a plain script run under `~/.hermes/hermes-agent/venv/bin/python` that compares against
    `agent.prompt_builder._agents_md_candidates` on every real project dir plus a synthetic tree
    (nested `.git`, override wins, empty override falls through, 2-level subdir, no git). The
    Hermes venv has no pytest and must not get one; the app venv can't import Hermes — so a pytest
    version of this check only skips.
  - Sources it reads: profile `config.yaml` (`model.default`, `agent.reasoning_effort`,
    `terminal.cwd`), `gateway_state.json` (`platforms['<bot>:discord'].state`,
    `served_profiles` list), `cron/jobs.json` (`jobs[].enabled`), `kanban/boards/<b>/board.json`
    + `kanban.db` tasks.
  - Board → project mapping: `default_workdir` is often `null` (board created without
    `--default-workdir`), so a workdir-only join silently drops that project's tasks. Fall back to
    board slug = folder name, then the most common `tasks.workspace_path` (kind `dir`); skip
    archived/`_tmp` boards. "Active tasks" = every status except `done`/`archived` (Hermes
    `VALID_STATUSES` in `hermes_cli/kanban_db.py` also has `triage`, `scheduled`) — an allow-list
    of running/blocked/ready misses scheduled work. When the user says tasks are missing, compare
    `select status,count(*) from tasks group by status` per board with the page before guessing.
    Deadlines come from a `마감 YYYY-MM-DD` line in the project AGENTS.md; finished projects without
    one need an explicit ended list (env var), or they show as active.
  - k8s Secret mounted into a non-root pod: `defaultMode: 0400` stays root-owned and the app gets
    Permission denied (every page 500). Set pod `runAsGroup`/`fsGroup` to the app uid and
    `defaultMode: 0440`.
  - Deploy with `imagePullPolicy: Never` + git-short-hash tags; Makefile renders `kubectl
    kustomize` and seds the tag in. Put `token`/`test`/`build`/`deploy`/`agent-install`/
    `pf-install`/`status`/`down` targets in it so the user can stop everything with one command.
    The `-dirty` suffix must come from `git status --porcelain` (includes untracked files), not
    `git diff --quiet`: with the latter a build containing a NEW uncommitted file gets the same
    tag as the running image, the rollout is a no-op, and the new route 404s. Commit before
    `make build` anyway, and after deploy hit the new endpoint rather than trusting "web 접속
    가능". Changing host-agent code needs `launchctl kickstart -k gui/$(id -u)/<agent label>`
    (separate from the gateway; bots unaffected).
  - launchd: `bootout` immediately followed by `bootstrap` can fail while the old job unloads —
    rerun the install once and confirm with `/health`. Check `/health` a few seconds after
    bootstrap; an immediate probe races uvicorn startup and looks like a failure (read the log).
  - Commands promoted to background (timeout > 600 s) run in a shell without `~/.hermes/bin` on
    PATH (`uv: command not found`) — `export PATH="$HOME/.hermes/bin:$PATH"` first, and keep
    each step in its own foreground call (< 600 s) so a failure in one is visible.
  - Verify rendering visually: `browser_exec(local=true)` (the user's machine) reaches
    127.0.0.1 — `new_tab(url)` + `capture_screenshot()`, and drive interactions with `js(...)`
    (click, then read back DOM state such as `details.open`). The cloud browser cannot reach the
    Mac's loopback; the desktop preview pane (`desktop_preview open`/`read`) is the other option.
    Also curl every route for status + time (warm median is the metric; the first request after
    a pod start is slow), and a forbidden path (`/etc/passwd`) must render the refusal. Record
    results in `phase1/결과.md`.
  - Typecheck inside the build image, not with the Mac's `node_modules` (platform-specific
    binaries may be absent there): `docker build -q --target build -t <app>-typecheck apps/web &&
    docker run --rm <app>-typecheck npx tsc --noEmit; echo rc=$?`, then `docker rmi` it.
    `next build` also typechecks unless `typescript.ignoreBuildErrors` is set — check
    `next.config.ts` before relying on that.
- Phase 2 (thread summaries) — what held up on real data:
  - Host reader endpoints: list sessions (`source='discord'`, `last_activity_at >= since`) and
    messages after a cursor id: `role in (user, assistant)`, drop `display_kind` in
    (hidden, internal_notification, session_meta), keep `steer`, include `active=0` rows
    (compacted-away originals are still real conversation), and drop bodies starting with
    `[CONTEXT COMPACTION` (huge handoff text that re-summarizes old decisions as new) or
    `Gateway message origin (JSON data` (metadata). Validate profile/session ids by regex.
  - Discord sessions have `cwd` NULL — infer the project from the transcript (path mentions ×3 +
    slug mentions, minimum score, else unknown); kanban sessions have it.
  - Batch: same image as the api, CronJob with `timeZone: Asia/Seoul`, `concurrencyPolicy:
    Forbid`; forced tool-use JSON (headline/decisions/progress/next/open_questions); save summary
    + move cursor in one transaction; a failed session keeps its cursor (retried next run);
    per-run input cap decides with a token ESTIMATE — Korean-heavy text is ≈ len/1.2 tokens, not
    len/2.2 (the latter under-counts ~1.8×, so the cap is blown).
  - The prompt must say decisions = the USER's instructions only, quoted; otherwise the model
    files the bot's own judgments as decisions.
  - Always `--dry-run` first (prints sessions + estimated tokens, no API call) and report the
    estimate; then one real run and report actual tokens/cost (Haiku: $1/$5 per 1M).
  - Verify quality before claiming it: grep every number/ID in the summary against that
    session's messages (`content like '%<x>%'`), and list the user's own utterances to check each
    decision maps to one. Report the sample size; "10-thread check" waits for enough threads.
  - Reuse the user's existing key file only after asking (offer a dedicated key first); copy the
    file into the gitignored overlay `secrets/` and generate the Secret — never read the value.
    When asked "what does the cluster bill?", answer from evidence: CronJob env + mounted
    Secrets (names only), `model` column of the summary tables, run-cost sum, key prefix only.
  - Running the batch on the user's Claude subscription instead of an API key ("api말고 cli
    토큰"): the ONLY permitted route is the official `claude` CLI authenticated with
    `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token` (1-year token, user runs it and saves it
    via `read -rs` to a 600 file; never handle the value). Putting a subscription token into the
    Anthropic SDK is token extraction and is banned. Recipe:
    - One `llm.py` with `structured(model, system, prompt, schema, name, max_tokens)` and two
      backends (`SUMMARY_BACKEND=cli|api`); callers and tests use only that interface, so the
      fake client mocks `structured()`, not SDK internals.
    - CLI call: `claude -p --model <id> --output-format json --json-schema '<schema>'
      --system-prompt <sys> --tools "" --setting-sources "" --strict-mcp-config
      --disable-slash-commands --no-session-persistence --effort low`, prompt on stdin. Read
      `structured_output`, `usage` (input + cache tokens), `is_error`/`api_error_status`,
      `total_cost_usd` (list-price estimate, not billed on a subscription). Overhead ≈1.3k input
      tokens/call with the default system prompt replaced and tools off.
    - Never `--bare` (it ignores the OAuth token), and strip `ANTHROPIC_API_KEY` /
      `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_BASE_URL` from the child env — an API key present wins
      and silently bills the API account. Remove the API-key Secret from the CronJob too.
    - Container: separate Dockerfile target (`--target run` for api, `--target summarizer`),
      install the CLI pinned to the host's version via `curl -fsSL https://claude.ai/install.sh |
      bash -s <ver>` in a build stage and copy the resolved binary (`readlink -f
      ~/.local/bin/claude`) to `/usr/local/bin`; runtime needs `ca-certificates`. With
      `readOnlyRootFilesystem`, set `HOME`/`CLAUDE_CONFIG_DIR` under the `/tmp` emptyDir and
      `DISABLE_AUTOUPDATER=1`; raise the memory limit (~768Mi). Smoke-test with `docker run
      --read-only --tmpfs /tmp --user 10001` before any token exists.
    - Probe the exact flag set once on the Mac first (subscription login already there) to learn
      the JSON shape; test the backend with a fake `claude` executable that records argv/env
      (asserts: token passed, API key absent, no `--bare`, stdin prompt, error JSON → raise).
    - Tell the user: usage now shares the subscription's limits with their own Claude Code, the
      token expires in a year (runs then fail), and the old API-key path keeps running until the
      token is in and redeployed.
  - When proposing "what else to add", give a numbered table (feature / why, citing a number seen
    in the live data / token cost) plus one recommended subset; the user answers by number.
  - Freshness — when the user says "not up to date", locate the stale layer before fixing: compare
    the kanban DB rows with the api's `/v1/overview` (fetched_at age), then the summary table's
    `created_at` and per-session cursor against that session's latest message id/timestamp in
    state.db. Tasks were live; summaries were the stale layer. Rules that came out of it:
    - Run the batch hourly in working hours (`15 8-23 * * *`), not daily — sessions with fewer
      than 2 new messages make no API call, so idle hours cost nothing. Offer `make summarize-now`
      for an immediate refresh and show a "HH:MM 기준" time on each summary card.
    - One row per (session, day) means a second run the same day OVERWRITES the morning's
      decisions. Pass the existing same-day summary into the prompt and ask the model to merge
      (move finished `next` items to `progress`, drop answered questions, keep the rest).
    - The model sometimes omits an empty list field even when the schema marks it required;
      default every list field to `[]` instead of indexing, or one omission fails the whole run.
    - Guard against overlapping runs (scheduled + manual): skip when a non-dry `running` run row
      younger than the job deadline exists, or the same messages get summarized twice.
    - Pin a thread's project once known (most frequent non-null `project_slug` for that session)
      and backfill its NULL rows; a short new chunk rarely names the project, so re-inferring per
      run drops summaries off the project page.
  - Every redeploy replaces the web pod and drops `kubectl port-forward`; the launchd job
    reconnects within its throttle (~15 s). Make `make deploy` end with a loop polling
    `127.0.0.1:3300/api/health` (≤30 s) so the next check never hits the gap and reads 000 as an
    outage.
- Skills page (installed skills + Korean summaries):
  - Inventory: `**/SKILL.md` under `~/.hermes/skills` and each `profiles/<bot>/skills`, skipping
    dot-dirs (`.archive` is listed separately as "archived by curator"; `.hub/index-cache` is a
    cache, not installs). Name = frontmatter `name`, else folder.
  - Source: name in `skills/.bundled_manifest` (`name:hash` lines) → bundled; in
    `.hub/lock.json` `installed` → hub; else local (hand- or auto-written).
  - Merge by name across profiles; hash each copy and flag "differs per profile" when hashes
    differ — auto-edits drift per bot, so bots may follow different rules.
  - Shared skills: also read each profile's `skills.external_dirs` (expand `~`, relative =
    profile home, existing dirs only), walk them with `os.walk(followlinks=True)` (entries are
    symlinks), and emit `shared_with: {profile: dir}` only where the profile has no own copy of
    that name. Render it as a distinct colored `<profile>↗` with the dir in `title` plus a
    `공유 N` badge; otherwise a shared skill looks default-only. Expose the same union in any
    machine index other tools consume (e.g. a `/api/skills-index` web route for a recommendation
    hook — the api is reachable only from web, so the route lives in web).
  - Usage: `skill_view` calls in every profile's `state.db` (`json_each(messages.tool_calls)`,
    `function.name='skill_view'`, arguments `name`, strip a `plugin:` prefix), last 30 days.
    Aggregate by NAME across all profiles — a bot often calls a skill installed only in another
    profile, so per-install counting misses it. `messages` has no timestamp index, so this is a
    full scan: ~0.1 s warm, but several seconds on a cold page cache once bot `state.db`s reach
    GBs (after reboot/memory pressure). Precompute it on a timer or cache it in the host reader —
    don't compute it inside a request the api calls with a short timeout. Don't add an index to
    the Hermes DB (read-only access rule). Typically only ~10% of installed skills are used in 30 days — worth telling the user.
  - Change history: `skills/.curator_ledger.jsonl` (ts, actor, action, skill, evidence.file_path).
  - Grouping by function ("카테고리 나눠서 보기좋게"): the folder `category` from the reader is
    ~18 buckets, a third with one skill, and the user's own project/bot-ops skills sit inside
    `software-development` next to generic dev skills — don't render it as-is. Keep a pure TS
    module (`src/lib/skill-groups.ts`): ~9 functional groups (프로젝트·대회, 봇 운영·칸반, 개발,
    데이터·ML, 문서·업무, 리서치, 디자인·미디어, 기기·외부 연동, 기타), NAME regex rules first
    (project slugs, `kanban|hermes|claude-md|…`), then a folder-category map, else 기타. Run the
    rules against the live `/v1/skills` list and print group → names before building UI; fix
    misfiled names with a rule. Fixed group order (usage-sorted order reshuffles weekly and
    defeats scanning); `<details>` per group, open only when the group has 30-day uses, header =
    label · count · hint · 30일 N회; chip bar of anchors whose `onClick` sets `details.open =
    true` (an anchor alone scrolls to a closed group). While a search query is present, drop the
    grouping and show the relevance-ranked flat list. New project skills need one name rule —
    tell the user where the file is. Add its test file to the Makefile's node test line.
  - Summaries: a second step in the same summary batch, after threads, from the leftover input
    budget (own cap ~250k est. tokens/run); re-summarize only when the chosen copy's hash changed
    (default profile first, else newest), most-used first, so the first full pass spreads over a
    few hourly runs (~$0.6 for ~110 skills on Haiku) and later runs cost cents. Clip long
    SKILL.md to head 10k + tail 3k chars. Show "summary pending refresh" when the stored hash no
    longer matches. Cache the inventory in the api (~1 s to build) for ~2 min.
  - `desktop_preview read` may return a different (hovered/stale) tab; for content checks strip
    the curl'd HTML to text instead.
- Skill search ("find a skill by what it does"). Two tiers, both needed:
  - Instant client filter over the data already on the page (name > Korean summary/when-to-use >
    key points > description > category, weighted; all words must match; `?q=` synced with
    `history.replaceState` and kept when switching filter tabs). Not enough on its own: only ~half
    the skills have Korean summaries and descriptions are one line, so a feature word that lives
    only in the body (e.g. "discord") returns 0 — check a few real queries before reporting done.
  - Body full-text search on the host reader (`/v1/skills-search?q=`), proxied api → a Next
    route handler (the browser cannot reach the api), 300 ms debounce + AbortController. Never
    ship all SKILL.md bodies to the browser (~1 MB for ~110 skills). Cache bodies per file by
    mtime; dedupe by name (default profile first); return count + a masked ~140-char snippet
    around the first hit; show body-only hits in a separate "found in body" group.
  - Bodies are English, the user types Korean: keep a small Korean→English synonym map in the
    shared search module and send `term|alt|alt` groups (OR inside a word, AND across words).
  - Match short ASCII alternatives (≤4 chars) on word boundaries, or `bot` hits `both`/`robot`
    and floods results (60 → 15). Don't reject one-character terms wholesale — a single Hangul
    syllable (봇, 키) is a real word; reject only 1-char ASCII.
  - Keep the client and server matching rules identical, and unit-test the pure TS module with
    `docker run node:24-slim node --experimental-strip-types --test tests/*.test.mjs` (no npm
    install needed; pass an explicit file — a bare `tests/` dir is not resolved). When a test
    fails, check whether the fixture is wrong before "fixing" the matcher.
- Progress percentages ("진행상황을 퍼센트로"). Offer the candidates as a table with each one's
  flaw, let the user pick a subset, and build only those:
  - A score vs target: (best − start) ÷ (target − start). Needs target/current written somewhere
    machine-readable (a line in the project AGENTS.md or a `progress.json` the bots update) —
    ask where before building.
  - B per-task checklist: reviewer bodies already carry `- [ ]` completion criteria but bots never
    tick them, and bot tools cannot edit a body (`hermes kanban edit` rewrites the whole body —
    risky). Use the heartbeat note instead: add a shared-AGENTS rule "after each checklist item,
    `kanban_heartbeat` note `진행 k/N: <item>`", read the last match from `task_events`
    (`kind='heartbeat'`, payload JSON `note`), fall back to the body's checked/total, done = 100%,
    no evidence = no bar. Applies only to tasks started after the rule edit.
  - C task completion: done ÷ all is ~99% forever, and even "created in the last 7 days, excluding
    archived" stays 98–99% because bots finish tasks within hours. Say so after measuring and
    offer throughput, mean time-to-done, or blocked share instead.
  - D time elapsed: (today − start) ÷ (deadline − start); start = a `시작 YYYY-MM-DD` line in the
    project AGENTS.md, else `board.json` `created_at` (epoch). Tint ≥85% as a warning.
  - Show C/D on the project card and B per task row; tell the user where each start date came
    from so they can correct it.
- Project scope — keep the app project-agnostic. Hard-coding one workspace (e.g. a competitions
  folder) or the user's/bots' names makes it a single-purpose tool the user will push back on:
  - Discover projects from configured workspace roots (each subfolder) PLUS a home scan for
    direct children with `.git` or `AGENTS.md` (skip symlinks, dot-dirs, macOS media/Library
    folders, catch `OSError` on TCC-protected dirs); an ignore list env var for strays.
  - Order the home by last activity = max(`.git/logs/HEAD` mtime, own rule-file mtime, latest
    board task timestamp), with deadline-within-7-days pinned first. Deadline, board and
    progress bars are optional attributes shown only when present, never the card's frame.
  - Classify `idle` (no activity for N days, default 30) separately from `ended`; collapse both
    and exclude them from alerts. A plain repo without AGENTS.md is an info note, not a warning.
  - Summary prompts take the user name from env and say "topics vary"; no bot/user names baked in.
  - Widening discovery also widens the rule-file allow-list (`/v1/file` roots) — update both.
- Ops page (gateway/bots/disconnects/cron) — read-only sources and traps:
  - Disconnects live in `logs/gateway.error.log` (multiplexed `gateway.log` may have stopped
    being written); read only the last ~4 MB. Classify by regex: `Fatal discord adapter error
    for multiplexed profile <p>` / `socket_closed` = disconnect, `No route to host` etc. =
    network, `Can't keep up` = lag. One disconnect logs an adapter line (no profile) AND a
    gateway line (profile) in the same minute — drop the profile-less duplicate or counts double.
  - Cron: every profile's `cron/jobs.json` (`enabled`, `failure_streak`, `last_error`,
    `no_agent`/`script` → zero-token vs model job) + `cron/executions.db`. Iterate ALL profile
    dirs here — a skills-only profile helper skips profiles without `skills/` and loses jobs.
- Usage page (cost by bot/model/day) from each profile's `state.db` `session_model_usage`:
  - Rows are CUMULATIVE per session×model; a Discord thread lives for weeks, so bucketing by
    `last_seen` dumps weeks of spend onto today. Spread each row across days by that session's
    assistant-message count per day (`messages.timestamp`), and sum only the in-window share.
  - Cost = `actual_cost_usd` if >0 else `estimated_cost_usd`; flag a model "unpriced" only when
    its total cost is 0 with tokens (some rows of a priced model are 0 too). Label it an API-rate
    estimate, not the bill. Show top sessions by cost — one long thread is usually ~⅓ of spend.
- Urgent alerts (gateway down / bot not connected / flapping / cron failing) run as their own
  launchd job every 2 min, outside the gateway, so they fire when the gateway is dead:
  - Gateway down = pid in `gateway_state.json` dead (`os.kill(pid,0)`) or state ≠ running. Bot
    down only after a grace period (~5 min since the platform `updated_at`) so auto-reconnects
    stay quiet; skip profiles not in `served_profiles` and an ignore list (a long-dead default
    platform is noise).
  - Edge-triggered via a state file outside Hermes (open → remind every N h → resolved);
    mention only on a new critical. Send to macOS Notification Center (`osascript display
    notification`) plus Discord REST with a bot profile's token — independent of the gateway.
  - Keep machine-specific values (channel, user id) in `~/.config/<app>/notify.env` (chmod 600)
    loaded by the plist via `sh -c 'set -a; . file; exec …'`; commit only an `.example`.
  - Apply secret/ID masking to the body only: masking the whole message also masks the
    `<@user_id>` mention and the ping silently stops. Test with a realistic 19-digit id.
  - Verify by injecting a fake bad platform state in-process (patch the state read) and printing
    the formatted message, then `--dry-run` on real state (expect nothing), then one real
    `--test` send.
- Cost alerts (same launchd job): derive thresholds from the user's own last-30-day
  distribution (hourly median/p99/max, daily median/max) and state them next to each threshold.
  - Hourly burn: the per-session cost is cumulative, so snapshot `{profile/session: cost}` every
    run to a state file (keep ~75 min) and diff against the snapshot ~1 h old; count a session
    absent from the old snapshot only if `first_seen` is after it (an old thread reappearing is
    not new spend). Warn at the threshold, critical (mention) at 2×; the message names the
    biggest thread and says `/stop` in it.
  - Daily total (reuse the usage page's per-day spread) and "long thread" (cumulative ≥ N and
    active in 24 h → move to a new thread) fire ONCE per key — no reminders, no "resolved"
    message — via a `once` flag in the edge-trigger state.
  - Wrap the cost check in its own try/except so a failure never suppresses connection alerts;
    the hourly alert needs ~50 min of snapshots before it can fire — say so.
- Test fixtures use fake ids of the same shape (19 repeated `1` digits), never the user's real
  Discord ids — the repo's secret scan matches them, and they leak if the repo is ever shared.
- "데이터를 불러오지 못했다" / Minified React error #441 (Server Components render error) is the web
  layer reporting an upstream failure; the page's "host-agent off or token wrong" hint is often
  not the cause. Walk the chain once, in order, before changing anything:
  1. `kubectl -n <ns> logs deploy/web --tail=40` → `api <path> → 502` names the failing endpoint.
  2. From the api pod, call the host reader directly with the mounted token (`/health`, then the
     failing path) and print status + elapsed seconds: 200 on `/health` rules out launchd/token/
     network; `host-agent 연결 실패: ReadTimeout` at exactly the api's timeout means a slow read.
  3. Host reader log (`~/Library/Logs/<app>-agent.log`) for the traceback; profile a slow endpoint
     with `cProfile` in its venv and time it twice (cold vs warm).
  Known causes: a board dir holding a 0-byte `kanban.db` (no `tasks` table) crashes every
  board-reading endpoint — the reader must skip DBs without `tasks`, and the stray file usually
  came from a `sqlite3` CLI call on a missing path (move it to `~/.Trash`, not `rm`); and a
  cold-cache full scan exceeding the api's per-call timeout (see Skills page → Usage).
- When the user says they will run it "on the PC", confirm which machine before finalizing: the
  design is host-specific (launchd, `host.docker.internal`, 127.0.0.1-only). If the cluster runs
  on a different machine than the Hermes data, the host reader must listen on the LAN and the
  security section (token, firewall, allowed IPs) must be redesigned — say so, don't silently
  keep the single-host assumptions.
