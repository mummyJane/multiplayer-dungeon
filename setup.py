"""
One-time system setup for the Multiplayer Dungeon.

Run once before first use:
    python setup.py

Safe to re-run — skips steps already completed.
"""
import os
import sys
import shutil
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).parent

# ── ANSI colours (Windows 10+ supports VT by default) ────────────────────────
R = "\033[0;31m"   # red
G = "\033[0;32m"   # green
Y = "\033[0;33m"   # yellow
B = "\033[0;34m"   # blue
C = "\033[0;36m"   # cyan
W = "\033[1;37m"   # bold white
X = "\033[0m"      # reset


def ok(msg):   print(f"  {G}[OK]{X}  {msg}")
def warn(msg): print(f"  {Y}[!!]{X}  {msg}")
def err(msg):  print(f"  {R}[XX]{X}  {msg}")
def info(msg): print(f"  {C}[..]{X}  {msg}")
def hdr(msg):  print(f"\n{W}{msg}{X}")


# ── helpers ───────────────────────────────────────────────────────────────────

def ask(prompt, default=""):
    val = input(f"  {B}[?]{X}  {prompt} [{default}]: ").strip()
    return val or default


def run(cmd, check=True):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, check=check)


# ── steps ─────────────────────────────────────────────────────────────────────

def check_python():
    hdr("1. Python version")
    v = sys.version_info
    if v < (3, 11):
        err(f"Python 3.11+ required, found {v.major}.{v.minor}.{v.micro}")
        sys.exit(1)
    ok(f"Python {v.major}.{v.minor}.{v.micro}")


def install_dependencies():
    hdr("2. Python dependencies")
    req = ROOT / "requirements.txt"
    if not req.exists():
        err("requirements.txt not found")
        sys.exit(1)

    # check if already installed by trying a quick import
    try:
        import fastapi, uvicorn, anthropic, httpx  # noqa: F401
        ok("All packages already installed")
        return
    except ImportError:
        pass

    info("Installing from requirements.txt …")
    result = run(f'"{sys.executable}" -m pip install -r "{req}"', check=False)
    if result.returncode != 0:
        err("pip install failed:\n" + result.stderr[-800:])
        sys.exit(1)
    ok("Dependencies installed")


def create_env():
    hdr("3. Environment file (.env)")
    env_path = ROOT / ".env"
    example_path = ROOT / ".env.example"

    if env_path.exists():
        ok(".env already exists — skipping")
        return

    if not example_path.exists():
        err(".env.example not found")
        sys.exit(1)

    print(f"  {C}Creating .env from template. Press Enter to keep defaults.{X}")

    admin_secret = ask("Admin panel secret (used at /admin)", "changeme")
    api_key      = ask("Anthropic API key (for world generator, leave blank to skip)", "")
    ollama_model = ask("Ollama model name", "llama3")
    host         = ask("Server host", "0.0.0.0")
    port         = ask("Server port", "8000")

    lines = [
        f"ADMIN_SECRET={admin_secret}\n",
        f"ANTHROPIC_API_KEY={api_key}\n",
        f"OLLAMA_URL=http://localhost:11434/api/generate\n",
        f"OLLAMA_MODEL={ollama_model}\n",
        f"HOST={host}\n",
        f"PORT={port}\n",
    ]
    env_path.write_text("".join(lines), encoding="utf-8")
    ok(".env created")

    if admin_secret == "changeme":
        warn("You are using the default admin secret. Change ADMIN_SECRET in .env before going online.")


def create_data_dirs():
    hdr("4. Data directories")
    dirs = [
        ROOT / "data" / "worlds",
        ROOT / "logs",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    ok("data/worlds/ and logs/ present")


def check_ollama():
    hdr("5. Ollama")
    # check if ollama binary exists
    if shutil.which("ollama") is None:
        warn("ollama binary not found in PATH")
        warn("Install from https://ollama.ai then re-run setup.py")
        warn("The server will start without Ollama but the Game Master will be unavailable")
        return

    ok("ollama binary found")

    # check if it's reachable (may not be running yet — that's fine here)
    try:
        urllib.request.urlopen("http://localhost:11434", timeout=2)
        ok("Ollama is already running at localhost:11434")
        _check_model()
    except urllib.error.URLError:
        info("Ollama is not currently running — start.py will launch it automatically")


def _check_model():
    """Check whether the configured model is pulled."""
    model = _read_env_var("OLLAMA_MODEL", "llama3")
    result = run("ollama list", check=False)
    if result.returncode != 0:
        warn("Could not run 'ollama list'")
        return
    if model not in result.stdout:
        info(f"Model '{model}' not yet pulled")
        pull = ask(f"Pull '{model}' now? (can take a few minutes)", "y").lower()
        if pull == "y":
            info(f"Pulling {model} …")
            r = run(f"ollama pull {model}", check=False)
            if r.returncode == 0:
                ok(f"Model '{model}' pulled")
            else:
                warn(f"Pull failed — run 'ollama pull {model}' manually")
    else:
        ok(f"Model '{model}' is present")


def check_worlds():
    hdr("6. Worlds")
    worlds_dir = ROOT / "data" / "worlds"
    worlds = [d for d in worlds_dir.iterdir() if d.is_dir() and (d / "config.json").exists()]
    if worlds:
        ok(f"{len(worlds)} world(s) found: {[w.name for w in worlds]}")
    else:
        warn("No worlds found in data/worlds/ — create one via the admin panel at /admin")


def print_summary():
    hdr("Setup complete")
    print(f"""
  To start the server:
    {G}python start.py{X}

  Admin panel:  {C}http://localhost:8000/admin{X}
  Player UI:    {C}http://localhost:8000{X}
""")


# ── utility ───────────────────────────────────────────────────────────────────

def _read_env_var(name, default=""):
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip()
    return os.environ.get(name, default)


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n{W}{'='*50}")
    print("  Multiplayer Dungeon — System Setup")
    print(f"{'='*50}{X}")

    check_python()
    install_dependencies()
    create_env()
    create_data_dirs()
    check_ollama()
    check_worlds()
    print_summary()
