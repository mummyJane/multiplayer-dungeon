"""
Stop the running Multiplayer Dungeon server.

    python stop.py
"""
import sys
from pathlib import Path

ROOT     = Path(__file__).parent
PID_FILE = ROOT / ".server.pid"
STOP_FLAG = ROOT / ".stop.flag"

# ── ANSI colours ──────────────────────────────────────────────────────────────
G = "\033[0;32m"
Y = "\033[0;33m"
R = "\033[0;31m"
X = "\033[0m"

if __name__ == "__main__":
    if not PID_FILE.exists():
        print(f"  {Y}[!!]{X}  No server PID file found — is the server running?")
        sys.exit(1)

    pid_text = PID_FILE.read_text(encoding="utf-8").strip()
    if not pid_text.isdigit():
        print(f"  {R}[XX]{X}  PID file is corrupt. Delete .server.pid and restart.")
        sys.exit(1)

    pid = int(pid_text)
    print(f"  Requesting stop (server pid {pid}) …")

    # Write the stop flag — start.py's poll loop will see it and terminate cleanly
    STOP_FLAG.write_text(str(pid), encoding="utf-8")

    # Wait up to 8 seconds for the PID file to disappear (server has exited)
    import time
    for _ in range(16):
        time.sleep(0.5)
        if not PID_FILE.exists():
            print(f"  {G}[OK]{X}  Server stopped.")
            sys.exit(0)

    # If still running after 8s, force-kill
    print(f"  {Y}[!!]{X}  Server did not stop in time — force-killing pid {pid}")
    try:
        import os, signal
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    PID_FILE.unlink(missing_ok=True)
    STOP_FLAG.unlink(missing_ok=True)
    print(f"  {G}[OK]{X}  Done.")
