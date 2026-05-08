# Context Pool

> Shared memory between LLM agents — Claude, Kiro, Claude Code, or any other tool — with mutual exclusion so only one agent writes at a time.

When you work across multiple LLM tools on the same project, each one starts fresh with no memory of what the others did. Context Pool fixes that with a shared, append-only log on disk that any agent can read and write to safely.

## Features

- **No context loss** — append-only log + per-write history snapshots
- **Continuity** — `state.json` tracks the current task, last agent, open questions, and next actions, so any agent can pick up where the last one left off
- **Mutual exclusion** — atomic file locking ensures only one agent writes at a time; others wait
- **Crash recovery** — stale locks (from crashed agents) are automatically detected and stolen after a configurable timeout
- **Human-readable** — the log is plain markdown, the state is plain JSON. `git diff` works, `cat` works, your eyes work
- **Zero dependencies** — pure Python standard library, works anywhere Python 3.10+ runs
- **CLI included** — agents that aren't Python (Kiro, Claude Code via bash) call it via the command line

## Quick start

```bash
git clone https://github.com/<your-username>/context-pool.git
cd context-pool

# Initialise a pool for your project
python3 src/context_pool.py read /path/to/your/project-context
```

From any agent's session, point it at the pool:

```bash
# Read current context
python3 src/context_pool.py read /path/to/your/project-context

# See structured state
python3 src/context_pool.py state /path/to/your/project-context

# Append a new entry (handles locking automatically)
echo "Implemented the CSV uploader. Next: wire it to Mintsoft API." | \
  python3 src/context_pool.py append /path/to/your/project-context \
    claude-code "mintsoft-uploader"
```

## How it works

Every pool is just a folder on disk:

```
project-context/
├── context.md       # Append-only running log (newest at the bottom)
├── state.json       # Structured state: current task, last agent, blockers
├── context.lock     # Exists only when an agent is writing
└── history/         # Snapshot of context.md after every write
    ├── 2026-05-08T14-32__claude.md
    ├── 2026-05-08T15-10__kiro.md
    └── 2026-05-08T16-45__claude-code.md
```

When an agent wants to write:

1. It checks for `context.lock`
2. If absent, it atomically creates one with `O_CREAT | O_EXCL` (kernel guarantees only one agent wins this race)
3. If present and fresh, it waits and polls
4. If present but stale (older than 5 minutes), it assumes the holder crashed and steals the lock
5. After writing, it deletes the lock

The atomic lock creation is the core trick — it's the same mechanism used by `mkdir` for safe directory creation, applied to a file.

## Agent onboarding

Paste this into any new session with Claude / Kiro / Claude Code:

> There's a shared context pool at `<your-pool-path>`. Before doing anything, read `state.json` and the latest 1–2 files in `history/`. When you're ready to record progress, run `python3 context_pool.py append <pool-path> <your-agent-name> "<task>" <<< 'your markdown'`. The script handles locking automatically — it will wait if another agent is writing.

See [docs/AGENT_PROTOCOL.md](docs/AGENT_PROTOCOL.md) for the full contract every agent should follow.

## Configuration

Defaults at the top of `src/context_pool.py`:

| Constant | Default | Purpose |
|---|---|---|
| `STALE_LOCK_SECONDS` | 300 | How long before a held lock is assumed dead |
| `POLL_INTERVAL_SECONDS` | 2 | How often to retry while waiting |
| `MAX_WAIT_SECONDS` | 600 | Give up if a lock is held this long |

## Limitations

- **Local filesystems only.** The atomic `O_CREAT | O_EXCL` guarantee does not hold reliably on NFS or some networked filesystems. If you need to share a pool across machines over a network mount, swap the lock layer for `fcntl.flock()` or move to SQLite.
- **No streaming reads.** If an agent needs to react to another agent's writes in real time, you'd want to add file-watching (e.g. `watchdog`). For turn-based collaboration this isn't needed.
- **Trust model assumes cooperation.** Agents are expected to follow the protocol. A misbehaving agent that writes without acquiring the lock will corrupt the log. The `_we_hold_lock()` check catches accidental misuse but not malicious actors.

## Running tests

```bash
python3 tests/test_pool.py
```

Tests cover: basic write, two-agent race condition (process-level), and stale lock recovery.

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Issues and PRs welcome. Particularly interested in:

- Adapters for other lock backends (fcntl, SQLite, Redis)
- A simple TUI or web dashboard for live pool status
- Integration recipes for specific agent tools
