#!/usr/bin/env python3
"""Script to install shell completion for slcli."""

import os
import subprocess
import sys
from pathlib import Path


def install_bash_completion():
    """Install bash completion."""
    home = Path.home()

    # Try common bash completion directories
    completion_dirs = [
        home / ".bash_completion.d",
        Path("/usr/local/etc/bash_completion.d"),
        Path("/etc/bash_completion.d"),
    ]

    # Find writable completion directory
    completion_dir = None
    for dir_path in completion_dirs:
        if dir_path.exists() and os.access(dir_path, os.W_OK):
            completion_dir = dir_path
            break

    if not completion_dir:
        # Create user completion directory
        completion_dir = home / ".bash_completion.d"
        completion_dir.mkdir(exist_ok=True)

    completion_file = completion_dir / "slcli"

    # Generate completion script
    result = subprocess.run(
        ["slcli", "completion", "--shell", "bash"], capture_output=True, text=True
    )

    if result.returncode == 0:
        completion_file.write_text(result.stdout)
        print(f"✓ Bash completion installed to {completion_file}")
        print("To activate, reload your shell or add to ~/.bashrc:")
        print(f"  source {completion_file}")
        return True
    else:
        print("✗ Failed to generate bash completion script")
        return False


def install_zsh_completion():
    """Install zsh completion."""
    home = Path.home()

    # Create zsh completion directory
    zsh_completion_dir = home / ".zsh_completions"
    zsh_completion_dir.mkdir(exist_ok=True)
    completion_file = zsh_completion_dir / "_slcli"

    # Generate completion script
    result = subprocess.run(
        ["slcli", "completion", "--shell", "zsh"], capture_output=True, text=True
    )

    if result.returncode == 0:
        completion_file.write_text(result.stdout)
        print(f"✓ Zsh completion installed to {completion_file}")
        print("To activate, add these lines to your ~/.zshrc:")
        print("  fpath=(~/.zsh_completions $fpath)")
        print("  autoload -U compinit && compinit")
        return True
    else:
        print("✗ Failed to generate zsh completion script")
        return False


def install_fish_completion():
    """Install fish completion."""
    home = Path.home()

    # Create fish completion directory
    fish_completion_dir = home / ".config/fish/completions"
    fish_completion_dir.mkdir(parents=True, exist_ok=True)
    completion_file = fish_completion_dir / "slcli.fish"

    # Generate completion script
    result = subprocess.run(
        ["slcli", "completion", "--shell", "fish"], capture_output=True, text=True
    )

    if result.returncode == 0:
        completion_file.write_text(result.stdout)
        print(f"✓ Fish completion installed to {completion_file}")
        print("Completion is now active (restart fish if needed)")
        return True
    else:
        print("✗ Failed to generate fish completion script")
        return False


def install_powershell_completion():
    """Install PowerShell completion."""
    import platform

    home = Path.home()

    # Determine PowerShell profile directory based on OS
    if platform.system() == "Windows":
        # Windows PowerShell profile
        ps_profile_dirs = [
            home / "Documents" / "PowerShell",
            home / "Documents" / "WindowsPowerShell",
        ]
    else:
        # PowerShell Core on Unix
        ps_profile_dirs = [
            home / ".config" / "powershell",
        ]

    # Find or create PowerShell profile directory
    profile_dir = None
    for dir_path in ps_profile_dirs:
        if dir_path.exists():
            profile_dir = dir_path
            break

    if not profile_dir:
        # Create the first option
        profile_dir = ps_profile_dirs[0]
        profile_dir.mkdir(parents=True, exist_ok=True)

    completion_file = profile_dir / "slcli_completion.ps1"

    # Generate completion script
    result = subprocess.run(
        ["slcli", "completion", "--shell", "powershell"], capture_output=True, text=True
    )

    if result.returncode == 0:
        completion_file.write_text(result.stdout)
        print(f"✓ PowerShell completion installed to {completion_file}")
        print("To activate, add this line to your PowerShell profile:")
        print(f"  . {completion_file}")
        print("Or run this command to add it automatically:")
        print(f"  Add-Content $PROFILE '. {completion_file}'")
        return True
    else:
        print("✗ Failed to generate PowerShell completion script")
        return False


def main():
    """Main function."""
    if len(sys.argv) > 1:
        shell = sys.argv[1].lower()
    else:
        # Auto-detect shell
        shell_path = os.environ.get("SHELL", "")
        if "bash" in shell_path:
            shell = "bash"
        elif "zsh" in shell_path:
            shell = "zsh"
        elif "fish" in shell_path:
            shell = "fish"
        elif os.name == "nt" or "pwsh" in os.environ.get("PSModulePath", ""):
            shell = "powershell"
        else:
            print("Could not auto-detect shell. Specify: bash, zsh, fish, or powershell")
            sys.exit(1)

    print(f"Installing {shell} completion for slcli...")

    if shell == "bash":
        success = install_bash_completion()
    elif shell == "zsh":
        success = install_zsh_completion()
    elif shell == "fish":
        success = install_fish_completion()
    elif shell == "powershell":
        success = install_powershell_completion()
    else:
        print(f"Unsupported shell: {shell}")
        print("Supported shells: bash, zsh, fish, powershell")
        sys.exit(1)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
