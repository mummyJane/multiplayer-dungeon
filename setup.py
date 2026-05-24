"""
One-time system setup for the Multiplayer Dungeon.

    python setup.py          # uses system Python to bootstrap the local venv

Safe to re-run — skips steps already completed.
Everything is installed into .venv/ inside this directory.
"""
import os
import sys
import shutil
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
def ask(prompt, default=""):
    try:
        val = input(f"  {B}[?]{X}  {prompt} [{default}]: ").strip()
        return val or default
    except EOFError:
        return default


# ── venv paths ────────────────────────────────────────────────────────────────

_IS_WIN = sys.platform == "win32"
VENV_DIR    = ROOT / ".venv"
VENV_PYTHON = VENV_DIR / ("Scripts" if _IS_WIN else "bin") / ("python.exe" if _IS_WIN else "python")
VENV_PIP    = VENV_DIR / ("Scripts" if _IS_WIN else "bin") / ("pip.exe" if _IS_WIN else "pip")


def run(cmd, check=True, **kwargs):
    return subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=check, **kwargs
    )


# ── steps ─────────────────────────────────────────────────────────────────────

def check_python():
    hdr("1. Python version")
    v = sys.version_info
    if v < (3, 11):
        err(f"Python 3.11+ required — found {v.major}.{v.minor}.{v.micro}")
        sys.exit(1)
    ok(f"Python {v.major}.{v.minor}.{v.micro} (system)")


def create_venv():
    hdr("2. Virtual environment (.venv/)")
    if VENV_PYTHON.exists():
        ok(f".venv already exists at {VENV_DIR}")
        return

    info("Creating .venv …")
    result = run(f'"{sys.executable}" -m venv "{VENV_DIR}"', check=False)
    if result.returncode != 0 or not VENV_PYTHON.exists():
        err("venv creation failed:\n" + result.stderr[-600:])
        sys.exit(1)
    ok(f".venv created at {VENV_DIR}")


def install_dependencies():
    hdr("3. Dependencies (into .venv)")
    req = ROOT / "requirements.txt"
    if not req.exists():
        err("requirements.txt not found")
        sys.exit(1)

    # check if already installed inside the venv
    check = run(
        f'"{VENV_PYTHON}" -c "import fastapi, uvicorn, anthropic, httpx"',
        check=False
    )
    if check.returncode == 0:
        ok("All packages already installed in .venv")
        return

    info("Running pip install inside .venv …")
    result = run(f'"{VENV_PIP}" install -r "{req}"', check=False)
    if result.returncode != 0:
        err("pip install failed:\n" + result.stderr[-800:])
        sys.exit(1)
    ok("Dependencies installed into .venv")


def create_env():
    hdr("4. Environment file (.env)")
    env_path = ROOT / ".env"
    if env_path.exists():
        ok(".env already exists — skipping")
        return

    interactive = sys.stdin.isatty()
    if interactive:
        print(f"  {C}Creating .env — press Enter to keep defaults.{X}")
    else:
        info("Non-interactive mode — creating .env with defaults (edit it before starting)")

    admin_secret = ask("Admin panel secret", "changeme")
    api_key      = ask("Anthropic API key (leave blank to skip)", "")
    ollama_model = ask("Ollama model name", "llama3")
    host         = ask("Server host", "0.0.0.0")
    port         = ask("Server port", "8000")

    env_path.write_text(
        f"ADMIN_SECRET={admin_secret}\n"
        f"ANTHROPIC_API_KEY={api_key}\n"
        f"OLLAMA_URL=http://localhost:11434/api/generate\n"
        f"OLLAMA_MODEL={ollama_model}\n"
        f"HOST={host}\n"
        f"PORT={port}\n",
        encoding="utf-8",
    )
    ok(".env created")
    if admin_secret == "changeme":
        warn("Still using default admin secret — change ADMIN_SECRET in .env before going online")


def create_data_dirs():
    hdr("5. Data directories")
    for d in [ROOT / "data" / "worlds", ROOT / "data" / "players",
              ROOT / "logs", ROOT / "backups" / "worlds", ROOT / "backups" / "players"]:
        d.mkdir(parents=True, exist_ok=True)
    ok("data/worlds/, data/players/, logs/, backups/ ready")
    _init_data_repos()


def _init_data_repos():
    """Initialise local git repos inside data/worlds/ and data/players/."""
    import subprocess as sp
    for label, path in [("worlds", ROOT / "data" / "worlds"),
                        ("players", ROOT / "data" / "players")]:
        git_dir = path / ".git"
        if git_dir.exists():
            ok(f"data/{label}/ git repo already initialised")
            continue
        info(f"Initialising local git repo for data/{label}/ …")
        for cmd in [
            f'git -C "{path}" init',
            f'git -C "{path}" config user.name "dungeon-data"',
            f'git -C "{path}" config user.email "dungeon@localhost"',
        ]:
            r = sp.run(cmd, shell=True, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
            if r.returncode != 0:
                warn(f"git command failed: {cmd}\n{r.stderr[:300]}")
                break
        else:
            # create initial commit
            (path / ".gitkeep").touch()
            sp.run(f'git -C "{path}" add .gitkeep', shell=True)
            sp.run(f'git -C "{path}" commit -m "init data repo"', shell=True,
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
            ok(f"data/{label}/ git repo initialised")


def check_ollama():
    hdr("6. Ollama")
    if shutil.which("ollama") is None:
        warn("ollama not found in PATH")
        warn("Install from https://ollama.ai then re-run setup.py")
        warn("Server will start without Ollama but the Game Master will be unavailable")
        return
    ok("ollama binary found")

    try:
        urllib.request.urlopen("http://localhost:11434", timeout=2)
        ok("Ollama is running")
        _check_model()
    except urllib.error.URLError:
        info("Ollama is not running — start.py will start it automatically")


def _check_model():
    model = _read_env("OLLAMA_MODEL", "llama3")
    result = run("ollama list", check=False)
    if result.returncode != 0:
        return
    if model not in result.stdout:
        if ask(f"Pull model '{model}' now?", "y").lower() == "y":
            info(f"Pulling {model} …")
            # don't capture output — let Ollama's progress bar print to the terminal
            r = subprocess.run(f"ollama pull {model}", shell=True, check=False)
            ok(f"Model '{model}' pulled") if r.returncode == 0 else warn(f"Pull failed — run: ollama pull {model}")
    else:
        ok(f"Model '{model}' is present")


def check_worlds():
    hdr("7. Worlds")
    worlds_dir = ROOT / "data" / "worlds"
    worlds = [d for d in worlds_dir.iterdir() if d.is_dir() and (d / "config.json").exists()] \
             if worlds_dir.exists() else []
    if worlds:
        ok(f"{len(worlds)} world(s) found: {[w.name for w in worlds]}")
    else:
        warn("No worlds yet — create one via the admin panel after starting")


def print_summary():
    hdr("Setup complete")
    print(f"""
  Start the server:
    {G}python start.py{X}

  Everything runs inside {C}.venv/{X} — no manual activation needed.
  Player UI :  {C}http://localhost:8000{X}
  Admin panel: {C}http://localhost:8000/admin{X}
""")


def _read_env(name, default=""):
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
    create_venv()
    install_dependencies()
    create_env()
    create_data_dirs()
    check_ollama()
    check_worlds()
    print_summary()
