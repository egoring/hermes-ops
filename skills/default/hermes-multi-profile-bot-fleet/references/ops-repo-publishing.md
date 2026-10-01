# Ops docs repo: project-agnostic docs, kanban hygiene, publishing

## Keep fleet docs out of any project

Fleet operation (bots, gateway, rule layers, pipeline, runbook) is not project content. A doc
living in a project repo drifts into that project's vocabulary (paths, versions, thresholds) and
is invisible from the next project. Put it in its own repo (e.g. `~/hermes-ops`) and leave a
one-line "moved to …" stub at the old path (history stays in git).

Layout that worked (one topic per file, current state separate from history):

| File | Content |
|---|---|
| `docs/01_운영구조.md` | bots, runtime, per-profile config, rule layers + "what goes in which layer" table, pipeline, verification, behavior tests |
| `docs/02_프로젝트_연결.md` | attach a new project (folder + AGENTS.md + board), `terminal.cwd` options (switch per project / common parent / per channel), project AGENTS.md template |
| `docs/03_runbook.md` | weekly check, model swap, after `hermes update`, rule edits, task anomalies, notify cleanup, rollback locations |
| `docs/04_운영지표.md` | metric definitions, baseline, dated record table |
| `docs/05_결정기록.md` | D1… decisions with reason + rejected alternative; reversals add a new row |
| `docs/06_이슈.md` | open issues only; resolved ones as a one-line summary |
| `docs/변경이력.md` | dated changes + backup paths — **local only** (user preference; `.gitignore` it) |
| `projects/<name>.md` | the only place project facts (paths, board, current build pointer) appear |
| `scripts/kanban_metrics.py` | read-only board metrics (open DB with `file:…?mode=ro`) |
| `scripts/sync_skills.py` | snapshot own skills + SOUL.md into the repo with redaction + PII check |

When generalizing, grep the result for project words and replace examples with neutral ones;
never copy a version number into ops docs — point at the project AGENTS.md instead.

## Metrics worth tracking (from kanban.db)

Reject rate (tasks with ≥1 `changes_requested` / tasks with `review_requested`), rounds at cap,
`crashed`, `reclaimed` split by payload `stale_lock` (lost work) vs manual, `protocol_violation`,
`blocked`/`block_loop_detected` whose reason asks for user approval (should be 0 once decision
authority is in SOUL), share of tasks with `model_override`, per-profile median run minutes, open
tasks by age, and a weekly table via `strftime('%Y-%W', created_at,'unixepoch','localtime')`.
Record a baseline row before changing rules so the effect is measurable.

## Notify-subscription cleanup

Repeated gateway warnings `has no parent_chat_id anchor` come from notify subscriptions on long-
finished tasks. Back up `hermes kanban --board <b> notify-list --json`, then for every sub whose
task is `done`/`archived` run `notify-unsubscribe <task> --platform <p> --chat-id <c>
[--thread-id <t>]`; keep subscriptions on open tasks. Re-run `notify-list` to confirm.

## Publishing to GitHub without leaking identity

1. Scan before any push, both repos you might publish: secret patterns (Anthropic/GitHub/AWS
   keys, Discord bot token shape, private keys, platform API keys), sensitive files (`.env`,
   credential JSON such as `auth.json`), long numeric IDs (Discord user/channel), `/Users/<name>`,
   account names, big files (>5 MB), third-party code copies. Scan history too:
   `git log -p --all | grep -E …`. Report a per-repo table and a verdict (private ok / public ok
   after X / never public).
2. Code of a live project: private while it runs (its strategy leaks otherwise); third-party
   code needs a license check before going public.
3. Replace IDs in docs with placeholders (`<CHANNEL_ID>`, `<USER_ID>`) — originals stay in the
   live config/SOUL, so the fleet is unaffected.
4. `gh repo create <name> --private --source=. --remote=origin --push`; verify with
   `gh repo view … --json visibility,url` and `git ls-remote origin` matching local HEAD.
