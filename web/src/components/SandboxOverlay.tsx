'use client';

// The counterfactual sandbox. UX_SPEC.md Section 5, WIREFRAMES/07.
// AC-030 to AC-034.
//
// An overlay, not a page, and it occupies the lower two thirds of the viewport
// so the line strip stays visible. The line does not stop for a dialog.
//
// The footer is not decoration. It states the replication count, the runtime
// and the timestamp of the state the run started from, and where replications
// were reduced to meet the latency budget it says so in the same place and the
// ranges widen visibly.
//
// Nothing here is applied. "Save as decision" records the choice so its effect
// can be scored later; it changes nothing on the line, and the confirmation
// says so in those words.

import { useState } from 'react';
import { Cross } from '@/components/icons';
import {
  Button,
  IntervalBar,
  Notice,
  NumberField,
  Select,
} from '@/components/primitives';
import { api } from '@/lib/api';
import { clock, estimateText, probability } from '@/lib/format';
import type {
  CounterfactualResult,
  Intervention,
  SandboxOption,
  Station,
} from '@/lib/types';

const TYPES = [
  { value: 'ADD_OPERATOR', label: 'Add an operator' },
  { value: 'REMOVE_OPERATOR', label: 'Take an operator off' },
  { value: 'CHANGE_TAKT', label: 'Change takt' },
  { value: 'CHANGE_BUFFER_TARGET', label: 'Change a buffer target' },
  { value: 'STATION_DOWN', label: 'Take a station down' },
];

interface Draft {
  id: number;
  type: string;
  stationId: string;
  bufferId: string;
  count: number;
  percent: number;
  minutes: number;
}

function toOption(draft: Draft): SandboxOption {
  const intervention: Intervention = { type: draft.type };
  if (draft.type === 'ADD_OPERATOR' || draft.type === 'REMOVE_OPERATOR') {
    intervention.station_id = draft.stationId;
    intervention.count = draft.count;
  } else if (draft.type === 'CHANGE_TAKT') {
    intervention.percent = draft.percent;
  } else if (draft.type === 'CHANGE_BUFFER_TARGET') {
    intervention.buffer_id = draft.bufferId;
    intervention.count = draft.count;
  } else if (draft.type === 'STATION_DOWN') {
    intervention.station_id = draft.stationId;
    intervention.minutes = draft.minutes;
  }
  return { label: labelFor(draft), interventions: [intervention] };
}

function labelFor(draft: Draft): string {
  if (draft.type === 'ADD_OPERATOR') {
    return `Add ${draft.count} operator at ${draft.stationId}`;
  }
  if (draft.type === 'REMOVE_OPERATOR') {
    return `Take ${draft.count} operator off ${draft.stationId}`;
  }
  if (draft.type === 'CHANGE_TAKT') {
    return `${draft.percent < 0 ? 'Slow' : 'Speed up'} takt by ${Math.abs(draft.percent)} percent`;
  }
  if (draft.type === 'CHANGE_BUFFER_TARGET') {
    return `Set ${draft.bufferId} to ${draft.count} places`;
  }
  return `Take ${draft.stationId} down for ${draft.minutes} min`;
}

