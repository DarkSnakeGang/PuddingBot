import json
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import requests

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_CHAT_URL = f"{OLLAMA_HOST}/api/chat"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
MAX_TOOL_ROUNDS = int(os.getenv("OLLAMA_TOOL_ROUNDS", "3"))
FETCH_MAX_CHARS = 4000
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "180"))
OLLAMA_RETRY_TIMEOUT = int(os.getenv("OLLAMA_RETRY_TIMEOUT", "300"))

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


def _ollama_chat(
    messages: List[Dict[str, Any]],
    use_tools: bool = True,
    timeout: Optional[int] = None,
) -> Dict[str, Any]:
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

    response = requests.post(
        OLLAMA_CHAT_URL,
        json=payload,
        timeout=timeout or OLLAMA_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _search_query_from_user_text(text: str) -> str:
    """Clean Discord prompt noise into a usable search query."""
    query = text or ""
    query = re.sub(
        r",?\s*give a short answer but never mention that I asked for a short answer\s*$",
        "",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(r"https?://\S+", " ", query)
    query = re.sub(r"\s+", " ", query).strip(" ,.")
    return query


_ROLE_PREFIX_RE = re.compile(
    r"^\s*(?:assistant|assistent|ai|bot|puddingbot)\s*:?\s*",
    re.IGNORECASE,
)
_STANDALONE_ROLE_LINE_RE = re.compile(
    r"^(?:assistant|assistent|ai|bot|puddingbot)\s*$",
    re.IGNORECASE,
)


def _clean_reply(text: str) -> str:
    """Strip leaked chat-role labels the small model sometimes echoes."""
    if not text:
        return text
    lines = text.replace("\r\n", "\n").split("\n")
    while lines and (not lines[0].strip() or _STANDALONE_ROLE_LINE_RE.match(lines[0].strip())):
        lines.pop(0)
    cleaned = "\n".join(lines).strip()
    for _ in range(3):
        updated = _ROLE_PREFIX_RE.sub("", cleaned, count=1).strip()
        if updated == cleaned:
            break
        cleaned = updated
    return cleaned


def _run_ollama_conversation(
    chat_messages: List[Dict[str, Any]],
    timeout: int,
) -> str:
    """Run tool loop + final answer against Ollama."""
    working = [dict(m) for m in chat_messages]

    for _ in range(MAX_TOOL_ROUNDS):
        result = _ollama_chat(working, use_tools=True, timeout=timeout)
        message = result.get("message") or {}
        tool_calls = message.get("tool_calls") or []

        working.append(message)

        if not tool_calls:
            content = _clean_reply((message.get("content") or "").strip())
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
            working.append(
                {
                    "role": "tool",
                    "tool_name": name,
                    "content": str(tool_result)[:8000],
                }
            )

    result = _ollama_chat(working, use_tools=False, timeout=timeout)
    content = _clean_reply(((result.get("message") or {}).get("content") or "").strip())
    return content or "Sorry, I couldn't generate a response right now."


def chat_with_gpt(messages: List[Dict[str, str]], status_notify=None) -> str:
    """
    Chat with local Ollama. Always web-searches every user message, then answers.
    On timeout/connection failure, notifies Discord and retries once.
    """
    chat_messages: List[Dict[str, Any]] = [dict(m) for m in messages]

    last_user = next((m for m in reversed(chat_messages) if m.get("role") == "user"), None)
    if last_user:
        user_text = last_user.get("content", "")

        urls = re.findall(r"https?://[^\s<>\")]+", user_text)
        for url in urls[:2]:
            fetched = web_fetch(url.rstrip(".,);]"))
            print(f"[DEBUG] Prefetch URL: {url}")
            chat_messages.append(
                {
                    "role": "system",
                    "content": f"Pre-fetched page content for the user's link:\n{fetched}",
                }
            )

        search_query = _search_query_from_user_text(user_text) or user_text.strip() or "latest news"
        print(f"[DEBUG] Auto web_search (always): {search_query!r}")
        search_results = web_search(search_query, max_results=5)
        chat_messages.append(
            {
                "role": "system",
                "content": (
                    "Live web search results for this user message are below. "
                    "You DO have internet access through these results. "
                    "NEVER say you lack real-time access, cannot browse, or cannot check CNN/news. "
                    "Answer using these results. If they are thin, still summarize what they contain "
                    "instead of refusing.\n\n"
                    f"{search_results}"
                ),
            }
        )

        top_urls = re.findall(r"https?://[^\s]+", search_results)
        for url in top_urls[:1]:
            if url in urls:
                continue
            print(f"[DEBUG] Auto web_fetch top result: {url}")
            chat_messages.append(
                {
                    "role": "system",
                    "content": f"Top search result page content:\n{web_fetch(url)}",
                }
            )

    try:
        return _run_ollama_conversation(chat_messages, timeout=OLLAMA_TIMEOUT)
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as first_error:
        print(f"[DEBUG] Ollama first attempt failed: {first_error}")
        if status_notify:
            try:
                status_notify(
                    "The AI is taking a while — trying one more time, hang on…"
                )
            except Exception as notify_error:
                print(f"[DEBUG] status_notify failed: {notify_error}")

        try:
            return _run_ollama_conversation(chat_messages, timeout=OLLAMA_RETRY_TIMEOUT)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            return (
                "Sorry, the AI is overloaded or still loading the model. "
                "Please try again in a minute."
            )
        except requests.exceptions.RequestException:
            return (
                "Sorry, I couldn't reach the AI on the second try either. "
                "Please try again shortly."
            )
    except requests.exceptions.RequestException:
        return (
            "Sorry, I hit a temporary AI error. "
            "Please try again in a moment."
        )
    except Exception as e:
        print(f"[DEBUG] Unexpected AI error: {e}")
        return "Sorry, something went wrong while generating a reply. Please try again."
