import asyncio
import getpass
import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Optional

from paprika_mcp_server.paprika_client import PaprikaClient


def detect_mcp_clients() -> dict[str, Path]:
    """
    Detect installed MCP clients and their config file locations.

    Returns:
        Dictionary mapping client name to config file path
    """
    clients = {}
    system = platform.system()

    # Claude Desktop
    if system == "Darwin":  # macOS
        claude_desktop_config = (
            Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
        )
    elif system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        claude_desktop_config = (
            Path(appdata) / "Claude/claude_desktop_config.json" if appdata else None
        )
    else:  # Linux
        claude_desktop_config = Path.home() / ".config/Claude/claude_desktop_config.json"

    if claude_desktop_config and claude_desktop_config.parent.exists():
        clients["Claude Desktop"] = claude_desktop_config

    # Claude Code (CLI)
    claude_code_config = Path.home() / ".claude/config.json"
    if claude_code_config.parent.exists():
        clients["Claude Code"] = claude_code_config

    # VS Code with MCP extension
    vscode_config = Path.home() / ".vscode/mcp.json"
    if vscode_config.exists():
        clients["VS Code"] = vscode_config

    return clients


async def test_paprika_connection(username: str, password: str) -> bool:
    """
    Test connection to Paprika API with provided credentials.

    Args:
        username: Paprika email/username
        password: Paprika password

    Returns:
        True if authentication successful, False otherwise
    """
    try:
        client = PaprikaClient(username=username, password=password)
        await client.authenticate()
        return True
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False


def write_mcp_config(config_path: Path, credentials: dict[str, str]) -> None:
    """
    Write or update MCP client configuration file.

    Args:
        config_path: Path to the MCP client config file
        credentials: Dictionary with username, password, and optional replicate_token
    """
    # Create parent directory if it doesn't exist
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing config or create new one
    if config_path.exists():
        # Backup existing config
        backup_path = config_path.with_suffix(".json.backup")
        shutil.copy(config_path, backup_path)
        print(f"  Backed up existing config to: {backup_path}")

        with open(config_path, "r") as f:
            config = json.load(f)
    else:
        config = {}

    # Ensure mcpServers section exists
    if "mcpServers" not in config:
        config["mcpServers"] = {}

    # Find pipx executable
    pipx_path = shutil.which("pipx")
    if not pipx_path:
        print("  Warning: pipx not found in PATH. Using 'pipx' as command.")
        pipx_path = "pipx"

    # Add or update paprika-mcp server configuration
    env_vars = {
        "PAPRIKA_USERNAME": credentials["username"],
        "PAPRIKA_PASSWORD": credentials["password"],
    }

    if credentials.get("replicate_token"):
        env_vars["REPLICATE_API_TOKEN"] = credentials["replicate_token"]

    config["mcpServers"]["paprika"] = {
        "command": pipx_path,
        "args": ["run", "paprika-mcp"],
        "env": env_vars,
    }

    # Write config file
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    print(f"  ✓ Configured: {config_path}")


async def run_setup(reconfigure: bool = False) -> None:
    """
    Run the interactive setup wizard.

    Args:
        reconfigure: If True, reconfigure existing setup
    """
    print("Paprika MCP Server Setup\n")

    # Detect MCP clients
    clients = detect_mcp_clients()

    if not clients:
        print("No MCP clients detected.")
        print("\nSupported clients:")
        print("  - Claude Desktop")
        print("  - Claude Code")
        print("  - VS Code (with MCP extension)")
        print("\nInstall one of these clients and run setup again.")
        sys.exit(1)

    print(f"Found {len(clients)} MCP client(s):")
    for name in clients:
        print(f"  - {name}")
    print()

    # Gather credentials
    print("Paprika Credentials")
    print("──────────────────")

    username = input("Email/Username: ").strip()
    if not username:
        print("Username is required.")
        sys.exit(1)

    password = getpass.getpass("Password: ").strip()
    if not password:
        print("Password is required.")
        sys.exit(1)

    # Test connection
    print("\nTesting connection...")
    if not await test_paprika_connection(username, password):
        print("\nSetup aborted. Please check your credentials and try again.")
        sys.exit(1)

    print("✓ Successfully connected to Paprika API")

    # Optional: Replicate API token for image generation
    print("\n AI Image Generation (Optional)")
    print("─────────────────────────────────")
    print("Generate food photos with Flux (Black Forest Lab)")
    print("Get token at: https://replicate.com/account/api-tokens")

    replicate_token = getpass.getpass("Replicate API Token (press Enter to skip): ").strip()

    # Prepare credentials dict
    credentials = {
        "username": username,
        "password": password,
    }
    if replicate_token:
        credentials["replicate_token"] = replicate_token

    # Write config files
    print("\nConfiguring MCP clients...")
    for client_name, config_path in clients.items():
        write_mcp_config(config_path, credentials)

    # Success message
    print("\n✓ Setup complete!")
    print("\nNext steps:")
    print("  1. Restart your MCP client (fully quit and reopen)")
    print("  2. Try: 'Create a simple pasta recipe'")
    print("\nFor help: https://github.com/sandordaroczi/paprika-mcp-python-server")


if __name__ == "__main__":
    asyncio.run(run_setup())
