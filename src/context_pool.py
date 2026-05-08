"""
Context Pool Manager
--------------------
Shared memory between multiple LLM agents (Claude, Kiro, Claude Code).

Design goals:
1. No context loss      -> append-only history + atomic writes
2. Continuity           -> state.json tracks last agent + open task
3. Mutual exclusion     -> lock file with stale-lock detection
4. Human-auditable      -> markdown for content, JSON for metadata

Usage from any agent:
    pool = ContextPool("/path/to/project-context")
    with pool.acquire(agent="claude", task="refactor mintsoft uploader"):
        ctx = pool.read()
        # ... think, work, decide what to add ...
        pool.append("## 2026-05-08 — Claude\n\nFigured out the CSV mapping...")
    # lock auto-releases on exit, even if exception
"""

import json
import os
import time
import shutil
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


STALE_LOCK_SECONDS = 300       # 5 min — assume crashed agent after this
POLL_INTERVAL_SECONDS = 2      # how often to retry while waiting
MAX_WAIT_SECONDS = 600         # 10 min — give up if lock held this long


class ContextPool:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.context_file = self.root / "context.md"
        self.lock_file = self.root / "context.lock"
        self.state_file = self.root / "state.json"
        self.history_dir = self.root / "history"
        self._init_if_missing()

    def _init_if_missing(self):
        self.root.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(exist_ok=True)
        if not self.context_file.exists():
            self.context_file.write_text(
                "# Project Context Pool\n\n"
                "Shared memory across Claude, Kiro, and Claude Code.\n"
                "Append entries below. Newest at the bottom.\n\n"
                "---\n\n"
            )
        if not self.state_file.exists():
            self._write_state({
                "last_agent": None,
                "last_updated": None,
                "current_task": None,
                "open_questions": [],
                "blockers": [],
                "next_actions": [],
            })

    # ---------- locking ----------

    def _read_lock(self) -> dict | None:
        if not self.lock_file.exists():
            return None
        try:
            return json.loads(self.lock_file.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def _is_stale(self, lock_data: dict) -> bool:
        acquired = datetime.fromisoformat(lock_data["acquired_at"])
        age = (datetime.now(timezone.utc) - acquired).total_seconds()
        return age > STALE_LOCK_SECONDS

    @contextmanager
    def acquire(self, agent: str, task: str = ""):
        """
        Block until we own the lock, then yield. Auto-release on exit.
        Forcibly steals stale locks (crashed agents).
        """
        waited = 0
        acquired = False
        while not acquired:
            existing = self._read_lock()
            if existing is not None:
                if self._is_stale(existing):
                    print(f"[context-pool] stealing stale lock from "
                          f"{existing['agent']} (age > {STALE_LOCK_SECONDS}s)")
                    try:
                        self.lock_file.unlink()
                    except FileNotFoundError:
                        pass  # someone else already cleaned it up
                else:
                    if waited >= MAX_WAIT_SECONDS:
                        raise TimeoutError(
                            f"Lock held by {existing['agent']} for too long. "
                            f"Manual intervention required."
                        )
                    print(f"[context-pool] {agent} waiting — held by "
                          f"{existing['agent']} ({existing.get('task', '?')})")
                    time.sleep(POLL_INTERVAL_SECONDS)
                    waited += POLL_INTERVAL_SECONDS
                    continue

            # Try atomic create. O_EXCL guarantees only one agent wins.
            try:
                fd = os.open(
                    self.lock_file,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY
                )
                with os.fdopen(fd, "w") as f:
                    json.dump({
                        "agent": agent,
                        "task": task,
                        "acquired_at": datetime.now(timezone.utc).isoformat(),
                        "pid": os.getpid(),
                    }, f)
                acquired = True
            except FileExistsError:
                # Lost the race — another agent grabbed it. Loop and wait.
                continue

        try:
            yield self
        finally:
            try:
                self.lock_file.unlink()
            except FileNotFoundError:
                pass

    # ---------- reads ----------

    def read(self) -> str:
        return self.context_file.read_text()

    def state(self) -> dict:
        return json.loads(self.state_file.read_text())

    def latest_history(self, n: int = 3) -> list[Path]:
        files = sorted(self.history_dir.glob("*.md"))
        return files[-n:]

    # ---------- writes (must be inside acquire()) ----------

    def append(self, markdown: str, agent: str = "unknown"):
        """Append to context.md and snapshot to history."""
        if not self._we_hold_lock(agent):
            raise RuntimeError(
                f"{agent} tried to write without holding the lock. "
                "Wrap writes in `with pool.acquire(agent=...):`."
            )

        timestamp = datetime.now(timezone.utc).isoformat()
        entry = f"\n## {timestamp} — {agent}\n\n{markdown.strip()}\n\n---\n"

        # Atomic append: write to temp, then move.
        current = self.context_file.read_text()
        tmp = self.context_file.with_suffix(".md.tmp")
        tmp.write_text(current + entry)
        tmp.replace(self.context_file)

        # Snapshot to history.
        slug = timestamp.replace(":", "-").replace(".", "-")
        snapshot = self.history_dir / f"{slug}__{agent}.md"
        shutil.copy(self.context_file, snapshot)

    def update_state(self, agent: str, **changes):
        """Patch state.json. Must hold lock."""
        if not self._we_hold_lock(agent):
            raise RuntimeError(f"{agent} tried to update state without lock.")
        state = self.state()
        state.update(changes)
        state["last_agent"] = agent
        state["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._write_state(state)

    def _write_state(self, state: dict):
        tmp = self.state_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=2))
        tmp.replace(self.state_file)

    def _we_hold_lock(self, agent: str) -> bool:
        lock = self._read_lock()
        return lock is not None and lock["agent"] == agent


# ---------- CLI for non-Python agents (Kiro, Claude Code via bash) ----------

if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if not args:
        print("Usage:")
        print("  context_pool.py read <root>")
        print("  context_pool.py state <root>")
        print("  context_pool.py append <root> <agent> <task> <<< 'markdown'")
        sys.exit(1)

    cmd, root = args[0], args[1]
    pool = ContextPool(root)

    if cmd == "read":
        print(pool.read())
    elif cmd == "state":
        print(json.dumps(pool.state(), indent=2))
    elif cmd == "append":
        agent, task = args[2], args[3]
        markdown = sys.stdin.read()
        with pool.acquire(agent=agent, task=task):
            pool.append(markdown, agent=agent)
            pool.update_state(agent=agent, current_task=task)
        print(f"[context-pool] {agent} appended successfully")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
