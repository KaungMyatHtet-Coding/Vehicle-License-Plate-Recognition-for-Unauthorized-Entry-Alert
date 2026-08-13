import type { Metadata } from "next";

import { PageHeader } from "@/components/page-layout";
import { AlertsView } from "@/components/operational-views";

export const metadata: Metadata = {
  title: "Alerts",
};

export default function AlertsPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Review queue"
        title="Alerts"
        description="Backend-selected unauthorized and manual-review outcomes for non-accusatory operator review."
      />
      <AlertsView />
    </div>
  );
}
