# DEFINITION_OF_DONE.md

**Purpose:** the checklists that decide whether something is finished. Three levels: a single change, a feature, and the Round 2 submission.
**Last updated:** 2026-08-28

---

## 1. A single change (pull request)

Every pull request satisfies all of these before merge.

### Code
- [ ] Does one thing. A pull request that changes the forecaster and the design tokens is two pull requests
- [ ] Every new function has a type annotation, and mypy passes in strict mode on changed files
- [ ] No new dependency without a line in the pull request description saying why the standard library or an existing dependency is insufficient
- [ ] No plant-specific value (station ID, capacity, threshold, tag name) added to code. Configuration only
- [ ] No use of a global random generator. Every draw comes from a seeded generator
- [ ] No new `Estimate` produced without a provenance
- [ ] No broad exception handler that swallows without re-raising or recording

### Tests
- [ ] New behaviour has a test that fails without the change
- [ ] The calm state is tested first for any new component
- [ ] Coverage on changed files does not fall
- [ ] Scenario tests still pass, including SC-06, the fault-free one

### Design rules
- [ ] The twelve checks in ../human-design/HUMAN_DESIGN_GUIDELINES.md Section 5 pass
- [ ] Lint suite passes with no suppressions added
- [ ] Any new user-facing string follows the checklist in ../human-design/UX_WRITING_GUIDELINES.md Section 7
- [ ] Any new component renders correctly in greyscale

### Accessibility
- [ ] axe-core reports no serious or critical violations on affected views
- [ ] Keyboard path exists and focus is visible for any new interactive element
- [ ] Target size and separation hold at the 1280 breakpoint
- [ ] No information is conveyed by colour alone

### Documentation
- [ ] If behaviour changed, the relevant document in `docs/` changed in the same pull request
- [ ] If a number in the README changed, the evaluation report was regenerated
- [ ] Commit messages follow ../human-design/CONTENT_STYLE_GUIDELINES.md Section 6

---

## 2. A feature

A user story is done when all of the following hold.

- [ ] Every acceptance criterion for the story passes, by ID, in ACCEPTANCE_CRITERIA.md
- [ ] The story's flow in ../product/USER_FLOWS.md works end to end, including its failure branches
- [ ] The relevant edge cases in EDGE_CASES.md are handled and tested
- [ ] Error paths produce messages meeting the ERROR_HANDLING.md standard
- [ ] The feature works at all four contexts in ../design/RESPONSIVE_DESIGN.md Section 1
- [ ] Visual regression baselines are updated deliberately, with the diff reviewed, not accepted blindly
- [ ] If the feature produces a prediction, it writes to the ledger and respects shadow mode. Verified at the API boundary
- [ ] If the feature displays a twin value, it renders provenance
- [ ] A person who did not build it can use it without being told how

That last item is checked by having another team member use it cold, for five minutes,
without narration. It catches more than the automated checks do.

---

## 3. The Round 2 submission

This is the list that decides whether we are finished.

**Status at the Round 2 cut, 2026-08-30.** A box is ticked only where the thing was
checked rather than assumed. An unticked box carries the sentence saying why, because an
unticked box with a reason is more use to a reader than a ticked one that is wrong.

### The prototype runs
- [ ] A clean machine with Docker installed reaches the seeded demo in under 5 minutes with `docker compose up`. **Not verified in this pass.** The stack was run as two processes rather than through Compose
- [x] The demo script in ../product/MVP_SCOPE.md Section 1 runs end to end without touching a terminal, with one difference: no stall forecast card appears, because the stall forecaster has not cleared its promotion gate at any station. The shadow-mode moment in step 9 is therefore the whole of steps 4 to 6 as well
- [x] It runs with no network connection. A design rule fails the build on any reference to a host outside the deployment, and the application loads no external script, style or font
- [ ] It runs on Windows, macOS and Linux. **Windows only.** Everything delegates to `tools/tasks.py` and there is no shell-specific step, but the other two were not run
- [x] A non-Docker path is documented and tested for the case where Docker is unavailable. Tested on Windows
- [ ] `make evaluate` regenerates the evidence pack in under 30 minutes. **It does not.** The last full run took about 40 minutes on this machine

