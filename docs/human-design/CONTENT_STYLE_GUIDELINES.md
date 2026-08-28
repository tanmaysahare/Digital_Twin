# CONTENT_STYLE_GUIDELINES.md

**Scope:** everything written outside the interface. The README, these specification documents, code comments, commit messages, the demo video script, the business proposal, and the pitch.
**Relationship to UX_WRITING_GUIDELINES.md:** that document governs strings in the product. This one governs everything else. They agree on voice and diverge on length.
**Last updated:** 2026-08-28

---

## 1. Voice

Write as an engineer explaining work to another engineer who will check it. Specific, quantified, willing to say what did not work.

The register to avoid is the one that submissions default to: confident, abstract, uncheckable. "Our solution leverages advanced AI to seamlessly transform manufacturing operations" contains no information. "The forecaster reached 0.74 precision and 27-minute median lead time on the SC-01 scenario over 200 replications, and produced 0.8 false alerts per simulated shift on the fault-free scenario" contains four checkable claims.

Prefer the second, always, including in the pitch. Judges have heard the first one all day.

---

## 2. Hard rules

1. **No em dashes.** Anywhere in the repository, in any file, including this one. Lint-enforced.
2. **No emoji.** Including in commit messages and README section headers.
3. **No banned marketing vocabulary.** The list in HUMAN_DESIGN_GUIDELINES.md rule 21 applies to prose as well as to UI strings. It is lint-enforced over Markdown.
4. **No exclamation marks.**
5. **Sentence case for headings.** Documents included.
6. **No lorem ipsum, no placeholder names.** If an example is needed, use a plausible plant value.
7. **Every quantitative claim is either measured, cited, or labelled as an assumption.** There is no fourth category.
8. **Cite with an ID.** Sources are listed in RESEARCH_SOURCES.md as `S-nn` and referenced by ID, so a claim can be traced in one step.

---

## 3. Rhythm, or how to not sound generated

Generated prose has a recognisable cadence. These are the patterns to break:

| Pattern | Example of the tell | Fix |
|---|---|---|
| Triads | "faster, smarter, and more reliable" | Say one thing, or say two things of different lengths |
| "Not just X, but Y" | "Not just a dashboard, but a decision engine" | Say what it is |
| Rhetorical question opener | "But what if the line could tell you first?" | Start with the point |
| Symmetrical paragraph lengths | Five paragraphs, each four sentences | Vary deliberately. A one-sentence paragraph is allowed and effective |
| Every paragraph starting with a subject noun | "The system... The model... The interface..." | Vary the opening |
| Summary sentence restating the paragraph | "In short, this means the twin is predictive." | Delete it |
| Hedging stacked on hedging | "It could potentially help to possibly reduce" | Commit, or state the uncertainty once and precisely |
| Abstract nouns doing the work | "enablement", "optimisation", "transformation", "capability" | Name the concrete thing |
| A colon before every list | Three consecutive paragraphs each ending in a colon and a bullet list | Write some of them as prose |

Read a page aloud. Where the rhythm is metronomic, break it.

---

## 4. Structure

**Lead with the answer.** First sentence of any section states the conclusion. Reasoning follows. Nobody reads to the end to find out what you decided.

**One idea per paragraph**, and let paragraph length vary with the idea.

**Tables for anything with more than three parallel items.** Prose for reasoning, tables for comparison, lists for sequences. Do not use bullets for reasoning; a bulleted argument is an argument with the connectives removed.

**Headings are navigational, not rhetorical.** "Where we would lose" beats "Challenges and considerations".

**Short documents where possible, but complete over short.** A specification that omits the awkward case is worse than a long one that covers it. Do not pad, and do not amputate.

---

## 5. Honesty rules

These matter more than style, and they are the reason to trust anything else in the repository.

