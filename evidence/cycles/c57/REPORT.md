# C57 security and UI validation

2026-09-10. Branch: `cycle-57-security-ui`.

Implemented strict CSP on chat, dashboard and questionnaire; extracted local
assets; pinned DOMPurify; sanitized dashboard rendering; identity/visibility and
data-handling links; stage progress; manual upload classification; and an opt-in
direct-upload path with scoped, expiring delegation SAS and conditional copy.

The sponsor cancelled Google/GitHub OAuth registration. No registrations were
created. Setup browser stopped; temporary helper removed. Authentication remains
Microsoft Entra ID only. Regression coverage rejects explicit other providers.

## Check

- Full pytest suite: **568 passed, 13 skipped**, one existing Starlette warning.
- Playwright browser suite: **11 passed**, including populated strict-CSP
  dashboard/questionnaire, hostile HTML sanitation and large-file upload flow.
- Evals: **32 SQL, 30 faults, 74 adversarial, 8 scenarios passed**; three previously
  pending adversarial acceptance items remain pending.
- JavaScript syntax checks passed for chat, dashboard, safe-html and DOMPurify.
- Generated questionnaire/catalog assets checked for consistency.

Browser failures revealed a stale generated remote font link and expected
optional-resource 404 diagnostics; corrected generated assets and introduced
explicit optional-resource semantics before rerunning successfully.

## Remaining acceptance

Web deployment and live verification are pending. Direct uploads are disabled
until storage CORS, abandoned-upload lifecycle and live acceptance are configured.
Mocked browser journeys do not prove two-user Entra production isolation. Real
participant sign-in and independent reviews remain outstanding. C56 API deployed;
its web client and agent tool refresh still require release and live acceptance.
