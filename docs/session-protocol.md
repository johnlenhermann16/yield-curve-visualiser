# Session Protocol

- Use claude-opus-5 for architecture and complex/judgment-heavy logic
- Use claude-sonnet-5 for straightforward coding and multi-file work
- Use claude-haiku-4-5 for small, well-scoped fixes
- No mid-task questions unless truly blocking
- One focused milestone per session
- Diagnostic-first for any new data source: read/verify before building,
  never guess API parameters or assume column/label positions — inspect
  real data first
- Prefer complete file replacements over partial edits when the file is
  small enough; for larger files, be precise with str_replace
- Ponytail plugin installed (enforces minimal/lean code generation,
  stdlib-preferred) — user scope, from https://github.com/dietrichgebert/ponytail
  Reinstall after a machine move with:
    claude plugin marketplace add https://github.com/dietrichgebert/ponytail --scope user
    claude plugin install ponytail@ponytail --scope user
  Ships three hooks (SessionStart, SubagentStart, UserPromptSubmit) that run
  local node scripts, so node must be on PATH or the plugin silently no-ops.
  Plugins load at CLI process start — after a fresh install, `/clear` does
  NOT pick it up, you must fully quit and relaunch Claude Code. To check
  whether it is live: `cat ~/.claude/.ponytail-active` (absent = off,
  otherwise holds the mode: lite/full/ultra).
