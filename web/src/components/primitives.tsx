'use client';

// The small components everything else is built from. UI_COMPONENTS.md 8, 9,
// 13, 14, 15, 18, 19, 20, 28.
//
// They live in one file because they are one idea: a value reaches the screen
// with its provenance, an interval reaches it as an interval, and a control is
// a word rather than a shape. Splitting them across nine files would make that
// harder to read, not easier.

import type { ReactNode } from 'react';
import { HatchSwatch, ArrowDown, ArrowUp } from '@/components/icons';
import { estimateText, NO_DATA } from '@/lib/format';
import type { Estimate, Provenance, Range } from '@/lib/types';

// -- ProvenanceMark ------------------------------------------------------
//
// Measured renders nothing, because the plain case should be the quiet one.
// Derived takes a left rule. Inferred takes the hatch swatch and drops to
// --ink-2, so that an inference never looks like a reading.

const PROVENANCE_TITLE: Record<Provenance, string> = {
  MEASURED: 'Measured. The source reported this value directly.',
  DERIVED: 'Derived. Computed from measurements by a known relation.',
  INFERRED: 'Inferred. Reasoned to, with no direct observation of it.',
};

export function ProvenanceMark({
  provenance,
  children,
}: {
  provenance: Provenance;
  children: ReactNode;
}) {
  if (provenance === 'MEASURED') {
    return <span title={PROVENANCE_TITLE.MEASURED}>{children}</span>;
  }
  if (provenance === 'DERIVED') {
    return (
      <span
        className="border-l-2 border-rule-strong pl-2"
        title={PROVENANCE_TITLE.DERIVED}
        aria-label="derived value"
      >
        {children}
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center gap-1 text-ink-2"
      title={PROVENANCE_TITLE.INFERRED}
      aria-label="inferred value"
    >
      <HatchSwatch className="h-3 w-3" />
      {children}
    </span>
  );
}

// -- Value ---------------------------------------------------------------
//
// The one path from an Estimate to the screen. It renders the provenance mark
// itself, which is what makes UI_COMPONENTS.md rule 4 structural rather than a
// convention somebody has to remember.

export function Value({
  estimate,
  digits = 1,
  className = '',
}: {
  estimate: Estimate | null;
  digits?: number;
  className?: string;
}) {
  if (estimate === null) {
    return <span className={`numeral text-ink-4 ${className}`}>{NO_DATA}</span>;
  }
  return (
    <ProvenanceMark provenance={estimate.provenance}>
      <span className={`numeral ${className}`} title={estimate.basis}>
        {estimateText(estimate, digits)}
      </span>
    </ProvenanceMark>
  );
}

// -- IntervalBar ---------------------------------------------------------
//
// A rule with marked endpoints and, where there is one, a tick at a point
// estimate. It never renders a midpoint alone and it never fades: a gradient
// across an interval says the middle is more likely, and for a bound derived
// from flanking timestamps that is not true.

export function IntervalBar({
  lo,
  hi,
  point,
  min,
  max,
  label,
  tone = 'neutral',
}: {
  lo: number;
  hi: number;
  point?: number | null;
  min: number;
  max: number;
  label?: string;
  tone?: 'neutral' | 'forecast';
}) {
  const span = Math.max(1e-6, max - min);
  const left = ((Math.max(min, lo) - min) / span) * 100;
  const width = ((Math.min(max, hi) - Math.max(min, lo)) / span) * 100;
  const colour = tone === 'forecast' ? 'var(--state-forecast)' : 'var(--ink-2)';
  return (
    <div
      className="relative h-4 w-full bg-paper-sunk"
      role="img"
      aria-label={label ?? `interval from ${lo} to ${hi}`}
    >
      <div
        className="absolute top-[6px] h-[3px]"
        style={{
          left: `${left}%`,
          width: `${Math.max(0.5, width)}%`,
          background: colour,
        }}
      />
      <div
        className="absolute top-[2px] h-[11px] w-[2px]"
        style={{ left: `${left}%`, background: colour }}
      />
      <div
        className="absolute top-[2px] h-[11px] w-[2px]"
        style={{ left: `calc(${left + width}% - 2px)`, background: colour }}
      />
      {point !== null && point !== undefined ? (
        <div
          className="absolute top-0 h-4 w-[2px]"
          style={{
            left: `${((point - min) / span) * 100}%`,
            background: 'var(--ink)',
          }}
        />
      ) : null}
    </div>
  );
}

// -- RangePlot -----------------------------------------------------------
//
// The small analogue indicator inside every station segment. It exists because
// a bare 61.2 s does not tell you whether 61.2 s is normal for that station,
// and a supervisor should not have to remember 42 baselines.
//
// A value outside the range extends past the track end and is clipped with a
// visible overflow mark rather than rescaling the track, because rescaling
// would make the abnormal reading look ordinary.

export function RangePlot({
  estimate,
  range,
  height = 34,
}: {
  estimate: Estimate | null;
  range: Range | null;
  height?: number;
}) {
  if (estimate === null || range === null) {
    return (
      <div
        className="w-full bg-paper-sunk"
        style={{ height }}
        aria-hidden="true"
      />
    );
  }
  const pad = Math.max(1e-6, (range.hi - range.lo) * 0.35);
  const min = range.lo - pad;
  const max = range.hi + pad;
  const span = max - min;
  const place = (value: number) =>
    Math.min(100, Math.max(0, ((value - min) / span) * 100));
  const isInterval = estimate.lo !== estimate.hi;
  const overflowLow = estimate.lo < min;
  const overflowHigh = estimate.hi > max;
  return (
    <div
      className="relative w-full bg-paper-sunk"
      style={{ height }}
      role="img"
      aria-label={`cycle ${estimateText(estimate)} against a normal band of ${range.lo.toFixed(
        1,
      )} to ${range.hi.toFixed(1)} s`}
    >
      <div
        className="absolute inset-y-0"
        style={{
          left: `${place(range.lo)}%`,
          width: `${place(range.hi) - place(range.lo)}%`,
          background: 'var(--band)',
        }}
      />
      {isInterval ? (
        <div
          className="absolute inset-y-[3px]"
          style={{
            left: `${place(estimate.lo)}%`,
            width: `${Math.max(2, place(estimate.hi) - place(estimate.lo))}%`,
            background: 'var(--state-dark)',
            opacity: 0.55,
          }}
        />
      ) : (
        <div
          className="absolute inset-y-0 w-[2px] transition-[left] duration-[var(--motion-value)] ease-[var(--motion-ease)]"
          style={{ left: `${place(estimate.lo)}%`, background: 'var(--ink)' }}
        />
      )}
      {overflowLow ? (
        <div className="absolute inset-y-0 left-0 w-[3px] bg-ink" />
      ) : null}
      {overflowHigh ? (
        <div className="absolute inset-y-0 right-0 w-[3px] bg-ink" />
      ) : null}
    </div>
  );
}

// -- MetricLine ----------------------------------------------------------
//
// A label, a value, its unit, and optionally an interval, a signed delta and
// one line of context. This component is why there is no card grid in this
// product: several of these stack in a column with no borders between them.

export function MetricLine({
  label,
  value,
  unit,
  delta,
  deltaLabel,
  context,
  tone = 'normal',
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  delta?: number;
  deltaLabel?: string;
  context?: string;
  tone?: 'normal' | 'attention';
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-label text-ink-2">{label}</span>
        <span
          className={`flex items-baseline gap-1 ${
            tone === 'attention' ? 'text-state-drift' : ''
          }`}
        >
          <span className="numeral text-body">{value}</span>
          {unit ? <span className="text-small text-ink-3">{unit}</span> : null}
          {delta !== undefined && delta !== 0 ? (
            <span className="ml-2 inline-flex items-baseline gap-1 text-small text-ink-2">
              {delta > 0 ? <ArrowUp /> : <ArrowDown />}
              <span className="numeral">{Math.abs(delta)}</span>
              {deltaLabel ? <span>{deltaLabel}</span> : null}
            </span>
          ) : null}
        </span>
      </div>
      {context ? <p className="text-small text-ink-3">{context}</p> : null}
    </div>
  );
}

// -- StateChip -----------------------------------------------------------
//
// Rectangular, 2px radius, never a pill. Colour is never the sole carrier:
// every state also has a pattern and the word itself, so the chip works for a
// colour-blind supervisor and in monochrome print.

const CHIP: Record<string, { fill: string; pattern: string; ink: string }> = {
  RUNNING: { fill: 'transparent', pattern: 'none', ink: 'var(--ink-2)' },
  IDLE: { fill: 'var(--paper-sunk)', pattern: 'none', ink: 'var(--ink-2)' },
  IDLE_UNKNOWN: {
    fill: 'var(--paper-sunk)',
    pattern: 'hatch',
    ink: 'var(--ink-2)',
  },
  BLOCKED: {
    fill: 'var(--state-blocked)',
    pattern: 'vertical',
    ink: 'var(--ink)',
  },
  STARVED: {
    fill: 'var(--state-starved)',
    pattern: 'horizontal',
    ink: 'var(--ink)',
  },
  DOWN: { fill: 'var(--state-down)', pattern: 'solid', ink: 'var(--paper)' },
  DRIFTING: {
    fill: 'var(--state-drift)',
    pattern: 'diagonal',
    ink: 'var(--ink)',
  },
  NO_MACHINE_DATA: {
    fill: 'transparent',
    pattern: 'hatch',
    ink: 'var(--ink-2)',
  },
  UNRESOLVED: { fill: 'transparent', pattern: 'hatch', ink: 'var(--ink-2)' },
  CHANGEOVER: { fill: 'var(--paper-sunk)', pattern: 'none', ink: 'var(--ink-2)' },
};

const CHIP_FALLBACK = {
  fill: 'var(--paper-sunk)',
  pattern: 'none',
  ink: 'var(--ink-2)',
};

export function StateChip({ state }: { state: string }) {
  const style = CHIP[state] ?? CHIP_FALLBACK;
  return (
    <span
      className="inline-flex items-center rounded border border-rule px-1 text-micro"
      style={{ background: style.fill, color: style.ink }}
    >
      {state.toLowerCase().replace(/_/g, ' ')}
    </span>
  );
}

// -- Notice --------------------------------------------------------------
//
// Never a toast, never a modal, never auto-dismissing. A notice about something
// that is still true stays on screen.

export function Notice({
  tone = 'neutral',
  children,
}: {
  tone?: 'neutral' | 'attention';
  children: ReactNode;
}) {
  return (
    <div
      className={`border-l-2 py-1 pl-3 text-small text-ink-2 ${
        tone === 'attention' ? 'border-l-state-drift' : 'border-l-rule-strong'
      }`}
      role={tone === 'attention' ? 'status' : undefined}
    >
      {children}
    </div>
  );
}

// -- Button --------------------------------------------------------------
//
// Three variants, all rectangular, all text. A button that triggers work
// becomes disabled with its label in the present participle: there is no
// spinner anywhere in this product.

const BUTTON_VARIANT = {
  primary: 'bg-ink text-paper border border-ink',
  secondary: 'bg-paper text-ink border border-rule-strong',
  quiet: 'bg-transparent text-accent border border-transparent underline-offset-4 hover:underline',
} as const;

export function Button({
  variant = 'secondary',
  onClick,
  disabled,
  children,
  type = 'button',
  title,
}: {
  variant?: keyof typeof BUTTON_VARIANT;
  onClick?: () => void;
  disabled?: boolean;
  children: ReactNode;
  type?: 'button' | 'submit';
  title?: string;
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`h-[36px] rounded px-3 text-label ${BUTTON_VARIANT[variant]} ${
        disabled ? 'cursor-not-allowed text-ink-4' : 'hover:bg-paper-sunk'
      }`}
    >
      {children}
    </button>
  );
}

