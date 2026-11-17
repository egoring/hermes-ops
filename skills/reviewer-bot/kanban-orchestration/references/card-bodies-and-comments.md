# Getting a long spec into a card

Read when posting a long card body or a multi-line comment/reason.

Any multi-line comment/reason: write a file, pass `"$(cat f)"`; backticks inline in a double-quoted arg run as commands and silently drop text.

A multi-paragraph card body inlined as `--body "$(cat <<'EOF' ... EOF)"` can be refused by the
shell guard, which cannot prove the executable body of a large heredoc and blocks the whole
command. Do not fight it by shortening the spec. Two working paths, in order:

1. Write the body to a file with the `write_file` tool (not a shell heredoc), then
   `kanban create "<title>" --assignee X --body-file <path> --json`. `--body-file` is a real flag and
   avoids shell substitution entirely; `--body "$(cat <path>)"` is the fallback.
2. If that is still refused, create with a one-line stub body (`"스펙은 첫 코멘트 참조"` /
   "spec in first comment") and post the full spec as the first `kanban comment`. The worker
   reads comments, so nothing is lost.

**Give every body file a unique, descriptive name** (`/tmp/kb_<ver>_<purpose>.md`), never a short
generic one (`/tmp/kb_sub.md`). Generic paths get reused across sessions, and a stale file a later
step never overwrote has shipped a completely unrelated spec into three separate cards here — once
silently, because the card was archived before the worker ran. Before `create`, `grep -c` the
defining keyword of the intended topic against the file, and grep the keyword of the *wrong* topic
expecting 0; run that grep through the terminal, not through the same helper that just wrote it.

Always `kanban show <id>` afterwards to confirm the body or comment actually landed — a failed
`cat` inside the substitution yields an empty body and the CLI rejects it with a bare
"comment body is required". `show` echoes the opening body lines, which is the cheapest way to
catch a contaminated body before the worker starts.
- **A comment that fails with `'utf-8' codec can't encode characters ... surrogates not allowed`
  posted nothing.** Re-post it with the emoji written as words ("red 0 / yellow 2") and no
  `$(...)` substitutions inside the text, then confirm with "Comment added". Never assume the
  first attempt landed: the card record is what the next worker and the final check read.

## Card ids

- **Never announce a card id you did not see in tool output.** Run `create ... --json` in its own
  terminal call and print the parsed id on a line by itself. When `create` is chained with crons,
  comments and `notify-subscribe` in one call, the result can come back collapsed to a one-line
  summary, and the id never reaches you. Recover it with `kanban list | grep "<title keyword>"`
  and confirm with `show` before putting it in the reply or in a routing line.
