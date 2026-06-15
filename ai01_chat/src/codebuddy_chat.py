#!/usr/bin/env python3
"""Interactive terminal chat powered by CodeBuddy CLI."""

from __future__ import annotations

import argparse
import subprocess
import sys

from codebuddy_client import (
    AVAILABLE_MODELS,
    DEFAULT_MODEL,
    ChatSession,
    CodeBuddyClient,
)


def print_models(current: str) -> None:
    print("\n可用模型：")
    for key, model_id in AVAILABLE_MODELS.items():
        marker = " (当前)" if model_id == current else ""
        print(f"  {key:>2}. {model_id}{marker}")
    print()


def print_help() -> None:
    print(
        """
命令：
  /help     显示帮助
  /models   列出可用模型
  /model N  切换模型（N 为编号，如 /model 1）
  /new      开始新对话
  /quit     退出
"""
    )


def choose_model(default: str) -> str:
    print_models(default)
    while True:
        choice = input(f"选择模型 [1-{len(AVAILABLE_MODELS)}，回车默认 {default}]: ").strip()
        if not choice:
            return default
        if choice in AVAILABLE_MODELS:
            return AVAILABLE_MODELS[choice]
        print("无效编号，请重试。")


def resolve_model(model_arg: str | None) -> str:
    if not model_arg:
        return choose_model(DEFAULT_MODEL)

    if model_arg in AVAILABLE_MODELS:
        return AVAILABLE_MODELS[model_arg]

    if model_arg in AVAILABLE_MODELS.values():
        return model_arg

    print(f"未知模型: {model_arg}，使用默认模型 {DEFAULT_MODEL}")
    return DEFAULT_MODEL


def run_chat(model: str) -> None:
    client = CodeBuddyClient()
    session = ChatSession(model=model)

    print(f"\nCodeBuddy 聊天已启动 | 模型: {session.model} | 会话: {session.session_id}")
    print("输入 /help 查看命令，/quit 退出\n")

    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue

        if user_input.lower() in {"/quit", "/exit", "quit", "exit"}:
            print("再见！")
            break

        if user_input.lower() == "/help":
            print_help()
            continue

        if user_input.lower() == "/models":
            print_models(session.model)
            continue

        if user_input.lower().startswith("/model"):
            parts = user_input.split(maxsplit=1)
            if len(parts) == 1:
                print_models(session.model)
                continue
            key = parts[1].strip()
            if key not in AVAILABLE_MODELS and key not in AVAILABLE_MODELS.values():
                print("无效模型编号或 ID。")
                continue
            session.model = AVAILABLE_MODELS.get(key, key)
            print(f"已切换模型: {session.model}")
            continue

        if user_input.lower() == "/new":
            session = ChatSession(model=session.model)
            print(f"已开始新对话 | 会话: {session.session_id}")
            continue

        print("助手: ", end="", flush=True)
        try:
            reply = client.chat(session, user_input)
            print(reply)
        except RuntimeError as exc:
            print(f"\n错误: {exc}", file=sys.stderr)
            break
        except subprocess.SubprocessError as exc:
            print(f"\n调用 CodeBuddy 失败: {exc}", file=sys.stderr)
            break

        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="CodeBuddy 多模型聊天程序")
    parser.add_argument(
        "--model",
        "-m",
        help="模型 ID 或编号（1-13），不传则启动时选择",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="列出可用模型后退出",
    )
    args = parser.parse_args()

    if args.list_models:
        print_models("")
        return

    model = resolve_model(args.model)
    run_chat(model)


if __name__ == "__main__":
    main()