1. **Label simulated data as simulated, every time it appears.** The README, every chart, every screenshot, the video. "Simulated line, 42 stations" appears in the interface header of the prototype and is not removable.
2. **Never present a modelled benefit as a measured one.** "Modelled at +14 units per day under the assumptions listed" is honest. "+14 units per day" is not.
3. **Report the null result.** The false alarm rate on the fault-free scenario appears next to every accuracy figure. A document that reports only successes is a document nobody senior reads twice.
4. **Attribute borrowed numbers.** The Siemens automotive downtime figure carries its source and its industry context. Numbers repeated from a secondary source say so.
5. **Distinguish what we built from what we specified.** The adapter interfaces for OPC UA and MQTT are designed and documented; they are not implemented. Every document that mentions them says so.
6. **Say what we do not know.** USER_RESEARCH.md Section 3 and PRD Section 10 exist for this. Do not quietly delete them when the pitch gets tight.
7. **No invented endorsements, no invented pilot results, no invented customers.** Obvious, and worth writing down.

---

## 6. Code comments and commit messages

**Comments** explain why, not what. The code says what. A comment explaining what a line does is either redundant or a sign the line needs rewriting.

Good:
```python
# Active period attribution needs an uninterrupted window, so a shift
# boundary resets the accumulator rather than spanning it. Roser et al.
# assume continuous operation; a two-shift line does not satisfy that.
```

Bad:
```python
# Loop through the stations
```

**Commit messages**: imperative mood, one line under 72 characters, a body if the reason is not obvious.

```
Reset active period accumulator at shift boundaries

Spanning a shift boundary inflated the accumulated active period for
whichever station happened to be running at 14:30, which made it look
like the constraint on every second-shift start.
```

No emoji, no conventional-commit prefixes with emoji, no "fix stuff".

---

## 7. The README specifically

The README is the first thing a judge reads and the only thing some will read. It is a deliverable, not documentation.

Required order:

1. **One sentence on what this is.** No preamble.
2. **What problem it solves**, in four sentences, with the concrete failure it addresses.
3. **How to run it.** Two commands. Before anything else technical, because a judge who cannot run it will not read the rest.
4. **What you will see**, mapping to the demo script in MVP_SCOPE.md.
5. **What is simulated and what is not.** Prominent, early, unavoidable.
6. **Architecture**, one diagram and a paragraph.
7. **How the prediction works**, one section per mechanism, honest about which are classical methods rather than novel.
8. **Evaluation results**, with the command to regenerate them.
9. **Limitations**, as a real section with real limitations.
10. **Repository layout.**
11. **Team and context.**

No badges beyond build status and licence. No animated GIF header. No "Features" section of one-line bullets with icons.

---

## 8. The pitch and the video

Same voice. Three additional rules:

1. **Show the product doing the thing before explaining how it works.** The forecast appearing 27 minutes before the stall is the argument. The method is the answer to the first question afterwards.
2. **Include the quiet shift.** Ten seconds showing the system saying nothing on a normal shift is more persuasive to an operations audience than a minute of alerts, because it is the part nobody else does.
3. **Show a failure.** Open the scorecard and show a predictor sitting in shadow mode because it has not earned promotion. That single moment separates a team that understands the problem from a team that has built a demo.

---

## 9. Words and phrases with a house position

| Write | Not |
|---|---|
| digital twin | Digital Twin, DigitalTwin (except the product name DigitalTwin.ai) |
| the twin | our solution, the platform, the system (occasionally, for variety) |
| forecast | prediction, in UI copy |
| dark station | uninstrumented asset |
| read-only | non-intrusive, passive |
| simulated | synthetic, mock (in user-facing text; "mock" is fine in test code) |
| plant | facility, site (a site may contain plants) |
| we did not test this | further validation is required |
| this is an assumption | based on industry benchmarks |
| roughly, about | approximately (occasionally fine, not every time) |

---

## 10. Review checklist for any document

- [ ] Leads with the answer
- [ ] No em dash, no emoji, no exclamation mark, no banned vocabulary
- [ ] Every number is measured, cited with an `S-nn`, or labelled as an assumption
- [ ] Simulated data labelled as simulated
- [ ] Contains at least one thing we do not know or did not do, if the topic has one
- [ ] Paragraph lengths vary
- [ ] Tables used for comparison, prose used for reasoning
- [ ] Read aloud without wincing

---

**Related:** [UX_WRITING_GUIDELINES.md](UX_WRITING_GUIDELINES.md) · [HUMAN_DESIGN_GUIDELINES.md](HUMAN_DESIGN_GUIDELINES.md) · [../ai/CODING_STANDARDS.md](../ai/CODING_STANDARDS.md)