### The prototype demonstrates the core mechanism
- [ ] SC-01: bottleneck forecast with median lead time between 20 and 40 minutes. **Median lead time is 5 minutes.** The cause is attributed correctly, to S20 rather than to the station that stalls; the lead time is not there and the README says so in its own table
- [ ] SC-02: at-risk units flagged at least 10 stations before the gate, and a containment list recalling at least 0.80 of affected units. **Half.** Defect risk lead time is 13 stations at G3, measured. The containment recall of 0.80 is asserted by a unit test on constructed data and has not been measured on SC-02 itself
- [x] SC-05: dark station handled with an interval and a Sensor Value Card. `docs/design/SCREENSHOTS/06-station-drawer-dark.png`
- [x] SC-06: at most one false stall alert per fault-free simulated shift. Measured at 0.70
- [x] The counterfactual sandbox returns a ranked comparison in under 5 seconds, and states the replication count and the runtime when it does not
- [x] At least one predictor is visibly sitting in shadow mode during the demo. Every one of them is
- [x] All three views are functional, none faked, no placeholder panels

### The evidence is checkable
- [x] Every quantitative claim in the README traces to a value in `evaluation/metrics.json`, checked one number at a time
- [x] The evaluation report includes the false alarm rate, the calibration curves, the lead-time distributions and the virtual sensor coverage
- [x] The evaluation report includes its own limitations section, in its own words
- [x] Seeds, configuration version and code version are recorded, and two runs produce identical numbers
- [x] Simulated data is labelled as simulated everywhere: the interface header, every screenshot, every export. Not the video, which does not exist

### The repository
- [x] Public at `github.com/tanmaysahare/Digital_Twin`
- [x] README follows the required structure in ../human-design/CONTENT_STYLE_GUIDELINES.md Section 7
- [x] README includes the "For your controls engineer" section from ../technical/SECURITY_REQUIREMENTS.md Section 9
- [x] README states plainly what is built and what is specified but not built
- [x] The full `docs/` specification set is committed
- [x] Licence file present
- [x] No secrets, no credentials, no `.env` committed. Verified by a scan of the full history, not just the head commit. The only committed file of that shape is `.env.example`, whose first line says that no secret in it is real
- [ ] CI passes on the default branch. **The work is on `master` and the default branch is `main`.** CI has not run against it

### The video
- [ ] 3 to 4 minutes
- [ ] Follows the demo script order: the quiet shift first, then the drift, then the forecast, then the counterfactual, then the defect flow, then the dark station, then the evidence pack, then a predictor in shadow
- [ ] Shows a real screen recording, not slides of screenshots
- [ ] States that the data is simulated, out loud, in the first thirty seconds
- [ ] Includes the moment where the system says nothing on a normal shift
- [ ] Includes the moment where a predictor is shown as not yet promoted
- [ ] No music over narration. No stock footage. No animated logo

### The business proposal
- [ ] Problem framing, solution design, target users, business case, phased roadmap, risks with mitigations. All six, because those are what Round 2 asks for
- [ ] Every number is measured, cited with an `S-nn` from RESEARCH_SOURCES.md, or labelled as an assumption
- [ ] The competitive position states where we would lose, not only where we win
- [ ] The risk section includes the risks that would embarrass us, not only the ones we have solved

### Quality gates
- [ ] Full test suite green
- [ ] Design rule lint green, with no suppressions anywhere in the repository
- [ ] Accessibility automated checks green, and both manual passes completed
- [ ] Dependency audit clean at high severity
- [ ] Every document in `docs/` reviewed against the checklist in ../human-design/CONTENT_STYLE_GUIDELINES.md Section 10

---

## 4. What we will not ship

Recorded so that the pressure of a deadline meets something written down.

- We will not ship a prediction claim we have not measured.
- We will not remove the false alarm rate from a page that shows an accuracy figure.
- We will not remove the shadow-mode demonstration from the video to make the demo look stronger.
- We will not drop the limitations section from the README or from the evaluation report.
- We will not relabel simulated results as anything other than simulated.
- We will not loosen a promotion gate to make a predictor look promotable.
- We will not add a dark theme, a gradient, or an AI sparkle icon.

If the deadline forces a cut, it comes from ../product/MVP_SCOPE.md Section 4, in order,
and never from this list.

---

**Related:** [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) · [TEST_PLAN.md](TEST_PLAN.md) · [../product/MVP_SCOPE.md](../product/MVP_SCOPE.md) · [../ai/TASKS.md](../ai/TASKS.md)
