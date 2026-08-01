import type { Metadata } from "next";

import { PageHeader } from "@/components/page-layout";
import { HistoryView } from "@/components/operational-views";

export const metadata: Metadata = {
  title: "Detection history",
};

export default function HistoryPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Audit trail"
        title="Detection history"
        description="Paginated, filtered detection records with sanitized detail and restricted evidence metadata."
      />
      <HistoryView />
    </div>
  );
}
