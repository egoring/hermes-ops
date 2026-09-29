# Writing the fleet design document

The user wants the bot-fleet architecture as a Markdown file with Mermaid diagrams, saved in
the project's `docs/` directory (ask location/format once if not known). Every value must come
from files read this session — never from memory, which has held wrong IDs before (a user ID
recorded as the channel ID).

## Sources to read (read_file/search_files, no approval needed)

| What | Where |
|---|---|
| model, reasoning_effort, discord channel/mention, delegation.model, logging | `~/.hermes/profiles/<bot>/config.yaml` |
| role rules | `~/.hermes/profiles/<bot>/SOUL.md` |
| project rules | `<project>/AGENTS.md` |
| kanban global settings (dispatch interval, failure_limit) | `~/.hermes/config.yaml` → `kanban:` |
| board workdir | `~/.hermes/kanban/boards/<board>/board.json` (`default_workdir`) |
| services | `~/Library/LaunchAgents/ai.hermes.*.plist` |
| dispatcher owner | gateway log line "another gateway already holds the dispatcher lock" |

## Section order that worked

0. Change log (version / date / change / applied-or-pending) + backup paths
1. Overview table + topology flowchart; design principles table with rationale
2. Runtime processes (launchd labels, run command, logs, restart = approval)
3. Per-profile config comparison table (flag odd values like stale delegation models)
4. Rule layers diagram (SOUL always / AGENTS only when cwd is the project), role table,
   role-boundary example requests, shared rules, AGENTS summary by section
5. Kanban pipeline: scale modes, sequence diagram with the bounded review loop, severity
   table, round cap, per-stage responsibilities ending in a DECIDE stage owned by the user
   (plus any external decision model), and a decision-authority table
6. Session & cost operations (fresh session = new channel mention under auto-thread; `/new`
   only inside a thread; kanban workers are always fresh; cache; model-swap procedure)
7. Verification: load checks + numbered behavior tests
8. Known issues table with a Status column (unverified / not done / pending / resolved)
   and "what we deliberately did not adopt" with reasons
9. File map; appendix with any edit that could not be applied (exact patch text)

## Revising

- When comparing against an external agent-team template collection, adopt mechanisms that
  bound cost (severity levels, round caps, scale modes, explicit trigger/non-trigger examples,
  fixed behavior tests) and reject ones that multiply agents on a machine that can only run
  one heavy job at a time. Record both in the doc.
- Apply the adopted rules to SOUL.md files first (backups), then rewrite the doc marking each
  change applied vs pending — never describe an unapplied edit as live.
- When pending items get done later, patch the doc in place: flip the change-log status, strike
  resolved known-issue rows (`~~...~~` + "resolved"), relabel the appendix as "applied, for the
  record", and add a behavior-test results table (test / pass-fail / evidence / how it was run,
  and which tests were left for the user and why).
- `write_file` refuses to overwrite a file this session only wrote; `read_file` it first.
- When the user reports a step that happens outside the fleet (a final decision made with another
  tool/model), put it in the topology diagram as a dashed external node and in the sequence
  diagram as a `Note` after review — the doc must show where the pipeline's authority ends.
- When a project-rule drift is found during behavior tests (a standard stated in one bot's SOUL
  but only vaguely in AGENTS.md), fix it by making AGENTS.md the single explicit source and
  mark the known-issue row resolved.

## Revising after a structural change (folder move, rule split)

The doc drifts section by section, not just in the change log. Grep it for the old path, old
baseline version, `/new`, old AGENTS section numbers (`§1[0-3]`) and model ids, then list every
hit as a table (section / now says / should say) plus "records to add" and show it before
editing. Apply all replacements in one `execute_code` pass that asserts each old string exists
(fail loudly on drift), re-grep afterwards, and commit. Also: add a note that pre-change
change-log rows use the old section numbering instead of rewriting history; replace an
"appendix of pending patches" with a pointer once applied (git keeps it); add a "new project
start procedure" section; keep old test results as a dated subsection. An ops doc about the
fleet belongs in its own ops repo, not inside any project — see `ops-repo-publishing.md`; update
your memory pointer when it moves.

## Evolving the design from data ("발전시킬 방법")

Don't answer from the doc alone — mine the kanban DB first and anchor each proposal to a number:

```bash
q(){ sqlite3 -header -column ~/.hermes/kanban/boards/<b>/kanban.db "$1"; }
q "select assignee,status,count(*) from tasks group by 1,2"
q "select kind,count(*) from task_events group by 1 order by 2 desc"      # changes_requested, crashed, block_loop_detected, protocol_violation
q "select assignee,round(avg((completed_at-started_at)/60.0),1) from tasks where completed_at is not null group by 1"
q "select count(*),sum(model_override is not null),sum(reasoning_effort is not null),sum(workflow_template_id is not null) from tasks"
```

Then `hermes kanban create --help` to see per-task features the fleet never uses (`--model`,
`--skill`, `--goal`, `--max-runtime`, `--completion-contract`) and `hermes kanban --help` for
`stats`/`specify`/`decompose`. Classify causes before proposing fixes: read every
`changes_requested` reason (payload `reason`) and bucket them (real analysis defect / report or
doc omission / UI / spec error). A high reject share made of real defects means review is
working — the fix is a recurring-pitfall checklist in the project AGENTS.md (each pitfall with
example task IDs and the standard helper to use), not a gate script. Check timing before
proposing a decide stage: approval-blocks that stopped once decision authority entered SOUL need
no new stage. For crashes, check `gateway.log` for restarts at the same minute and the worker
log tail; reclaims with `stale_lock` are lost work on long runs (`--max-runtime`, split tasks).
Zero per-task model overrides → a routing rule (see `kanban-review-loop.md`); plus an ops-metrics section with a weekly check, crash triage, a runbook
(post-update checks, model swap, rollback), and splitting current-state from history. Rank by
impact, recommend "classify causes with data first", and hand log-synthesis analysis to the
reviewer bot.
