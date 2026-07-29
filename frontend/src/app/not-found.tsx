import Link from "next/link";

import { ErrorState } from "@/components/feedback";

export default function NotFound() {
  return (
    <div className="space-y-5">
      <ErrorState
        title="Page not found"
        message="The requested operations page does not exist."
      />
      <Link
        href="/dashboard"
        className="inline-flex min-h-11 items-center rounded-md bg-[var(--brand)] px-4 py-2 font-semibold text-white hover:bg-[var(--brand-strong)]"
      >
        Return to dashboard
      </Link>
    </div>
  );
}
