import type { Metadata } from "next";

import { PageHeader } from "@/components/page-layout";
import { DashboardView } from "@/components/operational-views";

export const metadata: Metadata = {
  title: "Dashboard",
};

export default function DashboardPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Operations overview"
        title="Dashboard"
        description="Server-derived recognition totals and a timezone-aware seven-day operational trend."
      />
      <DashboardView />
    </div>
  );
}
