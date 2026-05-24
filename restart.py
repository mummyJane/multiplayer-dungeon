"""
Restart the running Multiplayer Dungeon server without stopping start.py.

    python restart.py

start.py keeps running; it relaunches uvicorn automatically when it sees
the restart flag. Pre-flight checks are NOT re-run — for a full restart
(including checks) use stop.py then start.py.
"""
import sys
import time
from pathlib import Path

ROOT         = ROOT = Path(__file__).parent
PID_FILE     = ROOT / ".server.pid"
RESTART_FLAG = ROOT / ".restart.flag"

# ── ANSI colours ──────────────────────────────────────────────────────────────
G = "\033[0;32m"
Y = "\033[0;33m"
R = "\033[0;31m"
C = "\033[0;36m"
X = "\033[0m"

if __name__ == "__main__":
    if not PID_FILE.exists():
        print(f"  {Y}[!!]{X}  No server PID file — is the server running?")
        sys.exit(1)

    pid_text = PID_FILE.read_text(encoding="utf-8").strip()
    if not pid_text.isdigit():
        print(f"  {R}[XX]{X}  PID file is corrupt. Delete .server.pid and restart manually.")
        sys.exit(1)

    pid = int(pid_text)
    print(f"  {C}[..]{X}  Requesting restart (server pid {pid}) …")

    # Set the restart flag BEFORE killing so start.py's loop picks it up
    RESTART_FLAG.write_text("1", encoding="utf-8")

    # Terminate the uvicorn process — start.py will see the flag and relaunch
    import os, signal
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError) as e:
        RESTART_FLAG.unlink(missing_ok=True)
        print(f"  {R}[XX]{X}  Could not signal process {pid}: {e}")
        sys.exit(1)

    # Wait for the PID file to update (old pid → new pid) or server to come back
    old_pid = pid
    for _ in range(20):          # up to 10 seconds
        time.sleep(0.5)
        if PID_FILE.exists():
            new_pid_text = PID_FILE.read_text(encoding="utf-8").strip()
            if new_pid_text.isdigit() and int(new_pid_text) != old_pid:
                print(f"  {G}[OK]{X}  Server restarted (new pid {new_pid_text})")
                sys.exit(0)

    # PID file didn't update — still show a best-effort OK if flag is gone
    if not RESTART_FLAG.exists():
        print(f"  {G}[OK]{X}  Restart signal sent.")
    else:
        print(f"  {Y}[!!]{X}  Restart flag still present — start.py may not be running the poll loop.")
        RESTART_FLAG.unlink(missing_ok=True)
