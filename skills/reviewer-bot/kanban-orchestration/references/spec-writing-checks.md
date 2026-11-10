# Spec checks before handing a design card to the coder

A spec written from memory instead of from the code costs a full review round trip per
defect. Run these checks first.

## Search the repo for an existing implementation
Before specifying an augmentation, loader trick or blend step, grep the repo for the
same idea (`grep -rn "flip\|mirror" src/`). An earlier phase may already hold the correct
version (e.g. a full L/R mirror that reverses the sagittal channels, not a W-flip of the
cor/ax slots alone). Point the spec at that file as the reference.

## Check the semantics of a geometric change
A partial transform that leaves one view of a multi-view study unchanged produces
inconsistent inputs, not an augmentation, and a failed arm then reads as "the idea does
not work". Spell out each view's transform and the position/encoding updates
(e.g. pos -> 1-pos) in the spec.

## Read the code before an operational instruction
Resume, restart, kill or swap instructions to a running chain depend on what the code
saves and re-seeds. Read the state-save and seeding lines before writing "resume from
epoch N" (see project-competition-lifecycle compute notes on resumed seed replicates).

## Copying a public notebook
Pin the scored version (page `Best Score ... V<n>`), not whatever `kernels pull` returns,
and diff the whole blend cell, not one visible constant.

## Latency, throughput and resource gates (live systems, dashboards, services)
Spec these from the system's own constants and noise, or the report comes back with
FAILs that are spec/measurement artifacts and need a review round to untangle.
- **Derive count gates from the throttle constants.** With a min refresh interval of 2 s, a
  5–6 s burst yields ~3 throttled refreshes plus one trailing coalesced refresh = 4; a "≤3"
  gate fails a correct implementation. Write the expected count as
  `ceil(burst_len / min_interval) + 1` and pin the burst length (the CLI producing it may be
  slower than the stated window).
- **"Spurious action" gates need a causal log, not timestamp proximity.** Comparing a page's
  refresh time to an event time recorded by a separate subscriber with a strict `event <= refresh`
  window miscounts when the two clocks differ by ~0.5 s. Have the client log the triggering
  event next to the action (`event-hit` → `refresh`) and judge "action without a preceding
  relevant trigger"; if timestamps must be compared, allow a stated tolerance (±50 ms) both ways.
- **Load-time regression gates: interleaved A/B, n ≥ 30, same path.** A sequential before/after
  of n=10 medians gave +18% (3.7 ms) that an alternating old/new run of n=30 showed to be noise
  (−2.7%). Run old and new images side by side and alternate requests; state the gate on that.
- **Resource gates must name the load and separate the component.** "CPU ≤ 1%" with 5 tabs
  refreshing on every event measures request handling, not the watcher. Specify: component
  alone (instrumented or profiled), idle, and under a stated load (tab count, events/min), each
  with its own bound. Record other workers/boards active during the window — another card's
  heartbeats can dominate the event stream.
- **Add a failure-injection recovery gate for every live consumer.** Happy-path latency gates
  pass a client that freezes forever after one failed fetch. Spec: a fake upstream that returns
  k× 5xx then 200; the visible client must return to a live/polling state within a stated time
  (e.g. ≤60 s) with retries ≥5 s apart and 0 requests while hidden; plus a producer-side test
  where a read fails once and the change still surfaces on the next tick with no new write.
  Require the repro to fail on the old code and pass on the new.
- **Measurement that needs synthetic kanban activity cannot run inside a worker**
  (see worker-limits-and-test-boards.md); put the reviewer-run step in the first body.

## When the defect is in the spec
Say so in the request-changes reason ("defect in the spec reviewer wrote; coder
implemented it as specified") and still count the round. If the fix lands before the
affected arm trains, record it as a pre-registration amendment, not a post-hoc change.
