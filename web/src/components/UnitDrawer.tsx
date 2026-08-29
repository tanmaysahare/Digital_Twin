'use client';

// The unit drawer and its process signature timeline. UX_SPEC.md Section 7,
// UI_COMPONENTS.md 26, WIREFRAMES/06.
//
// The timeline is the spine of this drawer and it is the visual answer to the
// thing that makes defects hard on an assembly line: a fault introduced at S12
// surfaces at G3, thirty stations and half an hour later. Reading down the
// column, the station that was out of its normal band is visible before the
// gate that caught it.
//
// Dark stations render hatched with an interval. Gates render as full-width
// rules, because a gate is not a station and drawing it as one would suggest
// the unit spent time there being worked on.

import { useEffect, useState } from 'react';
import { DataTable } from '@/components/DataTable';
import { Button, Notice, Value } from '@/components/primitives';
import { Drawer, ExportLink } from '@/components/frame';
import { api, exportUrls } from '@/lib/api';
import {
  clockShort,
  durationText,
  estimateShort,
  probability,
} from '@/lib/format';
import type {
  ContainedUnit,
  GateResult,
  RetroTrace,
  StationVisit,
  UnitDetail,
} from '@/lib/types';

function SignatureRow({
  visit,
  gate,
}: {
  visit: StationVisit;
  gate: GateResult | undefined;
}) {
  const dark = visit.cycle_time !== null && visit.cycle_time.provenance !== 'MEASURED';
  return (
    <>
      <li
        className={`flex items-baseline gap-3 border-b border-rule py-1 ${
          visit.outside_normal ? 'bg-paper-sunk' : ''
        }`}
      >
        <span className="numeral w-[46px] shrink-0 text-micro text-ink-2">
          {visit.station_id}
        </span>
        <span className="numeral w-[62px] shrink-0 text-small">
          {visit.cycle_time ? estimateShort(visit.cycle_time) : 'no data'}
        </span>
        <span className="numeral w-[62px] shrink-0 text-small text-ink-3">
          {visit.dwell_s !== null ? durationText(visit.dwell_s) : ''}
        </span>
        <span className="flex-1 text-small text-ink-3">
          {dark ? (
            <span className="inline-flex items-center gap-2">
              <span
                className="inline-block h-[10px] w-[28px] border border-rule bg-paper-sunk"
                aria-hidden="true"
              />
              bounded, not measured
            </span>
          ) : (
            visit.state_during.toLowerCase().replace(/_/g, ' ')
          )}
        </span>
        {visit.outside_normal ? (
          <span className="text-small text-state-drift">outside normal</span>
        ) : null}
      </li>
      {gate ? (
        <li
          className={`flex items-center justify-between border-y-2 py-1 ${
            gate.passed ? 'border-y-rule-strong' : 'border-y-state-defect'
          }`}
        >
          <span className="numeral text-small">
            {gate.gate_id} {gate.passed ? 'passed' : 'failed'}
          </span>
          <span className="numeral text-small text-ink-3">
            {clockShort(gate.at)}
          </span>
        </li>
      ) : null}
    </>
  );
}

function ContainmentList({
  title,
  rows,
}: {
  title: string;
  rows: ContainedUnit[];
}) {
  if (rows.length === 0) {
    return (
      <p className="text-small text-ink-3">
        {title}: none carried the same evidence.
      </p>
    );
  }
  return (
    <div>
      <h4 className="text-label text-ink-2">
        {title} ({rows.length})
      </h4>
      <DataTable<ContainedUnit>
        rowKey={(row) => row.unit_id}
        maxRows={6}
        columns={[
          {
            key: 'unit',
            header: 'Unit',
            render: (row) => <span className="numeral">{row.unit_id}</span>,
          },
          { key: 'at', header: 'At', render: (row) => row.at },
          {
            key: 'similarity',
            header: 'Similarity',
            numeric: true,
            render: (row) => probability(row.similarity),
          },
          {
            key: 'evidence',
            header: 'Evidence',
            render: (row) => (
              <span className="text-small text-ink-2">
                {row.evidence.join('; ')}
              </span>
            ),
          },
        ]}
        rows={rows}
      />
    </div>
  );
}

