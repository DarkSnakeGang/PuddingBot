import json
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import requests

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_CHAT_URL = f"{OLLAMA_HOST}/api/chat"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
MAX_TOOL_ROUNDS = int(os.getenv("OLLAMA_TOOL_ROUNDS", "3"))
FETCH_MAX_CHARS = 4000

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the public internet for current information. Use for news, facts, docs, or anything that may have changed.",
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch a web page by URL and return readable text content.",
            "parameters": {
                "type": "object",
                "required": ["url"],
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full http(s) URL to fetch",
                    }
                },
            },
        },
    },
]


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#39;", "'", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def web_search(query: str, max_results: int = 5) -> str:
    """Search via DuckDuckGo HTML results (no API key)."""
    try:
        response = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={
                "User-Agent": "PuddingBot/1.0 (+https://github.com/DarkSnakeGang/PuddingBot)"
            },
            timeout=20,
        )
        response.raise_for_status()
        html = response.text

        # result links look like <a rel="nofollow" class="result__a" href="...">title</a>
        links = re.findall(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        snippets = re.findall(
            r'class="result__snippet[^"]*"[^>]*>(.*?)</(?:a|td|div)>',
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if not links:
            # Fallback: DuckDuckGo instant answer API
            instant = requests.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                timeout=15,
            )
            instant.raise_for_status()
            data = instant.json()
            parts = []
            if data.get("AbstractText"):
                parts.append(f"Abstract: {data['AbstractText']}")
                if data.get("AbstractURL"):
                    parts.append(f"Source: {data['AbstractURL']}")
            for topic in data.get("RelatedTopics", [])[:max_results]:
                if isinstance(topic, dict) and topic.get("Text"):
                    parts.append(f"- {topic['Text']} ({topic.get('FirstURL', '')})")
            return "\n".join(parts) if parts else f"No search results for: {query}"

        lines = [f"Search results for: {query}"]
        for i, (url, title) in enumerate(links[:max_results]):
            clean_title = _strip_html(title)
            snippet = _strip_html(snippets[i]) if i < len(snippets) else ""
            lines.append(f"{i + 1}. {clean_title}\n   {url}\n   {snippet}")
        return "\n".join(lines)
    except Exception as e:
        return f"web_search error: {e}"


def web_fetch(url: str) -> str:
    """Fetch a URL and return truncated plain text."""
    try:
        if not url.startswith(("http://", "https://")):
            return "web_fetch error: URL must start with http:// or https://"

        response = requests.get(
            url,
            headers={
                "User-Agent": "PuddingBot/1.0 (+https://github.com/DarkSnakeGang/PuddingBot)"
            },
            timeout=20,
            allow_redirects=True,
        )
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        if "html" in content_type or url.endswith((".html", ".htm")) or "<html" in response.text[:200].lower():
            text = _strip_html(response.text)
        else:
            text = response.text
        text = text[:FETCH_MAX_CHARS]
        return f"Content from {url}:\n{text}"
    except Exception as e:
        return f"web_fetch error: {e}"


AVAILABLE_TOOLS = {
    "web_search": lambda args: web_search(args.get("query", "")),
    "web_fetch": lambda args: web_fetch(args.get("url", "")),
}


def _parse_tool_args(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _ollama_chat(messages: List[Dict[str, Any]], use_tools: bool = True) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "top_p": 0.9,
            "num_predict": 1024,
        },
    }
    if use_tools:
        payload["tools"] = TOOLS

    response = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=120)
    response.raise_for_status()
    return response.json()


def chat_with_gpt(messages: List[Dict[str, str]]) -> str:
    """
    Chat with local Ollama, with optional web_search / web_fetch tool calls.
    The model stays local; tools use the host/container network to reach the internet.
    """
    # Work on a copy so caller history is not mutated with tool messages
    chat_messages: List[Dict[str, Any]] = [dict(m) for m in messages]

    # If the latest user message contains URLs, prefetch them so even weak models get context
    last_user = next((m for m in reversed(chat_messages) if m.get("role") == "user"), None)
    if last_user:
        urls = re.findall(r"https?://[^\s<>\")]+", last_user.get("content", ""))
        for url in urls[:2]:
            fetched = web_fetch(url.rstrip(".,);]"))
            chat_messages.append(
                {
                    "role": "system",
                    "content": f"Pre-fetched page content for the user's link:\n{fetched}",
                }
            )

    try:
        for _ in range(MAX_TOOL_ROUNDS):
            result = _ollama_chat(chat_messages, use_tools=True)
            message = result.get("message") or {}
            tool_calls = message.get("tool_calls") or []

            # Keep assistant turn (may include tool_calls)
            chat_messages.append(message)

            if not tool_calls:
                content = (message.get("content") or "").strip()
                if content:
                    return content
                break

            for call in tool_calls:
                fn = call.get("function") or {}
                name = fn.get("name") or ""
                args = _parse_tool_args(fn.get("arguments"))
                print(f"[DEBUG] Tool call: {name}({args})")
                handler = AVAILABLE_TOOLS.get(name)
                tool_result = handler(args) if handler else f"Unknown tool: {name}"
                chat_messages.append(
                    {
                        "role": "tool",
                        "tool_name": name,
                        "content": str(tool_result)[:8000],
                    }
                )

        # Final answer without tools if tool loop produced nothing useful
        result = _ollama_chat(chat_messages, use_tools=False)
        content = ((result.get("message") or {}).get("content") or "").strip()
        return content or "Sorry, I couldn't generate a response at the moment."

    except requests.exceptions.RequestException as e:
        return f"Sorry, there was an error connecting to the AI service: {e}"
    except Exception as e:
        return f"An unexpected error occurred: {e}"
