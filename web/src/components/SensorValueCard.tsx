'use client';

// The Sensor Value Card. UI_COMPONENTS.md 25, AC-051.
//
// Not a card in the decorative sense: a bordered block with a heading and a
// definition list. It is the component that turns a blind spot from something
// to apologise for into a costed decision.
//
// Every number on it carries where it came from, and the cost carries the
// sentence that says it is an assumption rather than a quotation. A modelled
// annual value of zero is shown as zero, because the plant has not supplied a
// contribution margin and inventing one is the thing this product exists not to
// do.

import { IntervalBar, Value } from '@/components/primitives';
import { money, probability } from '@/lib/format';
import type { SensorCard } from '@/lib/types';

export function SensorValueCard({
  card,
  currency = 'USD',
}: {
  card: SensorCard;
  currency?: string;
}) {
  return (
    <section className="border border-rule bg-paper-raised p-3">
      <h3 className="text-section">
        <span className="numeral">{card.station_id}</span> sensor value
      </h3>
      <p className="mt-1 text-body text-ink-2">{card.unknown}</p>
      <dl className="mt-3 flex flex-col gap-2 text-body">
        <div className="flex justify-between gap-3">
          <dt className="text-label text-ink-2">Proposed</dt>
          <dd className="text-right">{card.option_name}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-label text-ink-2">Signal it adds</dt>
          <dd className="max-w-[60%] text-right text-small text-ink-2">
            {card.signal_provided}
          </dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-label text-ink-2">Confidence now</dt>
          <dd className="numeral text-right">
            {probability(card.confidence_now)}
          </dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-label text-ink-2">Projected</dt>
          <dd className="numeral text-right">
            {probability(card.confidence_projected_lo)} to{' '}
            {probability(card.confidence_projected_hi)}
          </dd>
        </div>
        <div>
          <IntervalBar
            lo={card.confidence_projected_lo}
            hi={card.confidence_projected_hi}
            point={card.confidence_now}
            min={0}
            max={1}
            label={`confidence moves from ${probability(card.confidence_now)} to between ${probability(card.confidence_projected_lo)} and ${probability(card.confidence_projected_hi)}`}
          />
          <p className="mt-1 text-small text-ink-3">
            The mark is where confidence sits today. The bar is where it would
            sit with the sensor fitted.
          </p>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-label text-ink-2">Indicative cost</dt>
          <dd className="numeral text-right">
            {money(card.indicative_cost_usd, currency)}
          </dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-label text-ink-2">Install effort</dt>
          <dd className="numeral text-right">
            {card.install_hours.toFixed(1)} h
          </dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-label text-ink-2">Next window</dt>
          <dd className="text-right text-small">{card.next_window}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-label text-ink-2">Modelled annual value</dt>
          <dd className="text-right">
            <Value estimate={card.modelled_annual_value} digits={0} />
          </dd>
        </div>
      </dl>
      <p className="mt-3 text-small text-ink-3">{card.resolves}</p>
      <p className="mt-2 text-small text-ink-3">{card.cost_source}</p>
      <p className="mt-1 text-small text-ink-3">
        {card.modelled_annual_value.basis}.
      </p>
      <p className="mt-1 text-small text-ink-3">
        Criticality {probability(card.criticality)}: {card.criticality_basis}.
      </p>
    </section>
  );
}
