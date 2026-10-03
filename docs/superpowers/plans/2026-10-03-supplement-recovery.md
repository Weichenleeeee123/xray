# Supplement task recovery implementation plan

**Goal:** On the #16 report, recover supplement and secondary-analysis tasks after refresh or a connection failure without submitting duplicate analysis.

**Architecture:** Use the existing POST /api/cases/{id}/runs and GET /api/runs/{id} endpoints. Save the request body and an idempotency key before submission, then save the run id. Scope pending records by case. Read back the saved case and open the task's exact version. Navigation cancels only the browser watcher, not the server task.

**Tech stack:** Native JavaScript, localStorage, existing report dialog/progress component, node:test VM integration tests.

### Task 1: Durable client
- [x] Add `web/tests/supplement-runs.test.cjs`: refresh only polls; lost POST response reuses key and body; polling failure retains record; exact completed version; terminal failures; storage unavailable; abort.
- [x] Run `node --test web/tests/supplement-runs.test.cjs` and observe missing-feature failures.
- [x] Add `web/supplement-runs.js`, exporting `create({api,storage,randomUUID,wait})` with `pending(caseId)`, `prepare(caseId,body)`, `follow(record,{signal,onEvent})`, and `clear(record)`.
- [x] Run the same tests to green.

### Task 2: Report integration
- [x] Update `web/tests/stream-integration.test.cjs` for the durable endpoint; add dialog recovery, duplicate-click and stale-navigation assertions.
- [x] Observe integration failures, then change `web/app.js`: intercept pending submissions; show progress/reconnect controls; restore on entering the case; retain pending completion if the reader left; allow explicit editing only after a confirmed terminal failure.
- [x] Register the new script and refresh app cache token in `web/index.html`.
- [x] Run `node --test --test-reporter=dot web/tests/*.test.cjs`.

### Task 3: Verification
- [x] Test local #16 in browser: submit, refresh, recover result, inspect version and console.
- [x] Run homepage regression suite: `node --experimental-strip-types --test --test-reporter=dot research-room/tests/*.test.mjs`.
- [x] Inspect diff and record results. No production deployment or file deletion.


### Verification results
- Report suite: 155/155 passed (21 added tests relative to the #16 baseline).
- Research-room suite: 99/99 passed.
- Existing backend supplement recovery/idempotency tests: 2/2 passed. Only the pre-existing Starlette/httpx deprecation warning was emitted.
- Browser on localhost, real #16 report and real backend, fictional demo data, model/commercial services disabled: submitted a supplement, blocked progress requests, refreshed, then resumed. Network trace contained exactly one POST and three GETs for the same run; the report opened version 3.
- Repeated with the final disconnection wording: unblocked progress requests and refreshed; version 4 opened automatically. Console warnings/errors: none. All temporary network blocking was removed.
- Navigation, dialog dismissal, lost submission response, exact-version readback, explicit retry after terminal failure, local-storage failure and original scenario restoration are covered by automated tests.
- Recovery is local to this browser and case. It cannot survive clearing browser storage. Server-interrupted tasks are not silently rerun; the reader can inspect existing versions and explicitly edit/resubmit.
- Browser evidence remains in `output/pr16-verification/supplement-recovery.jpg` and `supplement-restored.jpg` (local artifacts, not shipped).
- No backend API changes, deployment, or file deletion.
