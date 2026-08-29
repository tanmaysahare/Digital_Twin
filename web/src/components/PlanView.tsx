'use client';

// Plan view. UX_SPEC.md Section 3, WIREFRAMES/03. AC-060 to AC-064.
//
// Rakesh's screen. Scrollable, dense, and it prints on A4 landscape without a
// separate export step. Different structure from Line view on purpose: this is
// a document he reads once a week and takes into a meeting, not an instrument
// he glances at.
//
// The reconciliation line under the Pareto is not optional. If the twin's loss
// accounting does not tie to the plant's own numbers, the twin has produced a
// second set of books and it has to say so rather than presenting them as
// settled.

import { useEffect, useState } from 'react';
import { Heatmap, StackedBar } from '@/components/charts';
import { DataTable } from '@/components/DataTable';
import { SensorValueCard } from '@/components/SensorValueCard';
import { Button, Notice, Select, StateChip, Value } from '@/components/primitives';
import { ExportLink, Region } from '@/components/frame';
import { api, exportUrls } from '@/lib/api';
import { causeWords, clock, dayAndClock, money, probability } from '@/lib/format';
import type {
  ConstraintMigration,
  LossPareto,
  Recommendation,
  Recommendations,
  Scorecard,
  ScorecardRow,
  SensorCard,
  SensorRecommendations,
} from '@/lib/types';

const RANGES = [
  { value: '4', label: 'Last 4 hours' },
  { value: '8', label: 'Last shift' },
  { value: '24', label: 'Last day' },
  { value: '168', label: 'Last week' },
];

