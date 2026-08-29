'use client';

// Program view. UX_SPEC.md Section 4, WIREFRAMES/04. AC-070 to AC-072.
//
// Meera's screen. Narrower measure, more prose than the other two, designed to
// be projected. Different rhythm again: this one is an argument rather than an
// instrument or a report.
//
// Three rules from the specification are load-bearing here.
//
// Readiness bands are words, not a score out of ten, and a NOT READY site
// expands to exactly what is missing with the cost attached.
//
// Every assumption in the business case carries its source and its uncertainty.
// An assumption without a stated source is a number nobody can defend, and
// defending numbers is the whole of this job.
//
// The sensitivity table is mandatory. A case that does not show what it is
// sensitive to cannot be interrogated.

import { useCallback, useEffect, useState } from 'react';
import { DataTable } from '@/components/DataTable';
import { Button, NumberField, Notice } from '@/components/primitives';
import { Region } from '@/components/frame';
import { api } from '@/lib/api';
import { money, probability, signed } from '@/lib/format';
import type {
  BusinessCase,
  ReadinessComponent,
  Realised,
  RealisedRow,
  SensitivityRow,
  SiteReadiness,
  Sites,
  TopologyDraft,
  TopologyField,
} from '@/lib/types';

// AssumptionField. UI_COMPONENTS.md 29. The source note is not optional: it is
// rendered from the model, and the model refuses to hold an assumption without
// one.
function AssumptionField({
  label,
  value,
  unit,
  source,
  uncertainty,
  editable,
  onChange,
}: {
  label: string;
  value: number;
  unit: string;
  source: string;
  uncertainty: string;
  editable: boolean;
  onChange: (value: number) => void;
}) {
  return (
    <div className="flex flex-col gap-1 border-b border-rule pb-3">
      <NumberField
        label={label}
        value={value}
        unit={unit}
        disabled={!editable}
        onChange={onChange}
      />
      <p className="max-w-[68ch] text-small text-ink-3">{source}</p>
      <p className="max-w-[68ch] text-small text-ink-3">{uncertainty}</p>
      {!editable ? (
        <p className="text-small text-ink-3">
          Not editable: this value comes from the ledger and moves as the ledger
          fills.
        </p>
      ) : null}
    </div>
  );
}

