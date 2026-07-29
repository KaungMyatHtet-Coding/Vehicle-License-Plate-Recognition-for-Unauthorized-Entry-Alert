import type { Metadata } from "next";

import { FoundationPanel, PageHeader } from "@/components/page-layout";

export const metadata: Metadata = {
  title: "Detection history",
};

export default function HistoryPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Audit trail"
        title="Detection history"
        description="A safe placeholder for paginated, server-derived detection records planned for Day 14."
      />
      <FoundationPanel
        title="No history loaded"
        description="The browser has not requested detection metadata or private evidence."
      />
    </div>
  );
}
