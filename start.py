"""
Pre-flight checks and server launcher for the Multiplayer Dungeon.

    python start.py

Checks everything is ready, starts Ollama if needed, then launches the server.
"""
import os
import sys
import shutil
import time
import signal
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).parent

# ── ANSI colours ──────────────────────────────────────────────────────────────
R = "\033[0;31m"
G = "\033[0;32m"
Y = "\033[0;33m"
B = "\033[0;34m"
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
    """Load .env into os.environ (simple key=value parser, no deps required)."""
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


# ── checks ────────────────────────────────────────────────────────────────────

def check_python():
    v = sys.version_info
    if v < (3, 11):
        err(f"Python 3.11+ required, found {v.major}.{v.minor}")
        sys.exit(1)
    ok(f"Python {v.major}.{v.minor}.{v.micro}")


def check_dependencies():
    missing = []
    for pkg in ("fastapi", "uvicorn", "anthropic", "httpx", "websockets"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        err(f"Missing packages: {', '.join(missing)}")
        err("Run  python setup.py  first")
        sys.exit(1)
    ok("All Python packages installed")


def check_env_file():
    if not (ROOT / ".env").exists():
        warn(".env not found — run  python setup.py  to create it")
        warn("Using built-in defaults (not suitable for production)")
    else:
        ok(".env loaded")

    if cfg("ADMIN_SECRET", "changeme") == "changeme":
        warn("ADMIN_SECRET is still 'changeme' — change it in .env before going online")


def check_worlds():
    worlds_dir = ROOT / "data" / "worlds"
    worlds = [d for d in worlds_dir.iterdir() if d.is_dir() and (d / "config.json").exists()] \
             if worlds_dir.exists() else []
    if not worlds:
        warn("No worlds found in data/worlds/")
        warn("Create one via the admin panel after the server starts: /admin")
    else:
        ok(f"{len(worlds)} world(s) ready: {[w.name for w in worlds]}")


def check_anthropic():
    key = cfg("ANTHROPIC_API_KEY", "")
    if not key or key.startswith("sk-ant-..."):
        warn("ANTHROPIC_API_KEY not set — admin world generator will be unavailable")
        warn("Set it in .env to enable Claude-powered world creation")
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
        ok("Ollama is running at localhost:11434")
        _verify_model()
        return

    if shutil.which("ollama") is None:
        warn("Ollama not found in PATH — Game Master will be unavailable")
        warn("Install from https://ollama.ai")
        return

    info("Starting Ollama …")
    try:
        _ollama_proc = subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as e:
        warn(f"Could not start Ollama: {e}")
        return

    # wait up to 8 seconds for it to become ready
    for i in range(8):
        time.sleep(1)
        if _ping_ollama():
            ok(f"Ollama started (pid {_ollama_proc.pid})")
            _verify_model()
            return
        info(f"Waiting for Ollama… ({i+1}/8)")

    warn("Ollama did not become ready in time — Game Master may be unavailable")


def _verify_model():
    model = cfg("OLLAMA_MODEL", "llama3")
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=5
        )
        if model in result.stdout:
            ok(f"Ollama model '{model}' is available")
        else:
            warn(f"Model '{model}' not pulled — run: ollama pull {model}")
    except Exception:
        pass  # non-critical


# ── shutdown ──────────────────────────────────────────────────────────────────

_server_proc = None


def _shutdown(sig, frame):
    print(f"\n{Y}Shutting down…{X}")
    if _server_proc:
        _server_proc.terminate()
    if _ollama_proc:
        info("Stopping Ollama …")
        _ollama_proc.terminate()
    sys.exit(0)


# ── launch ────────────────────────────────────────────────────────────────────

def launch_server():
    global _server_proc

    host = cfg("HOST", "0.0.0.0")
    port = cfg("PORT", "8000")

    hdr("Starting server")
    print(f"\n  {W}Player UI :{X}  {C}http://{host}:{port}{X}")
    print(f"  {W}Admin     :{X}  {C}http://{host}:{port}/admin{X}")
    print(f"\n  {Y}Press Ctrl+C to stop{X}\n")
    print("─" * 50)

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    reload_flag = "--reload" if os.environ.get("DEV") else ""
    cmd = [
        sys.executable, "-m", "uvicorn",
        "main:app",
        "--host", host,
        "--port", port,
    ]
    if reload_flag:
        cmd.append("--reload")

    # exec directly — replaces this process, cleaner logs
    os.execv(sys.executable, cmd)


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n{W}{'='*50}")
    print("  Multiplayer Dungeon — Starting Up")
    print(f"{'='*50}{X}\n")

    load_env()

    hdr("Pre-flight checks")
    check_python()
    check_dependencies()
    check_env_file()
    check_worlds()
    check_anthropic()

    hdr("Services")
    ensure_ollama()

    launch_server()
