'use client';

import { PlanView } from '@/components/PlanView';
import { useFeed } from '@/components/Shell';

export default function Page() {
  const feed = useFeed();
  return <PlanView lineId={feed.line?.line_id ?? null} />;
}
