'use client';

// The station drawer. UX_SPEC.md Section 6, WIREFRAMES/05. AC-007.
//
// Two variants of one component rather than two components, so the dark case
// cannot be forgotten. The dark variant is the one that matters: it says in
// plain sentences what the twin knows, what it does not, and what it would cost
// to know it. A drawer that made a dark station look like a monitored one would
// undo the product's whole argument.

import { useEffect, useState } from 'react';
import { TimeSeriesChart } from '@/components/charts';
import { DataTable } from '@/components/DataTable';
import { SensorValueCard } from '@/components/SensorValueCard';
import { MetricLine, Notice, StateChip, Value } from '@/components/primitives';
import { Drawer } from '@/components/frame';
import { api } from '@/lib/api';
import {
  clockShort,
  durationText,
  probability,
  rangeText,
  stateWords,
} from '@/lib/format';
import type { ScorecardRow, StationDetail } from '@/lib/types';

function PredictorRows({ rows }: { rows: ScorecardRow[] }) {
  if (rows.length === 0) {
    return (
      <p className="text-small text-ink-3">
        No predictor has made a claim about this station yet.
      </p>
    );
  }
  return (
    <DataTable<ScorecardRow>
      rowKey={(row) => `${row.predictor}:${row.station_id}`}
      columns={[
        {
          key: 'predictor',
          header: 'Predictor',
          render: (row) => row.predictor.replace(/_/g, ' '),
        },
        {
          key: 'state',
          header: 'State',
          render: (row) => <StateChip state={row.state} />,
        },
        {
          key: 'record',
          header: 'Record',
          numeric: true,
          render: (row) =>
            row.state === 'ACTIVE'
              ? `${row.true_positive} of ${row.true_positive + row.false_positive}`
              : `${row.made} made, ${row.required ?? 20} needed`,
        },
      ]}
      rows={rows}
    />
  );
}

export function StationDrawer({
  lineId,
  stationId,
  onClose,
}: {
  lineId: string;
  stationId: string | null;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<StationDetail | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    if (!stationId) {
      setDetail(null);
      return;
    }
    let live = true;
    setProblem(null);
    api
      .station(lineId, stationId)
      .then((body) => {
        if (live) setDetail(body);
      })
      .catch((failure: unknown) => {
        if (live) {
          setProblem(
            failure instanceof Error
              ? failure.message
              : 'This station could not be read.',
          );
        }
      });
    return () => {
      live = false;
    };
  }, [lineId, stationId]);

  const station = detail?.station;
  return (
    <Drawer
      open={Boolean(stationId)}
      title={stationId ?? ''}
      onClose={onClose}
    >
      {problem ? <Notice tone="attention">{problem}</Notice> : null}
      {detail && station ? (
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-3">
              <StateChip state={station.state} />
              <span className="text-small text-ink-3">
                {detail.zone_name} · tier {station.tier} ·{' '}
                {durationText(detail.time_in_state_s)} in {stateWords(station.state)}
              </span>
            </div>
            <MetricLine
              label="Cycle time"
              value={<Value estimate={station.cycle_time} />}
              context={station.cycle_time?.basis}
            />
            <MetricLine
              label="Normal range"
              value={rangeText(detail.normal_range)}
              context={`${detail.cycles_recorded} cycles recorded${
                station.tier === 'C'
                  ? '. A station with no machine data never accumulates one.'
                  : `, ${detail.cycles_required} needed for a baseline.`
              }`}
            />
            {station.current_unit_id ? (
              <MetricLine
                label="Holding"
                value={
                  <span className="numeral">{station.current_unit_id}</span>
                }
              />
            ) : null}
          </div>

          <section>
            <h3 className="text-section">What the twin knows</h3>
            <ul className="mt-2 flex flex-col gap-2">
              {detail.knows.map((line) => (
                <li key={line} className="text-body text-ink-2">
                  {line}
                </li>
              ))}
              {detail.knows.length === 0 ? (
                <li className="text-small text-ink-3">
                  Nothing has been established about this station yet.
                </li>
              ) : null}
            </ul>
            {detail.does_not_know.length > 0 ? (
              <>
                <h3 className="mt-4 text-section">What it does not know</h3>
                <ul className="mt-2 flex flex-col gap-2">
                  {detail.does_not_know.map((line) => (
                    <li key={line} className="text-body text-ink-2">
                      {line}
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
          </section>

          {detail.cycle_series.length > 0 ? (
            <section>
              <h3 className="text-section">Recent cycles</h3>
              <TimeSeriesChart
                series={detail.cycle_series}
                band={detail.normal_range}
                markers={detail.markers}
                label={`Cycle time at ${station.station_id}`}
              />
            </section>
          ) : (
            <Notice>
              {station.tier === 'C'
                ? 'This station emits no cycle events, so there is no series to draw. Its bound comes from the stations either side.'
                : 'No cycles recorded here yet.'}
            </Notice>
          )}

          <section>
            <h3 className="text-section">Buffers either side</h3>
            <div className="mt-2 flex flex-col gap-2">
              {detail.buffer_upstream ? (
                <MetricLine
                  label={`${detail.buffer_upstream.buffer_id} upstream`}
                  value={
                    <span className="numeral">
                      {detail.buffer_upstream.occupancy.hi.toFixed(0)} of{' '}
                      {detail.buffer_upstream.capacity}
                    </span>
                  }
                  context={detail.buffer_upstream.trend.toLowerCase()}
                />
              ) : null}
              {detail.buffer_downstream ? (
                <MetricLine
                  label={`${detail.buffer_downstream.buffer_id} downstream`}
                  value={
                    <span className="numeral">
                      {detail.buffer_downstream.occupancy.hi.toFixed(0)} of{' '}
                      {detail.buffer_downstream.capacity}
                    </span>
                  }
                  context={detail.buffer_downstream.trend.toLowerCase()}
                />
              ) : null}
              {!detail.buffer_upstream && !detail.buffer_downstream ? (
                <p className="text-small text-ink-3">
                  No buffer is defined on either side of this station.
                </p>
              ) : null}
            </div>
          </section>

          <section>
            <h3 className="text-section">Predictor record here</h3>
            <div className="mt-2">
              <PredictorRows rows={detail.predictor_record} />
            </div>
          </section>

          {detail.sensor_card ? (
            <SensorValueCard card={detail.sensor_card} />
          ) : null}

          <section>
            <h3 className="text-section">Recent events</h3>
            {detail.recent_events.length === 0 ? (
              <p className="mt-2 text-small text-ink-3">
                Nothing has been recorded against this station in the window.
              </p>
            ) : (
              <ul className="mt-2 flex flex-col gap-2">
                {detail.recent_events.map((event) => (
                  <li key={`${event.at}${event.kind}`} className="text-body">
                    <span className="numeral text-small text-ink-3">
                      {clockShort(event.at)}
                    </span>{' '}
                    <span className="text-ink-2">{event.detail}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <p className="text-small text-ink-3">
            Confidence in this station&apos;s cycle time:{' '}
            <span className="numeral">
              {probability(station.cycle_time?.confidence ?? null)}
            </span>
            . {station.basis}
          </p>
        </div>
      ) : null}
    </Drawer>
  );
}
