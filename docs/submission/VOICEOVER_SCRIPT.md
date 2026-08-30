# VOICEOVER_SCRIPT.md

**Purpose:** the narration read over `DigitalTwin_demo.mp4`.
**Generated** by `tools/demo/voiceover_script.py` from `submission/demo/captions.json`. Do not edit by hand: edit the script in the tool and regenerate, or the timings stop describing the video.
**Runtime:** 3:30

---

## 1. How to read it

Start speaking as the caption card appears and carry on into the passage behind it. The card is a section marker rather than a rest, and a beat's whole slot is the card plus the footage after it.

Word counts assume 2.5 words a second, which is a deliberate, unhurried read. The station identifiers and the decimal figures are the part a listener needs time to take in.

Every line fits its slot with room to breathe.

**Written but not in this cut.** The recorder skips a beat whose screen the line did not produce. Re-record when it does, or leave the beat out and say nothing about it.

- Defect risk, before the gate that would catch it

---

## 2. The script

| In at | Beat | Words | Room for |
|---|---|---|---|
| 0:00 | A normal shift | 41 | 43 |
| 0:18 | Six of these stations emit nothing | 46 | 47 |
| 0:36 | A bound, not a number | 44 | 45 |
| 0:54 | The blind spot becomes a costed recommendation | 47 | 50 |
| 1:15 | A fixture wearing at S20 | 47 | 48 |
| 1:34 | What would help, compared against doing nothing | 48 | 48 |
| 1:54 | The stall forecaster has not cleared its gate | 47 | 48 |
| 2:13 | Plan view | 38 | 45 |
| 2:31 | Every predictor on this line is in shadow | 47 | 48 |
| 2:51 | Program view | 41 | 49 |
| 3:10 | The evidence | 20 | 22 |
| 3:19 | Closing card | 27 | 27 |

### 0:00  A normal shift

> This is a read-only digital twin of a forty-two station vehicle assembly line. Every number is simulated, from a model we wrote, and the header says so on every frame. Right now the line is fine, and the system says nothing.

*17.5 s of video. 41 words, room for 43.*

### 0:18  Six of these stations emit nothing

> Six of these forty-two stations have no instrumentation. S33 through S37, and S42. They are cross-hatched, not blank and not filled in with a plausible guess. Uneven sensor coverage is the condition of a real plant, and it is the problem we set out to solve.

*19.0 s of video. 46 words, room for 47.*

### 0:36  A bound, not a number

> Click S34 and the twin reports a range, not a number. It knows five dark stations share the time between S32 and S38. It cannot tell you how they split it, and it says exactly that, in plain language, rather than inventing a figure.

*18.0 s of video. 44 words, room for 45.*

### 0:54  The blind spot becomes a costed recommendation

> Scroll down and the blind spot turns into a decision. A sixty-five dollar photo-eye at S33 would resolve it, with the install effort and the next maintenance window. The cost is our assumption, not a quotation, and the card says so. The gap becomes a line item.

*20.1 s of video. 47 words, room for 50.*

### 1:15  A fixture wearing at S20

> This is the failure the product was built around. A fixture wearing at S20. Cycle time drifts from fifty-eight seconds to sixty-three over ninety minutes, stays inside specification, and trips no threshold alarm. Two detectors, EWMA and CUSUM, both have to fire before the twin says anything.

*19.5 s of video. 47 words, room for 48.*

### 1:34  What would help, compared against doing nothing

> Press T and the sandbox opens over the line, because the line does not stop for a dialog. Every option is compared against doing nothing, on the same replications from the same state, so the comparison is fair. The footer states the replication count and the state timestamp.

*19.4 s of video. 48 words, room for 48.*

### 1:54  The stall forecaster has not cleared its gate

> This is the most important part. Our stall forecaster does not work well enough. Precision is zero point two five against a target of zero point six, and median lead time is five minutes against fifteen. We show it on screen rather than quietly leaving it out.

*19.5 s of video. 47 words, room for 48.*

### 2:13  Plan view

> Plan view is the plant manager's screen. Where the constraint moved hour by hour, the loss Pareto under its reconciliation line, and the sensor investment queue, which exports as a CSV you can attach to a capital request.

*18.0 s of video. 38 words, room for 45.*

### 2:31  Every predictor on this line is in shadow

> The scorecard. Every predictor on this line is in shadow. Each is running and being scored, and not one of them reaches the floor. A model only becomes visible after it clears a precision and recall gate, station by station, and it demotes itself when it degrades.

*19.6 s of video. 47 words, room for 48.*

### 2:51  Program view

> Program view is the capital holder's screen. Site readiness scored from what each site actually emits, and a business case where every assumption carries its source and its uncertainty. It computes to zero here, because this line supplies no contribution margin.

*19.7 s of video. 41 words, room for 49.*

### 3:10  The evidence

> Every number in this video came from the running twin over HTTP while the recording was made. Nothing was staged.

*9.0 s of video. 20 words, room for 22.*

### 3:19  Closing card

> Five gates passed and two missed. Nothing was tuned to make a gate pass. The code is on GitHub, and the evidence pack regenerates with one command.

*11.0 s of video. 27 words, room for 27.*

---

## 3. What the narration must not do

- **Do not call a bound a measurement.** S34 has a range. Saying it takes a hundred and thirty seconds undoes the thing the beat exists to show.
- **Do not soften the stall forecaster.** It misses its gate. The line says so in the same tone as the rest, without apology and without a recovery clause after it.
- **Do not say the data is real.** The first beat states it is simulated, inside the first thirty seconds, which is what DEFINITION_OF_DONE.md Section 3 asks for.
- **Do not read the caption cards aloud.** They are already on screen and the narration says something different from them on purpose.
