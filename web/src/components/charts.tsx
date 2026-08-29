'use client';

// The charts. UI_COMPONENTS.md 21, 22, 23, 30, 31.
//
// Hand-drawn SVG, no charting library. The rules that come out of
// DESIGN_SYSTEM.md Section 9 and are easy to break with one:
//
// - Step or straight-line interpolation only, never a spline. A spline invents
//   values between two measurements and this product does not do that anywhere
//   else either.
// - Y-axis from zero, or an explicit break mark. A truncated axis makes a two
//   percent move look like a crisis.
// - Direct labels, no legend, wherever there are three or fewer series. A
//   legend makes the reader hold a colour in their head while they look
//   somewhere else.
// - Greyscale unless a series represents a state, in which case it takes that
//   state's colour because it is that state.

import type { ReactNode } from 'react';
import { causeWords, clockShort } from '@/lib/format';
import type { Marker, Range, SeriesPoint } from '@/lib/types';

const AXIS_LEFT = 44;
const AXIS_BOTTOM = 18;
const PAD_TOP = 10;
const PAD_RIGHT = 8;

// -- TimeSeriesChart -----------------------------------------------------

export function TimeSeriesChart({
  series,
  band,
  markers = [],
  height = 130,
  label,
  unit = 's',
}: {
  series: SeriesPoint[];
  band?: Range | null;
  markers?: Marker[];
  height?: number;
  label: string;
  unit?: string;
}) {
  if (series.length === 0) {
    return (
      <p className="text-small text-ink-3">
        No cycles recorded here yet, so there is nothing to plot.
      </p>
    );
  }
  const width = 420;
  const values = series.map((point) => point.value);
  const bandLo = band ? band.lo : Math.min(...values);
  const bandHi = band ? band.hi : Math.max(...values);
  const maxValue = Math.max(...values, bandHi) * 1.08;
  const times = series.map((point) => new Date(point.at).getTime());
  const first = Math.min(...times);
  const last = Math.max(...times, first + 1);
  const x = (at: number) =>
    AXIS_LEFT + ((at - first) / (last - first)) * (width - AXIS_LEFT - PAD_RIGHT);
  const y = (value: number) =>
    PAD_TOP + (1 - value / maxValue) * (height - PAD_TOP - AXIS_BOTTOM);
  const path = series
    .map((point, index) => {
      const px = x(new Date(point.at).getTime());
      const py = y(point.value);
      return `${index === 0 ? 'M' : 'L'}${px.toFixed(1)} ${py.toFixed(1)}`;
    })
    .join(' ');
  return (
    <figure className="m-0">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full"
        role="img"
        aria-label={label}
      >
        {band ? (
          <rect
            x={AXIS_LEFT}
            y={y(bandHi)}
            width={width - AXIS_LEFT - PAD_RIGHT}
            height={Math.max(1, y(bandLo) - y(bandHi))}
            fill="var(--band)"
          />
        ) : null}
        <line
          x1={AXIS_LEFT}
          y1={height - AXIS_BOTTOM}
          x2={width - PAD_RIGHT}
          y2={height - AXIS_BOTTOM}
          stroke="var(--rule-strong)"
          strokeWidth="1"
        />
        <line
          x1={AXIS_LEFT}
          y1={PAD_TOP}
          x2={AXIS_LEFT}
          y2={height - AXIS_BOTTOM}
          stroke="var(--rule-strong)"
          strokeWidth="1"
        />
        <path d={path} fill="none" stroke="var(--series-1)" strokeWidth="1.25" />
        {markers.map((marker) => {
          const px = x(new Date(marker.at).getTime());
          if (Number.isNaN(px)) return null;
          return (
            <g key={marker.at + marker.label}>
              <line
                x1={px}
                y1={PAD_TOP}
                x2={px}
                y2={height - AXIS_BOTTOM}
                stroke="var(--state-drift)"
                strokeWidth="1"
              />
              <text
                x={px + 3}
                y={PAD_TOP + 9}
                fontSize="10"
                fill="var(--ink-2)"
                className="numeral"
              >
                {clockShort(marker.at)}
              </text>
            </g>
          );
        })}
        <text x={0} y={y(maxValue) + 9} fontSize="10" fill="var(--ink-3)">
          {maxValue.toFixed(0)}
        </text>
        <text x={0} y={height - AXIS_BOTTOM} fontSize="10" fill="var(--ink-3)">
          0
        </text>
        <text
          x={AXIS_LEFT}
          y={height - 4}
          fontSize="10"
          fill="var(--ink-3)"
          className="numeral"
        >
          {clockShort(series[0]?.at ?? null)}
        </text>
        <text
          x={width - PAD_RIGHT}
          y={height - 4}
          fontSize="10"
          fill="var(--ink-3)"
          textAnchor="end"
          className="numeral"
        >
          {clockShort(series[series.length - 1]?.at ?? null)}
        </text>
      </svg>
      <figcaption className="text-small text-ink-3">
        {label} in {unit}. Band is the normal range for this station.
      </figcaption>
    </figure>
  );
}

