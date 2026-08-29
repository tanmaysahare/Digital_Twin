// How a number reaches the screen. DESIGN_SYSTEM.md Section 9.
//
// The rules this file exists to enforce, all of which are easy to break by
// accident in a component:
//
// - An interval is never collapsed to a midpoint. `estimateText` renders
//   "54 to 71 s" for an inference and "62.1 s" only where the bounds are equal,
//   which is the definition of a measurement.
// - A probability is two decimals. Not a percentage, and never a percentage
//   with decimals, because "71.3%" claims a precision no calibration supports.
// - A duration under an hour reads in minutes and seconds; beyond that it reads
//   as a clock time. A supervisor reading "4,412 s ago" has to do arithmetic.
// - Missing is never blank and never zero. It is the words "no data".

import type { Estimate, Range } from '@/lib/types';

export const NO_DATA = 'no data';

export function seconds(value: number, digits = 1): string {
  return value.toFixed(digits);
}

export function estimateText(estimate: Estimate | null, digits = 1): string {
  if (estimate === null) return NO_DATA;
  const unit = estimate.unit ? ` ${estimate.unit}` : '';
  if (estimate.provenance === 'MEASURED' || estimate.lo === estimate.hi) {
    return `${estimate.lo.toFixed(digits)}${unit}`;
  }
  return `${estimate.lo.toFixed(digits)} to ${estimate.hi.toFixed(digits)}${unit}`;
}

// The short form the line strip uses, where 42 of them sit side by side and
// there is room for about seven characters.
export function estimateShort(estimate: Estimate | null): string {
  // On the strip there is room for about five characters. A station with no
  // value at all takes a dash, and the drawer says why.
  if (estimate === null) return '–';
  if (estimate.provenance === 'MEASURED' || estimate.lo === estimate.hi) {
    return estimate.lo.toFixed(1);
  }
  return `${Math.round(estimate.lo)}-${Math.round(estimate.hi)}`;
}

export function rangeText(range: Range | null, digits = 1): string {
  if (range === null) return NO_DATA;
  const unit = range.unit ? ` ${range.unit}` : '';
  return `${range.lo.toFixed(digits)} to ${range.hi.toFixed(digits)}${unit}`;
}

export function probability(value: number | null): string {
  if (value === null || Number.isNaN(value)) return NO_DATA;
  return value.toFixed(2);
}

export function integer(value: number): string {
  return Math.round(value).toLocaleString('en-GB');
}

export function money(value: number, currency: string): string {
  return `${Math.round(value).toLocaleString('en-GB')} ${currency}`;
}

export function signed(value: number, digits = 0): string {
  const text = value.toFixed(digits);
  return value > 0 ? `+${text}` : text;
}

export function clock(iso: string | null): string {
  if (!iso) return NO_DATA;
  const at = new Date(iso);
  return at.toLocaleTimeString('en-GB', { hour12: false });
}

export function clockShort(iso: string | null): string {
  if (!iso) return NO_DATA;
  const at = new Date(iso);
  return at.toLocaleTimeString('en-GB', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function dayAndClock(iso: string | null): string {
  if (!iso) return NO_DATA;
  const at = new Date(iso);
  return `${at.toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
  })} ${at.toLocaleTimeString('en-GB', { hour12: false, hour: '2-digit', minute: '2-digit' })}`;
}

// Under a minute in seconds, under an hour in minutes, beyond that the absolute
// time. DESIGN_SYSTEM.md Section 9.
export function ageText(ageSeconds: number, at: string | null): string {
  if (ageSeconds < 60) return `${Math.round(ageSeconds)} s ago`;
  if (ageSeconds < 3600) return `${Math.round(ageSeconds / 60)} min ago`;
  return clock(at);
}

export function durationText(value: number): string {
  if (value < 60) return `${Math.round(value)} s`;
  if (value < 3600) return `${Math.round(value / 60)} min`;
  return `${(value / 3600).toFixed(1)} h`;
}

// A VIN is 17 characters and a plant reads the last eleven, which are the ones
// that identify the unit rather than the plant and the model year.
export function shortUnit(unitId: string): string {
  return unitId.length > 11 ? unitId.slice(-11) : unitId;
}

export function stateWords(state: string): string {
  return state.toLowerCase().replace(/_/g, ' ');
}

export function causeWords(cause: string): string {
  return cause.replace(/_/g, ' ');
}