export function UnitDrawer({
  lineId,
  unitId,
  onClose,
}: {
  lineId: string;
  unitId: string | null;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<UnitDetail | null>(null);
  const [trace, setTrace] = useState<RetroTrace | null>(null);
  const [tracing, setTracing] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    setTrace(null);
    setProblem(null);
    if (!unitId) {
      setDetail(null);
      return;
    }
    let live = true;
    api
      .unit(lineId, unitId)
      .then((body) => {
        if (live) setDetail(body);
      })
      .catch((failure: unknown) => {
        if (live) {
          setProblem(
            failure instanceof Error
              ? failure.message
              : 'This unit could not be read.',
          );
        }
      });
    return () => {
      live = false;
    };
  }, [lineId, unitId]);

  const runTrace = async () => {
    if (!unitId) return;
    setTracing(true);
    setProblem(null);
    try {
      setTrace(await api.retroTrace(unitId));
    } catch (failure) {
      setProblem(
        failure instanceof Error
          ? failure.message
          : 'The trace could not be run.',
      );
    } finally {
      setTracing(false);
    }
  };

  const gateAfter = (stationId: string) =>
    detail?.gates.find((gate) => gate.gate_id && gate.at && stationId)
      ? undefined
      : undefined;

  return (
    <Drawer open={Boolean(unitId)} title={unitId ?? ''} onClose={onClose}>
      {problem ? <Notice tone="attention">{problem}</Notice> : null}
      {detail ? (
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-1">
            <p className="text-body text-ink-2">
              Variant <span className="numeral">{detail.variant_id}</span> ·{' '}
              {detail.status.toLowerCase().replace(/_/g, ' ')} · entered{' '}
              <span className="numeral">{clockShort(detail.entered_at)}</span>
            </p>
            {detail.current_station_id ? (
              <p className="text-body text-ink-2">
                Currently at{' '}
                <span className="numeral">{detail.current_station_id}</span>
              </p>
            ) : null}
            {detail.part_lots.length > 0 ? (
              <p className="text-small text-ink-3">
                Part lots{' '}
                <span className="numeral">{detail.part_lots.join(', ')}</span>
              </p>
            ) : null}
          </div>

          {detail.risks.length > 0 ? (
            <section>
              <h3 className="text-section">Risk per remaining gate</h3>
              <div className="mt-2 flex flex-col gap-3">
                {detail.risks.map((risk) => (
                  <div key={risk.gate_id} className="flex flex-col gap-1">
                    <div className="flex items-baseline justify-between">
                      <span className="numeral text-body">{risk.gate_id}</span>
                      <Value estimate={risk.risk} digits={2} />
                    </div>
                    <p className="text-small text-ink-3">
                      <span className="numeral">{risk.stations_remaining}</span>{' '}
                      stations,{' '}
                      <span className="numeral">
                        {risk.minutes_remaining.toFixed(0)}
                      </span>{' '}
                      min remaining
                      {risk.dark_visits > 0
                        ? `, ${risk.dark_visits} of its visits so far were at stations with no machine data`
                        : ''}
                    </p>
                    <ul className="flex flex-col gap-1">
                      {risk.factors.map((factor) => (
                        <li key={factor.label} className="text-small text-ink-2">
                          {factor.label}
                          {factor.detail ? `: ${factor.detail}` : ''}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </section>
          ) : (
            <Notice>
              No gate ahead of this unit has a promoted model, so no risk is
              published for it.
            </Notice>
          )}

          <section>
            <h3 className="text-section">Process signature</h3>
            <p className="text-small text-ink-3">
              Every station this unit passed, in order. A hatched row is a
              station with no machine data, where the cycle time is a bound.
            </p>
            <ul className="mt-2 flex flex-col">
              <li className="flex gap-3 border-b border-rule-strong pb-1 text-label text-ink-2">
                <span className="w-[46px] shrink-0">Station</span>
                <span className="w-[62px] shrink-0">Cycle</span>
                <span className="w-[62px] shrink-0">Dwell</span>
                <span className="flex-1">State</span>
              </li>
              {detail.visits.map((visit) => (
                <SignatureRow
                  key={`${visit.station_id}${visit.seq}${visit.arrived_at ?? ''}`}
                  visit={visit}
                  gate={
                    detail.gates.find(
                      (gate) =>
                        gate.at &&
                        visit.departed_at &&
                        Math.abs(
                          new Date(gate.at).getTime() -
                            new Date(visit.departed_at).getTime(),
                        ) < 30000,
                    ) ?? gateAfter(visit.station_id)
                  }
                />
              ))}
            </ul>
          </section>

          {detail.has_retro_trace ? (
            <section>
              <h3 className="text-section">Retro-trace</h3>
              {trace === null ? (
                <div className="mt-2 flex flex-col gap-2">
                  <p className="text-small text-ink-3">
                    This unit failed a gate. The walk compares every station it
                    passed against what the rest of the line was doing at the
                    same time.
                  </p>
                  <div>
                    <Button onClick={runTrace} disabled={tracing}>
                      {tracing ? 'Walking back' : 'Walk it back'}
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="mt-2 flex flex-col gap-4">
                  <Notice tone="attention">{trace.disclaimer}</Notice>
                  <ol className="flex flex-col gap-2">
                    {trace.hypotheses.map((item) => (
                      <li key={item.rank} className="flex flex-col gap-1">
                        <span className="text-body">
                          <span className="numeral">{item.station_id}</span>{' '}
                          <span className="text-ink-3">({item.strength})</span>
                        </span>
                        <span className="text-small text-ink-2">
                          {item.description}, against{' '}
                          <span className="numeral">{item.population}</span>{' '}
                          comparable passages
                        </span>
                        {item.shared_attribute ? (
                          <span className="numeral text-small text-ink-3">
                            shared {item.shared_attribute.type.toLowerCase()}{' '}
                            {item.shared_attribute.value}
                          </span>
                        ) : null}
                      </li>
                    ))}
                    {trace.hypotheses.length === 0 ? (
                      <li className="text-small text-ink-3">
                        Nothing this unit did diverged from the contemporaneous
                        population by enough to report. That is an answer, and it
                        means the cause is not in the timing data.
                      </li>
                    ) : null}
                  </ol>
                  <ContainmentList title="On the line" rows={trace.on_line} />
                  <ContainmentList title="In the yard" rows={trace.in_yard} />
                  <ContainmentList title="Shipped" rows={trace.shipped} />
                  <ExportLink href={exportUrls.containment(detail.unit_id)}>
                    Export the containment list
                  </ExportLink>
                </div>
              )}
            </section>
          ) : null}
        </div>
      ) : null}
    </Drawer>
  );
}
