# Day 12 frontend foundation

## Scope

Day 12 establishes the browser shell only. Next.js App Router, strict
TypeScript, Tailwind CSS, and ESLint provide five responsive route layouts,
typed API access, reusable loading/error states, and an accessibility baseline.
Recognition submission/results, persistence queries, alerts, and vehicle
management remain later milestones.

## Routes and responsive behavior

The root redirects to `/dashboard`. Dashboard, recognition, history, alerts,
and authorized-vehicle routes each provide a unique page title, one descriptive
`h1`, and a safe empty foundation state. Navigation is horizontally scrollable
on narrow screens and becomes a persistent sidebar at the Tailwind `md`
breakpoint. Content uses bounded responsive padding and grids without a fixed
viewport width.

Accessibility foundations include:

- a keyboard-visible skip link;
- semantic `nav` and `main` landmarks;
- `aria-current` for the active route;
- unique metadata and headings for route announcements;
- visible focus outlines and minimum-height actions;
- polite loading status and assertive error status;
- reduced-motion handling.

## Typed API and security boundary

`NEXT_PUBLIC_API_BASE_URL` defaults to the non-secret local backend URL only in
development and tests. Production fails closed unless an explicit valid public
HTTP(S) API URL is configured. The client rejects credentials, query strings,
fragments, ambiguous endpoint paths, dot segments, and any endpoint that could
escape a configured base path. Request timeouts are bounded from 1 to 60
seconds. Operation-level parsers validate successful responses; malformed JSON,
non-contract responses, network failures, and provider details become stable
sanitized frontend errors.

Only the public backend base URL may use the `NEXT_PUBLIC_` prefix. Supabase
service-role keys, private evidence locations, signed grants, model paths, and
other credentials must never enter browser environment values or source.
Day 12 performs no API request during import or rendering and exposes no public
evidence URL.

Types mirror the stable backend contracts through Day 11, including transient
image validation, detection, OCR, Day 10 decisions, and Day 11 logging results.
Frozen audit and evidence results use deeply readonly TypeScript properties and
collections. The browser does not recompute or mutate authorization decisions.

## Dependencies and limitations

The frontend uses open-source npm dependencies only. Patched transitive
overrides are locked for PostCSS, Sharp, minimatch, and brace-expansion because
the generated dependency graph otherwise selected versions covered by current
security advisories. These overrides are verified by tests, lint, type-check,
production build, and `npm audit`.

Day 12 has no live Supabase adapter, authentication design, browser storage,
recognition workflow, or production deployment. Responsive evidence is limited
to component structure, breakpoint classes, route smoke tests, and the
production build. The installed jsdom environment cannot compute Tailwind
responsive layout and no browser runtime is installed, so an automated real
viewport assertion remains deferred rather than being represented by
user-agent-only HTTP checks.
