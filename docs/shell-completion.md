# Shell Completion for slcli

The SystemLink CLI supports shell completion for bash, zsh, fish, and PowerShell shells.

## Quick Installation

### Automatic Installation (Recommended)

```bash
# Install completion for your current shell
slcli completion --install

# Or specify a shell explicitly
slcli completion --shell bash --install
slcli completion --shell zsh --install
slcli completion --shell fish --install
slcli completion --shell powershell --install
```

### Manual Installation

#### Bash

1. Generate completion script:

   ```bash
   slcli completion --shell bash > ~/.bash_completion.d/slcli
   ```

2. Source the completion (add to ~/.bashrc for persistence):
   ```bash
   source ~/.bash_completion.d/slcli
   ```

#### Zsh

1. Create completion directory and generate script:

   ```bash
   mkdir -p ~/.zsh_completions
   slcli completion --shell zsh > ~/.zsh_completions/_slcli
   ```

2. Add to your ~/.zshrc:
   ```bash
   fpath=(~/.zsh_completions $fpath)
   autoload -U compinit && compinit
   ```

#### Fish

1. Generate completion script:
   ```bash
   slcli completion --shell fish > ~/.config/fish/completions/slcli.fish
   ```

Fish will automatically load the completion on next shell restart.

#### PowerShell

1. Generate completion script:

   ```powershell
   slcli completion --shell powershell > $env:USERPROFILE\Documents\PowerShell\slcli_completion.ps1
   ```

2. Add to your PowerShell profile:

   ```powershell
   # Add this line to your $PROFILE
   . $env:USERPROFILE\Documents\PowerShell\slcli_completion.ps1
   ```

   Or run this command to add it automatically:

   ```powershell
   Add-Content $PROFILE ". `$env:USERPROFILE\Documents\PowerShell\slcli_completion.ps1"
   ```

## Using the Installation Script

You can also use the dedicated installation script:

```bash
# Install for current shell (auto-detected)
python scripts/install_completion.py

# Install for specific shell
python scripts/install_completion.py bash
python scripts/install_completion.py zsh
python scripts/install_completion.py fish
python scripts/install_completion.py powershell
```

## What Gets Completed

The completion system will help with:

- Command names (`user`, `workspace`, `template`, etc.)
- Subcommands (`list`, `get`, `create`, `update`, `delete`)
- Option names (`--format`, `--filter`, `--id`, etc.)
- Option values for choices (e.g., `--format` will complete `table` and `json`)

## Troubleshooting

### Completion Not Working

1. Verify slcli is in your PATH:

   ```bash
   which slcli
   ```

2. Test completion generation:

   ```bash
   slcli completion --shell bash  # Should output bash completion script
   ```

3. For bash, ensure bash-completion is installed:

   ```bash
   # Ubuntu/Debian
   sudo apt install bash-completion

   # macOS with Homebrew
   brew install bash-completion
   ```

4. Restart your shell or source the completion file manually.

### Permission Issues

If you get permission errors during installation, try:

1. Install to user directory instead of system-wide
2. Run with appropriate permissions for system directories
3. Use the manual installation method

### PowerShell Module Not Loading

For PowerShell completion issues:

1. Check if execution policy allows script loading:

   ```powershell
   Get-ExecutionPolicy
   ```

2. If restricted, set execution policy (as Administrator):

   ```powershell
   Set-ExecutionPolicy RemoteSigned
   ```

3. Verify your profile exists:

   ```powershell
   Test-Path $PROFILE
   ```

4. Create profile if it doesn't exist:
   ```powershell
   New-Item -Path $PROFILE -ItemType File -Force
   ```

## Advanced Usage

### Custom Completion Location

You can save completion scripts to custom locations:

```bash
# Save to custom file
slcli completion --shell bash > /path/to/custom/completion

# Source it manually
source /path/to/custom/completion
```

### Integration with Package Managers

If you're distributing slcli via package managers, consider:

- **Homebrew**: Include completion in formula
- **APT/RPM**: Install completion to standard system directories
- **pip**: Use post-install hooks to offer completion installation
