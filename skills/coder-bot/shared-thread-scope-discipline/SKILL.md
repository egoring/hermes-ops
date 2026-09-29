---
name: shared-thread-scope-discipline
description: Use when a thread implies another agent owns the task.
---

# Shared-thread scope discipline

## Trigger
The channel/thread name, a message, or context mentions another agent, model, or
session already owning the work (e.g. "opus가 시킨것만 해", "continue what X set up",
a thread title referencing an ongoing task you were not present for). Common in
multi-user/multi-agent Discord threads where several models or people collaborate
on the same project over time.

## Rule
1. **Do not silently reconstruct scope by exploring the filesystem/repo.** Grepping an
   entire project tree for keywords from the thread title and then acting on what you
   find is NOT the same as following instructions — it is guessing, and the user will
   correct you for doing unrequested work. Ask via `clarify` when the actual instruction
   is missing or ambiguous, even if you technically found related files.
2. **When told "you only do what X told you here" (or equivalent), treat it as a hard
   scope boundary, not a formality.** Stop independent investigation immediately, state
   plainly that you have no handoff/instruction from that source, and ask the user to
   paste or summarize the actual directive. Do not keep digging through files hoping to
   infer it — inference is what triggered the correction.
3. **One clarify round is enough before acting; do not re-clarify the same ambiguity
   repeatedly.** If the user answers with something generic ("continue the work",
   "완료되면 알려줘"), fall back to the most recent concrete, verifiable state you
   already produced in-session (e.g. a script's actual output) rather than expanding
   scope again — report status on what exists, don't invent new sub-tasks to fill the gap.
4. **Prefer real command/script output as your progress report over prose summaries of
   what the codebase might mean.** In these threads the value is verifiable state
   (checklist items backed by an actual run), not narrative about docs you read.
