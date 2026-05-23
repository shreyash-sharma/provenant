"""``provenant serve`` - start the API server and web UI."""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import click
from click.core import ParameterSource

from provenant.cli import __version__
from provenant.cli.helpers import console, load_config

_GLOBAL_CONFIG_DIR = Path.home() / ".provenant"
_PID_FILE = _GLOBAL_CONFIG_DIR / "server.pid"


# ── PID / daemon helpers ──────────────────────────────────────────────────────

def _detach_kwargs() -> dict:
    """Subprocess kwargs that detach a child so it outlives the parent."""
    if sys.platform == "win32":
        return {
            "creationflags": subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
            | subprocess.CREATE_NEW_PROCESS_GROUP,  # type: ignore[attr-defined]
        }
    return {"start_new_session": True}


def _read_pid_file() -> dict | None:
    if not _PID_FILE.exists():
        return None
    try:
        return json.loads(_PID_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_pid_file(data: dict) -> None:
    _GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _PID_FILE.write_text(json.dumps(data), encoding="utf-8")


def _is_pid_alive(pid: int) -> bool:
    """Return True if the process with *pid* is still running.

    On Windows, ``os.kill(pid, 0)`` raises ``OSError`` (WinError 87 –
    "The parameter is incorrect") for processes started with
    ``DETACHED_PROCESS``.  Use the Win32 ``OpenProcess`` / ``GetExitCodeProcess``
    pair via ctypes instead, which works reliably for detached children.
    """
    if sys.platform == "win32":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong(0)
            ok = ctypes.windll.kernel32.GetExitCodeProcess(
                handle, ctypes.byref(exit_code)
            )
            return bool(ok) and exit_code.value == STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def _kill_pid(pid: int) -> None:
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
            )
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception:
        pass


def _stop_server() -> None:
    info = _read_pid_file()
    if not info:
        console.print("[dim]No server is running.[/dim]")
        return

    killed: list[int] = []
    for key in ("api_pid", "frontend_pid"):
        pid = info.get(key)
        if not pid:
            continue
        try:
            alive = _is_pid_alive(int(pid))
        except Exception:
            alive = True  # assume alive when check fails; taskkill is a no-op if not
        if alive:
            _kill_pid(int(pid))
            killed.append(int(pid))

    _PID_FILE.unlink(missing_ok=True)

    if killed:
        console.print("  Stopped.")
    else:
        console.print("[dim]Server was not running (stale pid file removed).[/dim]")


def _start_api_daemon(host: str, port: int, workers: int) -> subprocess.Popen:
    """Start uvicorn as a detached background process."""
    return subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "provenant.server.app:create_app",
            "--factory",
            "--host", host,
            "--port", str(port),
            "--workers", str(workers),
            "--log-level", "warning",
            "--no-access-log",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=os.environ.copy(),
        **_detach_kwargs(),
    )


