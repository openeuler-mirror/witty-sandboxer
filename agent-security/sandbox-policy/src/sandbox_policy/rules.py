"""
sandbox-policy 安全规则配置。

用户扩展写在同目录 rules.yaml。command、command_prefix、pattern 或安全命令名
只要已在本文件出现，yaml 里的同名条目会被忽略，以内置定义为准。
"""

import sys
from pathlib import Path
from typing import Any, Optional

import yaml

# ============================================================================
# 毁灭性命令 - 直接 DENY
# ============================================================================
DESTRUCTIVE_RULES = [
    {"command": "fdisk", "reason": "磁盘分区"},
    {"command": "parted", "reason": "磁盘分区"},
    {"command": "gdisk", "reason": "磁盘分区"},
    {"command": "cfdisk", "reason": "磁盘分区"},
    {"command_prefix": "mkfs", "reason": "磁盘格式化"},
    {"command": "shutdown", "reason": "关机"},
    {"command": "reboot", "reason": "重启"},
    {"command": "poweroff", "reason": "关机"},
    {"command": "halt", "reason": "停机"},
    {"command": "init", "reason": "系统初始化"},
    {
        "command": "rm",
        "flags": ["-f", "-rf", "-fr"],
        "target_in": [
            "/",
            "/*",
            "/etc",
            "/usr",
            "/var",
            "/boot",
            "/bin",
            "/sbin",
            "/lib",
            "/lib64",
            "/root",
            "/home",
        ],
        "reason": "删除系统关键目录",
    },
    {
        "command": "dd",
        "args_contain": ["of=/dev/sd", "of=/dev/nvme", "of=/dev/hd", "of=/dev/vd"],
        "reason": "写入块设备",
    },
    {
        "command": "kill",
        "args_contain": ["-9 -1", "-KILL -1"],
        "reason": "杀死所有进程",
    },
    {"command": "kill", "target_in": ["1"], "reason": "杀死 init 进程"},
    {"pattern": ":(){ :|:& };:", "reason": "Fork 炸弹"},
    {"pattern": ":(){ :|:", "reason": "Fork 炸弹变种"},
]

# ============================================================================
# 危险命令 - 沙箱执行（cwd + /tmp 可写，禁止网络）
# ============================================================================
DANGEROUS_RULES = [
    {
        "command": "rm",
        "first_arg_in": ["-f", "-rf", "-fr", "-r"],
        "reason": "删除文件或目录",
    },
    {"command": "chmod", "reason": "修改文件权限"},
    {"command": "chown", "reason": "修改文件归属"},
    {
        "command": "find",
        "args_contain": ["-delete", "-exec", "-execdir", "-ok", "-okdir"],
        "reason": "find 执行删除或外部命令",
    },
    {"command": "sed", "flags": ["-i"], "reason": "sed 原地修改文件"},
    {"command": "git", "subcommands": ["clean"], "reason": "git clean 删除未跟踪文件"},
    {"command": "sudo", "reason": "提权执行"},
]


# ============================================================================
# 安全命令 - 只读模板（禁网）
# ============================================================================
SAFE_COMMANDS = frozenset(
    [
        "cat",
        "cd",
        "cut",
        "echo",
        "expr",
        "false",
        "grep",
        "head",
        "id",
        "ls",
        "nl",
        "paste",
        "pwd",
        "rev",
        "seq",
        "stat",
        "tail",
        "tr",
        "true",
        "uname",
        "uniq",
        "wc",
        "which",
        "whoami",
    ]
)

# 仅 Linux 的安全命令
SAFE_COMMANDS_LINUX = frozenset(["numfmt", "tac"])

# 条件安全命令
SAFE_CONDITIONAL = [
    {
        "command": "base64",
        "deny_args": ["-o", "--output", "--output="],
        "deny_arg_prefixes": ["-o"],  # -ob64.txt 形式
        "reason": "Base64 编解码（无输出重定向）",
    },
    {
        "command": "find",
        "deny_args": [
            "-exec",
            "-execdir",
            "-ok",
            "-okdir",
            "-delete",
            "-fls",
            "-fprint",
            "-fprint0",
            "-fprintf",
        ],
        "reason": "文件查找（不含执行/删除参数）",
    },
    {
        "command": "rg",
        "deny_args": [
            "--pre",
            "--pre=",
            "--hostname-bin",
            "--hostname-bin=",
            "--search-zip",
            "-z",
        ],
        "reason": "Ripgrep（不含外部命令调用）",
    },
    # git 和 sed 有 special_handler，在代码中单独处理
]

