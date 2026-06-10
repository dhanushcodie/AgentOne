import json

import anthropic


def warn_if_truncated(response: anthropic.types.Message, agent_name: str) -> None:
    if response.stop_reason == "max_tokens":
        print(
            f"\n[WARNING] {agent_name} output was cut off — "
            f"increase tokens_{agent_name.lower()} in config.py if the plan looks incomplete."
        )


def run_search_loop(
    client: anthropic.Anthropic,
    *,
    system: str,
    messages: list,
    max_searches: int,
    model: str,
    max_tokens: int,
    agent_name: str,
    max_continuations: int = 8,
) -> str:
    """
    Agentic loop for agents using the server-side web_search tool.

    web_search executes on Anthropic's servers — the client never sends
    tool_result blocks for it. When the server-side sampling loop hits its
    iteration limit, the response stops with stop_reason "pause_turn"; the
    correct continuation is to append the assistant content and re-request,
    and the server resumes where it left off. Breaking on pause_turn (or
    fabricating tool results) silently truncates the research.
    """
    tools = [{
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": max_searches,
    }]
    text_parts = []
    response = None

    for _ in range(max_continuations + 1):
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            messages=messages,
        )
        for block in response.content:
            if getattr(block, "type", "") == "text":
                text_parts.append(block.text)

        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue
        break

    if response is not None:
        warn_if_truncated(response, agent_name)
    return "\n\n".join(text_parts)


def strip_json_fences(text: str) -> str:
    """Extract the JSON payload from a response that may wrap it in ``` fences."""
    text = text.strip()
    if "```" not in text:
        return text
    for part in text.split("```"):
        candidate = part.strip()
        if candidate.startswith("json"):
            candidate = candidate[4:].strip()
        if candidate.startswith("{") or candidate.startswith("["):
            return candidate
    return text


def create_json_with_retry(
    client: anthropic.Anthropic,
    *,
    model: str,
    max_tokens: int,
    system: str,
    messages: list,
    retries: int = 2,
):
    """
    Call the API expecting a JSON reply; on malformed JSON, retry with the
    bad reply in context so one glitchy response doesn't kill the session.
    """
    last_err: Exception = ValueError("no attempts made")
    attempt_messages = list(messages)
    for _ in range(retries):
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=attempt_messages,
        )
        text = response.content[0].text if response.content else ""
        try:
            return json.loads(strip_json_fences(text))
        except (json.JSONDecodeError, IndexError) as err:
            last_err = err
            attempt_messages = attempt_messages + [
                {"role": "assistant", "content": text},
                {"role": "user", "content": (
                    "Your previous reply was not valid JSON. Respond again with "
                    "ONLY valid JSON in the required shape — no prose, no fences."
                )},
            ]
    raise last_err