// -- StackedBar ----------------------------------------------------------
//
// Horizontal, used for the loss split and for output against target. Segments
// carry state colours where the segments are states, and are labelled directly
// on the bar where they are wide enough.

const SEGMENT_FILL: Record<string, string> = {
  blocked: 'var(--state-blocked)',
  starved: 'var(--state-starved)',
  down: 'var(--state-down)',
  changeover: 'var(--series-3)',
  quality: 'var(--state-defect)',
};

const SEGMENT_INK: Record<string, string> = {
  blocked: 'var(--ink)',
  starved: 'var(--ink)',
  down: 'var(--paper)',
  changeover: 'var(--ink)',
  quality: 'var(--paper)',
};

export function StackedBar({
  segments,
  unit,
  height = 22,
}: {
  segments: { key: string; value: number }[];
  unit: string;
  height?: number;
}) {
  const total = segments.reduce((sum, item) => sum + item.value, 0);
  if (total <= 0) {
    return (
      <p className="text-small text-ink-3">
        Nothing lost in this window, so the bar is empty rather than absent.
      </p>
    );
  }
  const wide = segments.filter((item) => item.value / total < 0.12);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex w-full" style={{ height }}>
        {segments
          .filter((item) => item.value > 0)
          .map((item) => {
            const share = item.value / total;
            return (
              <div
                key={item.key}
                className="flex items-center justify-center overflow-hidden text-micro"
                style={{
                  width: `${share * 100}%`,
                  background: SEGMENT_FILL[item.key] ?? 'var(--series-2)',
                  color: SEGMENT_INK[item.key] ?? 'var(--ink)',
                }}
                title={`${causeWords(item.key)} ${item.value.toFixed(0)} ${unit}`}
              >
                {share >= 0.12 ? (
                  <span className="numeral px-1">
                    {causeWords(item.key)} {item.value.toFixed(0)}
                  </span>
                ) : null}
              </div>
            );
          })}
      </div>
      {wide.length > 0 ? (
        <p className="text-small text-ink-3">
          {wide
            .filter((item) => item.value > 0)
            .map((item) => `${causeWords(item.key)} ${item.value.toFixed(0)}`)
            .join(' · ')}{' '}
          {unit}
        </p>
      ) : null}
    </div>
  );
}

// -- PaceBar -------------------------------------------------------------
//
// Output against the shift target, with a mark where the line should be now.
// Not a StackedBar: it has one filled segment and a reference mark, and forcing
// it through the stacked shape would lose the mark, which is the only part a
// supervisor reads.

export function PaceBar({
  completed,
  target,
  paceUnits,
}: {
  completed: number;
  target: number;
  paceUnits: number;
}) {
  const share = target > 0 ? Math.min(1, completed / target) : 0;
  const paceShare = target > 0 ? Math.min(1, (completed - paceUnits) / target) : 0;
  return (
    <div className="relative h-[22px] w-full bg-paper-sunk">
      <div
        className="absolute inset-y-0 left-0"
        style={{ width: `${share * 100}%`, background: 'var(--series-1)' }}
      />
      <div
        className="absolute inset-y-0 w-[2px]"
        style={{ left: `${paceShare * 100}%`, background: 'var(--ink)' }}
        title="where the line should be now"
      />
    </div>
  );
}

