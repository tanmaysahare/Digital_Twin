# DEMO_SCRIPT.md

**Purpose:** the shot list the demo video follows, and the record of how it was made.
**Video:** `submission/demo/DigitalTwin_demo.mp4`, built by `tools/demo/` and not
committed. The file is 6.9 MB and regenerable, so the repository carries the script and
the recorder rather than the output.
**Voiceover:** `docs/submission/VOICEOVER_SCRIPT.md`
**Runtime:** 3:30
**Last updated:** 2026-08-30

---

## 1. How it was made

The video is a screen recording of the running application reading the running API. It
is not a slideshow of screenshots and it is not a mock. `tools/demo/record_demo.mjs`
drives a real browser through the interface and refuses to start unless `GET /health`
reports the twin `LIVE`, so a recording of a loading state cannot be produced by
accident. Every value visible in the recording arrived over HTTP from the twin while the
recording was running.

`tools/demo/build_video.py` cuts the recording against the caption timings the recorder
logged and puts a caption card in front of each passage. The cards use the product's own
tokens: light, flat, no gradient, 2px radius, colour only where something is abnormal.

`tools/demo/voiceover_script.py` then writes the narration script against the cut the
build actually produced, taking its timecodes from the same `captions.json` and the same
build constants. The script and the video cannot drift apart, and a line too long for the
passage it plays over is reported as an overrun rather than discovered in the recording
booth.

To rebuild it, with the stack running as `docs/technical/RUNNING.md` Section 2.3
describes:

```
npm install playwright && npx playwright install chromium
node tools/demo/record_demo.mjs
python tools/demo/build_video.py
python tools/demo/voiceover_script.py
```

The recording is paced for narration: each beat holds long enough for a sentence to be
said over it rather than long enough to be read silently. `DEMO_PACE=read` records the
shorter silent cut instead, for a viewer reading the caption cards with no voice over
them.

---

## 2. The shot list

The order is the one `docs/product/MVP_SCOPE.md` Section 1 sets out and
`docs/quality/DEFINITION_OF_DONE.md` Section 3 requires: the quiet shift first, then the
drift, then the forecast, then the counterfactual, then the defect flow, then the dark
station, then the evidence, and a predictor in shadow.

| # | Beat | What is on screen | Why it is in the video |
|---|---|---|---|
| 1 | A normal shift | Line view, calm state. The action region reads that nothing needs attention | A system that always has something urgent to say is one nobody believes. This is the screen a supervisor sees most days and it is shown first |
| 2 | Six stations emit nothing | The strip, with S33 to S37 and S42 cross-hatched | The uneven coverage is the problem, not a footnote |
| 3 | A bound, not a number | Station drawer on S34: an interval, and the sentence that five stations share the bound and none can be separated | The single clearest statement of what the twin does and does not know |
| 4 | The blind spot becomes a costed recommendation | The Sensor Value Card, with the indicative cost and the sentence saying the cost is our assumption | The blind spot becomes an output rather than a limitation |
| 5 | A fixture wearing at S20 | The drift mark on the strip | The failure the product was built around, invisible to any threshold alarm |
| 6 | What would help | The counterfactual sandbox over the line strip, with its footer stating replications, runtime and state timestamp | A comparison against doing nothing, on the same seeds |
| 7 | Defect risk before the gate | The unit drawer, with the calibrated probability, the conformal interval and the top three factors | The lead time is in stations, which is what a supervisor can act on |
| 8 | The stall forecaster has not cleared its gate | Line view with the shadow count | The most important beat in the video. The measured miss is stated on screen rather than skipped |
| 9 | Plan view | Constraint heatmap, loss Pareto under its reconciliation line, sensor investment queue | The plant manager's screen, and the reconciliation that is allowed to disagree with itself |
| 10 | Every predictor is in shadow | The predictor scorecard | The trust ledger working by withholding, which is the shadow-mode moment |
| 11 | Program view | Site readiness and the business case with its assumptions and sensitivity | The capital holder's screen |
| 12 | The evidence | Closing card, drawn from `evaluation/metrics.json` at build time | Passed and missed gates on the same frame |

The closing card is generated from the metrics file rather than typed, so the numbers in
the video cannot drift from the numbers in the evidence pack.

---

## 3. What the video does not do

Recorded here rather than left for a viewer to notice.

- **The recorded file carries no audio.** `DEFINITION_OF_DONE.md` Section 3 asks for the
  simulated-data statement out loud in the first thirty seconds. The narration that
  satisfies it is read by a person over the video from
  `docs/submission/VOICEOVER_SCRIPT.md`, whose first line states the data is simulated at
  0:00. We were not willing to put a synthetic voice on a submission about honest
  reporting, so the voice is ours or there is none. Until that read is recorded and
  muxed, the statement stands on the first caption card, on every caption card, and on
  every frame through the application's own header marker.
- **There is no music, no stock footage and no animated logo.** Those the checklist asks
  us to avoid, and we have.
- **Nothing is sped up or cut mid-interaction.** The passages between cards are
  continuous recording at normal speed.
- **No stall forecast card appears**, because the stall forecaster has not cleared its
  promotion gate at any station. That is the product working, and beats 8 and 10 say so
  explicitly rather than editing around it.
- **Beat 7 is absent from the current cut.** The defect drawer needs a unit above the
  risk threshold and the replay had none: the highest risk on the line was 0.03. The
  recorder skips the beat rather than opening an empty drawer, and the narration for it
  is written and held in `VOICEOVER_SCRIPT.md` against a replay that produces one. Eleven
  beats, not twelve.
