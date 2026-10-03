# Readable source records implementation plan

**Approved design:** Use common recursive fields, record cards and financial tables, with source-specific field ordering. Preserve saved JSON, all unknown fields, provenance, citation highlights and original values. Distinguish platform totals from returned rows. No new queries or derived risk judgments.

**Execution:** Inline in the existing workspace, as requested by the user. Do not delete files.

- [x] Create `web/source-records.js`: standalone renderer; nested groups and arrays; cards for cases, jobs, changes, licenses, news; financial period table; raw JSON disclosure.
- [x] Create `web/dossier/source-records.css`: readable responsive cards and before/after comparison; scope styles to source content.
- [x] Connect `openRaw` in `web/app.js`, load assets in `web/index.html`, preserve noncommercial rendering.
- [x] Test each family, unknown fields, zero/false/null, mixed arrays, incomplete samples, links, escaping, highlights and data immutability with Node tests.
- [x] Audit every commercial record in the saved cold-run report and compare rendered field/value coverage; inspect each family in browser, including 390px mobile width. All 12 source families preserve every saved nonempty leaf value and field; no section overflow, financial table scrolls within its own region.
- [ ] Run all frontend tests, commit only task files, push main, deploy exact committed revision and verify public assets and source dialogs.