# Shell 不安全操作符（用于 bash -c 解析）
SHELL_UNSAFE_OPERATORS = frozenset([">", "<", ">>", "(", ")", "`", "$("])
SHELL_SAFE_OPERATORS = frozenset(["&&", "||", ";", "|"])

# ============================================================================
# 额外权限配置 - default 命令的网络/路径权限
# ============================================================================
PERMISSION_RULES = [
    # 网络 + 额外写路径（更具体的规则放前面，优先匹配）
    {
        "command": "npm",
        "subcommands": ["install"],
        "args_contain": ["-g", "--global"],
        "grant": {
            "network": True,
            "write_paths": ["/usr/local/lib/node_modules", "/usr/local/bin"],
        },
    },
    {
        "command": "pip",
        "subcommands": ["install"],
        "args_contain": ["--system"],
        "grant": {
            "network": True,
            "write_paths": ["/usr/lib/python3", "/usr/local/lib/python3"],
        },
    },
    {
        "command": "docker",
        "subcommands": ["build", "run", "compose"],
        "grant": {"network": True, "write_paths": ["/var/lib/docker"]},
    },
    # 网络权限（通用规则）
    {
        "command": "cargo",
        "subcommands": ["build", "run", "test", "fetch", "update", "install", "add"],
        "grant": {"network": True},
    },
    {
        "command": "npm",
        "subcommands": ["install", "ci", "update", "audit"],
        "grant": {"network": True},
    },
    {
        "command": "yarn",
        "subcommands": ["install", "add", "upgrade"],
        "grant": {"network": True},
    },
    {
        "command": "pnpm",
        "subcommands": ["install", "add", "update"],
        "grant": {"network": True},
    },
    {
        "command": "pip",
        "subcommands": ["install", "download"],
        "grant": {"network": True},
    },
    {
        "command": "pip3",
        "subcommands": ["install", "download"],
        "grant": {"network": True},
    },
    {
        "command": "go",
        "subcommands": ["get", "mod", "install"],
        "grant": {"network": True},
    },
    {
        "command": "gem",
        "subcommands": ["install", "update"],
        "grant": {"network": True},
    },
    {
        "command": "bundle",
        "subcommands": ["install", "update"],
        "grant": {"network": True},
    },
    {"command": "curl", "grant": {"network": True}},
    {"command": "wget", "grant": {"network": True}},
    {
        "command": "git",
        "subcommands": ["clone", "fetch", "pull", "push"],
        "grant": {"network": True},
    },
]


# ============================================================================
# 用户扩展 - 同目录 rules.yaml。冲突时保留上面的内置定义。
# ============================================================================

_USER_RULES_PATH = Path(__file__).with_name("rules.yaml")

# 内置规则占用的名字。yaml 再声明同一名字时丢弃 yaml 条目。
_RESERVED_NAMES: set[str] = set()
_RESERVED_PREFIXES: set[str] = set()
_RESERVED_PATTERNS: set[str] = set()
_RESERVED_OPERATORS: set[str] = set()

_RULE_FIELDS = {
    "command",
    "command_prefix",
    "pattern",
    "os",
    "recursive",
    "first_arg_in",
    "flags",
    "subcommands",
    "target_in",
    "args_contain",
    "deny_args",
    "deny_arg_prefixes",
    "reason",
    "grant",
}
_LIST_FIELDS = {
    "first_arg_in",
    "flags",
    "subcommands",
    "target_in",
    "args_contain",
    "deny_args",
    "deny_arg_prefixes",
}
_CLASSIFY_SECTIONS = (
    ("destructive", DESTRUCTIVE_RULES, "any"),
    ("dangerous", DANGEROUS_RULES, "any"),
    ("safe_conditional", SAFE_CONDITIONAL, "command"),
)


def _warn(message: str) -> None:
    print(f"rules.yaml: {message}", file=sys.stderr)


def _reserve_builtin() -> None:
    """把内置规则的主键登记下来，供冲突判断使用。"""
    builtin_rules = (
        DESTRUCTIVE_RULES + DANGEROUS_RULES + SAFE_CONDITIONAL + PERMISSION_RULES
    )
    for rule in builtin_rules:
        if "command" in rule:
            _RESERVED_NAMES.add(rule["command"])
        if "command_prefix" in rule:
            _RESERVED_PREFIXES.add(rule["command_prefix"])
        if "pattern" in rule:
            _RESERVED_PATTERNS.add(rule["pattern"])
    _RESERVED_NAMES.update(SAFE_COMMANDS)
    _RESERVED_NAMES.update(SAFE_COMMANDS_LINUX)
    _RESERVED_OPERATORS.update(SHELL_UNSAFE_OPERATORS)
    _RESERVED_OPERATORS.update(SHELL_SAFE_OPERATORS)


