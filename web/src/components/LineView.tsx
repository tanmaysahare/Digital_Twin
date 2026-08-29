'use client';

// Line view. UX_SPEC.md Section 2, WIREFRAMES/01 and 02.
//
// Six regions: the strip across the top, actions and at-risk units below it,
// then output, the predictor record and data health across the bottom. Fixed
// viewport, no page scroll, because a supervisor walking past should see the
// whole thing without touching anything.
//
// The calm state is the designed state. Most shifts nothing is wrong, and this
// screen has to read then as a complete, well-set instrument saying the line is
// fine: 42 live cycle times, eight buffer levels, output against pace, the loss
// accounting, the predictor record and source health. Nothing is blank, nothing
// says "no data yet", and there is no illustration.

import { useEffect, useState } from 'react';
import { ActionRegion } from '@/components/ActionCard';
import { PaceBar, StackedBar } from '@/components/charts';
import { DataTable } from '@/components/DataTable';
import { LineStrip } from '@/components/LineStrip';
import { MetricLine, Notice, Value } from '@/components/primitives';
import { SandboxOverlay } from '@/components/SandboxOverlay';
import { StationDrawer } from '@/components/StationDrawer';
import { UnitDrawer } from '@/components/UnitDrawer';
import { Region } from '@/components/frame';
import { api } from '@/lib/api';
import {
  clock,
  durationText,
  estimateText,
  probability,
  shortUnit,
} from '@/lib/format';
import type { LineFeed } from '@/lib/useLine';
import type { Scorecard, UnitAtRisk } from '@/lib/types';

