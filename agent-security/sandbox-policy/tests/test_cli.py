"""sandbox-policy 命令行。"""

import json

import pytest

from sandbox_policy.cli import main


def test_classify_text(capsys):
    main(["classify", "ls"])
    out = capsys.readouterr().out
    assert "命令: ls" in out
    assert "分类: safe" in out


def test_classify_json(capsys):
    main(["classify", "--json", "rm -rf /"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "destructive"


def test_classify_text_prints_permissions(capsys):
    main(["classify", "curl https://example.com"])
    assert "额外权限:" in capsys.readouterr().out


def test_policy_prints_json(capsys):
    main(["policy", "--cwd", "/workspace", "git status"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "sandbox"
    assert payload["sandbox_argv"][0] == "linux-sandbox"
    assert "/workspace" in payload["sandbox_argv"]


def test_policy_requires_cwd():
    with pytest.raises(SystemExit):
        main(["policy", "ls"])


def test_missing_verb_exits():
    with pytest.raises(SystemExit):
        main([])
