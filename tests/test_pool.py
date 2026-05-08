import os, sys, time, json, shutil
from pathlib import Path
from multiprocessing import Process

# Make src/ importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from context_pool import ContextPool

ROOT = Path("/tmp/test-pool")
if ROOT.exists():
    shutil.rmtree(ROOT)

# Test 1: basic acquire + write
print("=== Test 1: basic write ===")
pool = ContextPool(ROOT)
with pool.acquire(agent="claude", task="initial setup"):
    pool.append("Set up the project. Decided on Python 3.11.", agent="claude")
    pool.update_state(agent="claude", current_task="setup", next_actions=["write tests"])
print(pool.read())
print("State:", json.dumps(pool.state(), indent=2))

# Test 2: two agents racing — second must wait
print("\n=== Test 2: race condition ===")
def slow_writer(agent, delay):
    p = ContextPool(ROOT)
    with p.acquire(agent=agent, task=f"{agent}-task"):
        time.sleep(delay)
        p.append(f"{agent} wrote after holding for {delay}s", agent=agent)

p1 = Process(target=slow_writer, args=("kiro", 3))
p2 = Process(target=slow_writer, args=("claude-code", 1))
p1.start()
time.sleep(0.2)  # ensure p1 grabs the lock first
p2.start()
p1.join()
p2.join()

print("Final context after race:")
print(pool.read())

# Test 3: stale lock recovery
print("\n=== Test 3: stale lock recovery ===")
import datetime
fake_old = {
    "agent": "crashed-agent",
    "task": "died mid-edit",
    "acquired_at": (datetime.datetime.now(datetime.timezone.utc)
                    - datetime.timedelta(seconds=600)).isoformat(),
    "pid": 99999
}
pool.lock_file.write_text(json.dumps(fake_old))
print("Planted stale lock from 'crashed-agent' (10 min old)")

with pool.acquire(agent="claude", task="recovery test"):
    pool.append("Recovered from stale lock.", agent="claude")
print("✓ Stole stale lock and wrote successfully")

# Test 4: history preserved
print("\n=== Test 4: history snapshots ===")
files = sorted((ROOT / "history").glob("*.md"))
print(f"History snapshots: {len(files)}")
for f in files:
    print(f"  - {f.name}")