def _setup_embedder() -> None:
    """Ensure PROVENANT_EMBEDDER is set before the server starts.

    Priority:
      1. Already set in environment -> nothing to do.
      2. Saved in ~/.provenant/config.yaml -> restore it (and its API key).
      3. Prompt the user interactively -> save choice for next time.
    """
    if os.environ.get("PROVENANT_EMBEDDER"):
        return

    # Check global config saved by a previous serve/init run.
    cfg = load_config(Path.home())
    saved_embedder = cfg.get("embedder", "")
    if saved_embedder and saved_embedder != "mock":
        os.environ["PROVENANT_EMBEDDER"] = saved_embedder
        # Restore API key if saved alongside the config.
        if cfg.get("embedder_api_key"):
            _set_api_key_env(saved_embedder, cfg["embedder_api_key"])
        return

    # Detect which providers already have keys in the environment.
    has_gemini = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    has_openrouter = bool(os.environ.get("OPENROUTER_API_KEY"))

    console.print(
        "\n[bold]Chat & search require an embedder.[/bold] "
        "Choose one or skip (other features still work).\n"
    )

    options = []
    labels = []
    if has_gemini:
        options.append("gemini")
        labels.append("[1] gemini      [green]OK key set[/green]")
    else:
        options.append("gemini")
        labels.append("[1] gemini      [dim]needs GEMINI_API_KEY / GOOGLE_API_KEY[/dim]")
    if has_openai:
        options.append("openai")
        labels.append("[2] openai      [green]OK key set[/green]")
    else:
        options.append("openai")
        labels.append("[2] openai      [dim]needs OPENAI_API_KEY[/dim]")
    if has_openrouter:
        options.append("openrouter")
        labels.append("[3] openrouter  [green]OK key set[/green]")
    else:
        options.append("openrouter")
        labels.append("[3] openrouter  [dim]needs OPENROUTER_API_KEY[/dim]")
    options.append("skip")
    labels.append(f"[{len(options)}] skip        [dim]no chat/search[/dim]")

    for label in labels:
        console.print(f"  {label}")
    console.print()

    default = "1" if (has_gemini or has_openai) else "3"
    raw = click.prompt("  Select", default=default).strip()

    # Map number or name to option.
    choice = (
        raw
        if raw in options
        else (options[int(raw) - 1] if raw.isdigit() and 1 <= int(raw) <= len(options) else "skip")
    )

    if choice == "skip":
        console.print("[dim]Skipping embedder - chat and search will be unavailable.[/dim]\n")
        return

    os.environ["PROVENANT_EMBEDDER"] = choice

    # Ensure the API key is present; prompt if missing.
    api_key = _get_or_prompt_api_key(choice)
    if api_key:
        _set_api_key_env(choice, api_key)

    # Save choice (and key) to ~/.provenant/config.yaml for future runs.
    _save_global_embedder(choice, api_key)
    console.print()


def _get_or_prompt_api_key(embedder: str) -> str:
    """Return existing API key for *embedder* or prompt the user for one."""
    if embedder == "gemini":
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if key:
            return key
        return click.prompt("  GEMINI_API_KEY", default="", show_default=False).strip()
    if embedder == "openai":
        key = os.environ.get("OPENAI_API_KEY", "")
        if key:
            return key
        return click.prompt("  OPENAI_API_KEY", default="", show_default=False).strip()
    if embedder == "openrouter":
        key = os.environ.get("OPENROUTER_API_KEY", "")
        if key:
            return key
        return click.prompt("  OPENROUTER_API_KEY", default="", show_default=False).strip()
    return ""


def _set_api_key_env(embedder: str, key: str) -> None:
    if not key:
        return
    if embedder == "gemini":
        os.environ.setdefault("GEMINI_API_KEY", key)
    elif embedder == "openai":
        os.environ.setdefault("OPENAI_API_KEY", key)
    elif embedder == "openrouter":
        os.environ.setdefault("OPENROUTER_API_KEY", key)


