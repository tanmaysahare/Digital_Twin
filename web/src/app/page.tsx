'use client';

import { LineView } from '@/components/LineView';
import { useFeed } from '@/components/Shell';

export default function Page() {
  return <LineView feed={useFeed()} />;
}
