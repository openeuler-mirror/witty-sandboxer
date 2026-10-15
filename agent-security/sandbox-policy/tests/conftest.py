"""测试夹具。"""

import pytest

import sandbox_policy.rules as rules


@pytest.fixture
def restore_rules():
    """跑完用户规则用例后，把进程内规则表恢复成导入时的样子。"""
    snap = {
        "safe": rules.SAFE_COMMANDS,
        "linux": rules.SAFE_COMMANDS_LINUX,
        "unsafe": rules.SHELL_UNSAFE_OPERATORS,
        "safe_ops": rules.SHELL_SAFE_OPERATORS,
        "destructive": list(rules.DESTRUCTIVE_RULES),
        "dangerous": list(rules.DANGEROUS_RULES),
        "conditional": list(rules.SAFE_CONDITIONAL),
        "permissions": list(rules.PERMISSION_RULES),
        "names": set(rules._RESERVED_NAMES),
        "prefixes": set(rules._RESERVED_PREFIXES),
        "patterns": set(rules._RESERVED_PATTERNS),
        "operators": set(rules._RESERVED_OPERATORS),
    }
    yield rules
    rules.SAFE_COMMANDS = snap["safe"]
    rules.SAFE_COMMANDS_LINUX = snap["linux"]
    rules.SHELL_UNSAFE_OPERATORS = snap["unsafe"]
    rules.SHELL_SAFE_OPERATORS = snap["safe_ops"]
    rules.DESTRUCTIVE_RULES[:] = snap["destructive"]
    rules.DANGEROUS_RULES[:] = snap["dangerous"]
    rules.SAFE_CONDITIONAL[:] = snap["conditional"]
    rules.PERMISSION_RULES[:] = snap["permissions"]
    rules._RESERVED_NAMES.clear()
    rules._RESERVED_NAMES.update(snap["names"])
    rules._RESERVED_PREFIXES.clear()
    rules._RESERVED_PREFIXES.update(snap["prefixes"])
    rules._RESERVED_PATTERNS.clear()
    rules._RESERVED_PATTERNS.update(snap["patterns"])
    rules._RESERVED_OPERATORS.clear()
    rules._RESERVED_OPERATORS.update(snap["operators"])
