"""
Pre-flight checks and server launcher for the Multiplayer Dungeon.

    python start.py          # normal start
    DEV=1 python start.py    # with auto-reload

Use stop.py to stop, restart.py to restart without going back to the terminal.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent

# ── venv bootstrap ────────────────────────────────────────────────────────────
_IS_WIN   = sys.platform == "win32"
_VENV_PY  = ROOT / ".venv" / ("Scripts" if _IS_WIN else "bin") / ("python.exe" if _IS_WIN else "python")

def _inside_venv() -> bool:
    return Path(sys.executable).resolve() == _VENV_PY.resolve()

if _VENV_PY.exists() and not _inside_venv():
    os.execv(str(_VENV_PY), [str(_VENV_PY)] + sys.argv)

# ── from here we are inside .venv (or venv doesn't exist) ────────────────────
import shutil
import signal
import subprocess
import time
import urllib.request
import urllib.error

# ── runtime files ─────────────────────────────────────────────────────────────
_PID_FILE     = ROOT / ".server.pid"
_RESTART_FLAG = ROOT / ".restart.flag"
_STOP_FLAG    = ROOT / ".stop.flag"

# ── ANSI colours ──────────────────────────────────────────────────────────────
R = "\033[0;31m"
G = "\033[0;32m"
Y = "\033[0;33m"
C = "\033[0;36m"
W = "\033[1;37m"
X = "\033[0m"

def ok(msg):   print(f"  {G}[OK]{X}  {msg}")
def warn(msg): print(f"  {Y}[!!]{X}  {msg}")
def err(msg):  print(f"  {R}[XX]{X}  {msg}")
def info(msg): print(f"  {C}[..]{X}  {msg}")
def hdr(msg):  print(f"\n{W}{msg}{X}")


# ── config ────────────────────────────────────────────────────────────────────

def load_env():
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

def cfg(key, default=""):
    return os.environ.get(key, default)


# ── pre-flight checks ─────────────────────────────────────────────────────────

def check_python():
    v = sys.version_info
    if v < (3, 11):
        err(f"Python 3.11+ required — found {v.major}.{v.minor}")
        sys.exit(1)
    venv_note = f"  {C}(.venv){X}" if _inside_venv() else f"  {Y}(system Python — run setup.py first){X}"
    ok(f"Python {v.major}.{v.minor}.{v.micro}{venv_note}")


def check_venv():
    if not (ROOT / ".venv").exists():
        warn(".venv not found — run  python setup.py  to create it")
    elif _inside_venv():
        ok(f".venv active")


def check_dependencies():
    missing = []
    for pkg in ("fastapi", "uvicorn", "anthropic", "httpx", "websockets"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        err(f"Missing packages: {', '.join(missing)}")
        err("Run  python setup.py  to install them into .venv")
        sys.exit(1)
    ok("All packages installed")


def check_env_file():
    if not (ROOT / ".env").exists():
        warn(".env not found — run  python setup.py  to create it")
    else:
        ok(".env loaded")
    if cfg("ADMIN_SECRET", "changeme") == "changeme":
        warn("ADMIN_SECRET is still 'changeme' — change it in .env before going online")


def check_worlds():
    worlds_dir = ROOT / "data" / "worlds"
    worlds = []
    if worlds_dir.exists():
        worlds = [d for d in worlds_dir.iterdir() if d.is_dir() and (d / "config.json").exists()]
    if not worlds:
        warn("No worlds found — create one at /admin after the server starts")
    else:
        ok(f"{len(worlds)} world(s) ready: {[w.name for w in worlds]}")


def check_anthropic():
    key = cfg("ANTHROPIC_API_KEY", "")
    if not key or key.startswith("sk-ant-..."):
        warn("ANTHROPIC_API_KEY not set — admin world generator unavailable")
    else:
        ok("Anthropic API key configured")


# ── Ollama ────────────────────────────────────────────────────────────────────

_ollama_proc = None

def _ping_ollama() -> bool:
    try:
        urllib.request.urlopen("http://localhost:11434", timeout=2)
        return True
    except urllib.error.URLError:
        return False


def ensure_ollama():
    global _ollama_proc
    if _ping_ollama():
        ok("Ollama running at localhost:11434")
        _verify_model()
        return
    if shutil.which("ollama") is None:
        warn("ollama not found — Game Master will be unavailable")
        return
    info("Starting Ollama …")
    try:
        _ollama_proc = subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except OSError as e:
        warn(f"Could not start Ollama: {e}")
        return
    for i in range(8):
        time.sleep(1)
        if _ping_ollama():
            ok(f"Ollama started (pid {_ollama_proc.pid})")
            _verify_model()
            return
        info(f"Waiting for Ollama… ({i + 1}/8)")
    warn("Ollama did not become ready in time")


def _verify_model():
    model = cfg("OLLAMA_MODEL", "llama3")
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=5,
        )
        if model in result.stdout:
            ok(f"Model '{model}' available")
        else:
            warn(f"Model '{model}' not pulled — run: ollama pull {model}")
    except Exception:
        pass


# ── server loop ───────────────────────────────────────────────────────────────

_server_proc: subprocess.Popen | None = None


def _write_pid(pid: int):
    _PID_FILE.write_text(str(pid), encoding="utf-8")


def _clear_pid():
    _PID_FILE.unlink(missing_ok=True)


def _kill_server():
    global _server_proc
    if _server_proc and _server_proc.poll() is None:
        _server_proc.terminate()
        try:
            _server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _server_proc.kill()
    _server_proc = None
    _clear_pid()


def _shutdown(sig, frame):
    print(f"\n{Y}Stopping server…{X}")
    _kill_server()
    if _ollama_proc:
        info("Stopping Ollama …")
        _ollama_proc.terminate()
    _RESTART_FLAG.unlink(missing_ok=True)
    _STOP_FLAG.unlink(missing_ok=True)
    sys.exit(0)


def launch_server():
    global _server_proc

    host = cfg("HOST", "0.0.0.0")
    port = cfg("PORT", "8000")

    hdr("Starting server")
    print(f"\n  {W}Player UI :{X}  {C}http://{host}:{port}{X}")
    print(f"  {W}Admin     :{X}  {C}http://{host}:{port}/admin{X}")
    print(f"  {Y}stop.py{X} to stop  ·  {Y}restart.py{X} to restart  ·  Ctrl+C to quit\n")
    print("─" * 50)

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    cmd = [
        str(sys.executable), "-m", "uvicorn", "main:app",
        "--host", host, "--port", str(port),
    ]
    if os.environ.get("DEV"):
        cmd.append("--reload")

    while True:
        # clean up stale flags from previous run
        _STOP_FLAG.unlink(missing_ok=True)

        _server_proc = subprocess.Popen(cmd)
        _write_pid(_server_proc.pid)
        info(f"Server started  pid={_server_proc.pid}")

        # wait — poll so we can check flags without blocking forever
        while _server_proc.poll() is None:
            time.sleep(0.5)
            if _STOP_FLAG.exists():
                info("Stop requested")
                _kill_server()
                _STOP_FLAG.unlink(missing_ok=True)
                _RESTART_FLAG.unlink(missing_ok=True)
                print(f"\n{Y}Server stopped.{X}")
                if _ollama_proc:
                    _ollama_proc.terminate()
                return

        _clear_pid()
        exit_code = _server_proc.returncode
        _server_proc = None

        if _RESTART_FLAG.exists():
            _RESTART_FLAG.unlink(missing_ok=True)
            print(f"\n{C}Restarting server…{X}\n" + "─" * 50)
            continue  # loop → relaunch

        # unexpected exit
        if exit_code not in (0, -15, 15):  # 0=clean, 15=SIGTERM
            warn(f"Server exited with code {exit_code}")
        break


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n{W}{'='*50}")
    print("  Multiplayer Dungeon — Starting Up")
    print(f"{'='*50}{X}\n")

    load_env()

    hdr("Pre-flight checks")
    check_python()
    check_venv()
    check_dependencies()
    check_env_file()
    check_worlds()
    check_anthropic()

    hdr("Services")
    ensure_ollama()

    launch_server()
