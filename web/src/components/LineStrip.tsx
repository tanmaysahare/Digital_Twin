'use client';

// The line strip. UI_COMPONENTS.md 4 to 7, UX_SPEC.md Section 2.2,
// WIREFRAMES/01 and 02. AC-001.
//
// Forty-two stations across a desk screen without scrolling, and the whole
// strip is one tab stop with arrow keys inside it (roving tabindex), because a
// forty-two stop tab order is a keyboard trap with extra steps.
//
// The rule that generates the look: greyscale by default, colour means
// abnormal. A normal line renders with no saturation at all. There is no green
// for good, because painting 38 normal stations green makes the four abnormal
// ones harder to find.
//
// A Tier C station shows a cross-hatch and an interval, never a point. Any
// change that makes a dark station look like a monitored one is wrong, and this
// component is where that would happen first.

import { useCallback, useEffect, useRef, useState } from 'react';
import { RangePlot } from '@/components/primitives';
import { estimateShort, clockShort } from '@/lib/format';
import type {
  Buffer,
  Forecast,
  Gate,
  LineState,
  Station,
  Zone,
} from '@/lib/types';

// The strip's own geometry, from UX_SPEC.md Section 2.2.
const TRACK_HEIGHT = 40;
const STATION_HEIGHT = 90;
const BUFFER_HEIGHT = 30;
const ZONE_HEIGHT = 20;

function fillFor(station: Station): { background: string; ink: string } {
  if (station.state === 'DOWN') {
    return { background: 'var(--state-down)', ink: 'var(--paper)' };
  }
  if (station.flags.includes('DRIFTING')) {
    return { background: 'var(--state-drift)', ink: 'var(--ink)' };
  }
  if (station.state === 'BLOCKED' || station.state === 'STARVED') {
    return { background: 'var(--state-blocked)', ink: 'var(--ink)' };
  }
  return { background: 'transparent', ink: 'var(--ink-2)' };
}

// The pattern that goes with the fill, so that colour is never the only carrier
// of meaning. Rendered as a repeating-linear background would be a gradient, so
// these are SVG patterns instead.
function patternFor(station: Station): string | null {
  if (station.tier === 'C') return 'hatch';
  if (station.flags.includes('DRIFTING')) return 'diagonal';
  if (station.state === 'BLOCKED') return 'vertical';
  if (station.state === 'STARVED') return 'horizontal';
  return null;
}

function StripPatterns() {
  return (
    <svg width="0" height="0" className="absolute" aria-hidden="true">
      <defs>
        <pattern
          id="strip-hatch"
          width="6"
          height="6"
          patternTransform="rotate(45)"
          patternUnits="userSpaceOnUse"
        >
          <line
            x1="0"
            y1="0"
            x2="0"
            y2="6"
            stroke="var(--state-dark)"
            strokeWidth="3"
          />
        </pattern>
        <pattern
          id="strip-diagonal"
          width="6"
          height="6"
          patternTransform="rotate(45)"
          patternUnits="userSpaceOnUse"
        >
          <line x1="0" y1="0" x2="0" y2="6" stroke="var(--ink)" strokeWidth="1" />
        </pattern>
        <pattern
          id="strip-vertical"
          width="5"
          height="5"
          patternUnits="userSpaceOnUse"
        >
          <line x1="0" y1="0" x2="0" y2="5" stroke="var(--ink)" strokeWidth="1" />
        </pattern>
        <pattern
          id="strip-horizontal"
          width="5"
          height="5"
          patternUnits="userSpaceOnUse"
        >
          <line x1="0" y1="0" x2="5" y2="0" stroke="var(--ink)" strokeWidth="1" />
        </pattern>
      </defs>
    </svg>
  );
}

