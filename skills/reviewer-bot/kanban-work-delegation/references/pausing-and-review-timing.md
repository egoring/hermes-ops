# Pausing cards and review-run timing (Hermes kanban v0.22.x)

## Pausing a todo card
- Running `hermes kanban block <id>` on a `todo` card fails with "cannot block". To pause todo or ready cards, use `hermes kanban --board B schedule <id> "<reason>" --ids <id2> ...`. This sets them to `scheduled`, and they will not be claimed. To resume, use `unblock`.
- When you `unlink` a parent, the child can turn `ready` for a moment and get claimed. Link the new parent first, then unlink the old one. If you must unlink first, check `runs <child>` right after.

## Chat-session findings vs. a review run already in flight
- A review worker reads card comments only at start. If you post a chat-session 🔴 after the run starts (even 40 s after), that run's verdict will usually miss it.
- After the verdict, post a short comment addressed to the next implementation round: "round N에 꼭 넣을 것: <finding> + 재현 + 관문". Before saying the reviewer's proposed model fixes it, re-run your repro against the reviewer's scratch model. In FX2 r1 the reviewer's model still failed the chat repro.

## Shell quoting
- If you pass a comment inline with `"..."`, bash executes any backticks inside it, and the text disappears. Always write the comment to a file and pass it as `"$(cat file)"`.
