"""linux-sandbox 策略生成。"""

import json

from sandbox_policy.policy import generate_sandbox_policy


def _filesystem(result: dict) -> dict:
    argv = result["sandbox_argv"]
    return json.loads(argv[argv.index("--file-system-sandbox-policy") + 1])


def _network(result: dict) -> str:
    argv = result["sandbox_argv"]
    return json.loads(argv[argv.index("--network-sandbox-policy") + 1])


def test_destructive_is_denied():
    result = generate_sandbox_policy("rm -rf /", "/workspace")
    assert result["decision"] == "deny"
    assert result["classification"] == "destructive"
    assert "sandbox_argv" not in result


def test_safe_is_read_only_without_network():
    result = generate_sandbox_policy("ls", "/workspace")
    assert result["decision"] == "sandbox"
    assert result["sandbox_mode"] == "read-only"
    assert result["sandbox_argv"][0] == "linux-sandbox"
    assert result["sandbox_argv"][1:3] == ["--sandbox-policy-cwd", "/workspace"]
    assert _filesystem(result) == {
        "kind": "restricted",
        "entries": [
            {
                "path": {"type": "special", "value": {"kind": "root"}},
                "access": "read",
            }
        ],
    }
    assert _network(result) == "restricted"
    assert "网络: 禁止" in result["sandbox_summary"]
    assert result["sandbox_argv"][-2:] == ["--", "ls"]


def test_dangerous_can_write_workspace_and_tmp():
    result = generate_sandbox_policy("chmod 644 file", "/workspace")
    assert result["sandbox_mode"] == "workspace-write"
    entries = _filesystem(result)["entries"]
    assert {
        "path": {"type": "special", "value": {"kind": "current_working_directory"}},
        "access": "write",
    } in entries
    assert {
        "path": {"type": "special", "value": {"kind": "slash_tmp"}},
        "access": "write",
    } in entries
    assert _network(result) == "restricted"


def test_default_command_can_open_network_and_extra_paths():
    curl = generate_sandbox_policy("curl https://example.com", "/workspace")
    assert curl["sandbox_mode"] == "workspace-write"
    assert _network(curl) == "enabled"
    assert "网络: 开启" in curl["sandbox_summary"]

    npm = generate_sandbox_policy("npm install -g leftpad", "/workspace")
    assert "/usr/local/bin" in npm["sandbox_summary"]
    write_paths = [
        entry["path"]["path"]
        for entry in _filesystem(npm)["entries"]
        if entry["path"]["type"] == "path" and entry["access"] == "write"
    ]
    assert "/usr/local/lib/node_modules" in write_paths
    assert "/usr/local/bin" in write_paths


def test_unbalanced_quotes_fall_back_to_whitespace_split():
    result = generate_sandbox_policy("echo 'unterminated", "/workspace")
    assert result["sandbox_argv"][-2:] == ["echo", "'unterminated"]