function PredictorRecord({ scorecard }: { scorecard: Scorecard | null }) {
  if (scorecard === null) {
    return (
      <p className="text-small text-ink-3">
        The ledger has not been scored yet.
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-2">
      {scorecard.totals.map((row) => (
        <li
          key={row.predictor}
          className="flex items-baseline justify-between gap-3"
        >
          <span className="text-body">{row.predictor.replace(/_/g, ' ')}</span>
          <span className="flex items-baseline gap-3">
            <span className="text-small text-ink-2">
              {row.state.toLowerCase()}
            </span>
            <span className="numeral text-small">
              {row.state === 'ACTIVE'
                ? `${row.true_positive} of ${row.true_positive + row.false_positive} right`
                : `${row.made} of ${row.required ?? 20} needed`}
            </span>
            {row.state === 'ACTIVE' && row.median_lead_min !== null ? (
              <span className="numeral text-small text-ink-3">
                {row.median_lead_min.toFixed(0)} min median lead
              </span>
            ) : null}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function LineView({ feed }: { feed: LineFeed }) {
  const { line, state, actions, risk, forecast, notices, waiting, failure } =
    feed;
  const [stationId, setStationId] = useState<string | null>(null);
  const [unitId, setUnitId] = useState<string | null>(null);
  const [sandboxFor, setSandboxFor] = useState<string | null>(null);
  const [sandboxOpen, setSandboxOpen] = useState(false);
  const [scorecard, setScorecard] = useState<Scorecard | null>(null);

  useEffect(() => {
    if (!line) return undefined;
    let live = true;
    const load = () => {
      api
        .scorecard(line.line_id)
        .then((body) => {
          if (live) setScorecard(body);
        })
        .catch(() => undefined);
    };
    load();
    const timer = window.setInterval(load, 20000);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [line]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && ['INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName)) {
        return;
      }
      if (event.key === 't') {
        setSandboxOpen(true);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  if (failure) {
    return (
      <div className="px-6 py-6">
        <Notice tone="attention">{failure}</Notice>
        <p className="mt-3 text-small text-ink-3">
          The interface holds the last state it had rather than clearing the
          screen. Nothing here is being estimated in the meantime.
        </p>
      </div>
    );
  }

  if (waiting || !state || !line) {
    return (
      <div className="flex flex-col gap-3 px-6 py-6">
        <h1>Building the line state</h1>
        <p className="max-w-[68ch] text-body text-ink-2">
          {waiting ??
            'The twin is reading the event stream and rebuilding what the line is doing.'}
        </p>
        <p className="text-small text-ink-3">
          Forecasts start once every station has produced enough cycles for a
          baseline. This is a normal condition on a cold start and it is what the
          screen shows rather than a spinner.
        </p>
      </div>
    );
  }

  const loss = state.loss_this_shift;
  const health = state.data_health;

  return (
    <div className="flex flex-col gap-6 px-6 py-4">
      <LineStrip
        state={state}
        forecast={forecast}
        zones={line.zones}
        gates={line.gates}
        selectedStationId={stationId}
        onSelectStation={(id) => setStationId(id)}
      />

      <div className="grid grid-cols-12 gap-8">
        <Region title="Actions" className="col-span-7">
          <ActionRegion
            actions={actions}
            onTestFix={(id) => {
              setSandboxFor(id);
              setSandboxOpen(true);
            }}
          />
          {notices.map((notice) => (
            <Notice key={notice.text} tone={notice.tone}>
              {notice.text} {notice.detail}
            </Notice>
          ))}
        </Region>

        <Region
          title="Units at risk"
          className="col-span-5"
          aside={
            risk
              ? `${risk.total} above ${probability(risk.threshold)}`
              : undefined
          }
        >
          {risk && risk.units.length > 0 ? (
            <DataTable<UnitAtRisk>
              rowKey={(row) => `${row.unit_id}:${row.gate_id}`}
              maxRows={8}
              onRowClick={(row) => setUnitId(row.unit_id)}
              columns={[
                {
                  key: 'unit',
                  header: 'Unit',
                  render: (row) => (
                    <span className="numeral" title={row.unit_id}>
                      {shortUnit(row.unit_id)}
                    </span>
                  ),
                },
                {
                  key: 'at',
                  header: 'At',
                  render: (row) => (
                    <span className="numeral">
                      {row.current_station_id ?? ''}
                    </span>
                  ),
                },
                {
                  key: 'gate',
                  header: 'Gate',
                  render: (row) => (
                    <span className="numeral">{row.gate_id}</span>
                  ),
                },
                {
                  key: 'risk',
                  header: 'Risk',
                  numeric: true,
                  render: (row) => <Value estimate={row.risk} digits={2} />,
                },
                {
                  key: 'left',
                  header: 'Remaining',
                  numeric: true,
                  render: (row) =>
                    `${row.stations_remaining} st · ${row.minutes_remaining.toFixed(0)} min`,
                },
                {
                  key: 'factor',
                  header: 'Top factor',
                  render: (row) => (
                    <span className="text-small text-ink-2">
                      {row.factors[0]?.label ?? 'no single factor stands out'}
                    </span>
                  ),
                },
              ]}
              rows={risk.units}
            />
          ) : (
            <div className="flex flex-col gap-2">
              <p className="text-body text-ink-2">
                No unit is above the risk threshold.
              </p>
              {risk?.highest_below_threshold ? (
                <p className="text-small text-ink-3">
                  Highest current risk{' '}
                  <span className="numeral">
                    {probability(risk.highest_below_threshold.risk_point)}
                  </span>{' '}
                  (
                  <span className="numeral">
                    {shortUnit(risk.highest_below_threshold.unit_id)}
                  </span>{' '}
                  at{' '}
                  <span className="numeral">
                    {risk.highest_below_threshold.current_station_id ?? ''}
                  </span>
                  , {risk.highest_below_threshold.gate_id}).
                </p>
              ) : (
                <p className="text-small text-ink-3">
                  No gate has a promoted model yet, so no unit risk is published.
                </p>
              )}
            </div>
          )}
        </Region>
      </div>

      <div className="grid grid-cols-12 gap-8">
        <Region title="Output and loss" className="col-span-4">
          <div className="flex flex-col gap-3">
            <MetricLine
              label="Units this shift"
              value={
                <span className="numeral">
                  {state.shift.completed} of {state.shift.target_units}
                </span>
              }
              context={state.shift.pace_note}
              tone={state.shift.pace_delta_units < 0 ? 'attention' : 'normal'}
            />
            <PaceBar
              completed={state.shift.completed}
              target={state.shift.target_units}
              paceUnits={state.shift.pace_delta_units}
            />
            <MetricLine
              label="Lost this shift"
              value={
                <span className="numeral">
                  {loss.accounted_min.toFixed(0)}
                </span>
              }
              unit="station min"
            />
            <StackedBar
              segments={Object.entries(loss.minutes).map(([key, value]) => ({
                key,
                value,
              }))}
              unit="min"
            />
            <p className="text-small text-ink-3">{loss.reconciliation}</p>
          </div>
        </Region>

        <Region title="Predictor record" className="col-span-4">
          <PredictorRecord scorecard={scorecard} />
          <p className="text-small text-ink-3">
            A predictor in shadow shows its progress towards the gate rather than
            a hit rate. An unpromoted hit rate invites the floor to trust
            something that has not been earned.
          </p>
        </Region>

        <Region title="Data health" className="col-span-4">
          <div className="flex flex-col gap-2">
            <MetricLine
              label="Sources"
              value={
                <span className="numeral">
                  {health.sources_live} of {health.sources_total} live
                </span>
              }
            />
            <MetricLine
              label="Last event"
              value={
                <span className="numeral">{clock(health.last_event_at)}</span>
              }
              context={`${durationText(state.age_s)} behind the line`}
              tone={state.age_s > 600 ? 'attention' : 'normal'}
            />
            <MetricLine
              label="Clock skew"
              value={
                <span className="numeral">
                  max {health.max_skew_s.toFixed(1)}
                </span>
              }
              unit="s"
            />
            <MetricLine
              label="Coverage"
              value={
                <span className="numeral">
                  {health.stations_reporting} of {state.stations.length}
                </span>
              }
              context={`${health.stations_dark_by_design} dark by design`}
            />
            {health.notes.map((note) => (
              <Notice key={note} tone="attention">
                {note}
              </Notice>
            ))}
            <p className="text-small text-ink-3">
              {state.replay.note} Forecast horizon{' '}
              <span className="numeral">
                {forecast ? forecast.horizon_min.toFixed(0) : '120'}
              </span>{' '}
              min at{' '}
              <span className="numeral">
                {forecast ? forecast.replications : 0}
              </span>{' '}
              replications
              {forecast?.output
                ? `, modelled output ${estimateText(forecast.output, 0)}`
                : ''}
              .
            </p>
          </div>
        </Region>
      </div>

      <StationDrawer
        lineId={line.line_id}
        stationId={stationId}
        onClose={() => setStationId(null)}
      />
      <UnitDrawer
        lineId={line.line_id}
        unitId={unitId}
        onClose={() => setUnitId(null)}
      />
      {sandboxOpen ? (
        <SandboxOverlay
          lineId={line.line_id}
          stations={state.stations}
          buffers={state.buffers.map((buffer) => ({
            buffer_id: buffer.buffer_id,
            capacity: buffer.capacity,
          }))}
          preselectStationId={sandboxFor}
          onClose={() => setSandboxOpen(false)}
        />
      ) : null}
    </div>
  );
}
