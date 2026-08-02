import type { Metadata } from "next";

import { PageHeader } from "@/components/page-layout";
import { VehicleManagement } from "@/components/vehicle-management";

export const metadata: Metadata = {
  title: "Authorized vehicles",
};

export default function AuthorizedVehiclesPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Vehicle records"
        title="Authorized vehicles"
        description="Manage normalized allowlist records, validity windows, and entry-decision status without exposing server credentials."
      />
      <VehicleManagement />
    </div>
  );
}