export function PlanView({ lineId }: { lineId: string | null }) {
  const [hours, setHours] = useState('8');
  const [migration, setMigration] = useState<ConstraintMigration | null>(null);
  const [pareto, setPareto] = useState<LossPareto | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendations | null>(null);
  const [sensors, setSensors] = useState<SensorRecommendations | null>(null);
  const [scorecard, setScorecard] = useState<Scorecard | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [openCard, setOpenCard] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!lineId) return undefined;
    let live = true;
    setLoading(true);
    Promise.allSettled([
      api.constraintMigration(lineId),
      api.lossPareto(lineId, Number(hours)),
      api.recommendations(lineId),
      api.sensors(lineId),
      api.scorecard(lineId),
    ]).then((results) => {
      if (!live) return;
      const [a, b, c, d, e] = results;
      if (a.status === 'fulfilled') setMigration(a.value);
      if (b.status === 'fulfilled') setPareto(b.value);
      if (c.status === 'fulfilled') setRecommendations(c.value);
      if (d.status === 'fulfilled') setSensors(d.value);
      if (e.status === 'fulfilled') setScorecard(e.value);
      const failed = results.find((item) => item.status === 'rejected');
      setProblem(
        failed && failed.status === 'rejected'
          ? String((failed.reason as Error).message)
          : null,
      );
      setLoading(false);
    });
    return () => {
      live = false;
    };
  }, [lineId, hours]);

  if (!lineId) {
    return (
      <div className="px-6 py-6">
        <p className="text-body text-ink-2">Waiting for the twin.</p>
      </div>
    );
  }

  const cellFor = (station: string, period: string) =>
    migration?.cells.find((cell) => cell.station_id === station && cell.period === period)
      ?.share ?? 0;

  return (
    <div className="print-full-width flex flex-col gap-12 px-6 py-6">
      <div className="flex flex-col gap-3">
        <h1>Plan</h1>
        <div className="flex flex-wrap items-end gap-6">
          <Select label="Range" value={hours} options={RANGES} onChange={setHours} />
          <span className="text-small text-ink-3">
            {pareto
              ? `${dayAndClock(pareto.from_at)} to ${dayAndClock(pareto.to_at)}`
              : ''}
          </span>
        </div>
      </div>

      {problem ? <Notice tone="attention">{problem}</Notice> : null}
      {loading ? <p className="text-small text-ink-3">Reading the ledger.</p> : null}

      <Region
        title="Constraint migration"
        aside={migration?.current_constraint ?? undefined}
      >
        <p className="max-w-[68ch] text-body text-ink-2">
          Which station has been holding the line back, and whether it stays in one place.
          A constraint that moves every hour is a different problem from one that does
          not.
        </p>
        {migration ? (
          <>
            <Heatmap
              rows={migration.stations}
              columns={migration.periods}
              valueAt={cellFor}
              markRow={migration.current_constraint}
            />
            <p className="text-small text-ink-3">{migration.note}</p>
          </>
        ) : null}
      </Region>

      <Region
        title="Loss Pareto"
        aside={
          pareto ? (
            <ExportLink href={exportUrls.loss(lineId, Number(hours))}>Export</ExportLink>
          ) : undefined
        }
      >
        {pareto ? (
          <>
            <StackedBar
              segments={pareto.rows.map((row) => ({
                key: row.cause,
                value: row.minutes,
              }))}
              unit="station min"
            />
            <DataTable<{ cause: string; minutes: number; share: number }>
              rowKey={(row) => row.cause}
              density="regular"
              columns={[
                {
                  key: 'cause',
                  header: 'Cause',
                  render: (row) => causeWords(row.cause),
                },
                {
                  key: 'minutes',
                  header: 'Station minutes',
                  numeric: true,
                  render: (row) => row.minutes.toFixed(0),
                },
                {
                  key: 'share',
                  header: 'Share',
                  numeric: true,
                  render: (row) => probability(row.share),
                },
              ]}
              rows={pareto.rows}
            />
            <p className="max-w-[68ch] text-body text-ink-2">{pareto.reconciliation}</p>
            <p className="max-w-[68ch] text-small text-ink-3">
              The two sides of that line are computed independently: the causes from
              timestamps at instrumented stations, the total from production time against
              work recorded. They are allowed to disagree, and where they do the
              difference is shown rather than spread across the causes to make them add
              up.
            </p>
          </>
        ) : null}
      </Region>

      <Region title="Buffer and staffing recommendations">
        <p className="max-w-[68ch] text-body text-ink-2">
          Each row is modelled against doing nothing on shared replications. The
          assumptions are inline because a modelled effect whose assumption is hidden is a
          number nobody can argue with.
        </p>
        {recommendations ? (
          <>
            <DataTable<Recommendation>
              rowKey={(row) => row.rec_id}
              density="regular"
              columns={[
                {
                  key: 'change',
                  header: 'Change',
                  render: (row) => row.change,
                },
                {
                  key: 'effect',
                  header: 'Modelled effect',
                  numeric: true,
                  render: (row) => <Value estimate={row.modelled_effect} digits={0} />,
                },
                {
                  key: 'assumptions',
                  header: 'Assumptions',
                  render: (row) => (
                    <span className="text-small text-ink-2">
                      {row.assumptions.join(' ')}
                    </span>
                  ),
                },
              ]}
              rows={recommendations.rows}
              emptyNote={recommendations.note}
            />
            <p className="text-small text-ink-3">{recommendations.note}</p>
          </>
        ) : null}
      </Region>

      <Region
        title="Sensor investment queue"
        aside={
          <ExportLink href={exportUrls.sensorQueue(lineId)}>
            Export for a capital request
          </ExportLink>
        }
      >
        <p className="max-w-[68ch] text-body text-ink-2">
          Every blind spot on this line, ranked by what closing it is modelled to be
          worth. Costs are indicative and each row says whose assumption it is.
        </p>
        {sensors ? (
          <>
            <DataTable<SensorCard>
              rowKey={(row) => row.rec_id}
              density="regular"
              onRowClick={(row) =>
                setOpenCard(openCard === row.rec_id ? null : row.rec_id)
              }
              selectedKey={openCard ?? undefined}
              columns={[
                {
                  key: 'station',
                  header: 'Station',
                  render: (row) => <span className="numeral">{row.station_id}</span>,
                },
                {
                  key: 'unknown',
                  header: 'What is unknown',
                  render: (row) => (
                    <span className="text-small text-ink-2">{row.unknown}</span>
                  ),
                },
                {
                  key: 'option',
                  header: 'Proposed',
                  render: (row) => row.option_name,
                },
                {
                  key: 'confidence',
                  header: 'Confidence',
                  numeric: true,
                  render: (row) =>
                    `${probability(row.confidence_now)} to ${probability(row.confidence_projected)}`,
                },
                {
                  key: 'cost',
                  header: 'Indicative cost',
                  numeric: true,
                  render: (row) => money(row.indicative_cost_usd, sensors.currency),
                },
                {
                  key: 'effort',
                  header: 'Install',
                  numeric: true,
                  render: (row) => `${row.install_hours.toFixed(1)} h`,
                },
                {
                  key: 'window',
                  header: 'Next window',
                  render: (row) => <span className="text-small">{row.next_window}</span>,
                },
                {
                  key: 'value',
                  header: 'Modelled annual value',
                  numeric: true,
                  render: (row) => (
                    <Value estimate={row.modelled_annual_value} digits={0} />
                  ),
                },
              ]}
              rows={sensors.recommendations}
              emptyNote="No station is both poorly observed and critical enough to justify a sensor."
            />
            <p className="text-small text-ink-3">{sensors.note}</p>
            {openCard ? (
              <div className="max-w-[420px]">
                <SensorValueCard
                  card={
                    sensors.recommendations.find(
                      (item) => item.rec_id === openCard,
                    ) as SensorCard
                  }
                  currency={sensors.currency}
                />
              </div>
            ) : null}
          </>
        ) : null}
      </Region>

      <Region title="Predictor scorecard">
        <p className="max-w-[68ch] text-body text-ink-2">
          Every predictor at every station. A row in shadow shows its progress towards the
          gate rather than a hit rate, and a demoted row says when it was withdrawn and
          why.
        </p>
        {scorecard ? (
          <>
            <DataTable<ScorecardRow>
              rowKey={(row) => `${row.predictor}:${row.station_id ?? 'line'}`}
              density="regular"
              maxRows={40}
              columns={[
                {
                  key: 'predictor',
                  header: 'Predictor',
                  render: (row) => row.predictor.replace(/_/g, ' '),
                },
                {
                  key: 'station',
                  header: 'Station',
                  render: (row) => (
                    <span className="numeral">{row.station_id ?? 'line'}</span>
                  ),
                },
                {
                  key: 'state',
                  header: 'State',
                  render: (row) => <StateChip state={row.state} />,
                },
                {
                  key: 'made',
                  header: 'Made',
                  numeric: true,
                  render: (row) => row.made,
                },
                {
                  key: 'precision',
                  header: 'Precision',
                  numeric: true,
                  render: (row) =>
                    row.precision === null ? (
                      <span className="text-ink-4">not published</span>
                    ) : (
                      probability(row.precision)
                    ),
                },
                {
                  key: 'recall',
                  header: 'Recall',
                  numeric: true,
                  render: (row) =>
                    row.recall === null ? (
                      <span className="text-ink-4">not published</span>
                    ) : (
                      probability(row.recall)
                    ),
                },
                {
                  key: 'lead',
                  header: 'Median lead',
                  numeric: true,
                  render: (row) =>
                    row.median_lead_min === null
                      ? ''
                      : `${row.median_lead_min.toFixed(0)} min`,
                },
                {
                  key: 'false',
                  header: 'False per shift',
                  numeric: true,
                  render: (row) =>
                    row.false_per_shift === null ? '' : row.false_per_shift.toFixed(2),
                },
                {
                  key: 'changed',
                  header: 'Last change',
                  render: (row) => (
                    <span className="text-small text-ink-2">
                      {row.state_changed_at ? clock(row.state_changed_at) : ''}{' '}
                      {row.state_reason ?? ''}
                    </span>
                  ),
                },
              ]}
              rows={[...scorecard.totals, ...scorecard.rows]}
            />
            <p className="text-small text-ink-3">
              Window {scorecard.window_days} days. A shadow row returns no precision even
              where one could be computed, because an unpromoted hit rate invites the
              floor to trust something that has not cleared its gate.
            </p>
          </>
        ) : null}
      </Region>

      <div className="no-print">
        <Button onClick={() => window.print()}>Print this view</Button>
      </div>
    </div>
  );
}