5. If anything identifying already landed in a commit, squash: `git checkout --orphan fresh &&
   git add -A && git commit … && git branch -D main && git branch -m main`, then re-grep
   `git log -p --all` (expect only the author email line) and `git push --force` — force push
   rewrites remote history, so ask first. Old commits linger on GitHub only by hash.

New scripts: use `#!/usr/bin/env python3` and re-exec into `~/.hermes/hermes-agent/venv` at
runtime; an absolute shebang leaks `/Users/<name>`. (Commit gating on the checker's exit code:
see "Including skills and SOUL.md".)

## Going public (private → public)

Run a full audit first and report it as a table (secrets, identity, active-project content,
broken refs, scripts run, README/LICENSE). Then:

1. **Active project content is the real leak, not keys.** Grep tracked files for
   project words, version tags, strategy vocabulary (seeds, opponents, win rate, pool, prices).
   Withhold files dense with live-project cases *in the sync script* (a `WITHHOLD` map that
   replaces the file with a "published after the project ends" stub, plus exact phrase → neutral
   phrase substitutions). The live skill in `~/.hermes` stays untouched, and the rule survives
   every future sync; release later by deleting the entry. Load the substitution pairs from a
   git-ignored local file (`public_subs_local.txt`, `original<TAB>replacement`, `\n` escaped) —
   a literal list in the tracked script publishes the very phrases it hides. Grep the pushed
   script for them afterwards.
2. **Real project connection info stays local.** `.gitignore` `projects/*.md` with
   `!projects/example.md`, publish only a blank template (connection table: folder, parent/project
   AGENTS.md, board + `default_workdir`, `terminal.cwd` option, env, work log; behavior-test
   table), `git rm --cached` the real files, and say "local only, template = example.md" in README
   and `02`. In every tracked doc, replace real project paths/board names with neutral examples
   (`~/work`, `~/work/webapp`, board `<보드>`/"메인 보드") — runbook commands, diagram labels,
   metric-table board names, decision-record wording and script usage lines included. Keep
   measured numbers; only the identifying names change.
3. Make the checker scan the **whole repo** (minus `.git`, the local deny/redact lists and the
   local-only changelog), not just the copied folders — docs and scripts leak too. Match
   private keys by header (`-----BEGIN [A-Z ]*PRIVATE KEY-----`), never the words "private key"
   under `re.I`, or prose about keys trips it. Don't deny-list the public GitHub handle — it is
   already in the repo URL and belongs in LICENSE.
4. README for strangers: one-paragraph what/why, an English summary line, "not a drop-in
   template — values verified on one setup at <version>", a "read these first" table. Add a
   LICENSE (MIT unless the user says otherwise).
5. Author identity is the user's choice — offer the noreply address
   (`gh api user --jq '"\(.id)+\(.login)@users.noreply.github.com"'`) but switch to the real
   email when asked (it links commits to the profile's contribution graph; mention it is
   publicly visible via `.patch`). Set it repo-local only and rewrite with
   `git rebase --root --exec "git commit --amend --no-edit --reset-author"`. After the force
   push, `git fetch --prune` before re-grepping — the stale remote-tracking ref still shows the
   old email.
6. **Squash to one commit before flipping visibility**: withheld originals and replaced
   phrases still sit in earlier private commits. Re-grep `git log -p --all` for the withheld
   phrases, then `git push --force`, then `gh repo edit <repo> --visibility public
   --accept-visibility-change-consequences --add-topic …`, and verify with `gh repo view
   --json visibility,licenseInfo,repositoryTopics`. Tell the user this is irreversible once
   forked.
