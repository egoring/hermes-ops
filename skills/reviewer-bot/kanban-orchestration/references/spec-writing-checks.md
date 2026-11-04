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

## When the defect is in the spec
Say so in the request-changes reason ("defect in the spec reviewer wrote; coder
implemented it as specified") and still count the round. If the fix lands before the
affected arm trains, record it as a pre-registration amendment, not a post-hoc change.
