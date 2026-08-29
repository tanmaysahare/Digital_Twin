'use client';

// The action region. UI_COMPONENTS.md 10 and 11, UX_SPEC.md Section 2.3,
// WIREFRAMES/01 and 02. AC-012, AC-016.
//
// Two things here are the product rather than the interface.
//
// The lead time is the single --text-display element on the screen, because it
// is the number that decides whether Priya can act at all. Everything else on
// Line view is smaller than it.
//
// The empty variant is a first-class variant, not a fallback. Most shifts have
// nothing wrong, and that state has to read as a complete instrument saying the
// line is fine rather than as a screen waiting for content. It states a
// positive fact with its supporting detail and it carries no illustration.
//
// Evidence expands inside the card rather than opening a drawer, so the user
// does not lose the card they were reading.

import { useState } from 'react';
import { TimeSeriesChart } from '@/components/charts';
import { Button, Notice, Value } from '@/components/primitives';
import { api } from '@/lib/api';
import { clockShort, probability } from '@/lib/format';
import type { Action, Actions, Evidence } from '@/lib/types';

function PredictorLine({ record }: { record: Action['predictor_record'] }) {
  return <p className="text-small text-ink-3">{record.note}</p>;
}

function EvidencePanel({ evidence }: { evidence: Evidence }) {
  const constraint = evidence.attribution.find((row) => row.is_constraint);
  const worst = Math.max(
    ...evidence.attribution.map((row) => row.average_active_s),
    1,
  );
  return (
    <div className="mt-4 flex flex-col gap-4 border-t border-rule pt-4">
      <TimeSeriesChart
        series={evidence.cycle_series}
        band={evidence.normal_range}
        markers={evidence.markers}
        label={`Cycle time at ${evidence.cause_station_id ?? 'the cause station'}`}
      />
      <div>
        <h3 className="text-label text-ink-2">Average active period</h3>
        <p className="text-small text-ink-3">
          The station that never waits is the one holding the line back.
          {constraint
            ? ` This method names ${constraint.station_id}.`
            : ' No station stood out in this window.'}
        </p>
        <ul className="mt-2 flex flex-col gap-1">
          {evidence.attribution.map((row) => (
            <li key={row.station_id} className="flex items-center gap-2">
              <span className="numeral w-[42px] text-micro text-ink-2">
                {row.station_id}
              </span>
              <span
                className="h-[8px]"
                style={{
                  width: `${(row.average_active_s / worst) * 60}%`,
                  background: row.is_constraint
                    ? 'var(--series-1)'
                    : 'var(--series-3)',
                }}
              />
              <span className="numeral text-micro text-ink-3">
                {row.average_active_s.toFixed(0)} s
              </span>
            </li>
          ))}
        </ul>
      </div>
      {evidence.buffer_id ? (
        <p className="text-small text-ink-3">
          Buffer {evidence.buffer_id} held{' '}
          <span className="numeral">
            {evidence.buffer_series[0]?.value.toFixed(0) ?? '0'}
          </span>{' '}
          units at the time of this forecast.
        </p>
      ) : null}
      <PredictorLine record={evidence.predictor_record} />
      <p className="text-small text-ink-3">
        Model {evidence.model_version}. Inputs hash{' '}
        <span className="numeral">{evidence.inputs_hash.slice(0, 12)}</span>.
        Recorded at {clockShort(evidence.made_at)}, before any decision about
        whether to show it.
      </p>
      {evidence.notes.map((note) => (
        <Notice key={note}>{note}</Notice>
      ))}
    </div>
  );
}

function InterventionForm({
  onCancel,
  onSubmit,
}: {
  onCancel: () => void;
  onSubmit: (what: string, when: string) => void;
}) {
  const [what, setWhat] = useState('');
  const [when, setWhen] = useState('');
  return (
    <form
      className="mt-4 flex flex-col gap-3 border-t border-rule pt-4"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(what, when);
      }}
    >
      <label className="flex flex-col gap-1">
        <span className="text-label text-ink-2">What was done</span>
        <input
          value={what}
          onChange={(event) => setWhat(event.target.value)}
          placeholder="floater assigned to S20"
          className="h-[36px] rounded border border-rule bg-paper px-2 text-body"
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-label text-ink-2">When</span>
        <input
          value={when}
          onChange={(event) => setWhen(event.target.value)}
          placeholder="09:34"
          className="numeral h-[36px] w-[120px] rounded border border-rule bg-paper px-2 text-body"
        />
      </label>
      <div className="flex gap-3">
        <Button variant="primary" type="submit">
          Record it
        </Button>
        <Button variant="quiet" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