7. **Per-folder descriptions in the GitHub file list** = the message of the last commit touching
   each path. A single squashed commit shows one message on every folder. Instead of one squash,
   rebuild as one commit per top-level folder: `git checkout --orphan x && git rm -r -f -q --cached .`
   (`-f` is required — without it the index clear aborts when any file has staged changes, and
   the chained per-folder commits then run with no HEAD)
   then `git add <dir> && git commit -m "<what this folder is>"` per folder (root files last),
   confirm `git diff --stat <old> HEAD` is empty, swap branches, force push, and verify each with
   `gh api "repos/<o>/<r>/commits?path=<dir>&per_page=1" --jq '.[0].commit.message'`. Tell the
   user future commits overwrite a folder's label, so commit per folder to keep them meaningful.
   For routine edits, reuse the folder's existing message (`git add docs && git commit -m "<docs
   label>"`) so the label survives without another force push; no history rewrite needed.
8. **"Remove project X entirely" means history too.** Grep content AND file names ever tracked
   (`git log --all --name-only --format= | sort -u | grep -i <x>`) — a file removed by a normal
   commit (e.g. an untracked-now `projects/<x>.md`) still sits in history. Neutralize remaining
   mentions in skill snapshots via the local substitution list (not by editing the live skill),
   then rebuild the per-folder commits and force push.
9. **Verify from an anonymous clone, not the working tree**: `git clone https://github.com/<o>/<r>
   <scratch>`, then in the clone count commits/files, grep `git log -p --all` for project words,
   IDs, secrets, withheld phrases, check no local-only file is tracked, compile the scripts, and
   `diff -rq --exclude=.git <clone> <repo>` — the only differences must be the known local-only
   files (changelog, `projects/<real>.md`, deny/redact/subs lists) and `__pycache__`. Report it
   as a table when the user asks "제대로 된 거 맞지?". Grep for the project's DOMAIN
   vocabulary too, not only its name: board names, game or domain nouns inside examples in
   skills (e.g. a role word from the game), and domain terms in metric tables. Each new doc edit
   can reintroduce a real board name, so re-run this after every change that touches docs.

## Filing upstream bug reports from ops findings

Keep drafts in `issue_drafts/` with: Hermes version + upstream commit (`hermes --version`),
OS, measured numbers, the code path read (file::function + the few lines), a suggested fix,
and Related links. Before filing, `gh search issues --repo NousResearch/hermes-agent "<terms>"`
for duplicates and cite the related ones. Strip local `<!-- … -->` memo comments into a scratch
body file, then `gh issue create --title "[Bug]: …" --body-file …`, confirm with `gh issue view`,
and replace the draft's memo with the issue URL. Filing is the user's call.

Follow-up: comment notifications arrive by email ("you authored the thread"). Check with
`gh issue view <n> --comments` and `gh pr view <n> --json state,mergedAt`. When maintainers say
it is fixed on main, verify locally (`git merge-base --is-ancestor <sha> HEAD` → not yet →
update → re-measure). Then post one comment with before/after numbers, versions and thanks
that names the people who triaged, and close it as completed. To add something to your own
comment later, edit it (`gh api -X PATCH repos/<o>/<r>/issues/comments/<id> -F body=@file`)
instead of posting a second one, so nobody gets notified again.

## Including skills and SOUL.md

Include only self-authored ops skills — from `~/.hermes/skills/` AND each profile's
`profiles/<bot>/skills/` (filter out names in `.bundled_manifest` and hub-installed ones). Leave
out project-specific skills (they carry strategy) and bundled/hub skills (they update and a
copy goes stale).

The live copy is always `~/.hermes`: the agent keeps patching skills, so the repo holds a
snapshot produced by a sync script, never a symlink target. The script copies skills + SOUL.md,
redacts SOUL at copy time (`<@\d{17,20}>` → `<@USER_ID>`, other long IDs → `<ID>`, local
`original<TAB>replacement` list for usernames), then scans every copied file and exits 1 on any
hit. Gate every commit/push on the checker's real exit code (`python3 scripts/sync_skills.py
--check && git commit … && git push`); piping it through `| tail -1` first swallows exit 1 and
the push goes out with the hit. Keep personal deny-words and the redaction list in git-ignored local files — putting
account names into the tracked script as a deny-list publishes them. Warn in the README never to
copy the repo's SOUL back into a profile (placeholders break the mention). Test the checker by
dropping a file with a known deny-word and confirming exit 1.