// -- Select --------------------------------------------------------------
//
// A native select. Keyboard-accessible, screen-reader-correct, and it works
// with gloves on a touchscreen. A custom one is a week of work to be worse at
// all three.

export function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-label text-ink-2">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-[36px] rounded border border-rule bg-paper px-2 text-body text-ink"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

// -- NumberField ---------------------------------------------------------
//
// Mono, tabular, right-aligned, with the unit outside the field. An invalid
// value is marked with a Notice beneath, never with a red glow.

export function NumberField({
  label,
  value,
  unit,
  step = 1,
  disabled,
  onChange,
  problem,
}: {
  label: string;
  value: number;
  unit?: string;
  step?: number;
  disabled?: boolean;
  onChange: (value: number) => void;
  problem?: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="flex items-center justify-between gap-3">
        <span className="text-label text-ink-2">{label}</span>
        <span className="flex items-baseline gap-2">
          <input
            type="number"
            value={Number.isFinite(value) ? value : 0}
            step={step}
            disabled={disabled}
            onChange={(event) => onChange(Number(event.target.value))}
            className="numeral h-[36px] w-[120px] rounded border border-rule bg-paper px-2 text-right text-body text-ink disabled:text-ink-4"
          />
          {unit ? <span className="text-small text-ink-3">{unit}</span> : null}
        </span>
      </label>
      {problem ? <Notice tone="attention">{problem}</Notice> : null}
    </div>
  );
}
