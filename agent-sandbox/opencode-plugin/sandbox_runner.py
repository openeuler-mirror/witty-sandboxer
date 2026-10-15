#!/usr/bin/env python3
"""
OpenSandbox Agent Infra Runner
===============================
A general-purpose CLI that provides sandbox lifecycle primitives for
AI agents.  Each subcommand is an atomic operation that the agent can
compose into arbitrary workflows.

Subcommands:
    create    [--image IMG] [--cpu N] [--memory SIZE] [--timeout SEC]
              Create a sandbox, print the sandbox ID.

    exec      --sandbox-id ID --command CMD [--timeout SEC] [--workdir DIR]
              Execute a shell command in an existing sandbox.

    upload    --sandbox-id ID --local-path PATH --remote-path PATH
              Upload a local file into the sandbox.

    upload_text --sandbox-id ID --remote-path PATH --text TEXT
              Write text content directly to a remote path in the sandbox.

    download  --sandbox-id ID --remote-path PATH --local-path PATH
              Download a file from the sandbox to the local machine.

    download_dir --sandbox-id ID --remote-dir DIR --local-dir DIR [--pattern GLOB]
              Download all files matching a glob from a remote directory.

    destroy   --sandbox-id ID
              Destroy a sandbox.

Output: Every subcommand prints a JSON line on stdout so the caller
(TypeScript tool layer) can parse results programmatically.

Usage:
    python3 sandbox_runner.py create --image opensandbox/code-interpreter:v1.1.0
    python3 sandbox_runner.py exec --sandbox-id sb-xxx --command "echo hi"
    python3 sandbox_runner.py upload --sandbox-id sb-xxx --local-path ./f.csv --remote-path /home/user/data.csv
    python3 sandbox_runner.py download --sandbox-id sb-xxx --remote-path /home/user/out.png --local-path ./out.png
    python3 sandbox_runner.py destroy --sandbox-id sb-xxx
"""

import sys
import os
import json
import asyncio
import argparse
from datetime import timedelta

from opensandbox import Sandbox
from opensandbox.models.execd import RunCommandOpts
from opensandbox.models.filesystem import DirectoryListEntry


# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────

def _emit(data: dict) -> None:
    """Print a single JSON line so the TS layer can parse."""
    print(json.dumps(data, ensure_ascii=False, default=str))


async def _connect(sandbox_id: str) -> Sandbox:
    """Reconnect to an existing sandbox by ID."""
    return await Sandbox.connect(sandbox_id, skip_health_check=True)


# ──────────────────────────────────────────────
#  Subcommand: create
# ──────────────────────────────────────────────

async def cmd_create(args: argparse.Namespace) -> None:
    resource = {}
    if args.cpu:
        resource["cpu"] = args.cpu
    if args.memory:
        resource["memory"] = args.memory

    sandbox = await Sandbox.create(
        args.image,
        timeout=timedelta(seconds=args.timeout) if args.timeout else timedelta(minutes=15),
        resource=resource if resource else None,
    )
    _emit({
        "status": "ok",
        "sandbox_id": sandbox.id,
        "image": args.image,
        "message": f"Sandbox {sandbox.id} created with image {args.image}",
    })
    await sandbox.close()


# ──────────────────────────────────────────────
#  Subcommand: exec
# ──────────────────────────────────────────────

async def cmd_exec(args: argparse.Namespace) -> None:
    sandbox = await _connect(args.sandbox_id)
    try:
        opts = RunCommandOpts(
            timeout=timedelta(seconds=args.timeout) if args.timeout else timedelta(seconds=120),
            working_directory=args.workdir,
        )
        result = await sandbox.commands.run(args.command, opts=opts)

        stdout_parts = [m.text for m in result.logs.stdout]
        stderr_parts = [m.text for m in result.logs.stderr]
        stdout_text = "".join(stdout_parts)
        stderr_text = "".join(stderr_parts)
        exit_code = result.exit_code if result.exit_code is not None else 0

        _emit({
            "status": "ok" if exit_code == 0 else "error",
            "sandbox_id": args.sandbox_id,
            "exit_code": exit_code,
            "stdout": stdout_text,
            "stderr": stderr_text,
        })
    finally:
        await sandbox.close()


# ──────────────────────────────────────────────
#  Subcommand: upload
# ──────────────────────────────────────────────

async def cmd_upload(args: argparse.Namespace) -> None:
    sandbox = await _connect(args.sandbox_id)
    try:
        local = os.path.abspath(args.local_path)
        if not os.path.isfile(local):
            _emit({"status": "error", "error": f"Local file not found: {local}"})
            return
        with open(local, "rb") as f:
            data = f.read()
        await sandbox.files.write_file(args.remote_path, data)
        size = len(data)
        _emit({
            "status": "ok",
            "sandbox_id": args.sandbox_id,
            "local_path": local,
            "remote_path": args.remote_path,
            "bytes": size,
            "message": f"Uploaded {size} bytes to {args.remote_path}",
        })
    finally:
        await sandbox.close()


# ──────────────────────────────────────────────
#  Subcommand: upload_text
# ──────────────────────────────────────────────

