# Chat-session findings vs. an already-running review run

**Rule:** if you post a 🔴 finding as a card comment while that card's review run is already `(running)`, read the final approval/BLOCK text and confirm it explicitly addresses your finding. If it does not, do not treat the approval as covering it. Open a small follow-up card (`--parent <approved card>`) with the repro and closed-rule fix, and hold deployment until that follow-up card is approved.

**Why:** the review run may have loaded the card before your comment landed, or it may record your leak as an "accepted residual". Example: aitop100 PX5. The chat session showed that names ending in 비/료 (김은비) leaked through a suffix exemption. The run-2 approval listed it as a known residual instead. Follow-up card PX6 closed it with a closed cost-term list plus an accounting-header exemption, and the leak count went to 0/50.

**Steer the live review run instead of waiting for it.** When your chat check finds 🔴 items before the run has posted a verdict, write a comment that tells the run exactly what to do: "review worker: request-changes [round N/3] with these items only, add nothing else", then the numbered items, each with its evidence (the command output that proves it) and the exact fix. Mark the items that are your own spec errors as such. The run then bounces with your reasons in one round, instead of approving and leaving you a follow-up card. The default boilerplate "approve only" is for the no-🔴 case only.

**Also:** when your own earlier review/spec introduced the loophole, say so in the follow-up card and in the user report. The user values that attribution.

**Out-of-order wake-ups.** Gateway notifications can arrive late and out of order: a "handed off for review" message may land after the same card's "completed" message, or after you already acted on its result. Before re-verifying or re-reporting, run `hermes kanban --board <b> show <id>` (status) and `runs <id> | tail -2`. If the card is already `done` with an approval, reply in one or two lines ("already approved at HH:MM, verdict X, follow-up Y running") and do nothing else. Don't recompute, don't re-comment, and never create a follow-up card a second time.

## Two reviewers, one decision (step 6)

