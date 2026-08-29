'use client';

import { ProgramView } from '@/components/ProgramView';
import { useFeed } from '@/components/Shell';

export default function Page() {
  const feed = useFeed();
  return <ProgramView lineId={feed.line?.line_id ?? null} />;
}
