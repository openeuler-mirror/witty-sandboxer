"""四层命令分类。"""

from sandbox_policy.classify import CommandClassifier


def test_destructive_commands():
    cases = {
        "rm -rf /": "删除系统关键目录",
        "shutdown": "关机",
        "mkfs.ext4 /dev/sdb": "磁盘格式化",
        ":(){ :|:& };:": "Fork 炸弹",
        'bash -c "rm -rf /"': "删除系统关键目录",
    }
    classifier = CommandClassifier()
    for command, reason in cases.items():
        result = classifier.classify(command)
        assert result["decision"] == "destructive", command
        assert reason in result["reason"]
        assert result["additional_permissions"] is None


def test_dangerous_commands():
    cases = [
        "rm -rf /tmp/build",
        "chmod 644 file",
        "sudo ls",
        "git clean -fd",
        "sed -i 's/a/b/' file",
    ]
    classifier = CommandClassifier()
    for command in cases:
        result = classifier.classify(command)
        assert result["decision"] == "dangerous", command
        assert result["additional_permissions"] is None


def test_safe_commands():
    cases = ["ls", "git status", "sed 's/a/b/' file", 'bash -c "ls && pwd"']
    classifier = CommandClassifier()
    for command in cases:
        result = classifier.classify(command)
        assert result["decision"] == "safe", command
        assert result["additional_permissions"] is None


def test_default_without_extra_permissions():
    result = CommandClassifier().classify("python3 app.py")
    assert result["decision"] == "default"
    assert result["additional_permissions"] is None


def test_default_grants_network_and_write_paths():
    curl = CommandClassifier().classify("curl https://example.com")
    assert curl["decision"] == "default"
    assert curl["additional_permissions"] == {"network": {"enabled": True}}

    npm = CommandClassifier().classify("npm install -g leftpad")
    assert npm["additional_permissions"]["network"] == {"enabled": True}
    assert "/usr/local/bin" in npm["additional_permissions"]["file_system"]["write"]


def test_chain_takes_the_strictest_decision():
    classifier = CommandClassifier()
    assert classifier.classify("ls && pwd")["decision"] == "safe"
    assert classifier.classify("ls && rm -rf /")["decision"] == "destructive"

    mixed = classifier.classify("ls && curl https://example.com")
    assert mixed["decision"] == "default"
    assert mixed["additional_permissions"] is None


def test_empty_command_is_default():
    result = CommandClassifier().classify("")
    assert result["decision"] == "default"
    assert result["command"] == ""


def test_user_safe_command(restore_rules):
    restore_rules._apply_user_rules({"safe_commands": ["jq"]})
    result = CommandClassifier().classify("jq .")
    assert result["decision"] == "safe"


def test_user_destructive_command(restore_rules):
    restore_rules._apply_user_rules(
        {"destructive": [{"command": "mkswap", "reason": "创建交换分区"}]}
    )
    result = CommandClassifier().classify("mkswap /dev/sdb")
    assert result["decision"] == "destructive"
    assert result["reason"] == "创建交换分区"


def test_user_permission_command(restore_rules):
    restore_rules._apply_user_rules(
        {
            "permissions": [
                {
                    "command": "gh",
                    "subcommands": ["api"],
                    "grant": {"network": True},
                }
            ]
        }
    )
    result = CommandClassifier().classify("gh api repos")
    assert result["decision"] == "default"
    assert result["additional_permissions"] == {"network": {"enabled": True}}
