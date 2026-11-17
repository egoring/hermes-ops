# Closing out a session

Depth for the Closing out a session section of SKILL.md.

When the user signals wrap-up ("세션정리", "summarize for next time", "hand this off"),
write a handoff document into the project's own docs directory rather than only answering in
chat. Structure that survives the context gap:

1. **Headline diagnosis** in one or two lines.
2. **Numbers you personally reproduced**, marked as such — distinguish them from worker
   claims you relayed.
3. **Artifacts produced**, with paths, hashes, and current state (merged / awaiting upload /
   experimental).
4. **Methodology lessons** — sample sizes that proved inadequate, classifiers that worked,
   replay fidelity you measured.
5. **Ranked next steps**, each with the identifier a future session needs to find the data
   again (group hash, file path, id list).
6. **A rejected list** with reasons and sources, so the next session does not re-propose
   what was already measured and killed.
7. **Board state and operational gotchas** hit during the session.

Attach the file to the chat as well as writing it — on platforms that render attachments the
user wants the downloadable artifact, not only the prose.

When the user asks for "everything so far as an md file" mid-project, build it from fresh
primary sources in the same turn (submission CSV, LB CSV, `git log`, zip sha256/size,
CHANGES files, result summaries, cron list, board `ls`), not from memory or the compacted
summary. Put the timestamp of the snapshot in the header, mark estimates as such, and
include a table of your own corrected claims and one of the final checks run.
Write it under the profile's `outbox/` (not the repo, and not `cache/scratch`) and attach it with
`MEDIA:`; committing it into the project is a separate decision for after the fact-check. Scratch
is pruned after 24 h idle, and a `MEDIA:` path that no longer exists is skipped silently. The user
then gets no file when he asks for it again the next day. Any deliverable he may re-download
goes to `outbox/`. If one vanished, rebuild it from the source, with current facts in its
header, rather than replaying the old text. For a competition, use these
sections:
- submission table: ref, UTC date, config, LB, pre-registered verdict
- completed phases, with measured numbers only
- in progress, with live counts
- decisions pending, each with your recommendation
- ops state: quota, slots left today, active crons, live cards
- risks and unverified items
- file locations

Re-poll the scored list right before writing: a score that lands while you write changes
the pending decisions. Lead the reply with it, and say which recommendation it weakens.
If he asks for it to be
checked, the check card is a pure fact-audit: every number traced to its source file,
mismatches returned as line number + doc value + source value + replacement text, and the
checker edits nothing.

Writing and revising that summary doc:
- **State each threshold once and derive every restatement from it.** A summary that says
  "±3 tasks are distinguishable" in one section and computes power 0.55 for +3 in another
  contradicts itself; write the computed section first and copy its conclusion verbatim.
  Give every quoted outside number its source (notebook slug, thread id, "participant
  claim" vs staff reply) and give every comparison its baseline ("−3 vs v6", not a bare "−8").
- **When state changes after the snapshot time** (a cron registered, a card approved),
  comment on the running check card that it happened after the snapshot, so the checker
  reports it as "changed since" instead of as an error.
- **Treat a checker's "unsupported" as a prompt to re-check, not to delete.** Open the
  primary source yourself; if it confirms the claim, keep it with the citation (a staff
  reply quoted verbatim), and delete only what nothing supports.
- **Revise as a versioned file**: copy the checked version to `<name>_v1.md`, mark the
  header "corrected v2 (check <card id>, N items)", add the doc itself to the corrections
  table, re-attach with `MEDIA:`, and list the fixes item by item in the reply, plus what
  the checker could not verify. A fix that belongs in the repo (a missing record) goes to
  a worker card in the same turn.

**"Didn't we decide X earlier?" — check the record before you answer.** Search the session
history: the profile's `state.db`, table `messages`, filtered by session_id and a keyword,
opened read-only. Also grep the user's shared documents and the project docs. Then quote
what was actually said. If nothing was decided, say so plainly. Give the reason the
premise doesn't hold (e.g. the data step uses no GPU at all), and ask whether the decision
was made in another chat. Agreeing from a vague memory plants a false decision in the plan.

If a conclusion recorded earlier in the same session was later refuted by your own analysis,
correct it in the handoff and say it was corrected. Carrying a superseded framing into the
handoff is how a wrong cause outlives the session that disproved it.
