# Hangzhou Demo Refresh Implementation Plan

> **Execution:** User explicitly requested no subagents. The primary agent implements, reviews, verifies, and deploys in this session. The initially started subagent was interrupted before any edits.

**Goal:** Refresh Hangzhou Bank's actual prebuilt evidence using current sources and improve its approved factual presentation without changing risk evidence or fabricating a high trust rating.

**Architecture:** A server-only prebuilt presentation payload is bound to the precise company, scenario, version, and saved evidence. A pure validation function accepts it only on a matching prebuilt version. The UI and print view render the approved factual summary while retaining every anomaly, count, reference, and the existing prebuilt date. Fresh research is generated in a new staging directory before any live switch.

**Tech Stack:** Python/Pydantic/FastAPI, vanilla JavaScript, pytest, node:test, Linux systemd deployment, PowerShell orchestration.

---

## Task 1: Evidence-bound prebuilt presentation

Files: `backend/app/models.py`, a new focused module `backend/app/demo_presentation.py`, `backend/app/main.py` integration, `web/dossier-report.js`, print integration in `web/app.js`, narrowly scoped CSS if needed; focused backend and frontend tests.

- [ ] Write failing backend tests for a valid server-prepared presentation, unchanged underlying overview/status/counts, and rejection after evidence, company, scenario, version, or need changes; reject on non-prebuilt versions and missing references.
- [ ] Define an optional presentation model carrying title, note, body, refs, and evidence digest. The public CaseIn/SupplementIn interfaces must not accept it. Keep the name neutral, e.g. `report_presentation`; do not add “示例解读” or “人工解读” to user-visible text.
- [ ] Implement a stable fingerprint and validation over the relevant version and its actual raw records. Exclude derived presentation/overview fields and replay identity so a new owner/id does not invalidate a legitimate replay. Validate raw reference membership. Persist/read hooks validate after derived data refresh. A new non-prebuilt version must never inherit the presentation.
- [ ] Write failing frontend tests: approved title/note/body render and are escaped; anomaly counts/evidence actions remain; ordinary reports are unchanged; print uses the same factual presentation without claiming a higher algorithmic rating.
- [ ] Render the presentation in the main summary using existing layout and neutral factual styling. Do not use a high-trust checkmark or make trust_level high. Preserve adverse items and counts in the same report.
- [ ] Run targeted backend/frontend tests, review diff, commit only task files. Report the exact server payload format and helper API to the parent.
- [ ] Separate spec review, then quality review; fix any findings and re-review.

Run backend tests with UTF-8, a new explicit retained basetemp, cacheprovider disabled, and PYTHONDONTWRITEBYTECODE=1. Run frontend tests with `node --test`. No file deletion, test cleanup, worktree creation, or unrelated edits.

## Task 2: Refresh actual prebuilt data

Files: private audit/build scripts and reports under `.tmp/hangzhou-demo-refresh-20261003/`; new remote build workspace under `/var/lib/qier/`.

- [ ] Compare old bundle source IDs, coverage, source dates, and supplement stages with the current source collection and demo configuration.
- [ ] Use current production credentials through its existing EnvironmentFile, without printing secrets. Preserve configured provider budget; no purchase or budget increase.
- [ ] Generate B only with prebuilt replay disabled and an empty isolated cache. Isolate cases, memory, runs, reviews, private data, and output bundle. Use a background systemd unit and inspect concise progress.
- [ ] Confirm complete configured supplement sequence, source failures, normal/attention/abnormal/unknown counts, and raw references. A fresh failed or less complete record is not automatically eligible to replace the previous bundle.
- [ ] If a source fails, diagnose and retry only the specific failed calls using already collected successful results. Keep the limitation visible if it cannot be recovered.
- [ ] Write presentation payloads only after fresh facts support the approved wording. Do not hard-code old record counts or assert that penalties are minor/rectified. Use the actual records and dates from each version.

## Task 3: Integrate, verify, deploy

- [ ] Run existing relevant/full backend and frontend checks once after integration. Validate fresh B using the actual deployed application path and replay all configured stages with external access disabled.
- [ ] Prepare a new release, backup the previous bundle and code, and verify hashes. Do not delete or rewrite other saved user cases.
- [ ] Check production queries before switching; perform the existing service/link activation procedure. Preserve rollback paths and all backups.
- [ ] Verify live health, new assets, authenticated demo creation, headline/body/counts/references, and supplement replay. Report evidence dates separately from the build time, unresolved source gaps, and the new release identifier.

## Constraints and review

User approved the design and removed the extra interpretation label. User additionally requested source refresh. Existing prebuilt origin/date remain. Work stays in `D:/company research` per the earlier workspace consolidation request. No files may be deleted. Existing unrelated local changes remain untouched. The implementation must not turn sponsorship into a company-specific rating override.
