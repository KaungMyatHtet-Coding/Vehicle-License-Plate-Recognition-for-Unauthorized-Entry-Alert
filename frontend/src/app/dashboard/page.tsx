import type { Metadata } from "next";

import { FoundationPanel, PageHeader } from "@/components/page-layout";

export const metadata: Metadata = {
  title: "Dashboard",
};

export default function DashboardPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Operations overview"
        title="Dashboard"
        description="A responsive foundation for recognition activity, decision totals, and system health. Live statistics arrive in a later milestone."
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <FoundationPanel
          title="Recognition status"
          description="The Day 12 shell is ready for the still-image workflow without invoking detector or OCR services."
        />
        <FoundationPanel
          title="Decision summary"
          description="Authorized, unauthorized, and manual-review totals remain server-derived future work."
        />
        <FoundationPanel
          title="Privacy posture"
          description="Evidence stays private; this foundation exposes no storage path, credential, or public evidence URL."
        />
      </div>
    </div>
  );
}
