# Spec checks before handing a design card to the coder

A spec written from memory instead of from the code costs a full review round trip per
defect. Run these checks first.

## Contents

- Search the repo for an existing implementation
- Check the semantics of a geometric change
- Read the code before an operational instruction
- Copying a public notebook
- Latency, throughput and resource gates (live systems, dashboards, services)
- When the defect is in the spec
- Premise details: borrowed components and reused label mappings
- Throwaway feasibility probe
- Rejected approaches and multi-view augmentations
- Cards that spend paid API credit
- Regression gates whose input cannot exist on the box
- Quoting pipeline durations

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

## Premise details: borrowed components and reused label mappings

Part of "pre-verify the premise before assigning" (SKILL.md, Writing cards).

  For a component borrowed from someone else's code, the premise includes which branch
  actually runs with the mounted assets (manifest fields, Dataset version), not what
  its variable names suggest (recipe: the deadline-reader notes in the
  project-competition-lifecycle skill's public-notebooks reference). When the worker
  finds such a premise wrong, own it as a spec error in your review comment and approve
  the faithful execution.
  For a spec that reuses a label mapping on a new release of the same source ("only swap
  the column prefix", e.g. a later study visit), print each mapped column's distinct
  values in both releases before writing the card. A release can store a coarser value
  domain: integer grades with no 2.1/2.2 subgrades sent every grade 2 to the lower soft
  value, so the same lesion got 1.0 in one release and 0.6 in the other, and the
  experiment changed two variables at once. Put the fix in the card: a conditional mean
  computed in code from the finer release (asserted, not hard-coded), negative or
  unknown codes → NaN, and a check on the shared subjects that the soft means match and
  the binarised positive rate is unchanged. A shifted mean is a value-domain question
  before it is a cohort question; do not explain it by cohort or reader composition
  until both domains have been compared.

## Throwaway feasibility probe

- **For a small, well-defined rule, run a throwaway feasibility probe in your own scratch first**
  (a wrapper around the live artifact, never a repo edit) and set the card's thresholds below the
  probe's result on a DIFFERENT seeded seed list, reporting zero intersection. The probe also
  catches constants taken from memory (domain constants were wrong until checked against the
  source module). Name the probe file in the card as the reference implementation, and forbid
  importing it from the deliverable.

## Rejected approaches and multi-view augmentations

- **List already-rejected approaches by name** with a pointer to where they were rejected,
  so the worker doesn't re-propose them. Do the same search for your own design before
  writing it: grep the phase docs, data dirs AND `src/` for the same component (labeller, mapping,
  loss, augmentation/transform). A design that silently repeats a failed phase costs a full
  checker round, and the checker will flag it as 🔴. When an earlier implementation exists,
  cite it in the card as the reference instead of re-deriving the definition from memory.
  For a geometric augmentation on a multi-view input (several planes/series of one study
  fused by one model), define it so every view describes the same transformed object: a
  left/right mirror flips the in-plane width axis of the planes that show L/R, AND reverses
  slice order (channel order + position = 1 − pos) of the plane whose slice axis is L/R.
  Flipping only some views feeds the model contradictory views, so a FAIL would wrongly
  reject the augmentation itself. Anatomical label names (medial/lateral) do not swap under
  a mirror.

## Cards that spend paid API credit

- **A card that spends the user's paid API credit** (LLM labelling, hosted inference) gets a
  usage-based pilot gate with an extrapolated full-run cost cap, a cumulative cap checked before
  every batch, a pinned model id (stop if missing, never substitute), and a key-hygiene clause:
  the user stores the key in a 600 file himself; you check only mode, line count and prefix,
  never print it; the worker greps outputs and logs for the key prefix = 0 at the end.
  Recipe details: project-competition-lifecycle, plateau-levers reference, label section.
  Make the first API step a **single synchronous request with byte-identical params** (HTTP 200,
  `stop_reason` not `max_tokens`, the forced output block present, every field in-enum) before any
  batch. Params the API rejects fail every item of a batch: two 50-item pilots were lost this way,
  each costing a batch wait plus a review round (errored items are not billed). Let the worker drop a
  parameter the API names as unsupported/deprecated (max 2, documented and committed before any
  result) instead of blocking each time; repeated blocks send the card to triage. Known Anthropic
  quirks (10/2026): Opus 5.5 rejects `tool_choice` type `tool`/`any` (use `auto` + schema) and
  rejects `temperature`; a key not scoped to a workspace gets HTTP 400 without an
  `anthropic-workspace-id` header, so have the user create a workspace key with a spend cap.

## Regression gates whose input cannot exist on the box

- **Before writing a regression gate, confirm that its input can legally exist on the machine that runs it.** "Rebuild 5 competition studies with the new builder and compare to the old cache" cannot run on a box where the project rules forbid raw competition data. Gate instead on the builder's source md5 matching the commit that built the old cache, a build-twice determinism check, and recorded library versions.

## Quoting pipeline durations

- **Quote pipeline durations from the previous run's artifacts, not from impression.** Before
  telling the user how long a design→build→gates→review cycle takes, list the prior card's output
  dir by mtime (`ls -lT -tr`) and split wall time into first build, rejection rounds, and the final
  gate run. A guessed "10-12h" was really ~1h of gates plus ~2.5h of rework — and the rework,
  not the verification, is what a reusable/generalised tool removes. For a generalisation card,
  make byte-identical reproduction of the old artifact (md5) plus the old gate numbers the
  completion criteria, and keep the original scripts untouched as the reference.
