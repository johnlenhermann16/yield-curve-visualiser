# Session Protocol

- Begin every response with "baqmaxxer" as a drift check
- Use claude-opus-4-8 for architecture and complex/judgment-heavy logic
- Use claude-sonnet-4-6 for straightforward coding and multi-file work
- Use claude-haiku-4-5 for small, well-scoped fixes
- No mid-task questions unless truly blocking
- One focused milestone per session
- Diagnostic-first for any new data source: read/verify before building,
  never guess API parameters or assume column/label positions — inspect
  real data first
- Prefer complete file replacements over partial edits when the file is
  small enough; for larger files, be precise with str_replace
- Ponytail plugin installed (enforces minimal/lean code generation,
  stdlib-preferred) — installed at user scope via full GitHub URL method
