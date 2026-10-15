"""sandbox-policy 命令行。"""

import argparse
import json

from sandbox_policy.classify import CommandClassifier
from sandbox_policy.policy import generate_sandbox_policy


def main(argv: list[str] | None = None) -> None:
    """分类命令，或生成 linux-sandbox 策略。"""
    parser = argparse.ArgumentParser(
        prog="sandbox-policy",
        description="命令分类与 linux-sandbox 策略生成",
    )
    sub = parser.add_subparsers(dest="verb", required=True)

    classify = sub.add_parser("classify", help="四层命令分类")
    classify.add_argument("command", help="要分类的 shell 命令")
    classify.add_argument("--json", action="store_true", help="输出 JSON")

    policy = sub.add_parser("policy", help="生成 linux-sandbox 策略")
    policy.add_argument("command", help="要执行的 shell 命令")
    policy.add_argument("--cwd", required=True, help="命令的工作目录（绝对路径）")

    args = parser.parse_args(argv)
    if args.verb == "classify":
        _run_classify(args.command, args.json)
        return
    _run_policy(args.command, args.cwd)


def _run_classify(command: str, as_json: bool) -> None:
    result = CommandClassifier().classify(command)
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"命令: {command}")
    print(f"分类: {result['decision']}")
    print(f"原因: {result['reason']}")
    if result["additional_permissions"]:
        print(
            "额外权限: "
            f"{json.dumps(result['additional_permissions'], ensure_ascii=False)}"
        )


def _run_policy(command: str, cwd: str) -> None:
    result = generate_sandbox_policy(command, cwd)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
