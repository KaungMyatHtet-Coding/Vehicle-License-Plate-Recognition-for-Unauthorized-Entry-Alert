# Day 14 UI evidence

These eight 1440×1100 Playwright/system-Chrome screenshots demonstrate the real
Day 14 frontend rendering deterministic intercepted API contracts:

- populated and empty dashboard states;
- populated history and restricted-evidence detail states;
- sanitized history-detail not-found and accessible invalid-filter states;
- populated backend-selected alerts;
- a sanitized server-failure state.

Verify the states without writing screenshots from `frontend` with
`npm.cmd run evidence:day14`. To intentionally regenerate screenshots in
PowerShell, set `$env:CVPX_CAPTURE_DAY14_EVIDENCE='1'` for that command and
remove the variable afterward. Interception is test-only and does not bypass
production behavior. The images do not prove live
detector or OCR accuracy, database performance, Supabase integration, or
production authentication/authorization.
