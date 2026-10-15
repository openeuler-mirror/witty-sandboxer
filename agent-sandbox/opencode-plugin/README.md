# opencode-opensandbox-infra

A general-purpose **agent infrastructure** plugin for OpenCode that provides full control over **OpenSandbox** containers through composable tool primitives.

## Architecture

```
Agent
  │
  ├── sandbox_create ──────▶ Spin up container, get sandbox ID
  ├── sandbox_upload ──────▶ Push local file into sandbox
  ├── sandbox_upload_text ─▶ Write text content to remote path
  ├── sandbox_exec ────────▶ Run shell command in sandbox
  ├── sandbox_download ────▶ Pull file from sandbox to local
  ├── sandbox_download_dir ▶ Pull multiple files (glob) from sandbox
  └── sandbox_destroy ─────▶ Destroy sandbox, free resources
```

The seven tools are **atomic primitives** that the agent can compose into arbitrary workflows.

## Tools

| Tool | Description |
|---|---|
| `sandbox_create` | Create a new sandbox container. Returns `sandbox_id`. |
| `sandbox_exec` | Execute a shell command in a sandbox. Returns stdout/stderr/exit_code. |
| `sandbox_upload` | Upload a local file to a path inside the sandbox. |
| `sandbox_upload_text` | Write text content directly to a remote path (no local file needed). |
| `sandbox_download` | Download a single file from the sandbox to local. |
| `sandbox_download_dir` | Download multiple files matching a glob pattern from a remote directory. |
| `sandbox_destroy` | Destroy a sandbox and release resources. |

## Prerequisites

1. **OpenCode** installed
2. **Python 3.10+** with `opensandbox` SDK:
   ```bash
   pip install opensandbox
   ```
3. OpenSandbox API key configured (`OPENSANDBOX_API_KEY` env var or SDK config)

## Installation

Copy the plugin files into your project's `.opencode/plugins/` directory:

```bash
mkdir -p .opencode/plugins
cp agent-sandbox-infra.ts  .opencode/plugins/
cp sandbox_runner.py      .opencode/plugins/
```

Or install globally:

```bash
mkdir -p ~/.config/opencode/plugins
cp agent-sandbox-infra.ts  ~/.config/opencode/plugins/
cp sandbox_runner.py      ~/.config/opencode/plugins/
```

Restart OpenCode. The 7 tools will be available to the agent.

## Usage Examples

### Composed Workflow (primitives)

Ask the agent:

> "Create a sandbox with python:3.12, upload my script.py, run it, download the output.txt, then destroy the sandbox."

The agent will chain these tools:
1. `sandbox_create` → gets `sandbox_id`
2. `sandbox_upload` → pushes `script.py`
3. `sandbox_exec` → runs `python script.py`
4. `sandbox_download` → pulls `output.txt`
5. `sandbox_destroy` → cleanup

### Standalone CLI

```bash
# Create sandbox
python3 sandbox_runner.py create --image python:3.12

# Exec command
python3 sandbox_runner.py exec --sandbox-id sb-xxx --command "echo hello"

# Upload file
python3 sandbox_runner.py upload --sandbox-id sb-xxx --local-path ./data.csv --remote-path /home/user/data.csv

# Download file
python3 sandbox_runner.py download --sandbox-id sb-xxx --remote-path /home/user/output.png --local-path ./output.png

# Download all PNGs from a directory
python3 sandbox_runner.py download_dir --sandbox-id sb-xxx --remote-dir /home/user/output --local-dir ./charts --pattern "*.png"

# Destroy
python3 sandbox_runner.py destroy --sandbox-id sb-xxx
```

## Output Format

All CLI subcommands output a single JSON line on stdout:

```json
{"status": "ok", "sandbox_id": "sb-xxx", "exit_code": 0, "stdout": "hello\n", "stderr": ""}
```

The TypeScript plugin layer parses this JSON and returns it to the agent as the tool result.

## Files

| File | Description |
|---|---|
| `agent-sandbox-infra.ts` | OpenCode plugin — registers 7 custom tools |
| `sandbox_runner.py` | Python CLI with subcommands for each sandbox primitive |
