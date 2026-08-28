import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import '@/styles/tokens.css';
import '@/styles/globals.css';

export const metadata: Metadata = {
  title: 'DigitalTwin.ai',
  description: 'A live read-only digital twin of a mixed-model vehicle assembly line',
};

interface RootLayoutProps {
  children: ReactNode;
}

// The simulated-data marker sits in the layout rather than in a view so that no
// screenshot of any screen can be taken without it (AC-092).
export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="en">
      <body>
        <header className="flex items-baseline justify-between border-b border-rule px-6 py-3">
          <span className="text-section font-mono">DigitalTwin.ai</span>
          <span className="text-small text-ink-2">Simulated data</span>
        </header>
        <main className="px-6 py-6">{children}</main>
      </body>
    </html>
  );
}
