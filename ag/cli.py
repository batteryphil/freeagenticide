"""CLI entry point for Antigravity-Local."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click

from ag.core.config import load_config


@click.group(invoke_without_command=True)
@click.option("--config", "-c", default=None, help="Path to config.yaml")
@click.pass_context
def cli(ctx: click.Context, config: Optional[str]) -> None:
    """Antigravity-Local — multi-provider AI coding assistant.

    Run without a subcommand to launch the TUI.
    """
    ctx.ensure_object(dict)
    cfg = load_config(config)
    ctx.obj["config"] = cfg

    if ctx.invoked_subcommand is None:
        # Default: launch TUI
        from ag.tui.app import AntigravityApp

        app = AntigravityApp(cfg)
        app.run()


@cli.command("check-providers")
@click.pass_context
def check_providers(ctx: click.Context) -> None:
    """Run health checks on all configured providers and print results."""
    import asyncio
    import sys

    from ag.providers.registry import ProviderRegistry

    config = ctx.obj["config"]
    registry = ProviderRegistry(config.providers)

    async def _run() -> None:
        """Run async health checks."""
        click.echo("Checking providers…\n")
        health = await registry.check_all()
        for name, h in sorted(health.items()):
            status = "✅  AVAILABLE" if h.available else "❌  UNAVAILABLE"
            latency = f"  {h.latency_ms:.0f}ms" if h.available else ""
            err = f"  ({h.error})" if h.error else ""
            click.echo(f"  {status}  {name}{latency}{err}")
            if h.models:
                click.echo(f"     models: {', '.join(h.models[:5])}")
        click.echo()
        available = [n for n, h in health.items() if h.available]
        click.echo(f"Available ({len(available)}): {', '.join(available) or 'none'}")

    asyncio.run(_run())


@cli.command("configure")
@click.option("--out", "-o", default="config.yaml", help="Output config file path")
def configure(out: str) -> None:
    """Write a default config.yaml template to disk."""
    import shutil
    from importlib.resources import files

    template = Path(__file__).parent.parent / "config.yaml"
    target = Path(out)
    if target.exists():
        click.confirm(f"{out} already exists. Overwrite?", abort=True)
    shutil.copy(template, target)
    click.echo(f"Config written to {target.resolve()}")
    click.echo("Edit it to add your API keys, then run: antigravity")


@cli.command("serve")
@click.option("--host", default="127.0.0.1", help="Bind host", show_default=True)
@click.option("--port", "-p", default=7800, help="Bind port", show_default=True)
@click.option("--no-browser", is_flag=True, help="Don't open browser automatically")
@click.option("--reload", is_flag=True, help="Enable uvicorn hot-reload (dev mode)")
@click.pass_context
def serve(
    ctx: click.Context,
    host: str,
    port: int,
    no_browser: bool,
    reload: bool,
) -> None:
    """Start the web UI server (React + Monaco frontend).

    Opens http://HOST:PORT in your browser after startup.
    Run 'antigravity serve' from the project directory.
    """
    import uvicorn

    config = ctx.obj["config"]

    if not no_browser:
        import threading
        import webbrowser
        import time

        def _open_browser() -> None:
            """Open browser after a short delay to let the server start."""
            time.sleep(1.2)
            webbrowser.open(f"http://{host}:{port}")

        threading.Thread(target=_open_browser, daemon=True).start()

    click.echo(f"🚀  Antigravity UI  →  http://{host}:{port}")
    click.echo("     Press Ctrl+C to stop.\n")

    uvicorn.run(
        "ag.server.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
        log_level="warning",
    )



def main() -> None:
    """Entrypoint called by the installed script."""
    cli()


if __name__ == "__main__":
    main()