function StationSegment({
  station,
  selected,
  focused,
  onSelect,
  registerRef,
}: {
  station: Station;
  selected: boolean;
  focused: boolean;
  onSelect: (stationId: string) => void;
  registerRef: (node: HTMLButtonElement | null) => void;
}) {
  const fill = fillFor(station);
  const pattern = patternFor(station);
  const isDark = station.tier === 'C';
  const label = [
    station.station_id,
    station.state.toLowerCase().replace(/_/g, ' '),
    station.cycle_time
      ? `cycle ${estimateShort(station.cycle_time)} s`
      : 'no cycle recorded',
    station.normal_range
      ? `normal ${station.normal_range.lo.toFixed(1)} to ${station.normal_range.hi.toFixed(1)} s`
      : 'no baseline yet',
    station.cycle_time ? station.cycle_time.provenance.toLowerCase() : '',
  ]
    .filter(Boolean)
    .join(', ');
  return (
    <button
      type="button"
      ref={registerRef}
      tabIndex={focused ? 0 : -1}
      onClick={() => onSelect(station.station_id)}
      title={label}
      aria-label={label}
      className={`relative flex min-w-0 flex-1 flex-col justify-between border-r border-rule px-1 py-1 text-left last:border-r-0 ${
        selected ? 'outline outline-2 outline-accent' : ''
      }`}
      style={{
        height: STATION_HEIGHT,
        background: fill.background,
        color: fill.ink,
        transition: 'background var(--motion-value) var(--motion-ease)',
      }}
    >
      {pattern ? (
        <svg
          className="pointer-events-none absolute inset-0 h-full w-full"
          aria-hidden="true"
          preserveAspectRatio="none"
        >
          <rect
            width="100%"
            height="100%"
            fill={`url(#strip-${pattern})`}
            opacity={isDark ? 0.35 : 0.28}
          />
        </svg>
      ) : null}
      <span className="numeral relative z-10 text-micro">
        {station.station_id}
      </span>
      <span className="relative z-10 block">
        <RangePlot
          estimate={station.cycle_time}
          range={station.normal_range}
          height={34}
        />
      </span>
      <span className="numeral relative z-10 block truncate text-micro">
        {estimateShort(station.cycle_time)}
      </span>
    </button>
  );
}

function BufferBlock({ buffer }: { buffer: Buffer }) {
  const share = Math.min(1, buffer.occupancy.hi / Math.max(1, buffer.capacity));
  const trend =
    buffer.trend === 'RISING' ? '↑' : buffer.trend === 'FALLING' ? '↓' : '–';
  return (
    <div
      className="flex flex-col items-center gap-1"
      title={`${buffer.buffer_id} holds ${buffer.occupancy.hi.toFixed(0)} of ${buffer.capacity}, ${buffer.trend.toLowerCase()}`}
    >
      <div className="relative h-[30px] w-[24px] border border-rule bg-paper-sunk">
        <div
          className="absolute inset-x-0 bottom-0"
          style={{ height: `${share * 100}%`, background: 'var(--series-2)' }}
        />
        <div className="absolute right-0 top-0 h-full w-[1px] bg-rule-strong" />
      </div>
      <span className="numeral text-micro text-ink-3">
        {buffer.buffer_id} {buffer.occupancy.hi.toFixed(0)}/{buffer.capacity} {trend}
      </span>
    </div>
  );
}

function ForecastTrack({
  forecast,
  stations,
}: {
  forecast: Forecast | null;
  stations: Station[];
}): JSX.Element | null {
  if (!forecast || forecast.buckets.length === 0) {
    return (
      <div
        className="flex items-center border-b border-rule px-2 text-small text-ink-3"
        style={{ height: TRACK_HEIGHT }}
      >
        Next 120 min: no forecast cycle has run yet.
      </div>
    );
  }
  const buckets = forecast.buckets;
  const firstBucket = buckets[0];
  const lastBucket = buckets[buckets.length - 1];
  if (!firstBucket || !lastBucket) return null;
  const start = new Date(firstBucket.start_at).getTime();
  const end = new Date(lastBucket.end_at).getTime();
  const span = Math.max(1, end - start);
  const raised = forecast.stations
    .map((item) => {
      const peak = Math.max(...item.stall_probability, 0);
      const index = item.stall_probability.indexOf(peak);
      return { station_id: item.station_id, peak, index };
    })
    .filter((item) => item.peak >= 0.5)
    .sort((a, b) => b.peak - a.peak)
    .slice(0, 3);
  const ticks = buckets.filter((_, index) => index % 3 === 0);
  return (
    <div
      className="relative border-b border-rule"
      style={{ height: TRACK_HEIGHT }}
    >
      <span className="absolute left-2 top-1 text-small text-ink-3">
        Next {forecast.horizon_min.toFixed(0)} min
      </span>
      {raised.map((item, row) => {
        const bucket = buckets[item.index];
        if (!bucket) return null;
        const left =
          ((new Date(bucket.start_at).getTime() - start) / span) * 100;
        const width =
          ((new Date(bucket.end_at).getTime() -
            new Date(bucket.start_at).getTime()) /
            span) *
          100;
        return (
          <div
            key={item.station_id}
            className="absolute flex items-center gap-2"
            style={{ left: `${left}%`, top: 2 + row * 11 }}
          >
            <span
              className="block h-[3px]"
              style={{
                width: `${Math.max(12, width * 4)}px`,
                background: 'var(--state-forecast)',
              }}
            />
            <span className="numeral whitespace-nowrap text-micro text-ink-2">
              {item.station_id} p {item.peak.toFixed(2)}{' '}
              {clockShort(bucket.start_at)} to {clockShort(bucket.end_at)}
            </span>
          </div>
        );
      })}
      <div className="absolute inset-x-0 bottom-0 flex justify-between px-2">
        {ticks.map((bucket, index) => (
          <span key={bucket.index} className="numeral text-micro text-ink-4">
            +{index * 15}
          </span>
        ))}
      </div>
      {stations.length === 0 ? null : null}
    </div>
  );
}

