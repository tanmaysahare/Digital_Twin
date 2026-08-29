import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import '@/styles/tokens.css';
import '@/styles/globals.css';
import { Shell } from '@/components/Shell';

export const metadata: Metadata = {
  title: 'DigitalTwin.ai',
  description:
    'A live read-only digital twin of a mixed-model vehicle assembly line',
};

interface RootLayoutProps {
  children: ReactNode;
}

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="en">
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