def _name_conflicts(name: str) -> bool:
    """命令名与内置 command / command_prefix 重叠则视为冲突。"""
    if name in _RESERVED_NAMES or name in _RESERVED_PREFIXES:
        return True
    return any(name.startswith(prefix) for prefix in _RESERVED_PREFIXES)


def _prefix_conflicts(prefix: str) -> bool:
    """前缀会命中已有命令或前缀时视为冲突，避免放宽内置分类。"""
    if _name_conflicts(prefix):
        return True
    if any(
        prefix.startswith(owned) or owned.startswith(prefix) for owned in _RESERVED_PREFIXES
    ):
        return True
    return any(command.startswith(prefix) for command in _RESERVED_NAMES)


def _load_user_document(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with path.open(encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        _warn(f"解析失败，已忽略整个文件 ({exc})")
        return {}
    except OSError as exc:
        _warn(f"读取失败，已忽略 ({exc})")
        return {}
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        _warn("根节点必须是 mapping，已忽略整个文件")
        return {}
    return loaded


def _section_items(document: dict[str, Any], key: str) -> list[Any]:
    if key not in document:
        return []
    value = document[key]
    if value is None:
        return []
    if not isinstance(value, list):
        _warn(f"{key} 必须是列表，已忽略")
        return []
    return value


def _string_list(value: Any, where: str) -> Optional[list[str]]:
    if not isinstance(value, list) or not value:
        _warn(f"{where} 必须是非空字符串列表，已忽略该规则")
        return None
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            _warn(f"{where} 含非法条目 {item!r}，已忽略该规则")
            return None
        cleaned.append(item.strip())
    return cleaned


def _clean_grant(value: Any, where: str) -> Optional[dict[str, Any]]:
    if not isinstance(value, dict):
        _warn(f"{where} 必须是 mapping，已忽略该规则")
        return None
    unknown = set(value) - {"network", "write_paths"}
    if unknown:
        _warn(f"{where} 含未知字段 {sorted(unknown)}，已忽略这些字段")
    grant: dict[str, Any] = {}
    if "network" in value:
        if value["network"] is not True:
            _warn(f"{where}.network 只能为 true，已忽略该规则")
            return None
        grant["network"] = True
    if "write_paths" in value:
        paths = _string_list(value["write_paths"], f"{where}.write_paths")
        if paths is None:
            return None
        grant["write_paths"] = paths
    if not grant:
        _warn(f"{where} 没有可生效的权限，已忽略该规则")
        return None
    return grant


def _clean_rule(raw: Any, section: str, index: int, primary: str) -> Optional[dict[str, Any]]:
    """校验一条用户规则。冲突或格式不对时返回 None。"""
    where = f"{section}[{index}]"
    if not isinstance(raw, dict):
        _warn(f"{where} 必须是 mapping，已忽略")
        return None

    unknown = set(raw) - _RULE_FIELDS
    if unknown:
        _warn(f"{where} 含未知字段 {sorted(unknown)}，已忽略这些字段")

    present = [key for key in ("pattern", "command_prefix", "command") if key in raw]
    if primary == "command":
        if present != ["command"]:
            _warn(f"{where} 只能使用 command 作为主键，已忽略")
            return None
    elif len(present) != 1:
        _warn(f"{where} 必须且只能有一个主键 command / command_prefix / pattern，已忽略")
        return None

    kind = present[0]
    identity = raw[kind]
    if not isinstance(identity, str) or not identity.strip():
        _warn(f"{where}.{kind} 必须是非空字符串，已忽略")
        return None
    identity = identity.strip()

    if kind == "pattern":
        if identity in _RESERVED_PATTERNS:
            _warn(f"忽略 {where}：pattern 与内置规则冲突")
            return None
    elif kind == "command_prefix":
        if _prefix_conflicts(identity):
            _warn(f"忽略 {where}：command_prefix {identity!r} 与内置规则冲突")
            return None
    elif _name_conflicts(identity):
        _warn(f"忽略 {where}：command {identity!r} 与内置规则冲突")
        return None

    cleaned: dict[str, Any] = {kind: identity}
    if section != "permissions":
        reason = raw.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            _warn(f"{where} 缺少 reason，已忽略")
            return None
        cleaned["reason"] = reason.strip()

    if "os" in raw:
        if not isinstance(raw["os"], str) or not raw["os"].strip():
            _warn(f"{where}.os 必须是字符串，已忽略该规则")
            return None
        cleaned["os"] = raw["os"].strip()
    if "recursive" in raw:
        if not isinstance(raw["recursive"], bool):
            _warn(f"{where}.recursive 必须是布尔值，已忽略该规则")
            return None
        cleaned["recursive"] = raw["recursive"]

    for key in _LIST_FIELDS:
        if key not in raw:
            continue
        values = _string_list(raw[key], f"{where}.{key}")
        if values is None:
            return None
        cleaned[key] = values

    if section == "permissions":
        grant = _clean_grant(raw.get("grant"), f"{where}.grant")
        if grant is None:
            return None
        cleaned["grant"] = grant

    if kind == "pattern":
        _RESERVED_PATTERNS.add(identity)
    elif kind == "command_prefix":
        _RESERVED_PREFIXES.add(identity)
    else:
        _RESERVED_NAMES.add(identity)
    return cleaned


def _extend_names(document: dict[str, Any], key: str, target: set[str]) -> None:
    for index, raw in enumerate(_section_items(document, key)):
        where = f"{key}[{index}]"
        if not isinstance(raw, str) or not raw.strip():
            _warn(f"{where} 必须是非空字符串，已忽略")
            continue
        name = raw.strip()
        if _name_conflicts(name):
            _warn(f"忽略 {where}：{name!r} 与内置规则冲突")
            continue
        target.add(name)
        _RESERVED_NAMES.add(name)


def _extend_operators(document: dict[str, Any], key: str, target: set[str]) -> None:
    for index, raw in enumerate(_section_items(document, key)):
        where = f"{key}[{index}]"
        if not isinstance(raw, str) or not raw.strip():
            _warn(f"{where} 必须是非空字符串，已忽略")
            continue
        operator = raw.strip()
        if operator in _RESERVED_OPERATORS:
            _warn(f"忽略 {where}：{operator!r} 与内置规则冲突")
            continue
        target.add(operator)
        _RESERVED_OPERATORS.add(operator)


def _apply_user_rules(document: dict[str, Any]) -> None:
    """把用户规则追加到内置表。调用前必须已经登记内置主键。"""
    global SAFE_COMMANDS, SAFE_COMMANDS_LINUX, SHELL_UNSAFE_OPERATORS, SHELL_SAFE_OPERATORS

    known = {name for name, _, _ in _CLASSIFY_SECTIONS}
    known.update(
        {
            "safe_commands",
            "safe_commands_linux",
            "permissions",
            "shell_unsafe_operators",
            "shell_safe_operators",
        }
    )
    for key in document:
        if key not in known:
            _warn(f"未知字段 {key!r}，已忽略")

    for section, table, primary in _CLASSIFY_SECTIONS:
        for index, raw in enumerate(_section_items(document, section)):
            cleaned = _clean_rule(raw, section, index, primary)
            if cleaned is not None:
                table.append(cleaned)

    extra_safe: set[str] = set()
    extra_linux: set[str] = set()
    extra_unsafe: set[str] = set()
    extra_safe_ops: set[str] = set()
    _extend_names(document, "safe_commands", extra_safe)
    _extend_names(document, "safe_commands_linux", extra_linux)
    # 权限晚于安全名单登记，同一命令不能同时变成 safe 又自动补权。
    for index, raw in enumerate(_section_items(document, "permissions")):
        cleaned = _clean_rule(raw, "permissions", index, "command")
        if cleaned is not None:
            PERMISSION_RULES.append(cleaned)
    _extend_operators(document, "shell_unsafe_operators", extra_unsafe)
    _extend_operators(document, "shell_safe_operators", extra_safe_ops)
    if extra_safe:
        SAFE_COMMANDS = SAFE_COMMANDS | frozenset(extra_safe)
    if extra_linux:
        SAFE_COMMANDS_LINUX = SAFE_COMMANDS_LINUX | frozenset(extra_linux)
    if extra_unsafe:
        SHELL_UNSAFE_OPERATORS = SHELL_UNSAFE_OPERATORS | frozenset(extra_unsafe)
    if extra_safe_ops:
        SHELL_SAFE_OPERATORS = SHELL_SAFE_OPERATORS | frozenset(extra_safe_ops)


_reserve_builtin()
_apply_user_rules(_load_user_document(_USER_RULES_PATH))