function SiteRow({ site }: { site: SiteReadiness }) {
  const [open, setOpen] = useState(site.band === 'NOT READY');
  return (
    <div className="border-b border-rule py-3">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-baseline justify-between gap-4 text-left"
        aria-expanded={open}
      >
        <span className="text-body">
          <span className="numeral">{site.site_id}</span> {site.name}
        </span>
        <span className="text-label text-ink-2">{site.band}</span>
      </button>
      <p className="mt-1 max-w-[68ch] text-small text-ink-3">{site.note}</p>
      {open ? (
        <div className="mt-3 flex flex-col gap-3">
          <DataTable<ReadinessComponent>
            rowKey={(row) => row.name}
            density="regular"
            columns={[
              {
                key: 'name',
                header: 'Component',
                render: (row) => row.name.replace(/_/g, ' '),
              },
              { key: 'value', header: 'Measured', render: (row) => row.value },
              {
                key: 'score',
                header: 'Score',
                numeric: true,
                render: (row) => probability(row.score),
              },
              {
                key: 'weight',
                header: 'Weight',
                numeric: true,
                render: (row) => probability(row.weight),
              },
              {
                key: 'missing',
                header: 'What is missing',
                render: (row) => (
                  <span className="text-small text-ink-2">{row.missing}</span>
                ),
              },
            ]}
            rows={site.components}
          />
          {site.instrumentation_cost_usd > 0 ? (
            <p className="text-small text-ink-3">
              Instrumentation from this site&apos;s own sensor queue:{' '}
              <span className="numeral">
                {money(site.instrumentation_cost_usd, 'USD')}
              </span>
              , at indicative costs.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function ProgramView({ lineId }: { lineId: string | null }) {
  const [sites, setSites] = useState<Sites | null>(null);
  const [outcome, setOutcome] = useState<BusinessCase | null>(null);
  const [edits, setEdits] = useState<Record<string, number>>({});
  const [realised, setRealised] = useState<Realised | null>(null);
  const [topology, setTopology] = useState<TopologyDraft | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    Promise.allSettled([api.sites(), api.businessCase(), api.realised()]).then(
      (results) => {
        if (!live) return;
        const [a, b, c] = results;
        if (a.status === 'fulfilled') setSites(a.value);
        if (b.status === 'fulfilled') setOutcome(b.value);
        if (c.status === 'fulfilled') setRealised(c.value);
        const failed = results.find((item) => item.status === 'rejected');
        setProblem(
          failed && failed.status === 'rejected'
            ? String((failed.reason as Error).message)
            : null,
        );
      },
    );
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    if (!lineId) return undefined;
    let live = true;
    api
      .topology(lineId)
      .then((body) => {
        if (live) setTopology(body);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [lineId]);

  const recalculate = useCallback(
    async (next: Record<string, number>) => {
      setEdits(next);
      try {
        setOutcome(await api.recalculate(next));
      } catch (failure) {
        setProblem(
          failure instanceof Error
            ? failure.message
            : 'The case could not be recalculated.',
        );
      }
    },
    [],
  );

  return (
    <div className="mx-auto flex max-w-[1100px] flex-col gap-12 px-6 py-6">
      <h1>Program</h1>
      {problem ? <Notice tone="attention">{problem}</Notice> : null}

      <Region title="Site readiness">
        <p className="max-w-[68ch] text-body text-ink-2">
          Scored from what each site emits rather than from a survey. A site that
          has not been connected is scored on its line definition alone and says
          so, because a component that could not be measured is not a component
          that scored badly.
        </p>
        {sites ? (
          <>
            <div>
              {sites.sites.map((site) => (
                <SiteRow key={site.site_id} site={site} />
              ))}
            </div>
            <p className="max-w-[68ch] text-small text-ink-3">
              {sites.computed_from}
            </p>
          </>
        ) : null}
      </Region>

      <Region title="Business case">
        <p className="max-w-[68ch] text-body text-ink-2">
          Every assumption carries its source and its uncertainty. Forecast
          precision is the value measured from the ledger, not a target: if no
          predictor has been promoted, it is zero and the case computes to zero.
        </p>
        {outcome ? (
          <div className="grid grid-cols-12 gap-8">
            <div className="col-span-6 flex flex-col gap-3">
              <h3 className="text-section">Assumptions</h3>
              {outcome.assumptions.map((item) => (
                <AssumptionField
                  key={item.key}
                  label={item.label}
                  value={edits[item.key] ?? item.value}
                  unit={item.unit}
                  source={item.source}
                  uncertainty={item.uncertainty}
                  editable={item.editable}
                  onChange={(value) =>
                    void recalculate({ ...edits, [item.key]: value })
                  }
                />
              ))}
            </div>
            <div className="col-span-6 flex flex-col gap-4">
              <h3 className="text-section">Modelled result</h3>
              <p className="text-body">
                Annual benefit{' '}
                <span className="numeral">
                  {money(outcome.annual_benefit.lo, 'USD')} to{' '}
                  {money(outcome.annual_benefit.hi, 'USD')}
                </span>
              </p>
              <p className="text-small text-ink-3">
                {outcome.annual_benefit.basis}.
              </p>
              <p className="text-body">
                Payback{' '}
                <span className="numeral">
                  {outcome.payback_months === null
                    ? 'not computable at these assumptions'
                    : `${outcome.payback_months.toFixed(1)} months`}
                </span>
              </p>
              <h3 className="text-section">What it is most sensitive to</h3>
              <DataTable<SensitivityRow>
                rowKey={(row) => row.key}
                density="regular"
                columns={[
                  { key: 'label', header: 'Assumption', render: (row) => row.label },
                  {
                    key: 'low',
                    header: 'At its low end',
                    numeric: true,
                    render: (row) => money(row.low_result, 'USD'),
                  },
                  {
                    key: 'high',
                    header: 'At its high end',
                    numeric: true,
                    render: (row) => money(row.high_result, 'USD'),
                  },
                  {
                    key: 'swing',
                    header: 'Swing',
                    numeric: true,
                    render: (row) => money(row.swing, 'USD'),
                  },
                ]}
                rows={outcome.sensitivity}
                emptyNote="Nothing to rank while every assumption produces the same result."
              />
              {outcome.notes.map((note) => (
                <Notice key={note}>{note}</Notice>
              ))}
              {Object.keys(edits).length > 0 ? (
                <div>
                  <Button onClick={() => void recalculate({})}>
                    Reset the assumptions
                  </Button>
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
      </Region>

      <Region title="Modelled against realised">
        <p className="max-w-[68ch] text-body text-ink-2">
          Presented plainly whether the gap is positive or negative. A shortfall
          renders the same way a gain does.
        </p>
        {realised ? (
          <>
            <DataTable<RealisedRow>
              rowKey={(row) => `${row.site_id}:${row.measure}`}
              density="regular"
              columns={[
                { key: 'site', header: 'Site', render: (row) => row.site_id },
                { key: 'measure', header: 'Measure', render: (row) => row.measure },
                {
                  key: 'modelled',
                  header: 'Modelled',
                  numeric: true,
                  render: (row) => row.modelled.toFixed(0),
                },
                {
                  key: 'realised',
                  header: 'Realised',
                  numeric: true,
                  render: (row) =>
                    row.realised === null ? (
                      <span className="text-ink-4">not yet measured</span>
                    ) : (
                      row.realised.toFixed(0)
                    ),
                },
                {
                  key: 'gap',
                  header: 'Gap',
                  numeric: true,
                  render: (row) =>
                    row.gap === null ? '' : signed(row.gap, 0),
                },
                {
                  key: 'evidence',
                  header: 'Evidence',
                  render: (row) => (
                    <span className="text-small text-ink-2">{row.evidence}</span>
                  ),
                },
              ]}
              rows={realised.rows}
            />
            <p className="max-w-[68ch] text-small text-ink-3">{realised.note}</p>
          </>
        ) : null}
      </Region>

      <Region title="Onboarding a new line">
        <p className="max-w-[68ch] text-body text-ink-2">
          What the twin can read off a stream on its own, and what it cannot. A
          field it cannot infer is left blank and marked rather than guessed,
          because a guessed buffer capacity makes the forecast confident about a
          constraint that may not exist.
        </p>
        {topology ? (
          <>
            <DataTable<TopologyField>
              rowKey={(row) => row.field}
              density="regular"
              columns={[
                { key: 'field', header: 'Field', render: (row) => row.field },
                {
                  key: 'value',
                  header: 'Inferred',
                  render: (row) =>
                    row.value === null ? (
                      <span className="text-ink-4">left blank</span>
                    ) : (
                      <span className="numeral">{row.value}</span>
                    ),
                },
                {
                  key: 'confidence',
                  header: 'Confidence',
                  numeric: true,
                  render: (row) =>
                    row.confidence === null ? '' : probability(row.confidence),
                },
                {
                  key: 'from',
                  header: 'From',
                  render: (row) => (
                    <span className="text-small text-ink-2">
                      {row.inferred_from}
                    </span>
                  ),
                },
                {
                  key: 'note',
                  header: 'Note',
                  render: (row) => (
                    <span className="text-small text-ink-2">{row.note}</span>
                  ),
                },
              ]}
              rows={topology.fields}
            />
            <p className="max-w-[68ch] text-small text-ink-3">{topology.note}</p>
          </>
        ) : null}
      </Region>
    </div>
  );
}
