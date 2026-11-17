# Writing numeric acceptance gates (and pre-checking results against them)

Use when a spec card carries numeric completion criteria, and when you pre-verify a worker's
numbers before the review run judges them.

## Check every gate against the spec's own constants before sending
- A throttle with a minimum interval T, fed a burst lasting D seconds, fires ceil(D/T)+1 times
  (the trailing coalesced refresh counts). "≤3 refreshes for a 5 s burst at T=2 s" cannot pass.
  Derive the bound from the constant, or drop one of them.
- A rediscovery period equal to a detection deadline leaves no margin (10 s rescan vs "≤10 s"
  passes at ~7 s and can reach ~10.8 s). Put the deadline at period + margin.
- A gate that a running unrelated worker can move (CPU, event counts) must state the conditions:
  tab count, which boards are active. Otherwise isolate the component in its own measurement.

## Match the gate to the measurement's resolution
- A "±10 % latency regression" gate needs old and new measured interleaved (old, new, old, …)
  plus a bootstrap CI narrower than the threshold. With n=10 run sequentially, pure noise read
  +18 %. Even n=30 interleaved gave a CI of ±15–20 %p, so neither "no change" nor "within
  10 %" could be decided. Size n from a pilot's variance, or write the gate on the CI
  ("upper CI bound ≤ +10 %").
- When the gate is unresolvable at the measured n, report it as "undetermined", not as
  pass or fail. Then let the user decide whether a larger-n re-measure is worth it.

## Define event metrics from one clock
- Define "spurious" and "missed" from the client's own log: each reaction has its trigger just
  before it, and each relevant trigger is followed by a reaction. Do not compare timestamps from
  two separate subscribers. Their clocks drift by hundreds of ms, which flips the sign and
  manufactures failures.

## Pre-verifying an event-driven result: check both directions
- "Every refresh had a triggering event" (no wasted work) says nothing about "every relevant
  event produced a refresh" (no silent stall). Look for a client log that simply ends while
  events keep arriving: that is a dead subscriber, often an error boundary that unmounted the
  live component.
- Also check whether a failure is reflected in the status the client reports. A dead tab whose
  mode still read "live" hid the stall from the measurement.
- A one-directional pre-check called a card "no defects", and the review run then found the
  stall. Do not tell the review worker "approve, no defects" until both directions are checked.

## Reading a review run's approval before you relay it
A review worker's "승인, 🔴 0" is not the same as "the user's ask is met". Read the whole summary before you report it.
- **Look for unmet items inside the approval.** Watch for phrases like "체크 N 미충족", "사용자가 정한다", "미검증", or "설계단계로 남김". Workers approve a card whose code is faithful to the spec even when a user-requested outcome failed, such as "real AI call: 0 successes" or a scenario that never exercises the requested path. Report each one as unmet, then go fix the root cause or put the decision to the user.
- **Re-classify "user decision" labels yourself.** A worker may hand a plain data defect to the user, for example a reply dated after the event it caused. If the fix is implied by the approved design (that is, it follows the design value), it is a defect: route it to a card. Only a real trade-off goes to the user.
- **Treat a moved checkpoint as a finding.** When an implementer makes failing expectations pass by changing the check (an earlier inspection date, a refreshed baseline) instead of the code, the review must say why the old expectation was wrong. If it doesn't, ask that question yourself before you approve.
- **Verify at the level the user consumes.** A component checker passing ("replies 21/21 supported") does not mean the demo path uses those inputs. Run the actual user-facing scenario and feed each input through the real entry point on a copy. Inputs bound to a checker-only fixture are rejected on the real flow, and only that run shows it.
