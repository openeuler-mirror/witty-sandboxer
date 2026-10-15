"""rules.yaml 加载与冲突处理。"""

from pathlib import Path

import sandbox_policy.rules as rules


def test_packaged_rules_yaml_sits_beside_the_module():
    path = Path(rules.__file__).with_name("rules.yaml")
    assert path.is_file()
    assert isinstance(rules._load_user_document(path), dict)


def test_missing_file_is_empty(tmp_path):
    assert rules._load_user_document(tmp_path / "rules.yaml") == {}


def test_invalid_yaml_is_ignored(tmp_path, capsys):
    path = tmp_path / "rules.yaml"
    path.write_text(":\n  - [", encoding="utf-8")
    assert rules._load_user_document(path) == {}
    assert "解析失败" in capsys.readouterr().err


def test_non_mapping_root_is_ignored(tmp_path, capsys):
    path = tmp_path / "rules.yaml"
    path.write_text("- just-a-list\n", encoding="utf-8")
    assert rules._load_user_document(path) == {}
    assert "mapping" in capsys.readouterr().err


def test_builtin_name_conflict_is_dropped(restore_rules, capsys):
    before = len(restore_rules.DESTRUCTIVE_RULES)
    restore_rules._apply_user_rules(
        {"destructive": [{"command": "rm", "reason": "试图覆盖内置"}]}
    )
    assert len(restore_rules.DESTRUCTIVE_RULES) == before
    assert "冲突" in capsys.readouterr().err


def test_unknown_section_is_ignored(restore_rules, capsys):
    restore_rules._apply_user_rules({"not_a_section": ["x"]})
    assert "未知字段" in capsys.readouterr().err


def test_permission_without_grant_is_dropped(restore_rules, capsys):
    before = len(restore_rules.PERMISSION_RULES)
    restore_rules._apply_user_rules(
        {"permissions": [{"command": "gh", "grant": {}}]}
    )
    assert len(restore_rules.PERMISSION_RULES) == before
    assert "没有可生效的权限" in capsys.readouterr().err
