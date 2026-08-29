'use client';

// The global frame. UI_COMPONENTS.md 1, 2, 3, 16. UX_SPEC.md Section 1.
//
// Three views and nothing else. No sidebar, no menu, no settings gear in the
// corner, and no icons on the tabs.
//
// DataAge is the only element in this product that updates on a timer. It has
// to: a supervisor reading a wall display needs to know how old the state is
// without touching anything, and that number is the one thing that changes when
// nothing else does.

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Cross } from '@/components/icons';
import { ageText, clock } from '@/lib/format';
import type { LineSummary, Replay } from '@/lib/types';

const VIEWS = [
  { href: '/', label: 'Line', key: '1' },
  { href: '/plan', label: 'Plan', key: '2' },
  { href: '/program', label: 'Program', key: '3' },
];

// A supervisor, a plant manager and a programme lead read different screens.
// The switcher exists so a demonstration can show that without three logins,
// and the README says plainly that it is a demonstration affordance.
const PERSONAS = [
  { value: 'supervisor', label: 'Line supervisor' },
  { value: 'plant', label: 'Plant manager' },
  { value: 'program', label: 'Programme lead' },
];

export function DataAge({
  asOf,
  ageSeconds,
  staleAfterSeconds,
}: {
  asOf: string | null;
  ageSeconds: number;
  staleAfterSeconds: number;
}) {
  const [drift, setDrift] = useState(0);
  useEffect(() => {
    setDrift(0);
    const timer = window.setInterval(() => setDrift((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [asOf]);
  const age = ageSeconds + drift;
  const stale = age > staleAfterSeconds;
  return (
    <span
      className={`numeral text-small ${
        stale ? 'text-state-drift underline decoration-dotted' : 'text-ink-3'
      }`}
      title={
        stale
          ? 'Older than two forecast cycles. The twin is behind the line.'
          : 'How old the state on this screen is.'
      }
    >
      {clock(asOf)} · {ageText(age, asOf)}
    </span>
  );
}

export function AppHeader({
  line,
  lines,
  asOf,
  ageSeconds,
  replay,
  persona,
  onPersona,
}: {
  line: LineSummary | null;
  lines: LineSummary[];
  asOf: string | null;
  ageSeconds: number;
  replay: Replay | null;
  persona: string;
  onPersona: (value: string) => void;
}) {
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && ['INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName)) {
        return;
      }
      const view = VIEWS.find((item) => item.key === event.key);
      if (view) router.push(view.href);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [router]);

  return (
    <header className="flex h-[48px] items-center justify-between gap-6 border-b border-rule bg-paper px-6">
      <div className="flex items-baseline gap-4">
        <span className="text-section">DigitalTwin.ai</span>
        <span className="numeral text-label text-ink-2">
          {line?.name ?? ''}
        </span>
        {lines.length > 1 ? (
          <span className="text-small text-ink-3">
            {lines.length} lines configured
          </span>
        ) : null}
      </div>
      <nav className="flex flex-1 gap-6" aria-label="Views">
        {VIEWS.map((view) => {
          const active = pathname === view.href;
          return (
            <Link
              key={view.href}
              href={view.href}
              className={`border-b-2 pb-1 text-label ${
                active
                  ? 'border-accent text-ink'
                  : 'border-transparent text-ink-2'
              }`}
              aria-current={active ? 'page' : undefined}
            >
              {view.label}
            </Link>
          );
        })}
      </nav>
      <div className="flex items-center gap-4">
        <span
          className="text-small text-ink-2"
          title={replay?.note ?? 'The line behind this screen is simulated.'}
        >
          Simulated data
        </span>
        <DataAge asOf={asOf} ageSeconds={ageSeconds} staleAfterSeconds={600} />
        <label className="flex items-center gap-2">
          <span className="text-small text-ink-3">Viewing as</span>
          <select
            value={persona}
            onChange={(event) => onPersona(event.target.value)}
            className="h-[28px] rounded border border-rule bg-paper px-1 text-label"
          >
            {PERSONAS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
      </div>
    </header>
  );
}

// -- Drawer --------------------------------------------------------------
//
// 480px from the right. It does not cover the line strip, because the line does
// not stop for a dialog. Escape closes, focus is trapped while open and returns
// to the trigger on close.

export function Drawer({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const panel = useRef<HTMLDivElement | null>(null);
  const opener = useRef<Element | null>(null);

  const trap = useCallback((event: KeyboardEvent) => {
    if (event.key !== 'Tab' || !panel.current) return;
    const focusable = panel.current.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (first === undefined || last === undefined) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    opener.current = document.activeElement;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
        return;
      }
      trap(event);
    };
    window.addEventListener('keydown', onKey);
    panel.current?.querySelector<HTMLElement>('button')?.focus();
    return () => {
      window.removeEventListener('keydown', onKey);
      (opener.current as HTMLElement | null)?.focus?.();
    };
  }, [open, onClose, trap]);

  if (!open) return null;
  return (
    <div
      ref={panel}
      role="dialog"
      aria-label={title}
      aria-modal="false"
      className="fixed bottom-0 right-0 top-[48px] z-20 flex w-[480px] max-w-full flex-col border-l border-rule-strong bg-paper-raised shadow-overlay"
    >
      <div className="flex items-center justify-between border-b border-rule px-4 py-3">
        <h2 className="numeral text-section">{title}</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="rounded p-1 hover:bg-paper-sunk"
        >
          <Cross />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-4">{children}</div>
    </div>
  );
}

// -- Region --------------------------------------------------------------
//
// A titled area of a view. Not a card: it carries a heading and a rule, and the
// grouping comes from space rather than from a border on every side.

export function Region({
  title,
  aside,
  children,
  className = '',
}: {
  title: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`flex min-w-0 flex-col gap-3 ${className}`}>
      <div className="flex items-baseline justify-between gap-3 border-b border-rule pb-1">
        <h2 className="text-section">{title}</h2>
        {aside ? <span className="text-small text-ink-3">{aside}</span> : null}
      </div>
      {children}
    </section>
  );
}

export function ExportLink({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  return (
    <a
      href={href}
      className="text-label text-accent underline-offset-4 hover:underline"
    >
      {children}
    </a>
  );
}