// -- Heatmap -------------------------------------------------------------
//
// Constraint migration. Greyscale density, no colour ramp, and cells above the
// threshold carry their number directly, which is what removes the need for a
// legend.

export function Heatmap({
  rows,
  columns,
  valueAt,
  labelAbove = 0.2,
  markRow,
}: {
  rows: string[];
  columns: string[];
  valueAt: (row: string, column: string) => number;
  labelAbove?: number;
  markRow?: string | null;
}) {
  if (rows.length === 0) {
    return (
      <p className="text-small text-ink-3">
        No station has been named the constraint in this range.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="border-collapse text-body">
        <thead>
          <tr>
            <th className="px-2 py-1 text-left text-label text-ink-2">Station</th>
            {columns.map((column) => (
              <th
                key={column}
                className="numeral px-2 py-1 text-right text-micro text-ink-3"
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row}>
              <th
                scope="row"
                className={`numeral px-2 py-1 text-left text-label ${
                  row === markRow ? 'text-ink' : 'text-ink-2'
                }`}
              >
                {row}
                {row === markRow ? (
                  <span className="ml-2 text-micro text-ink-3">now</span>
                ) : null}
              </th>
              {columns.map((column) => {
                const value = valueAt(row, column);
                return (
                  <td
                    key={column}
                    className="numeral border border-paper px-2 py-1 text-right text-micro"
                    style={{
                      background: 'var(--ink)',
                      opacity: value === 0 ? 0.04 : 0.12 + value * 0.7,
                      color: value > 0.5 ? 'var(--paper)' : 'var(--ink)',
                    }}
                    title={`${row}, ${column}: ${value.toFixed(2)}`}
                  >
                    {value >= labelAbove ? value.toFixed(2) : ''}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// -- ReliabilityChart ----------------------------------------------------
//
// Predicted probability against observed frequency, with the diagonal marked.
// Small, plain, and capable of showing a badly calibrated model as badly
// calibrated.

export function ReliabilityChart({
  predicted,
  observed,
  counts,
  height = 150,
}: {
  predicted: number[];
  observed: number[];
  counts: number[];
  height?: number;
}) {
  const width = 200;
  const place = (value: number) => 10 + value * (width - 20);
  const placeY = (value: number) => height - 20 - value * (height - 30);
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full max-w-[200px]"
      role="img"
      aria-label="calibration curve, predicted probability against observed frequency"
    >
      <line
        x1={place(0)}
        y1={placeY(0)}
        x2={place(1)}
        y2={placeY(1)}
        stroke="var(--baseline)"
        strokeWidth="1"
        strokeDasharray="3 3"
      />
      <line
        x1={place(0)}
        y1={placeY(0)}
        x2={place(1)}
        y2={placeY(0)}
        stroke="var(--rule-strong)"
      />
      <line
        x1={place(0)}
        y1={placeY(0)}
        x2={place(0)}
        y2={placeY(1)}
        stroke="var(--rule-strong)"
      />
      {predicted.map((value, index) => {
        const seen = observed[index];
        if (seen === undefined) return null;
        if (!Number.isFinite(value) || !Number.isFinite(seen)) return null;
        return (
          <circle
            key={index}
            cx={place(value)}
            cy={placeY(seen)}
            r={Math.max(1.5, Math.min(5, Math.sqrt(counts[index] ?? 1) / 4))}
            fill="var(--series-1)"
          />
        );
      })}
    </svg>
  );
}

// -- SmallMultiples ------------------------------------------------------
//
// The one place a grid of repeated elements is correct, because the repetition
// is the comparison.

export function SmallMultiples<Item>({
  items,
  renderItem,
  columns = 4,
}: {
  items: Item[];
  renderItem: (item: Item) => ReactNode;
  columns?: number;
}) {
  return (
    <div
      className="grid gap-4"
      style={{ gridTemplateColumns: `repeat(${Math.min(8, columns)}, 1fr)` }}
    >
      {items.map((item, index) => (
        <div key={index}>{renderItem(item)}</div>
      ))}
    </div>
  );
}
