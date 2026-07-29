import type { Metadata } from "next";

import { FoundationPanel, PageHeader } from "@/components/page-layout";

export const metadata: Metadata = {
  title: "Alerts",
};

export default function AlertsPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Review queue"
        title="Alerts"
        description="A non-accusatory foundation for future operational alerts and manual-review states."
      />
      <FoundationPanel
        title="No alert feed connected"
        description="Day 12 sends no notifications and does not interpret an unauthorized result as proof of wrongdoing."
      />
    </div>
  );
}
