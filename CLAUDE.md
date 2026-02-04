This is CLI tool written in python to render argocd applications.

Always use context7 when I need code generation, setup or configuration steps, or
library/API documentation. This means you should automatically use the Context7 MCP
tools to resolve library id and get library docs without me having to explicitly ask.

Ignore all files mentioned in .gitignore.

## Output Behavior

- All logs go to stderr, only resulting YAML goes to stdout
- Detail logs are always shown (no --verbose flag required)
- --verbose flag shows commands executed and their stdout+stderr (to stderr)

## External Commands

When calling external commands (git, helm, etc.) via subprocess:
1. **Log commands only in verbose mode** - Use `if verbose: log(f"Running: {' '.join(cmd)}")` before execution
2. **Use non-interactive flags on commands themselves**:
   - git: Use `--no-pager` and set `GIT_TERMINAL_PROMPT=0` environment variable
   - helm: Use `--debug` flag for verbose output instead of relying on stdout
3. **Always capture output** - Use `capture_output=True`, never use `DEVNULL`
4. **Show output on errors** - Display captured stdout/stderr when command fails
5. **Fail on errors** - Every external command failure should fail the application unless explicitly handled with documented reason

