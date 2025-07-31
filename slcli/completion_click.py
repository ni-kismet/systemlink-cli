"""Shell completion functionality for slcli."""

import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

import click


def get_cli_commands_dynamically() -> Dict[str, List[str]]:
    """Extract commands and subcommands from the CLI structure dynamically.

    Returns:
        Dict mapping command names to lists of their subcommands.
    """
    try:
        # Import the main CLI group to inspect its structure
        from slcli.main import cli

        commands = {}

        # Get top-level commands
        commands[""] = list(cli.commands.keys())

        # Get subcommands for each command
        for cmd_name, cmd_obj in cli.commands.items():
            if isinstance(cmd_obj, click.Group):
                commands[cmd_name] = list(cmd_obj.commands.keys())
            else:
                commands[cmd_name] = []

        return commands
    except Exception:
        # Fallback to hardcoded commands if introspection fails
        return {
            "": [
                "completion",
                "login",
                "logout",
                "notebook",
                "template",
                "user",
                "workflow",
                "workspace",
            ],
            "notebook": ["list", "get", "create", "update", "delete", "run"],
            "template": ["list", "get", "create", "update", "delete"],
            "user": ["list", "get", "create", "update", "delete"],
            "workflow": ["list", "get", "create", "update", "delete", "run"],
            "workspace": ["list", "get", "create", "update", "delete"],
            "completion": [],
        }


def generate_powershell_completion_dynamic() -> str:
    """Generate PowerShell completion script using dynamic command discovery."""
    commands_dict = get_cli_commands_dynamically()

    # Build the command arrays as PowerShell code
    top_level_commands = commands_dict.get("", [])

    powershell_script = f"""
# PowerShell completion for slcli (dynamically generated)
Register-ArgumentCompleter -Native -CommandName slcli -ScriptBlock {{
    param($wordToComplete, $commandAst, $cursorPosition)
    
    # Get all arguments passed so far
    $arguments = $commandAst.CommandElements | Select-Object -Skip 1 | ForEach-Object {{ $_.Value }}
    
    # Dynamically defined command structure
    $topLevelCommands = @({', '.join(f"'{cmd}'" for cmd in top_level_commands)})
    
    # Subcommand mappings
    $subCommands = @{{"""

    # Add subcommand mappings
    for cmd, subcmds in commands_dict.items():
        if cmd and subcmds:  # Skip empty command key and empty subcommand lists
            subcmd_list = ", ".join(f"'{sub}'" for sub in subcmds)
            powershell_script += f"\n        '{cmd}' = @({subcmd_list})"

    powershell_script += """
    }
    
    # Function to get available options dynamically by calling slcli --help
    function Get-SlcliOptions {
        param($command, $subCommand = $null)
        
        $options = @()
        
        try {
            # Build command to get help for
            $helpCmd = @('slcli')
            if ($command) { $helpCmd += $command }
            if ($subCommand) { $helpCmd += $subCommand }
            $helpCmd += '--help'
            
            # Get options from help output
            $helpOutput = & $helpCmd[0] $helpCmd[1..($helpCmd.Length-1)] 2>$null
            if ($LASTEXITCODE -eq 0) {
                $options = $helpOutput | 
                    Select-String -Pattern "^\\s+(--?\\w+(?:-\\w+)*)" | 
                    ForEach-Object { $_.Matches[0].Groups[1].Value }
                return $options
            }
        } catch {
            # Fallback to basic options
        }
        
        # Fallback hardcoded options
        $options += @('--help', '-h')
        
        if (-not $command) {
            $options += @('--version')
        }
        
        return $options
    }
    
    # Determine what to complete based on current position
    $completions = @()
    
    if ($arguments.Count -eq 0) {
        # Complete top-level commands
        $completions = $topLevelCommands | Where-Object { $_ -like "$wordToComplete*" }
    } elseif ($arguments.Count -eq 1) {
        $firstArg = $arguments[0]
        
        if ($firstArg.StartsWith('-')) {
            # Complete global options
            $completions = Get-SlcliOptions | Where-Object { $_ -like "$wordToComplete*" }
        } elseif ($subCommands.ContainsKey($firstArg)) {
            # Complete subcommands
            $completions = $subCommands[$firstArg] | Where-Object { $_ -like "$wordToComplete*" }
        }
    } elseif ($arguments.Count -eq 2) {
        $command = $arguments[0]
        $subCommand = $arguments[1]
        
        if ($subCommand.StartsWith('-')) {
            # Complete command options
            $completions = Get-SlcliOptions $command | Where-Object { $_ -like "$wordToComplete*" }
        } else {
            # Complete subcommand options
            $completions = Get-SlcliOptions $command $subCommand | Where-Object { $_ -like "$wordToComplete*" }
        }
    } else {
        # Complete options for the current command/subcommand context
        $command = $arguments[0]
        $subCommand = if ($arguments.Count -gt 1 -and -not $arguments[1].StartsWith('-')) { $arguments[1] } else { $null }
        $completions = Get-SlcliOptions $command $subCommand | Where-Object { $_ -like "$wordToComplete*" }
    }
    
    $completions | ForEach-Object {{
        [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_)
    }}
}}
"""

    return powershell_script


def detect_shell() -> Optional[str]:
    """Auto-detect the current shell."""
    shell_path = os.environ.get("SHELL", "")
    if "bash" in shell_path:
        return "bash"
    elif "zsh" in shell_path:
        return "zsh"
    elif "fish" in shell_path:
        return "fish"
    elif os.name == "nt" or "pwsh" in os.environ.get("PSModulePath", ""):
        return "powershell"
    return None


