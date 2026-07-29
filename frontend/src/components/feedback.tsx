export function LoadingState({
  label = "Loading page",
}: Readonly<{ label?: string }>) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-xl border border-[var(--border)] bg-white p-6 shadow-sm"
    >
      <div
        aria-hidden="true"
        className="h-2 w-24 animate-pulse rounded-full bg-teal-600"
      />
      <p className="mt-4 font-medium text-slate-800">{label}…</p>
    </div>
  );
}

export function ErrorState({
  title = "This view is unavailable",
  message = "The request could not be completed. No entry decision was changed.",
  retry,
}: Readonly<{
  title?: string;
  message?: string;
  retry?: () => void;
}>) {
  return (
    <section
      role="alert"
      className="rounded-xl border border-red-200 bg-red-50 p-6"
    >
      <h2 className="text-lg font-semibold text-red-950">{title}</h2>
      <p className="mt-2 leading-6 text-red-800">{message}</p>
      {retry ? (
        <button
          type="button"
          onClick={retry}
          className="mt-5 min-h-11 rounded-md bg-red-800 px-4 py-2 font-semibold text-white hover:bg-red-900"
        >
          Try again
        </button>
      ) : null}
    </section>
  );
}
