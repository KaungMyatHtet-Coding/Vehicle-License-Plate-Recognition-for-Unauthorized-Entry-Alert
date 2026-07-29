"use client";

import { useEffect } from "react";

import { ErrorState } from "@/components/feedback";

export default function GlobalError({
  error,
  reset,
}: Readonly<{
  error: Error & { digest?: string };
  reset: () => void;
}>) {
  useEffect(() => {
    // Keep browser reporting free of raw provider details in the UI.
    console.error("A frontend route failed.", { digest: error.digest });
  }, [error.digest]);

  return <ErrorState retry={reset} />;
}