export function SandboxOverlay({
  lineId,
  stations,
  buffers,
  preselectStationId,
  onClose,
}: {
  lineId: string;
  stations: Station[];
  buffers: { buffer_id: string; capacity: number }[];
  preselectStationId: string | null;
  onClose: () => void;
}) {
  const first = preselectStationId ?? stations[0]?.station_id ?? '';
  const [drafts, setDrafts] = useState<Draft[]>([
    {
      id: 1,
      type: 'ADD_OPERATOR',
      stationId: first,
      bufferId: buffers[0]?.buffer_id ?? '',
      count: 1,
      percent: -4,
      minutes: 10,
    },
  ]);
  const [result, setResult] = useState<CounterfactualResult | null>(null);
  const [running, setRunning] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  const run = async () => {
    setRunning(true);
    setProblem(null);
    setSaved(null);
    try {
      setResult(await api.counterfactual(lineId, drafts.map(toOption)));
    } catch (failure) {
      setProblem(
        failure instanceof Error
          ? failure.message
          : 'The comparison could not be run.',
      );
    } finally {
      setRunning(false);
    }
  };

  const save = async (label: string) => {
    if (!result) return;
    try {
      await api.markExecuted(result.run_id, label, '');
      setSaved(
        `Recorded as a decision: ${label}. Nothing was sent to the line: this product has no path to a control system.`,
      );
    } catch (failure) {
      setProblem(
        failure instanceof Error
          ? failure.message
          : 'The decision could not be recorded.',
      );
    }
  };

  const bounds = result
    ? [
        result.baseline_units.lo,
        result.baseline_units.hi,
        ...result.options.flatMap((item) => [item.units.lo, item.units.hi]),
      ]
    : [];
  const min = bounds.length ? Math.min(...bounds) : 0;
  const max = bounds.length ? Math.max(...bounds) : 1;

  return (
    <div
      role="dialog"
      aria-label="Test a fix"
      className="fixed inset-x-0 bottom-0 z-30 h-[66vh] overflow-y-auto border-t border-rule-strong bg-paper-raised shadow-overlay"
    >
      <div className="flex items-center justify-between border-b border-rule px-6 py-3">
        <h2 className="text-section">Test a fix</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="rounded p-1 hover:bg-paper-sunk"
        >
          <Cross />
        </button>
      </div>
      <div className="grid grid-cols-12 gap-8 px-6 py-4">
        <div className="col-span-5 flex flex-col gap-6">
          <h3 className="text-label text-ink-2">Intervention</h3>
          {drafts.map((draft, index) => (
            <div key={draft.id} className="flex flex-col gap-3 border-b border-rule pb-4">
              <Select
                label={index === 0 ? 'Type' : `Option ${index + 1}`}
                value={draft.type}
                options={TYPES}
                onChange={(value) =>
                  setDrafts((items) =>
                    items.map((item) =>
                      item.id === draft.id ? { ...item, type: value } : item,
                    ),
                  )
                }
              />
              {draft.type === 'ADD_OPERATOR' ||
              draft.type === 'REMOVE_OPERATOR' ||
              draft.type === 'STATION_DOWN' ? (
                <Select
                  label="Station"
                  value={draft.stationId}
                  options={stations.map((station) => ({
                    value: station.station_id,
                    label: station.station_id,
                  }))}
                  onChange={(value) =>
                    setDrafts((items) =>
                      items.map((item) =>
                        item.id === draft.id ? { ...item, stationId: value } : item,
                      ),
                    )
                  }
                />
              ) : null}
              {draft.type === 'CHANGE_BUFFER_TARGET' ? (
                <>
                  <Select
                    label="Buffer"
                    value={draft.bufferId}
                    options={buffers.map((buffer) => ({
                      value: buffer.buffer_id,
                      label: `${buffer.buffer_id} (${buffer.capacity} now)`,
                    }))}
                    onChange={(value) =>
                      setDrafts((items) =>
                        items.map((item) =>
                          item.id === draft.id ? { ...item, bufferId: value } : item,
                        ),
                      )
                    }
                  />
                  <NumberField
                    label="Places"
                    value={draft.count}
                    unit="units"
                    onChange={(value) =>
                      setDrafts((items) =>
                        items.map((item) =>
                          item.id === draft.id ? { ...item, count: value } : item,
                        ),
                      )
                    }
                  />
                </>
              ) : null}
              {draft.type === 'CHANGE_TAKT' ? (
                <NumberField
                  label="Change"
                  value={draft.percent}
                  unit="percent"
                  onChange={(value) =>
                    setDrafts((items) =>
                      items.map((item) =>
                        item.id === draft.id ? { ...item, percent: value } : item,
                      ),
                    )
                  }
                />
              ) : null}
              {draft.type === 'STATION_DOWN' ? (
                <NumberField
                  label="For"
                  value={draft.minutes}
                  unit="min"
                  onChange={(value) =>
                    setDrafts((items) =>
                      items.map((item) =>
                        item.id === draft.id ? { ...item, minutes: value } : item,
                      ),
                    )
                  }
                />
              ) : null}
            </div>
          ))}
          <div className="flex gap-3">
            <Button variant="primary" onClick={run} disabled={running}>
              {running ? 'Running' : 'Run'}
            </Button>
            <Button
              onClick={() =>
                setDrafts((items) => {
                  const previous = items[items.length - 1];
                  if (items.length >= 3 || previous === undefined) return items;
                  return [...items, { ...previous, id: Date.now() }];
                })
              }
              disabled={drafts.length >= 3}
            >
              Add another option
            </Button>
          </div>
          {drafts.length >= 3 ? (
            <Notice>
              Three options plus doing nothing is what this compares. Ranking more
              than that is a table rather than a decision.
            </Notice>
          ) : null}
        </div>

        <div className="col-span-7 flex flex-col gap-4">
          <h3 className="text-label text-ink-2">Result</h3>
          {problem ? <Notice tone="attention">{problem}</Notice> : null}
          {result === null ? (
            <p className="text-body text-ink-2">
              Nothing has been run yet. Every option is compared against doing
              nothing, on the same replications, from the same state.
            </p>
          ) : (
            <>
              <table className="w-full border-collapse text-body">
                <thead>
                  <tr className="bg-paper-sunk">
                    <th className="border-b border-rule px-3 py-2 text-left text-label text-ink-2">
                      Option
                    </th>
                    <th className="border-b border-rule px-3 py-2 text-right text-label text-ink-2">
                      Units in {result.horizon_min.toFixed(0)} min
                    </th>
                    <th className="border-b border-rule px-3 py-2 text-right text-label text-ink-2">
                      Difference
                    </th>
                    <th className="border-b border-rule px-3 py-2 text-left text-label text-ink-2">
                      Range
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-b border-rule">
                    <td className="px-3 py-1">Do nothing</td>
                    <td className="numeral px-3 py-1 text-right">
                      {estimateText(result.baseline_units, 0)}
                    </td>
                    <td className="numeral px-3 py-1 text-right text-ink-3">0</td>
                    <td className="px-3 py-1">
                      <IntervalBar
                        lo={result.baseline_units.lo}
                        hi={result.baseline_units.hi}
                        min={min}
                        max={max}
                        label="units if nothing is done"
                      />
                    </td>
                  </tr>
                  {result.options.map((option) => (
                    <tr key={option.label} className="border-b border-rule">
                      <td className="px-3 py-1">
                        {option.label}
                        <span className="ml-2 text-small text-ink-3">
                          rank {option.rank}
                        </span>
                      </td>
                      <td className="numeral px-3 py-1 text-right">
                        {estimateText(option.units, 0)}
                      </td>
                      <td className="numeral px-3 py-1 text-right">
                        {estimateText(option.delta, 0)}
                      </td>
                      <td className="px-3 py-1">
                        <IntervalBar
                          lo={option.units.lo}
                          hi={option.units.hi}
                          min={min}
                          max={max}
                          label={`units with ${option.label}`}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="flex flex-col gap-2">
                <h4 className="text-label text-ink-2">
                  Highest stall probability by station
                </h4>
                <ul className="flex flex-wrap gap-4">
                  {Object.entries(result.baseline_stall_probability)
                    .filter(([, value]) => value > 0.1)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 6)
                    .map(([station, value]) => (
                      <li key={station} className="text-small">
                        <span className="numeral">{station}</span>{' '}
                        <span className="numeral text-ink-2">
                          {probability(value)}
                        </span>
                        {result.options[0] ? (
                          <span className="numeral ml-1 text-ink-3">
                            to{' '}
                            {probability(
                              result.options[0].stall_probability[station] ?? 0,
                            )}
                          </span>
                        ) : null}
                      </li>
                    ))}
                  {Object.values(result.baseline_stall_probability).every(
                    (value) => value <= 0.1,
                  ) ? (
                    <li className="text-small text-ink-3">
                      No station reaches a stall probability above 0.10 in this
                      horizon.
                    </li>
                  ) : null}
                </ul>
              </div>

              <div className="flex flex-col gap-2">
                {result.options.map((option) => (
                  <div key={`${option.label}-assumptions`}>
                    <p className="text-small text-ink-3">
                      {option.label}: {option.assumptions.join(' ')}
                    </p>
                  </div>
                ))}
              </div>

              {result.degraded ? (
                <Notice tone="attention">{result.degraded_note}</Notice>
              ) : null}
              {saved ? <Notice>{saved}</Notice> : null}
              <div className="flex items-center justify-between gap-4 border-t border-rule pt-3">
                <p className="text-small text-ink-3">
                  {result.footer} Seed state{' '}
                  <span className="numeral">{clock(result.seed_state_at)}</span>.
                  Baseline and every option share their replications, which is
                  what makes the difference readable.
                </p>
                {result.options[0] ? (
                  <Button
                    onClick={() => {
                      const best = result.options[0];
                      if (best) void save(best.label);
                    }}
                  >
                    Save as decision
                  </Button>
                ) : null}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
