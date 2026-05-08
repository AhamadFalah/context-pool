# Project Context Pool — Agent Contract

This folder is **shared memory** between Claude (web), Kiro, and Claude Code.
Any agent working on this project MUST follow this protocol.

## Files

| File | Purpose |
|---|---|
| `context.md` | Human-readable running log. Newest entries at the bottom. |
| `state.json` | Structured state: current task, last agent, blockers, next actions. |
| `context.lock` | Exists only when an agent is writing. Contains agent name + timestamp. |
| `history/` | Append-only snapshots after every write. Source of truth if anything corrupts. |

## Protocol — every agent follows this

### 1. Before doing anything

Read in this order:
1. `state.json` — what was the last agent doing? what's the current task? open questions?
2. Last 1–3 files in `history/` — most recent context, full fidelity
3. `context.md` — full log if you need deeper context

### 2. Before writing

Check `context.lock`. If it exists:
- Read the JSON inside. Note the `agent` and `acquired_at`.
- If `acquired_at` is **less than 5 minutes old**, WAIT. Poll every 2 seconds.
- If `acquired_at` is **more than 5 minutes old**, the holder probably crashed.
  You may steal the lock — but log that you did.

If `context.lock` does not exist, create it atomically with:
```json
{
  "agent": "claude-code",
  "task": "implementing mintsoft uploader",
  "acquired_at": "2026-05-08T16:45:00Z",
  "pid": 12345
}
```

### 3. While holding the lock

- Append your update to `context.md` with a header: `## <ISO timestamp> — <agent name>`
- Snapshot the new `context.md` into `history/<timestamp>__<agent>.md`
- Patch `state.json` — update `last_agent`, `current_task`, `next_actions`, etc.
- **Hold the lock for the minimum time needed.** Do your thinking BEFORE you grab it.

### 4. Release

Delete `context.lock`. Always. Even if you errored — wrap it in try/finally
or use the Python `acquire()` context manager.

## What to write in context.md

Be useful to the next agent, who has no memory. Include:

- **What I did** — concrete actions, files touched, decisions made
- **What I learned** — surprises, gotchas, dead ends
- **What's next** — specific next action, not vague intentions
- **Open questions** — things you couldn't resolve, that need the human or another agent
- **Don't repeat** — what's already in earlier entries; reference them by timestamp instead

## What NOT to do

- Do not write without holding the lock. The next agent's work will collide with yours.
- Do not delete or rewrite earlier entries. Append-only. If something was wrong, write a correction entry.
- Do not put secrets (API keys, tokens, credentials) in context.md. It's plain text and goes in git.
- Do not hold the lock while waiting for human input. Release, let the user reply, then re-acquire.

## Quick commands

From bash (Kiro, Claude Code):
```bash
# Read current context
python3 context_pool.py read /path/to/project-context

# Check state
python3 context_pool.py state /path/to/project-context

# Append (handles locking automatically)
echo "Did X. Next: Y." | python3 context_pool.py append \
  /path/to/project-context claude-code "task name"
```
