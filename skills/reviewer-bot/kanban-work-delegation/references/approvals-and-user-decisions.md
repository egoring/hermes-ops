# Approvals, spending and recording user decisions

Depth for step 7 of SKILL.md (Let the human approve side effects).

**Batch the user's hands-on checks into one session.** When a new feature needs the user
to do something himself (send a chat command, register a key, eyeball one message), do
not ask him per card. Build it so it works without him, with the feature off by default
and a test double in the card's criteria. Then append his steps to the final acceptance
script and tell him they are queued there. He wants "build it all, then check once".

**Do not automate spending of a limited resource on a guessed schedule.** A cron or retry
loop that keeps spending quota (API credit, free-tier generation, GPU hours) is itself a
spending decision. Propose it with its trigger and cap, and arm it only after the user agrees.
Never base it on an unverified assumption such as "quota refills at 00:00 UTC". When the user
says he will check the quota himself, pause the cron, kill any run it already started (and
that run's children), confirm with `ps`, and report the row and cost delta that run produced.
An explicit event-triggered request ("submit X as soon as the pending one finishes") is that agreement, even under a standing "no auto-submit cron" rule. Record it as a one-time override. The worker extends the guarded script and writes fake-backend tests. You run those tests and one live read-only dry-run yourself, then arm the cron at once, because the trigger can fire any time. Do not wait for the dispatched review to arm it. Pause the cron if that review finds a 🔴, and remove it after it fires. The submit-specific recipe is in the project-competition-lifecycle skill, code-agent-eval-harness reference, §6b.

**A decision that conflicts with a source you flagged stays open until the user names the governing source.** When his answer matches one of two conflicting official statements (a mail vs the main page), ask which one rules before you push the value into cards, docs or skill notes. If he says he has asked a third party ("문의 남겼으니 냅두고"), mark the item "unconfirmed" everywhere: post a correction comment on every card you already instructed, and keep the safe default (run longer, do not rewrite dates). Do not apply your own recommendation to it.
When he later confirms the value, ask first whether he means the exact boundary ("11/1 24:00 = 11/2 00:00?"). Then resolve it everywhere in the same turn. Send a doc card for the rest, carrying the exact replacement lines and a grep criterion: no "unconfirmed" or old date left. Keep the protected-file line off the headless card; apply it yourself only after his approval. Also update any operational constant tied to it (an alert window) and your skill notes. Keep a safety margin past the confirmed end for uptime.

**Write a user decision into the project work log in the turn it is made.** When he relaxes
a criterion or a standing rule (accepting a missed floor, dropping a one-shot held-out),
open a small helper card that appends a `user decision (override): <what>, basis: <numbers,
card>` section verbatim and commits it. A decision recorded only in a card comment is
invisible to the next audit and gets flagged as a rule violation.