**Two reviewers, one decision.** A `request-review` also dispatches a separate reviewer run
on the card while you may be reviewing it from the chat. If both of you make a design
decision (a resolution, a threshold), they can disagree, and the child card starts on
whichever one landed first. After the dispatched review completes, read its summary before
you report. When the bounce lands and its fix rule differs from the one in your chat comment, post a reconciliation comment at once: name the rule the worker follows (normally the bounce's), withdraw the other in so many words, and attach your extras as 🟡 add-ons. A worker holding two conflicting specs implements one of them, or a mix, and the next round bounces again. On a conflict, pick one by the scarce resource (GPU quota, deadline). Then
comment the correction on any child card that already started, and check that nothing was
pushed under the losing value. Tell the user plainly that the two reviews disagreed and
which one you kept.

**Label a chat-side opinion as unofficial in the first line of the reply** (the chat reply itself, not only the card comment you posted) ("채팅 확인 — 공식 판정은 리뷰가 냄"), and give the dispatched run's state (running since, retries). This applies most to a clean result: "직접 확인했어요, 🔴 없음" with no label is exactly the line that gets read as the approval. A "🔴 없음" from the chat reads to the user as the verdict, and when the dispatched run is slow or requeued after a quota wall he asks why the result has not moved. Never open with "문제없이 통과했습니다" while the review run is live. A data-import card was told "passed" from the chat twice in a row, and the dispatched review bounced it both times.
The slip happens most when you answer a "handed off for review" wake-up. You verify, post the comment, see `runs <id>` print `(running)` in the same command, and still open the reply with the result. Make the label your reply's first line whenever that output shows a live review run, and add "공식 판정은 리뷰 실행(<시각> 시작)이 냄" before any 🔴 count.
A chat-side "🔴 0" means only that **the probes you ran** found nothing. When the fix under review was a rule you wrote, probing just the fix tests your own rule against itself. One example: a check that only confirmed "no rows with provider containing AI Studio" passed, and the dispatched review then found the same label error behind a different route name. Before the opinion, run one probe for the whole defect class (here: every route for that label), not just the string the bounce named. Then list in the reply what you did not probe.

**When the dispatched review approves without your 🔴, the defect still gets fixed.** Its
approval does not cancel a correctness defect you reproduced (e.g. a year column summed as a
measure). This includes an approval that records your finding as an accepted "remaining limit"
(e.g. "names ending in 비 pass, 4 cases"). A privacy leak you reproduced is not a limit the
review may accept for the user. Do not reopen the closed card. Open a small child card (`--parent <closed id>`)
that carries your reproduction as a test fixture and requires the old fixture outputs to stay
byte-identical, so no re-measurement is needed. Announce it as your call, not the review's.

**Clear 🟡 findings that change the configuration a queued measurement card will use, before that card runs.** Examples are a default to flip off, a parsing false positive, or a code path that skips the feature. A blind or mock run on a configuration you already plan to change measures something you will not ship, and its numbers cannot be reused. Insert one small card in front of the measurement with the insert recipe above (unlink/link). Give it numeric gates and a byte-identical check for the off path. Tell the user the new order. Leave 🟡 items that do not touch measured behaviour (docs, naming) for later.

**Hold code changes to measured behaviour until a running measurement card finishes.** A dispatched review may open a follow-up design card for the same module (e.g. a privacy fix) just as the mock or blind measurement starts. Comment on that design card: "its implementation card gets `--parent <measurement card>`". Comment on the measurement card: "record the rows this behaviour affected", e.g. every mask/warn line and the wrong answers caused by it. The measurement then scores one code state, and its output becomes the fix's input.

**Near the round cap, merge both reviewers' 🔴 into one fix.** The dispatched reviewer's bounce lists only what it found. When you hold a separate 🔴 with the same root cause (e.g. another variant family the detector misses), comment it onto the card in the same round. Label it "fix together, the cap is 3" and give one combined acceptance test. Otherwise round 3 fixes half, and you are left with a 4th rejection or a redesign.
When the dispatched review ships a **model** of its corrected rule (a scratch copy of the module), run your own earlier reproduction against that model before the worker starts implementing it. A model built from the reviewer's probes can still fail your case; then comment the missing condition as part of the same round.
A chat-side 🔴 posted after the dispatched review run has already started usually misses that run's bounce text. The worker fixes only what the bounce lists. As soon as the bounce lands, comment on the card: "fold the chat-side 🔴 (comment <time>) into this round; the next review treats it as 🔴". Restate its repro and gate in a few lines. Check its fix in the next round before anything else.
When the last allowed bounce goes out, tell the user in the same reply what happens if it fails too. Name the fallback you will recommend, usually shipping with the new behaviour switched off or narrowed to its safest form, and say what that costs. Then a failed final round turns into a decision for him, not another loop.
When he says to drop it because it is getting too complex, do not kill a round that is already running and nearly done (e.g. a worker porting a reviewer's model). Killing it leaves half the change in HEAD and needs a revert card. Comment on the card: "this is the last round; port only the given rule; record newly found gaps as limits in the work log, do not fix them; no further bounce on this card". Then give him the endpoint choice with numbers: ship the current state if every gate moved only in the improving direction (the remaining holes existed before the card), or revert the card's commits and ship without it. Tell him he can still say "stop now" and what that costs.
When he picks the redesign after the cap, `complete` the escalated card with the decision as its summary (e.g. "user decision: redesign in <new card>; current code stays deployed with the switch off"). A blocked parent would hold the redesign child forever. Then create the redesign card with `--parent <escalated id>`, and `link` it in front of every queued card and gate that should see the redesigned code (cleanup cards, final check). In its body, list every probe folder and reproduction from all earlier rounds as required regression tests.

Before re-running a long check yourself (an offline dry-run takes minutes), run `ps` for
the dispatched review's process. If it is already running the same check, do not start a
second copy. Two copies compete for the CPU, and a foreground shell call can hit its
timeout. Wait for the dispatched verdict instead, and reproduce its claim afterwards with
a cheap targeted probe (e.g. a tiny fixture for the one function in question).

While that dispatched review run is live, `hermes kanban complete` from the chat is usually
refused ("a live worker is running it"). Post your verdict as a `comment` (severity-tagged, with the
numbers you reproduced) and let the dispatched run close the card. Do not `--force` or
`reclaim` to get your own approval in: that kills the run mid-review and leaves the card
with a crashed run and two half-verdicts.
**Run `show` (status + latest Events) immediately before `complete`, and skip it if a review run
is `claimed`.** The refusal is not guaranteed: a chat `complete` once landed in the same minute
the dispatched reviewer issued `request-changes`, so the card read `done` while the worker was
already re-running the bounce. The bounced fix then lands on a closed card; inspect the file it
rewrote yourself, and put any remaining defect on a small child card (`--parent <closed id>`,
round number continued) instead of reopening. Tell the user the two verdicts collided.
`request-changes` from the chat is refused the other way round: it works only inside an
active review run ("task is not in an active review run"), so a card sitting in `review`
before the reviewer run starts cannot be bounced from the chat. Post the 🔴 as a comment
that says "bounce this in the review run", with the exact fix and any "do not re-run the
side effect (no second push)" line. If the missing item is separable from an
irreversible step the card already did, have it moved to its own small card rather than
re-running the original body.
