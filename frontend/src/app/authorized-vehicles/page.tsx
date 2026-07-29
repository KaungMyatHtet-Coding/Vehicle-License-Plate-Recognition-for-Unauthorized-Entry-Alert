import type { Metadata } from "next";

import { FoundationPanel, PageHeader } from "@/components/page-layout";

export const metadata: Metadata = {
  title: "Authorized vehicles",
};

export default function AuthorizedVehiclesPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Vehicle records"
        title="Authorized vehicles"
        description="The responsive route is established. Search, validation, and record management remain Day 15 work."
      />
      <FoundationPanel
        title="Management tools not connected"
        description="No database connection or browser credential is present in this frontend foundation."
      />
    </div>
  );
}
