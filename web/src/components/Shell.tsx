'use client';

// The one place the live feed is opened, so that switching between the three
// views does not drop the connection and rebuild the state from nothing.
//
// The simulated-data marker sits in the header, which is rendered here rather
// than in a view, so that no screenshot of any screen can be taken without it
// (AC-092).

import { createContext, useContext, useState } from 'react';
import type { ReactNode } from 'react';
import { AppHeader } from '@/components/frame';
import { useLine, type LineFeed } from '@/lib/useLine';

const FeedContext = createContext<LineFeed | null>(null);

export function useFeed(): LineFeed {
  const feed = useContext(FeedContext);
  if (feed === null) {
    throw new Error('a view was rendered outside the shell that holds the feed');
  }
  return feed;
}

export function Shell({ children }: { children: ReactNode }) {
  const feed = useLine();
  const [persona, setPersona] = useState('supervisor');
  return (
    <FeedContext.Provider value={feed}>
      <AppHeader
        line={feed.line}
        lines={feed.lines}
        asOf={feed.state?.as_of ?? null}
        ageSeconds={feed.state?.age_s ?? 0}
        replay={feed.state?.replay ?? null}
        persona={persona}
        onPersona={setPersona}
      />
      <main>{children}</main>
    </FeedContext.Provider>
  );
}
