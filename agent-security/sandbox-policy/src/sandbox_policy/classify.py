"""
命令安全分类器 - 四层分类 + 统一规则引擎

分类层级（优先级从高到低）：
1. destructive → 直接拒绝，不进沙箱
2. dangerous   → 沙箱执行，禁止自动补权限
3. safe        → 沙箱执行，无需补权限
4. default     → 沙箱执行，可自动补最小权限

注：分类直接决定沙箱策略（safe→只读，dangerous/default→workspace-write），分类层同时控制是否允许扩权。

规则来自同包 rules.py，用户扩展写在 rules.yaml（与内置规则冲突时以内置规则为准）。
命令行入口是 ``sandbox-policy classify``。
"""

import re
import shlex
import sys
from pathlib import PurePath
from typing import Any, Dict, List, Optional, Tuple

from sandbox_policy import rules as rule_data


class RuleEngine:
    """统一规则匹配引擎 - 支持 rules.py 中所有 Match Schema 字段"""

    @staticmethod
    def match_rule(rule: dict, parts: List[str], full_cmd: str) -> Tuple[bool, str]:
        """
        检查命令是否匹配规则。
        返回 (matched, reason)
        """
        if not parts:
            return False, ""

        cmd = PurePath(parts[0]).name
        args = parts[1:]
        reason = rule.get("reason", "")

        # OS 限制
        if "os" in rule and sys.platform != rule["os"]:
            return False, ""

        # --- 主匹配条件（互斥） ---

        # pattern: 全命令字面子串匹配
        if "pattern" in rule:
            return (True, reason) if rule["pattern"] in full_cmd else (False, "")

        # command_prefix: 前缀匹配（mkfs.ext4 等）
        if "command_prefix" in rule:
            return (
                (True, reason)
                if cmd.startswith(rule["command_prefix"])
                else (False, "")
            )

        # command: 精确匹配可执行文件名
        if "command" in rule:
            if cmd != rule["command"]:
                return False, ""
        else:
            return False, ""

        # --- 附加条件（AND 逻辑，全部满足才命中） ---

        # recursive: sudo 等递归检查子命令
        if rule.get("recursive") and len(parts) > 1:
            return True, reason

        # first_arg_in: 第一个参数须在列表中
        if "first_arg_in" in rule:
            if not args or args[0] not in rule["first_arg_in"]:
                return False, ""

        # flags: 含这些 flag 才命中（OR 逻辑）
        if "flags" in rule:
            if not any(arg in rule["flags"] for arg in args):
                return False, ""

        # subcommands: 子命令匹配（第一个非 flag 参数）
        if "subcommands" in rule:
            subcmd = next((a for a in args if not a.startswith("-")), None)
            if subcmd not in rule["subcommands"]:
                return False, ""

        # target_in: 位置参数在此列表中
        if "target_in" in rule:
            targets = [a for a in args if not a.startswith("-")]
            if not any(
                t == d or t.startswith(d + "/")
                for t in targets
                for d in rule["target_in"]
            ):
                return False, ""

        # args_contain: 参数含这些子串（OR 逻辑）
        if "args_contain" in rule:
            found = False
            for pat in rule["args_contain"]:
                if " " in pat:
                    if all(t in args for t in pat.split()):
                        found = True
                        break
                else:
                    if any(pat in arg for arg in args):
                        found = True
                        break
            if not found:
                return False, ""

        return True, reason