def generate_bash_completion_compatible() -> str:
    """Generate version-compatible bash completion script.

    This script works with both old bash (3.2+) and new bash (4.4+) versions
    by detecting bash capabilities and using appropriate options.
    """
    return """_slcli_completion() {
    local IFS=$'\\n'
    local response

    response=$(env COMP_WORDS="${COMP_WORDS[*]}" COMP_CWORD=$COMP_CWORD _SLCLI_COMPLETE=bash_complete $1)

    for completion in $response; do
        IFS=',' read type value <<< "$completion"

        if [[ $type == 'dir' ]]; then
            COMPREPLY=()
            if command -v compopt >/dev/null 2>&1; then
                compopt -o dirnames
            fi
        elif [[ $type == 'file' ]]; then
            COMPREPLY=()
            if command -v compopt >/dev/null 2>&1; then
                compopt -o default
            fi
        elif [[ $type == 'plain' ]]; then
            COMPREPLY+=($value)
        fi
    done

    return 0
}

_slcli_completion_setup() {
    # Check if bash supports nosort option (bash 4.4+)
    if [[ ${BASH_VERSINFO[0]} -gt 4 || (${BASH_VERSINFO[0]} -eq 4 && ${BASH_VERSINFO[1]} -ge 4) ]]; then
        complete -o nosort -F _slcli_completion slcli
    else
        complete -F _slcli_completion slcli
    fi
}

_slcli_completion_setup;"""


def generate_completion_script(shell: str) -> Optional[str]:
    """Generate completion script for the specified shell."""
    if shell.lower() == "powershell":
        # Use dynamic completion for PowerShell
        return generate_powershell_completion_dynamic()
    elif shell.lower() == "bash":
        # Use version-compatible bash completion script
        return generate_bash_completion_compatible()

    # For zsh, fish - use Click's built-in completion
    env_vars = {
        "zsh": ("_SLCLI_COMPLETE", "zsh_source"),
        "fish": ("_SLCLI_COMPLETE", "fish_source"),
    }

    if shell.lower() not in env_vars:
        return None

    env_var, env_value = env_vars[shell.lower()]

    try:
        result = subprocess.run(
            ["slcli"], capture_output=True, text=True, env={**os.environ, env_var: env_value}
        )
        return result.stdout if result.returncode == 0 else None
    except Exception:
        return None


def install_bash_completion(completion_script: str) -> bool:
    """Install bash completion script."""
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
    completion_file.write_text(completion_script)

    click.echo(f"✓ Bash completion installed to {completion_file}")
    click.echo("To activate, reload your shell or run:")
    click.echo(f"  source {completion_file}")
    return True


def install_zsh_completion(completion_script: str) -> bool:
    """Install zsh completion script."""
    home = Path.home()
    zsh_completion_dir = home / ".zsh_completions"
    zsh_completion_dir.mkdir(exist_ok=True)
    completion_file = zsh_completion_dir / "_slcli"

    completion_file.write_text(completion_script)
    click.echo(f"✓ Zsh completion installed to {completion_file}")
    click.echo("To activate, add this to your ~/.zshrc:")
    click.echo("  fpath=(~/.zsh_completions $fpath)")
    click.echo("  autoload -U compinit && compinit")
    return True


def install_fish_completion(completion_script: str) -> bool:
    """Install fish completion script."""
    home = Path.home()
    fish_completion_dir = home / ".config/fish/completions"
    fish_completion_dir.mkdir(parents=True, exist_ok=True)
    completion_file = fish_completion_dir / "slcli.fish"

    completion_file.write_text(completion_script)
    click.echo(f"✓ Fish completion installed to {completion_file}")
    click.echo("Completion is now active (restart fish if needed)")
    return True


def install_powershell_completion(completion_script: str) -> bool:
    """Install PowerShell completion script."""
    home = Path.home()

    if os.name == "nt":
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
    completion_file.write_text(completion_script)

    click.echo(f"✓ PowerShell completion installed to {completion_file}")
    click.echo("To activate, add this line to your PowerShell profile:")
    click.echo(f"  . {completion_file}")
    click.echo("Or run this command to add it automatically:")
    click.echo(f"  Add-Content $PROFILE '. {completion_file}'")
    return True


def install_completion_for_shell(shell: str) -> bool:
    """Install completion script for the specified shell."""
    completion_script = generate_completion_script(shell)

    if not completion_script:
        click.echo("✗ Failed to generate completion script", err=True)
        return False

    installers = {
        "bash": install_bash_completion,
        "zsh": install_zsh_completion,
        "fish": install_fish_completion,
        "powershell": install_powershell_completion,
    }

    installer = installers.get(shell.lower())
    if not installer:
        click.echo(f"✗ Unsupported shell: {shell}", err=True)
        return False

    return installer(completion_script)


def register_completion_command(cli):
    """Register the completion command with the CLI."""

    @cli.command()
    @click.option(
        "--shell",
        type=click.Choice(["bash", "zsh", "fish", "powershell"], case_sensitive=False),
        help="Shell type (auto-detected if not specified)",
    )
    @click.option(
        "--install",
        is_flag=True,
        help="Install completion script to shell config file",
    )
    def completion(shell, install):
        """Generate and optionally install shell completion scripts.

        Examples:
            # Generate bash completion script
            slcli completion --shell bash

            # Install completion for current shell
            slcli completion --install

            # Generate and save to file
            slcli completion --shell zsh > ~/.zsh_completions/_slcli
        """
        # Auto-detect shell if not specified
        if not shell:
            shell = detect_shell()
            if not shell:
                click.echo("Could not auto-detect shell. Please specify with --shell", err=True)
                return

        if install:
            # Install completion script
            install_completion_for_shell(shell)
        else:
            # Just output the completion script
            completion_script = generate_completion_script(shell)

            if completion_script:
                click.echo(completion_script)
            else:
                click.echo("✗ Failed to generate completion script", err=True)