async def cmd_upload_text(args: argparse.Namespace) -> None:
    sandbox = await _connect(args.sandbox_id)
    try:
        await sandbox.files.write_file(args.remote_path, args.text)
        size = len(args.text.encode("utf-8"))
        _emit({
            "status": "ok",
            "sandbox_id": args.sandbox_id,
            "remote_path": args.remote_path,
            "bytes": size,
            "message": f"Wrote {size} bytes to {args.remote_path}",
        })
    finally:
        await sandbox.close()


# ──────────────────────────────────────────────
#  Subcommand: download
# ──────────────────────────────────────────────

async def cmd_download(args: argparse.Namespace) -> None:
    sandbox = await _connect(args.sandbox_id)
    try:
        data = await sandbox.files.read_bytes(args.remote_path)
        local = os.path.abspath(args.local_path)
        os.makedirs(os.path.dirname(local) or ".", exist_ok=True)
        with open(local, "wb") as f:
            f.write(data)
        _emit({
            "status": "ok",
            "sandbox_id": args.sandbox_id,
            "remote_path": args.remote_path,
            "local_path": local,
            "bytes": len(data),
            "message": f"Downloaded {len(data)} bytes to {local}",
        })
    finally:
        await sandbox.close()


# ──────────────────────────────────────────────
#  Subcommand: download_dir
# ──────────────────────────────────────────────

async def cmd_download_dir(args: argparse.Namespace) -> None:
    import fnmatch
    sandbox = await _connect(args.sandbox_id)
    try:
        listing = await sandbox.files.list_directory(DirectoryListEntry(path=args.remote_dir, depth=1))
        local_dir = os.path.abspath(args.local_dir)
        os.makedirs(local_dir, exist_ok=True)
        downloaded = []
        for entry in listing:
            entry_name = os.path.basename(entry.path)
            if entry.entry_type and entry.entry_type != "file":
                continue
            if args.pattern and not fnmatch.fnmatch(entry_name, args.pattern):
                continue
            data = await sandbox.files.read_bytes(entry.path)
            local_path = os.path.join(local_dir, entry_name)
            with open(local_path, "wb") as f:
                f.write(data)
            downloaded.append({"name": entry_name, "local_path": local_path, "bytes": len(data)})
        _emit({
            "status": "ok",
            "sandbox_id": args.sandbox_id,
            "remote_dir": args.remote_dir,
            "local_dir": local_dir,
            "files": downloaded,
            "count": len(downloaded),
        })
    finally:
        await sandbox.close()


# ──────────────────────────────────────────────
#  Subcommand: destroy
# ──────────────────────────────────────────────

async def cmd_destroy(args: argparse.Namespace) -> None:
    sandbox = await _connect(args.sandbox_id)
    try:
        await sandbox.destroy()
        _emit({
            "status": "ok",
            "sandbox_id": args.sandbox_id,
            "message": f"Sandbox {args.sandbox_id} destroyed",
        })
    except Exception as e:
        _emit({"status": "error", "sandbox_id": args.sandbox_id, "error": str(e)})


# ──────────────────────────────────────────────
#  CLI entry point
# ──────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="OpenSandbox Agent Infra Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="command", required=True)

    # create
    sp = sub.add_parser("create", help="Create a new sandbox")
    sp.add_argument("--image", default="opensandbox/code-interpreter:v1.1.0")
    sp.add_argument("--cpu", default=None)
    sp.add_argument("--memory", default=None)
    sp.add_argument("--timeout", type=int, default=None, help="Sandbox lifetime in seconds")
    sp.set_defaults(func=cmd_create)

    # exec
    sp = sub.add_parser("exec", help="Execute a command in a sandbox")
    sp.add_argument("--sandbox-id", required=True)
    sp.add_argument("--command", required=True)
    sp.add_argument("--timeout", type=int, default=None, help="Command timeout in seconds")
    sp.add_argument("--workdir", default=None)
    sp.set_defaults(func=cmd_exec)

    # upload
    sp = sub.add_parser("upload", help="Upload a local file to the sandbox")
    sp.add_argument("--sandbox-id", required=True)
    sp.add_argument("--local-path", required=True)
    sp.add_argument("--remote-path", required=True)
    sp.set_defaults(func=cmd_upload)

    # upload_text
    sp = sub.add_parser("upload_text", help="Write text to a remote path in the sandbox")
    sp.add_argument("--sandbox-id", required=True)
    sp.add_argument("--remote-path", required=True)
    sp.add_argument("--text", required=True)
    sp.set_defaults(func=cmd_upload_text)

    # download
    sp = sub.add_parser("download", help="Download a file from the sandbox")
    sp.add_argument("--sandbox-id", required=True)
    sp.add_argument("--remote-path", required=True)
    sp.add_argument("--local-path", required=True)
    sp.set_defaults(func=cmd_download)

    # download_dir
    sp = sub.add_parser("download_dir", help="Download multiple files from a remote directory")
    sp.add_argument("--sandbox-id", required=True)
    sp.add_argument("--remote-dir", required=True)
    sp.add_argument("--local-dir", required=True)
    sp.add_argument("--pattern", default=None, help="Glob pattern (e.g. *.png)")
    sp.set_defaults(func=cmd_download_dir)

    # destroy
    sp = sub.add_parser("destroy", help="Destroy a sandbox")
    sp.add_argument("--sandbox-id", required=True)
    sp.set_defaults(func=cmd_destroy)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