class CommandClassifier:
    def __init__(self) -> None:
        self.engine = RuleEngine()

    @staticmethod
    def _parse_command(command: str) -> List[str]:
        try:
            return shlex.split(command)
        except ValueError:
            return command.split()

    @staticmethod
    def _pack(
        decision: str,
        reason: str,
        command: str,
        additional_permissions: Optional[dict] = None,
    ) -> Dict[str, Any]:
        return {
            "decision": decision,
            "reason": reason,
            "command": command,
            "additional_permissions": additional_permissions,
        }

    @staticmethod
    def _match_chain_op(command: str, index: int) -> Optional[str]:
        """顶层分隔符。``>&`` / ``&>`` 是重定向，不当作后台 ``&``。"""
        if command.startswith(("&&", "||", "|&"), index):
            return command[index : index + 2]
        char = command[index]
        if char in ";|\n":
            return char
        if char != "&":
            return None
        prev = command[index - 1] if index else ""
        nxt = command[index + 1] if index + 1 < len(command) else ""
        if prev == ">" or nxt == ">":
            return None
        return char

    @staticmethod
    def _split_chain(command: str) -> Optional[List[str]]:
        """拆开顶层 ``&&`` / ``||`` / ``;`` / ``|`` / ``&`` / 换行。

        单引号内全部字面量。双引号内仍识别 ``$(...)`` 和反引号。括号帧
        记录被命令替换打断的双引号，闭合后恢复。不配对时返回 None。
        """
        segments: List[str] = []
        nested: List[str] = []
        buf: List[str] = []
        quote: Optional[str] = None
        backtick = False
        # 每层括号要恢复的引号；None 表示进入时不在双引号里。
        frames: List[Optional[str]] = []
        inner_start: Optional[int] = None
        backtick_resume: Optional[str] = None
        found_op = False
        i = 0
        n = len(command)

        def flush() -> None:
            segments.append("".join(buf).strip())
            buf.clear()

        def top() -> bool:
            return not frames and not backtick

        def begin_group(start: int, suspend_quote: bool) -> None:
            nonlocal quote, inner_start
            if suspend_quote and quote == '"':
                frames.append('"')
                quote = None
            else:
                frames.append(None)
            if len(frames) == 1:
                inner_start = start

        while i < n:
            char = command[i]

            if quote == "'":
                if top():
                    buf.append(char)
                if char == "'":
                    quote = None
                i += 1
                continue

            if quote == '"':
                if char == "\\" and i + 1 < n:
                    if top():
                        buf.append(char)
                        buf.append(command[i + 1])
                    i += 2
                    continue
                if char == "`":
                    if not frames:
                        inner_start = i + 1
                    backtick = True
                    backtick_resume = '"'
                    quote = None
                    i += 1
                    continue
                if char == "$" and i + 1 < n and command[i + 1] == "(":
                    begin_group(i + 2, suspend_quote=True)
                    i += 2
                    continue
                if top():
                    buf.append(char)
                if char == '"':
                    quote = None
                i += 1
                continue

            if backtick:
                if char == "`":
                    backtick = False
                    if not frames and inner_start is not None:
                        nested.append(command[inner_start:i].strip())
                        inner_start = None
                    if backtick_resume:
                        quote = backtick_resume
                        backtick_resume = None
                i += 1
                continue

            if char == "\\" and i + 1 < n:
                if top():
                    buf.append("\\")
                    buf.append(command[i + 1])
                i += 2
                continue

            if char in ("'", '"'):
                quote = char
                if top():
                    buf.append(char)
                i += 1
                continue

            if char == "`":
                if not frames:
                    inner_start = i + 1
                backtick = True
                i += 1
                continue

            if char == "$" and i + 1 < n and command[i + 1] == "(":
                begin_group(i + 2, suspend_quote=False)
                i += 2
                continue

            if char == "(":
                begin_group(i + 1, suspend_quote=False)
                i += 1
                continue

            if char == ")":
                if not frames:
                    return None
                resume = frames.pop()
                end = i
                i += 1
                if resume == '"':
                    quote = '"'
                if not frames and inner_start is not None:
                    nested.append(command[inner_start:end].strip())
                    inner_start = None
                continue

            if top():
                op = CommandClassifier._match_chain_op(command, i)
                if op:
                    found_op = True
                    flush()
                    i += len(op)
                    continue
                buf.append(char)
            i += 1

        if quote or backtick or frames:
            return None

        flush()
        nested_parts = [seg for seg in nested if seg]
        pieces = list(segments) if found_op else [seg for seg in segments if seg]
        pieces.extend(nested_parts)
        if not found_op and not nested_parts:
            return None
        if not any(pieces):
            return None
        if len(pieces) == 1 and pieces[0] == command.strip():
            return None
        return pieces

    def _classify_chain(self, command: str, segments: List[str]) -> Dict[str, Any]:
        """合并子命令：destructive / dangerous 取最严；safe 要求全部安全。"""
        results: List[Dict[str, Any]] = []
        for seg in segments:
            if not seg:
                results.append(self._pack("default", "空的命令片段", command))
                continue
            if seg == command:
                results.append(self._classify_simple(seg))
                continue
            results.append(self.classify(seg))

        for level in ("destructive", "dangerous"):
            for item in results:
                if item["decision"] == level:
                    return self._pack(level, item["reason"], command)

        if all(item["decision"] == "safe" for item in results):
            return self._pack("safe", "链式命令中所有命令都是安全的", command)
        # 链式命令不继承单段的自动补权，避免前缀把网络权限带给后续命令。
        return self._pack("default", "链式命令含未归类片段，使用默认沙箱策略", command)

    @staticmethod
    def _extract_shell_commands(parts: List[str]) -> Optional[List[List[str]]]:
        """从 bash -c "..." 形式提取内部命令"""
        if len(parts) < 3:
            return None

        cmd = PurePath(parts[0]).name
        if cmd not in ("bash", "sh", "zsh") or parts[1] not in ("-c", "-lc"):
            return None

        script = parts[2]
        if any(op in script for op in rule_data.SHELL_UNSAFE_OPERATORS):
            return None

        result = []
        for s in re.split(r"\s*(?:&&|\|\||;|\|)\s*", script):
            s = s.strip()
            if s:
                try:
                    result.append(shlex.split(s))
                except ValueError:
                    return None
        return result or None

    def _check_rules(
        self, rules: List[dict], parts: List[str], full_cmd: str
    ) -> Tuple[bool, str]:
        """检查命令是否匹配规则列表"""
        for rule in rules:
            matched, reason = self.engine.match_rule(rule, parts, full_cmd)
            if matched:
                return True, reason
        return False, ""

    def _check_with_shell_wrapper(
        self, rules: List[dict], parts: List[str], full_cmd: str
    ) -> Tuple[bool, str]:
        """检查命令（含 shell wrapper 递归，任一子命令匹配即可）"""
        matched, reason = self._check_rules(rules, parts, full_cmd)
        if matched:
            return True, reason
        all_commands = self._extract_shell_commands(parts)
        if all_commands:
            for cmd in all_commands:
                m, r = self._check_rules(rules, cmd, " ".join(cmd))
                if m:
                    return True, r
        return False, ""

    # --- 四层检测 ---

    def _is_destructive(self, parts: List[str], full_cmd: str) -> Tuple[bool, str]:
        """检查是否为毁灭性命令（含 sudo 递归）"""
        if parts and PurePath(parts[0]).name == "sudo" and len(parts) > 1:
            ok, reason = self._is_destructive(parts[1:], " ".join(parts[1:]))
            if ok:
                return True, f"sudo 提权 + {reason}"
        return self._check_with_shell_wrapper(rule_data.DESTRUCTIVE_RULES, parts, full_cmd)

    def _is_dangerous(self, parts: List[str], full_cmd: str) -> Tuple[bool, str]:
        """检查是否为危险命令"""
        # sudo 递归：所有 sudo 子命令视为 dangerous（destructive 层已优先检查）
        if parts and PurePath(parts[0]).name == "sudo" and len(parts) > 1:
            return True, f"sudo 提权执行: {' '.join(parts[1:])}"
        return self._check_with_shell_wrapper(rule_data.DANGEROUS_RULES, parts, full_cmd)

    @staticmethod
    def _is_safe_command(parts: List[str]) -> Tuple[bool, str]:
        """单条命令安全检查（frozenset + 条件规则 + 特殊处理）"""
        if not parts:
            return False, ""
        cmd = PurePath(parts[0]).name
        args = parts[1:]

        # 1. 无条件安全命令
        if cmd in rule_data.SAFE_COMMANDS:
            return True, f"安全命令: {cmd}"
        if sys.platform == "linux" and cmd in rule_data.SAFE_COMMANDS_LINUX:
            return True, f"安全命令(Linux): {cmd}"

        # 2. 条件安全命令（deny_args / deny_arg_prefixes 检查）
        for rule in rule_data.SAFE_CONDITIONAL:
            if cmd != rule["command"]:
                continue
            deny_args = rule.get("deny_args", [])
            deny_prefixes = rule.get("deny_arg_prefixes", [])
            for arg in args:
                # 精确匹配
                if arg in deny_args:
                    return False, ""
                # = 结尾做前缀匹配（--output= 匹配 --output=file.txt）
                if any(arg.startswith(d) for d in deny_args if d.endswith("=")):
                    return False, ""
                # 前缀匹配（-o 匹配 -ofile.txt）
                if any(arg.startswith(p) and len(arg) > len(p) for p in deny_prefixes):
                    return False, ""
            return True, rule.get("reason", f"条件安全: {cmd}")

        # 3. git 特殊处理：非危险 / 非网络子命令视为安全
        if cmd == "git":
            subcmd = next((a for a in args if not a.startswith("-")), None)
            dangerous_subcmds = {"clean"}
            network_subcmds = {"clone", "fetch", "pull", "push"}
            if subcmd is None or (
                subcmd not in dangerous_subcmds and subcmd not in network_subcmds
            ):
                return True, f"安全 git 操作: git {subcmd or ''}"
            return False, ""

        # 4. sed 特殊处理：无 -i 时为只读
        if cmd == "sed":
            if not any(a == "-i" or a.startswith("-i") for a in args):
                return True, "sed 只读模式"
            return False, ""

        return False, ""

    def _is_safe(self, parts: List[str], full_cmd: str) -> Tuple[bool, str]:
        """安全命令检测（含 shell wrapper 递归，所有子命令须安全）"""
        normalized = ["bash" if p == "zsh" else p for p in parts]
        ok, reason = self._is_safe_command(normalized)
        if ok:
            return True, reason
        # shell wrapper 递归：bash -c "cmd1 && cmd2" 所有子命令都安全才算安全
        all_commands = self._extract_shell_commands(normalized)
        if all_commands:
            for cmd in all_commands:
                m, _ = self._is_safe_command(cmd)
                if not m:
                    return False, ""
            return True, "shell 中所有命令都是安全的"
        return False, ""

    # --- 额外权限 ---

    @staticmethod
    def _convert_grant(grant: Optional[dict]) -> Optional[dict]:
        """将 rules.py 的 grant 格式转为 additional_permissions 格式"""
        if not grant:
            return None
        result = {}
        if grant.get("network"):
            result["network"] = {"enabled": True}
        if grant.get("write_paths"):
            result.setdefault("file_system", {})["write"] = grant["write_paths"]
        return result or None

    def _get_additional_permissions(self, parts: List[str]) -> Optional[dict]:
        """从 PERMISSION_RULES 查找匹配的额外权限（优先匹配更具体的规则）"""
        if not parts:
            return None
        cmd = PurePath(parts[0]).name
        args = parts[1:]

        for rule in rule_data.PERMISSION_RULES:
            if rule.get("command") != cmd:
                continue
            # 子命令匹配
            if "subcommands" in rule:
                subcmd = next((a for a in args if not a.startswith("-")), None)
                if subcmd not in rule["subcommands"]:
                    continue
            # args_contain 匹配（参数须包含指定值）
            if "args_contain" in rule:
                if not any(pat in args for pat in rule["args_contain"]):
                    continue
            return self._convert_grant(rule.get("grant"))
        return None

    # --- 主入口 ---

    def classify(self, command: str) -> Dict[str, Any]:
        """分类命令，返回四层分类结果 + 基础策略 + 额外权限。

        顶层链式命令先拆段再合并。跨分隔符的整句模式（fork bomb）仍对原文做
        destructive 检查，避免拆开后漏掉。
        """
        segments = self._split_chain(command)
        if segments is None:
            return self._classify_simple(command)

        parts = self._parse_command(command)
        ok, reason = self._is_destructive(parts, command)
        if ok:
            return self._pack("destructive", reason, command)
        return self._classify_chain(command, segments)

    def _classify_simple(self, command: str) -> Dict[str, Any]:
        """单条命令分类（不再按链式分隔符拆开）。"""
        parts = self._parse_command(command)

        ok, reason = self._is_destructive(parts, command)
        if ok:
            return self._pack("destructive", reason, command)

        ok, reason = self._is_dangerous(parts, command)
        if ok:
            return self._pack("dangerous", reason, command)

        ok, reason = self._is_safe(parts, command)
        if ok:
            return self._pack("safe", reason, command)

        # default: 唯一允许自动补权限的类别
        return self._pack(
            "default",
            "未匹配已知分类，使用默认沙箱策略",
            command,
            self._get_additional_permissions(parts),
        )