function ZoneRule({
  zones,
  gates,
  stations,
}: {
  zones: Zone[];
  gates: Gate[];
  stations: Station[];
}) {
  const order = stations.map((item) => item.station_id);
  return (
    <div
      className="flex border-t border-rule-strong"
      style={{ height: ZONE_HEIGHT }}
    >
      {zones.map((zone) => {
        const from = order.indexOf(zone.from_station_id);
        const to = order.indexOf(zone.to_station_id);
        const count = Math.max(1, to - from + 1);
        const gate = gates.find(
          (item) => item.after_station_id === zone.to_station_id,
        );
        return (
          <div
            key={zone.zone_id}
            className="flex items-center justify-between border-r border-rule px-2 last:border-r-0"
            style={{ flexGrow: count, flexBasis: 0 }}
          >
            <span className="truncate text-micro text-ink-2">
              {zone.name} {zone.from_station_id} to {zone.to_station_id}
            </span>
            {gate ? (
              <span className="numeral text-micro text-ink" title={gate.name}>
                {gate.gate_id}
              </span>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

export function LineStrip({
  state,
  forecast,
  zones,
  gates,
  selectedStationId,
  onSelectStation,
}: {
  state: LineState;
  forecast: Forecast | null;
  zones: Zone[];
  gates: Gate[];
  selectedStationId: string | null;
  onSelectStation: (stationId: string) => void;
}) {
  const stations = state.stations;
  const [focusIndex, setFocusIndex] = useState(0);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const move = useCallback(
    (next: number) => {
      const clamped = Math.max(0, Math.min(stations.length - 1, next));
      setFocusIndex(clamped);
      refs.current[clamped]?.focus();
    },
    [stations.length],
  );

  // Below 1024 the strip scrolls, and an abnormal station is brought into view
  // when it becomes abnormal rather than left off the edge of the screen.
  useEffect(() => {
    const abnormal = stations.findIndex(
      (item) =>
        item.state === 'DOWN' ||
        item.flags.includes('DRIFTING') ||
        item.state === 'BLOCKED',
    );
    if (abnormal >= 0) {
      refs.current[abnormal]?.scrollIntoView({
        block: 'nearest',
        inline: 'nearest',
      });
    }
  }, [stations]);

  return (
    <section
      aria-label="Line strip"
      className="border border-rule bg-paper-raised"
    >
      <StripPatterns />
      <ForecastTrack forecast={forecast} stations={stations} />
      <div
        className="flex overflow-x-auto"
        role="group"
        aria-label="42 stations, use the arrow keys"
        onKeyDown={(event) => {
          if (event.key === 'ArrowRight') {
            event.preventDefault();
            move(focusIndex + 1);
          } else if (event.key === 'ArrowLeft') {
            event.preventDefault();
            move(focusIndex - 1);
          } else if (event.key === 'Home') {
            event.preventDefault();
            move(0);
          } else if (event.key === 'End') {
            event.preventDefault();
            move(stations.length - 1);
          }
        }}
      >
        {stations.map((station, index) => (
          <StationSegment
            key={station.station_id}
            station={station}
            selected={station.station_id === selectedStationId}
            focused={index === focusIndex}
            onSelect={onSelectStation}
            registerRef={(node) => {
              refs.current[index] = node;
            }}
          />
        ))}
      </div>
      <div
        className="flex items-start justify-between gap-2 overflow-x-auto border-t border-rule px-2 py-1"
        style={{ minHeight: BUFFER_HEIGHT + 18 }}
      >
        {state.buffers.map((buffer) => (
          <BufferBlock key={buffer.buffer_id} buffer={buffer} />
        ))}
      </div>
      <ZoneRule zones={zones} gates={gates} stations={stations} />
    </section>
  );
}