export function ActionCard({
  action,
  onTestFix,
}: {
  action: Action;
  onTestFix: (stationId: string) => void;
}) {
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [loading, setLoading] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [logging, setLogging] = useState(false);
  const [logged, setLogged] = useState<string | null>(null);

  const showEvidence = async () => {
    if (evidence) {
      setEvidence(null);
      return;
    }
    setLoading(true);
    setProblem(null);
    try {
      setEvidence(await api.evidence(action.prediction_id));
    } catch (failure) {
      setProblem(
        failure instanceof Error
          ? failure.message
          : 'The evidence could not be read.',
      );
    } finally {
      setLoading(false);
    }
  };

  const isStall = action.kind === 'STALL_FORECAST';
  return (
    <article className="border-l-2 border-l-state-forecast bg-paper-raised p-4">
      <div className="flex items-start justify-between gap-6">
        <div className="flex min-w-0 flex-col gap-1">
          <h3 className="text-section">
            {isStall
              ? `Line stop likely at ${action.station_id}`
              : `${action.station_id} has drifted from its baseline`}
          </h3>
          {isStall ? (
            <p className="numeral text-body text-ink-2">
              {clockShort(action.window.from)} to {clockShort(action.window.to)}
              <span className="ml-3">
                probability {probability(action.probability)}
              </span>
            </p>
          ) : (
            <p className="numeral text-body text-ink-2">
              detected {clockShort(action.window.from)}
            </p>
          )}
          <p className="text-body text-ink-2">
            {action.cause.station_id
              ? `Cause: ${action.cause.station_id} ${action.cause.description}`
              : action.cause.description}
          </p>
          {!action.cause.agreement ? (
            <Notice tone="attention">
              The two attribution methods name different stations. Both are shown
              in the evidence rather than one being chosen.
            </Notice>
          ) : null}
          {isStall ? (
            <p className="text-body text-ink-2">
              At risk{' '}
              <Value estimate={action.expected_unit_loss} digits={0} /> units
            </p>
          ) : null}
        </div>
        {isStall ? (
          <div className="flex shrink-0 flex-col items-end">
            <span className="text-label text-ink-3">Lead time</span>
            <span className="numeral text-display leading-[var(--text-display-line)]">
              {action.lead_time_min.toFixed(0)}
            </span>
            <span className="text-small text-ink-3">min</span>
          </div>
        ) : null}
      </div>
      <div className="mt-4 flex flex-wrap gap-3">
        <Button variant="quiet" onClick={showEvidence} disabled={loading}>
          {loading ? 'Reading' : evidence ? 'Hide evidence' : 'Show evidence'}
        </Button>
        <Button
          variant="quiet"
          onClick={() => onTestFix(action.cause.station_id ?? action.station_id)}
        >
          Test a fix
        </Button>
        <Button variant="quiet" onClick={() => setLogging(true)}>
          We did this
        </Button>
      </div>
      {problem ? <Notice tone="attention">{problem}</Notice> : null}
      {logged ? <Notice>{logged}</Notice> : null}
      {logging ? (
        <InterventionForm
          onCancel={() => setLogging(false)}
          onSubmit={(what, when) => {
            setLogging(false);
            setLogged(
              `Recorded: ${what || 'an intervention'} at ${when || 'this cycle'}. ` +
                `It joins the ledger and will be scored against this forecast. ` +
                `Nothing was sent to the line.`,
            );
          }}
        />
      ) : null}
      {evidence ? <EvidencePanel evidence={evidence} /> : null}
      {action.degraded ? (
        <Notice>
          This forecast ran with fewer replications than configured, so its range
          is wider than usual.
        </Notice>
      ) : null}
    </article>
  );
}

export function ActionRegion({
  actions,
  onTestFix,
}: {
  actions: Actions | null;
  onTestFix: (stationId: string) => void;
}) {
  if (actions === null) {
    return (
      <p className="text-body text-ink-2">
        Waiting for the first forecast cycle.
      </p>
    );
  }
  if (actions.actions.length === 0) {
    return (
      <div className="flex flex-col gap-2">
        <p className="text-body text-ink-2">Nothing needs attention</p>
        <p className="text-small text-ink-3">{actions.calm_note}</p>
        {actions.learning_note ? (
          <Notice>{actions.learning_note}</Notice>
        ) : null}
        {actions.shadow_count > 0 ? (
          <p className="text-small text-ink-3">
            Forecasts held in shadow are recorded and scored. None is shown here
            until its predictor has cleared the promotion gate for that station.
          </p>
        ) : null}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      {actions.actions.map((action) => (
        <ActionCard
          key={action.prediction_id}
          action={action}
          onTestFix={onTestFix}
        />
      ))}
      <p className="text-small text-ink-3">
        {actions.shadow_count} further forecasts are in shadow and are not shown.
      </p>
    </div>
  );
}
