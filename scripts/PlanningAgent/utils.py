import anthropic


def warn_if_truncated(response: anthropic.types.Message, agent_name: str) -> None:
    if response.stop_reason == "max_tokens":
        print(
            f"\n[WARNING] {agent_name} output was cut off — "
            f"increase tokens_{agent_name.lower()} in config.py if the plan looks incomplete."
        )
