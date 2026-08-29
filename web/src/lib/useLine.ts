'use client';

// The live connection. T-082, EC-52.
//
// The socket is the primary path and polling is the fallback. Two behaviours
// are load-bearing:
//
// A gap in the sequence number triggers a full re-fetch rather than an attempt
// to patch. Applying a partial update on top of a state that may have moved
// produces a screen that is subtly wrong and says nothing about it, which is
// the failure this product exists to argue against.
//
// A connection that drops does not reconnect silently. `connected` goes false,
// the data age keeps counting, and the header shows the age going stale. A
// supervisor reading an old screen needs to know it is old far more than they
// need it to quietly recover.

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiProblem, api, socketUrl } from '@/lib/api';
import type {
  Actions,
  Forecast,
  LineState,
  LineSummary,
  Notice,
  UnitsAtRisk,
} from '@/lib/types';

// How often the fallback poll runs when the socket is not carrying. Matched to
// the forecast cadence rather than to a round number: polling faster than the
// twin thinks produces the same answer at a cost.
const POLL_MS = 4000;

export interface LineFeed {
  line: LineSummary | null;
  lines: LineSummary[];
  state: LineState | null;
  actions: Actions | null;
  risk: UnitsAtRisk | null;
  forecast: Forecast | null;
  notices: Notice[];
  waiting: string | null;
  failure: string | null;
  connected: boolean;
  refresh: () => void;
}

export function useLine(lineId?: string): LineFeed {
  const [lines, setLines] = useState<LineSummary[]>([]);
  const [line, setLine] = useState<LineSummary | null>(null);
  const [state, setState] = useState<LineState | null>(null);
  const [actions, setActions] = useState<Actions | null>(null);
  const [risk, setRisk] = useState<UnitsAtRisk | null>(null);
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [waiting, setWaiting] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [tick, setTick] = useState(0);
  const seq = useRef<number>(0);

  const refresh = useCallback(() => setTick((value) => value + 1), []);

  useEffect(() => {
    let live = true;
    api
      .lines()
      .then((body) => {
        if (!live) return;
        setLines(body.lines);
        const found =
          body.lines.find((item) => item.line_id === lineId) ?? body.lines[0];
        setLine(found ?? null);
      })
      .catch((problem: unknown) => {
        if (!live) return;
        setFailure(
          problem instanceof Error
            ? `The twin is not answering. ${problem.message}`
            : 'The twin is not answering.',
        );
      });
    return () => {
      live = false;
    };
  }, [lineId]);

  const load = useCallback(async (id: string) => {
    try {
      const next = await api.state(id);
      setState(next);
      setWaiting(null);
      setFailure(null);
    } catch (problem) {
      if (problem instanceof ApiProblem && problem.isWaitingForHistory) {
        setWaiting(problem.detail);
      } else if (problem instanceof Error) {
        setFailure(problem.message);
      }
      return;
    }
    const quiet = async <T,>(call: Promise<T>, set: (value: T) => void) => {
      try {
        set(await call);
      } catch (problem) {
        if (!(problem instanceof ApiProblem && problem.isWaitingForHistory)) {
          // A part of the screen that cannot answer leaves its own region
          // saying so; it does not take the rest of the screen down with it.
          return;
        }
      }
    };
    await Promise.all([
      quiet(api.actions(id), setActions),
      quiet(api.unitsAtRisk(id), setRisk),
      quiet(api.forecast(id), setForecast),
      quiet(api.notices(id), setNotices),
    ]);
  }, []);

  useEffect(() => {
    if (!line) return undefined;
    void load(line.line_id);
    const timer = window.setInterval(() => {
      void load(line.line_id);
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [line, load, tick]);

  useEffect(() => {
    if (!line) return undefined;
    let socket: WebSocket | null = null;
    try {
      socket = new WebSocket(socketUrl(line.line_id));
    } catch {
      return undefined;
    }
    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onerror = () => setConnected(false);
    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data as string) as {
          type: string;
          seq: number;
          payload: Record<string, unknown>;
        };
        if (seq.current && message.seq > seq.current + 1) {
          // A gap. Re-fetch everything rather than patch a state that may have
          // moved underneath the missing messages (EC-52).
          seq.current = message.seq;
          void load(line.line_id);
          return;
        }
        seq.current = message.seq;
        if (message.type === 'STATE') {
          setState(message.payload as unknown as LineState);
          setWaiting(null);
        } else if (message.type === 'ACTIONS') {
          setActions(message.payload as unknown as Actions);
        } else if (message.type === 'UNITS_AT_RISK') {
          setRisk(message.payload as unknown as UnitsAtRisk);
        } else if (message.type === 'NOTICE') {
          setNotices(
            (message.payload.notices as Notice[] | undefined) ?? [],
          );
        }
      } catch {
        void load(line.line_id);
      }
    };
    return () => {
      socket?.close();
    };
  }, [line, load]);

  return {
    line,
    lines,
    state,
    actions,
    risk,
    forecast,
    notices,
    waiting,
    failure,
    connected,
    refresh,
  };
}