def _save_global_embedder(embedder: str, api_key: str) -> None:
    """Persist embedder choice to ~/.provenant/config.yaml."""
    _GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config_path = _GLOBAL_CONFIG_DIR / "config.yaml"
    try:
        existing: dict = {}
        if config_path.exists():
            import yaml  # type: ignore[import-untyped]

            existing = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        existing["embedder"] = embedder
        if api_key:
            existing["embedder_api_key"] = api_key
        import yaml  # type: ignore[import-untyped]

        config_path.write_text(
            yaml.dump(existing, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
    except Exception:
        pass  # Non-fatal - user just gets prompted again next time.


_GITHUB_REPO = "shreyash-sharma/provenant"
_WEB_CACHE_DIR = Path.home() / ".provenant" / "web"
_MARKER_FILE = _WEB_CACHE_DIR / ".version"
_MAX_PORT_PROBES = 100


def _node_available() -> str | None:
    """Return the path to node binary, or None."""
    return shutil.which("node")


def _npm_available() -> str | None:
    """Return the path to npm binary, or None."""
    return shutil.which("npm")


def _port_is_available(host: str, port: int) -> bool:
    """Return True if a TCP port can be bound on *host*."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _find_available_port(host: str, preferred: int) -> int:
    """Return *preferred* if free, otherwise the next free TCP port."""
    for port in range(preferred, preferred + _MAX_PORT_PROBES):
        if _port_is_available(host, port):
            return port
    raise click.ClickException(
        f"No free port found from {preferred} to {preferred + _MAX_PORT_PROBES - 1}."
    )


def _resolve_port(
    *,
    label: str,
    host: str,
    preferred: int,
    explicit: bool,
) -> int:
    """Resolve a requested port, auto-falling back only for default ports."""
    if _port_is_available(host, preferred):
        return preferred
    if explicit:
        raise click.ClickException(
            f"{label} port {preferred} is already in use. "
            f"Choose another with --port."
        )
    selected = _find_available_port(host, preferred + 1)
    console.print(
        f"[yellow]{label} port {preferred} is in use; using {selected} instead.[/yellow]"
    )
    return selected


def _web_is_cached(version: str) -> bool:
    """Check if the web frontend static export is cached and matches the current version."""
    if not (_WEB_CACHE_DIR / "index.html").exists():
        return False
    return _MARKER_FILE.exists() and _MARKER_FILE.read_text().strip() == version


def _local_web_out(web_dir: Path) -> Path | None:
    """Return the local Next.js static export directory, if built."""
    out = web_dir / "out"
    return out if (out / "index.html").exists() else None


def _find_local_web() -> Path | None:
    """Check if running from the repo with packages/web available."""
    # Check from both __file__ (source installs) and cwd (pip-installed runs)
    roots = [Path(__file__).resolve(), Path.cwd().resolve()]
    for start in roots:
        candidate = start
        for _ in range(10):
            candidate = candidate.parent
            pkg_web = candidate / "packages" / "web"
            if (pkg_web / "package.json").exists():
                return pkg_web
    return None


def _local_build_is_stale(web_dir: Path) -> bool:
    """True if the local static export is older than any input source.

    Compares the out/index.html mtime against the newest mtime under the
    source roots that get compiled into the bundle (web/ui/types packages plus
    web's config files). Skips node_modules / .next / .turbo. Used so that a
    cloned monorepo with stale build artifacts falls back to the released
    tarball instead of serving a bundle behind the user's source tree.
    """
    out = _local_web_out(web_dir)
    if out is None:
        return True
    build_mtime = (out / "index.html").stat().st_mtime

    repo_root = web_dir.parent.parent  # packages/web -> repo root
    skip_dirs = {"node_modules", ".next", ".turbo", "dist", ".git"}

    file_inputs: list[Path] = [
        web_dir / "package.json",
        web_dir / "next.config.ts",
        web_dir / "next.config.js",
        web_dir / "tsconfig.json",
    ]
    dir_inputs: list[Path] = [
        web_dir / "src",
        web_dir / "app",
        web_dir / "components",
        web_dir / "lib",
        web_dir / "public",
        repo_root / "packages" / "ui" / "src",
        repo_root / "packages" / "types" / "src",
    ]

    for f in file_inputs:
        if f.exists() and f.is_file() and f.stat().st_mtime > build_mtime:
            return True

    for root in dir_inputs:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if any(part in skip_dirs for part in path.parts):
                continue
            try:
                if path.is_file() and path.stat().st_mtime > build_mtime:
                    return True
            except OSError:
                continue
    return False


def _download_web(version: str) -> bool:
    """Download pre-built web frontend from GitHub releases."""
    import httpx

    tag = f"v{version}"
    url = f"https://github.com/{_GITHUB_REPO}/releases/download/{tag}/provenant-web.tar.gz"

    console.print(f"[dim]Downloading web UI ({url})...[/dim]")
    try:
        tmp_path = None
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            tmp_path = tmp.name
            with httpx.stream("GET", url, follow_redirects=True, timeout=120) as resp:
                resp.raise_for_status()
                for chunk in resp.iter_bytes(chunk_size=65536):
                    tmp.write(chunk)
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        console.print(f"[yellow]Could not download web UI: {exc}[/yellow]")
        if tmp_path:
            os.unlink(tmp_path)
        return False

    try:
        _WEB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # Clean old cache
        for item in _WEB_CACHE_DIR.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        with tarfile.open(tmp_path, "r:gz") as tar:
            tar.extractall(_WEB_CACHE_DIR)

        _MARKER_FILE.write_text(version)
        console.print("[green]Web UI downloaded and cached.[/green]")
        return True
    except Exception as exc:
        console.print(f"[yellow]Failed to extract web UI: {exc}[/yellow]")
        return False
    finally:
        os.unlink(tmp_path)


def _build_local_web(web_dir: Path, npm: str) -> bool:
    """Build the Next.js frontend from source."""
    from rich.progress import Progress, SpinnerColumn, TextColumn
    import time

    needs_install = not (web_dir / "node_modules").exists()
    total_secs = 120 if needs_install else 60
    console.print()
    console.print(
        "[bold]Building web UI[/bold] [dim](first time only — takes 1–2 minutes)[/dim]"
    )
    console.print("[dim]Subsequent starts will be instant.[/dim]")
    console.print()

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console,
        ) as progress:
            if needs_install:
                task = progress.add_task("  Installing dependencies...", total=None)
                subprocess.run(
                    [npm, "install"],
                    cwd=str(web_dir),
                    check=True,
                    capture_output=True,
                )
                progress.update(task, description="  [green]Dependencies installed[/green]")

            task = progress.add_task("  Compiling frontend...", total=None)
            subprocess.run(
                [npm, "run", "build"],
                cwd=str(web_dir),
                check=True,
                capture_output=True,
            )
            progress.update(task, description="  [green]Build complete[/green]")

        console.print("  [green]✓[/green] Web UI ready")
        console.print()
        return True
    except subprocess.CalledProcessError as exc:
        console.print(f"[yellow]Web UI build failed: {exc}[/yellow]")
        return False



def _install_local_web_bundle(web_dir: Path) -> bool:
    """Install the Next.js static export (out/) into ~/.provenant/web."""
    out_dir = _local_web_out(web_dir)
    if out_dir is None:
        return False

    try:
        if _WEB_CACHE_DIR.exists():
            shutil.rmtree(_WEB_CACHE_DIR)
        shutil.copytree(str(out_dir), str(_WEB_CACHE_DIR))
        _MARKER_FILE.write_text(__version__)
        return True
    except OSError as exc:
        console.print(f"[yellow]Failed to install web UI bundle: {exc}[/yellow]")
        return False


def _build_and_install_local_web(web_dir: Path, npm: str) -> bool:
    """Build local web source and install it into the Provenant web cache."""
    from rich.progress import Progress, SpinnerColumn, TextColumn

    if not _build_local_web(web_dir, npm):
        return False
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console,
    ) as progress:
        progress.add_task("  Installing web UI...", total=None)
        ok = _install_local_web_bundle(web_dir)
    if not ok:
        console.print("[yellow]Web UI build finished but install failed.[/yellow]")
        return False
    return True


def _start_frontend(*_args, **_kwargs) -> None:
    """No-op: the frontend is now served as static files by FastAPI itself.

    Node.js is only required to BUILD the frontend (npm run build), not to
    run it.  FastAPI mounts the exported out/ directory on every request.
    """
    return None


@click.command("serve")
@click.option("--stop", is_flag=True, help="Stop the running server.")
@click.option("--port", default=7337, type=int, help="Port to listen on (API + web UI).")
@click.option("--host", default="127.0.0.1", help="Host to bind to.")
@click.option("--workers", default=1, type=int, help="Number of uvicorn workers.")
@click.option("--no-ui", is_flag=True, help="Skip building / installing the web UI.")
@click.option(
    "--refresh-ui",
    is_flag=True,
    help="Force re-download of the web UI tarball, ignoring any cache.",
)
@click.option(
    "--rebuild",
    is_flag=True,
    help="Force a fresh rebuild of the web UI from source before starting.",
)
@click.option(
    "--build-ui",
    is_flag=True,
    hidden=True,
    help="Deprecated: use --rebuild.",
)
@click.pass_context
def serve_command(
    ctx: click.Context,
    stop: bool,
    port: int,
    host: str,
    workers: int,
    no_ui: bool,
    refresh_ui: bool,
    rebuild: bool,
    build_ui: bool,
) -> None:
    """Start the Provenant server in the background.

    The API and the web UI are both served from the same port — no Node.js
    required at runtime.  Node is only needed if you want to build the
    frontend from source (the release tarball is downloaded automatically).

    Use --stop to shut the server down.
    """
    # ── Stop ─────────────────────────────────────────────────────────────────
    if stop:
        _stop_server()
        return

    # ── Already running? ─────────────────────────────────────────────────────
    info = _read_pid_file()
    if info and _is_pid_alive(info.get("api_pid", 0)):
        console.print(
            f"\n  [bold green]→  http://localhost:{info.get('port', port)}[/bold green]"
            f"  [dim](already running)[/dim]"
        )
        console.print("  [dim]Stop with: provenant serve --stop[/dim]\n")
        return

    # ── DB auto-detect ────────────────────────────────────────────────────────
    if not os.environ.get("PROVENANT_DB_URL"):
        local_provenant = Path.cwd() / ".provenant"
        if local_provenant.exists():
            local_db = local_provenant / "wiki.db"
            os.environ["PROVENANT_DB_URL"] = f"sqlite+aiosqlite:///{local_db.as_posix()}"
            console.print(f"[dim]Using local database: {local_db}[/dim]")

    # ── Port resolution ───────────────────────────────────────────────────────
    port_explicit = ctx.get_parameter_source("port") is ParameterSource.COMMANDLINE
    port = _resolve_port(label="Server", host=host, preferred=port, explicit=port_explicit)

    # ── Web UI ────────────────────────────────────────────────────────────────
    # The web UI is served as static files by FastAPI — no separate Node
    # process needed at runtime.  Node/npm is only used to BUILD the bundle.
    if not no_ui:
        npm = _npm_available()
        local_web: Path | None = None if refresh_ui else _find_local_web()

        if local_web and npm:
            needs_build = (
                rebuild or build_ui
                or _local_build_is_stale(local_web)
                or not _web_is_cached(__version__)
            )
            if needs_build:
                ok = _build_and_install_local_web(local_web, npm)
                if not ok:
                    console.print("[yellow]Web UI build failed — trying cache / download.[/yellow]")

        if not _web_is_cached(__version__) and not refresh_ui:
            pass  # fall through to download

        if not _web_is_cached(__version__):
            downloaded = _download_web(__version__)
            if not downloaded:
                console.print(
                    "[yellow]Web UI unavailable (no cache, no internet, no Node build).[/yellow]\n"
                    "[dim]Run with --rebuild if you have Node installed, or check your connection.[/dim]"
                )

    # ── Start API daemon ──────────────────────────────────────────────────────
    api_proc = _start_api_daemon(host, port, workers)

    # ── Save PIDs ─────────────────────────────────────────────────────────────
    _write_pid_file({
        "api_pid": api_proc.pid,
        "port": port,
    })

    # ── Done ──────────────────────────────────────────────────────────────────
    console.print()
    console.print(f"  [bold green]→  http://localhost:{port}[/bold green]")
    console.print("  [dim]Stop with: provenant serve --stop[/dim]")
    console.print()
