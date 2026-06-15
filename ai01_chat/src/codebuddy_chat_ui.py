#!/usr/bin/env python3
"""Simple web UI for CodeBuddy chat."""

from __future__ import annotations

import gradio as gr

from codebuddy_client import (
    DEFAULT_MODEL,
    MODEL_CHOICES,
    ChatSession,
    CodeBuddyClient,
)

client = CodeBuddyClient()


def respond(message: str, history: list, model: str, session: ChatSession | None):
    if session is None:
        session = ChatSession(model=model)

    session.model = model
    message = (message or "").strip()
    if not message:
        return history, session, ""

    history = history + [{"role": "user", "content": message}]

    try:
        reply = client.chat(session, message)
        history = history + [{"role": "assistant", "content": reply}]
    except Exception as exc:
        history = history + [{"role": "assistant", "content": f"❌ {exc}"}]

    return history, session, ""


def new_conversation(model: str):
    return [], ChatSession(model=model), ""


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="CodeBuddy Chat") as demo:
        gr.Markdown("# CodeBuddy 大模型聊天")
        gr.Markdown("基于 CodeBuddy CLI，支持多模型切换。")

        session_state = gr.State(ChatSession(model=DEFAULT_MODEL))

        with gr.Row():
            model_dropdown = gr.Dropdown(
                choices=MODEL_CHOICES,
                value=DEFAULT_MODEL,
                label="选择模型",
                scale=3,
            )
            new_btn = gr.Button("新对话", scale=1)

        chatbot = gr.Chatbot(label="对话", height=480)
        msg = gr.Textbox(
            label="输入消息",
            placeholder="输入问题，按 Enter 发送...",
            lines=2,
        )

        send_btn = gr.Button("发送", variant="primary")

        submit_inputs = [msg, chatbot, model_dropdown, session_state]
        submit_outputs = [chatbot, session_state, msg]

        msg.submit(respond, submit_inputs, submit_outputs)
        send_btn.click(respond, submit_inputs, submit_outputs)
        new_btn.click(
            new_conversation,
            inputs=[model_dropdown],
            outputs=[chatbot, session_state, msg],
        )

    return demo


def main() -> None:
    import os

    port = int(os.environ.get("PORT", "7860"))
    demo = build_ui()
    demo.launch(server_name="127.0.0.1", server_port=port, show_error=True)


if __name__ == "__main__":
    main()
