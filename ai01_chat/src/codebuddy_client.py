"""Shared CodeBuddy CLI client for chat programs."""

from __future__ import annotations

import shutil
import subprocess
import uuid
from dataclasses import dataclass, field

CODEBUDDY_BIN = shutil.which("codebuddy") or "/usr/local/bin/codebuddy"

SYSTEM_PROMPT = (
    "你是一个简洁友好的聊天助手，只进行对话，不要使用任何工具，"
    "直接回答用户问题。"
)

AVAILABLE_MODELS: dict[str, str] = {
    "1": "glm-4.7-ioa",
    "2": "glm-5.0-ioa",
    "3": "glm-5.1-ioa",
    "4": "deepseek-v4-flash-ioa", 
    "5": "deepseek-v4-pro-ioa",
    "6": "kimi-k2.6-ioa",
    "7": "gpt-5.5",
    "8": "gpt-5.4",
    "9": "gemini-3.5-flash",
    "10": "gemini-3.1-pro",
    "11": "claude-sonnet-4.6",
    "12": "claude-opus-4.8",
    "13": "minimax-m2.7-ioa",
}

MODEL_CHOICES = list(AVAILABLE_MODELS.values())
DEFAULT_MODEL = "glm-4.7-ioa"


@dataclass
class ChatSession:
    model: str = DEFAULT_MODEL
    session_id: str = field(default_factory=lambda: f"chat-{uuid.uuid4()}")
    turn_count: int = 0


class CodeBuddyClient:
    def __init__(self, bin_path: str = CODEBUDDY_BIN) -> None:
        self.bin_path = bin_path

    def chat(self, session: ChatSession, message: str) -> str:
        cmd = [
            self.bin_path,
            "--model",
            session.model,
            "-p",
            "--tools",
            "",
            "--max-turns",
            "1",
            "--output-format",
            "text",
            "--permission-mode",
            "bypassPermissions",
            "--system-prompt",
            SYSTEM_PROMPT,
            "--session-id",
            session.session_id,
        ]

        if session.turn_count > 0:
            cmd.append("--continue")

        cmd.append(message)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        output = (result.stdout or result.stderr or "").strip()
        if not output:
            raise RuntimeError("CodeBuddy 返回空响应")

        if "Authentication required" in output:
            raise RuntimeError(
                "CodeBuddy 未登录，请先运行 `codebuddy` 并在交互界面输入 /login"
            )

        session.turn_count += 1
        return output
