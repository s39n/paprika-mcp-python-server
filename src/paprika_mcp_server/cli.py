import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import NoReturn

from paprika_mcp_server import __version__


def run_server() -> None:
    """Run the MCP server (default command)."""
    from paprika_mcp_server.server import main as async_main

    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nServer stopped.")
        sys.exit(0)
    except Exception as e:
        print(f"Error starting server: {e}", file=sys.stderr)
        sys.exit(1)


def setup_wizard() -> None:
    """Run interactive setup wizard."""
    from paprika_mcp_server.setup_wizard import run_setup

    try:
        asyncio.run(run_setup())
    except KeyboardInterrupt:
        print("\nSetup cancelled.")
        sys.exit(0)
    except Exception as e:
        print(f"Setup failed: {e}", file=sys.stderr)
        sys.exit(1)


def reconfigure() -> None:
    """Reconfigure credentials and settings."""
    from paprika_mcp_server.setup_wizard import run_setup

    print("Reconfiguring Paprika MCP Server...")
    try:
        asyncio.run(run_setup(reconfigure=True))
    except KeyboardInterrupt:
        print("\nReconfiguration cancelled.")
        sys.exit(0)
    except Exception as e:
        print(f"Reconfiguration failed: {e}", file=sys.stderr)
        sys.exit(1)


def test_connection() -> None:
    """Test connection to Paprika API."""
    from paprika_mcp_server.config import get_config
    from paprika_mcp_server.paprika_client import PaprikaClient

    async def _test():
        print("Testing Paprika API connection...")
        try:
            config = get_config()
            client = PaprikaClient(username=config["username"], password=config["password"])
            await client.authenticate()
            print("✓ Successfully connected to Paprika API")
            print(f"✓ Authenticated as: {config['username']}")
            return 0
        except Exception as e:
            print(f"✗ Connection failed: {e}", file=sys.stderr)
            return 1

    try:
        exit_code = asyncio.run(_test())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nTest cancelled.")
        sys.exit(0)


def show_logs() -> None:
    """Show recent MCP logs from Claude Desktop."""
    import platform
    import subprocess

    system = platform.system()

    if system == "Darwin":  # macOS
        log_dir = Path.home() / "Library/Logs/Claude"
    elif system == "Windows":
        log_dir = Path(os.environ.get("APPDATA", "")) / "Claude/Logs"
    elif system == "Linux":
        log_dir = Path.home() / ".local/share/claude/logs"
    else:
        print(f"Unsupported platform: {system}", file=sys.stderr)
        sys.exit(1)

    if not log_dir.exists():
        print(f"Log directory not found: {log_dir}", file=sys.stderr)
        print("Make sure Claude Desktop is installed and has been run at least once.")
        sys.exit(1)

    # Find MCP log files
    mcp_logs = sorted(log_dir.glob("mcp*.log"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not mcp_logs:
        print("No MCP log files found.", file=sys.stderr)
        sys.exit(1)

    latest_log = mcp_logs[0]
    print(f"Showing logs from: {latest_log}\n")

    # Show last 50 lines
    try:
        if system == "Windows":
            # Use PowerShell Get-Content on Windows
            subprocess.run(["powershell", "-Command", f"Get-Content '{latest_log}' -Tail 50"])
        else:
            # Use tail on Unix-like systems
            subprocess.run(["tail", "-n", "50", str(latest_log)])
    except Exception as e:
        print(f"Error reading logs: {e}", file=sys.stderr)
        sys.exit(1)


def show_version() -> None:
    """Show version information."""
    print(f"paprika-mcp v{__version__}")
    print("Python MCP Server for Paprika Recipe Manager")
    print("https://github.com/sandordaroczi/paprika-mcp-python-server")


def main() -> NoReturn:
    """Main CLI entry point with subcommands."""
    parser = argparse.ArgumentParser(
        prog="paprika-mcp",
        description="MCP server for Paprika Recipe Manager with AI-generated food photography",
        epilog="For more information: https://github.com/sandordaroczi/paprika-mcp-python-server",
    )

    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Setup command
    setup_parser = subparsers.add_parser(
        "setup", help="Interactive setup wizard for first-time configuration"
    )

    # Config command
    config_parser = subparsers.add_parser("config", help="Reconfigure credentials and settings")

    # Test command
    test_parser = subparsers.add_parser("test", help="Test connection to Paprika API")

    # Logs command
    logs_parser = subparsers.add_parser("logs", help="Show recent MCP logs from Claude Desktop")

    # Version command (also available via --version flag)
    version_parser = subparsers.add_parser("version", help="Show version information")

    args = parser.parse_args()

    # Route to appropriate command
    if args.command == "setup":
        setup_wizard()
    elif args.command == "config":
        reconfigure()
    elif args.command == "test":
        test_connection()
    elif args.command == "logs":
        show_logs()
    elif args.command == "version":
        show_version()
        sys.exit(0)
    elif args.command is None:
        # No subcommand provided - run the MCP server (default behavior)
        run_server()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
