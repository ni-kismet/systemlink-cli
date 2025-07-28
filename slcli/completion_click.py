"""Shell completion functionality for slcli."""

import os
import subprocess
from pathlib import Path
from typing import Optional

import click


def generate_powershell_completion() -> str:
    """Generate PowerShell completion script for slcli."""
    return """
# PowerShell completion for slcli
Register-ArgumentCompleter -Native -CommandName slcli -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)
    
    # Get all arguments passed so far
    $arguments = $commandAst.CommandElements | Select-Object -Skip 1 | ForEach-Object { $_.Value }
    
    # Function to get available commands
    function Get-SlcliCommands {
        param($subCommand = $null)
        
        $commands = @()
        
        if (-not $subCommand) {
            # Top-level commands
            $commands += @('completion', 'login', 'logout', 'notebook', 'template', 'user', 'workflow', 'workspace')
        } else {
            switch ($subCommand) {
                'notebook' { $commands += @('list', 'get', 'create', 'update', 'delete', 'run') }
                'template' { $commands += @('list', 'get', 'create', 'update', 'delete') }
                'user' { $commands += @('list', 'get', 'create', 'update', 'delete') }
                'workflow' { $commands += @('list', 'get', 'create', 'update', 'delete', 'run') }
                'workspace' { $commands += @('list', 'get', 'create', 'update', 'delete') }
                'completion' { $commands += @() }
            }
        }
        
        return $commands
    }
    
    # Function to get available options
    function Get-SlcliOptions {
        param($command, $subCommand = $null)
        
        $options = @()
        
        # Global options
        $options += @('--help', '-h', '--version')
        
        # Command-specific options
        if ($command -eq 'completion') {
            $options += @('--shell', '--install')
        } elseif ($command -eq 'login') {
            $options += @('--url', '--api-key')
        } elseif ($subCommand) {
            switch ($subCommand) {
                'list' { $options += @('--format', '-f', '--filter', '--take', '--sortby', '--order') }
                'get' { $options += @('--id', '--name', '--email', '--format', '-f') }
                'create' { 
                    switch ($command) {
                        'user' { $options += @('--first-name', '--last-name', '--email', '--niua-id', '--accepted-tos', '--policies', '--keywords', '--properties') }
                        default { $options += @('--name', '--description') }
                    }
                }
                'update' { $options += @('--id', '--name', '--description') }
                'delete' { $options += @('--id') }
            }
        }
        
        return $options
    }
    
    # Function to get option values
    function Get-SlcliOptionValues {
        param($option)
        
        switch ($option) {
            '--format' { return @('table', 'json') }
            '-f' { return @('table', 'json') }
            '--shell' { return @('bash', 'zsh', 'fish', 'powershell') }
            '--order' { return @('ascending', 'descending') }
            '--sortby' { 
                # This would depend on the command context
                return @('name', 'created', 'updated', 'firstName', 'lastName', 'email', 'status')
            }
            default { return @() }
        }
    }
    
    # Parse current command context
    $currentCommand = $null
    $currentSubCommand = $null
    $lastOption = $null
    
    for ($i = 0; $i -lt $arguments.Count; $i++) {
        $arg = $arguments[$i]
        
        if ($arg.StartsWith('--') -or $arg.StartsWith('-')) {
            $lastOption = $arg
        } elseif (-not $currentCommand) {
            $currentCommand = $arg
        } elseif (-not $currentSubCommand) {
            $currentSubCommand = $arg
        } else {
            $lastOption = $null
        }
    }
    
    # If we're completing an option value
    if ($lastOption) {
        $values = Get-SlcliOptionValues -option $lastOption
        $values | Where-Object { $_ -like "$wordToComplete*" } | ForEach-Object {
            [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_)
        }
        return
    }
    
    # If we're completing an option
    if ($wordToComplete.StartsWith('-')) {
        $options = Get-SlcliOptions -command $currentCommand -subCommand $currentSubCommand
        $options | Where-Object { $_ -like "$wordToComplete*" } | ForEach-Object {
            [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterName', $_)
        }
        return
    }
    
    # If we're completing a command or subcommand
    if (-not $currentCommand) {
        # Top-level commands
        $commands = Get-SlcliCommands
        $commands | Where-Object { $_ -like "$wordToComplete*" } | ForEach-Object {
            [System.Management.Automation.CompletionResult]::new($_, $_, 'Command', $_)
        }
    } elseif (-not $currentSubCommand) {
        # Subcommands
        $commands = Get-SlcliCommands -subCommand $currentCommand
        $commands | Where-Object { $_ -like "$wordToComplete*" } | ForEach-Object {
            [System.Management.Automation.CompletionResult]::new($_, $_, 'Command', $_)
        }
    }
}
"""


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


def generate_completion_script(shell: str) -> Optional[str]:
    """Generate completion script for the specified shell."""
    if shell.lower() == "powershell":
        return generate_powershell_completion()

    # For bash, zsh, fish - use Click's built-in completion
    env_vars = {
        "bash": ("_SLCLI_COMPLETE", "bash_source"),
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
