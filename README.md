# OWUI_TwitterAPI_Tool

> Search X (Twitter) from inside [Open WebUI](https://openwebui.com), backed by the
> [twitterapi.io](https://twitterapi.io) REST API.

[![Version](https://img.shields.io/badge/version-v1.0.0-blue)](https://github.com/zmail-tech/OWUI_TwitterAPI_Tool/releases/tag/v1.0.0)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Author](https://img.shields.io/badge/author-zmail--tech-orange)](https://github.com/zmail-tech)
[![Platform](https://img.shields.io/badge/platform-Open%20WebUI-purple)](https://github.com/open-webui/open-webui)

An Open WebUI in-app tool that lets a chat model search X (Twitter) for tweets, user
timelines, profiles, and fresh news — **without any OAuth setup**. It is built on the
single-key **twitterapi.io** API, so the only thing it needs is one API key.

Everything ships as a single self-contained file: `tool-x_twitterapi_search_tool.py`.
Paste it into the Open WebUI tool editor and go.

---

## ✨ Features

- **4 tools** — general search, user timelines, user profiles, and topic news.
- **Zero OAuth** — one `X-API-Key` header; no user authorization flow to wire up.
- **Token-friendly output** — tweets are normalized into a compact, LLM-sized shape.
- **Configurable** — the Open WebUI *Valves* panel tunes defaults, news sources, and the
  news freshness window.
- **Machine-readable responses** — a consistent `success` / `code` contract so callers
  (or the model) can branch on results.
- **Self-contained** — one `.py` file, no dependencies beyond `requests`.

## 🔑 Requirements

- [Open WebUI](https://github.com/open-webui/open-webui)
- A **twitterapi.io** API key → create one at <https://twitterapi.io/dashboard>
- Python `requests` (declared in the tool's *Requirements* field; Open WebUI installs it)

## 📦 Installation

Do this once in Open WebUI. Either method works.

### Option A — Paste into the tool editor

1. Go to **Workspace → Tools → Create Tool**.
2. *Name*: e.g. `Twitter API Search`.
3. Paste the entire contents of
   [`tool-x_twitterapi_search_tool.py`](tool-x_twitterapi_search_tool.py) into the code editor.
4. Set the **Requirements** field to:
   ```
   requests
   ```
5. Click **Create**.
6. Open the tool, expand **Valves**, and enter your `twitterapi_api_key`.

### Option B — Upload the file

On the same **Create Tool** screen, upload `tool-x_twitterapi_search_tool.py`, set the
**Requirements** to `requests`, then add your key under **Valves**.

> **Tip:** Instead of the Valves panel you can export `TWITTERAPI_API_KEY` on the Open
> WebUI host — the tool falls back to that environment variable automatically.

## ⚙️ Configuration (Valves)

Set these in the tool's **Valves** panel. Every default preserves standard behavior, so
nothing changes until you tweak something.

| Valve | Type | Default | Description |
|---|---|---|---|
| `twitterapi_api_key` | `str` | *(empty)* | Your twitterapi.io key. Sent as the `X-API-Key` header on every request. |
| `default_max_results` | `int` | `15` | Results per call when the model omits `max_results` (clamped 1–100). |
| `default_query_type` | `str` | `Latest` | Default sort for search & news: `Latest` (newest) or `Top` (most engaging). |
| `default_include_media` | `bool` | `False` | Include media image URLs by default. |
| `default_include_replies` | `bool` | `False` | Include replies in `get_user_tweets` by default. |
| `news_freshness_hours` | `int` | `24` | How far back `search_news_tweets` reaches, in hours (clamped 1–168). |
| `news_accounts` | `str` | 14 outlets | Space- or comma-separated X handles used by the news search. |

An explicit argument passed in a tool call **always overrides** a valve. Empty or
invalid valve values fall back to safe built-in defaults, so clearing a valve can never
break a tool.

## 🛠️ The tools

### 1. `search_tweets`

General search of X using advanced operators.

| Param | Type | Default | Notes |
|---|---|---|---|
| `query` | str | *(required)* | Supports operators like `from:user`, `to:user`, `-is:retweet`, `min_faves:100`, `OR`. |
| `query_type` | str | `Latest` | `Latest` or `Top`. |
| `max_results` | int | `15` | 1–100; paginated internally. A `note` is added if clamped. |
| `lang` | str | `""` | Optional language filter, e.g. `en`. |
| `since` | str | `""` | Start date (`YYYY-MM-DD`, ISO datetime, or unix). |
| `until` | str | `""` | End date (same formats). |
| `include_media` | bool | `False` | Include media image URLs. |

**Example prompt:** “Find the top 10 tweets about #OpenAI from the last week, English only.”

### 2. `get_user_tweets`

A specific user's recent tweets.

| Param | Type | Default | Notes |
|---|---|---|---|
| `username` | str | *(required)* | Handle without the `@`. |
| `max_results` | int | `15` | 1–100. |
| `include_replies` | bool | `False` | Include replies. |
| `include_media` | bool | `False` | Include media image URLs. |

**Example prompt:** “What has @NASA posted recently?”
If the user doesn't exist, the tool returns `code: "not_found"`.

### 3. `get_user_info`

A user's profile details.

| Param | Type | Default | Notes |
|---|---|---|---|
| `username` | str | *(required)* | Handle without the `@`. |

Returns name, bio, follower/following counts, verification, profile picture URL, and more.
If the user doesn't exist, returns `code: "not_found"`.

### 4. `search_news_tweets`

Fresh, on-topic news pulled from the configured news outlets, limited to a recency window
(default 24 h) to guarantee freshness.

| Param | Type | Default | Notes |
|---|---|---|---|
| `topic` | str | `breaking news` | Topic / keywords, injected verbatim into the query. |
| `max_results` | int | `15` | 1–100. |
| `lang` | str | `en` | Language filter. |
| `query_type` | str | `Latest` | `Latest` or `Top`. |

The topic is always injected into the query (and echoed back in the response `query`
field). If the on-topic query matches nothing in the freshness window, the result is
empty (`count: 0`) with an explanatory `note` — it never silently returns off-topic items.

**Example prompt:** “What's the latest news on artificial intelligence?”

## 📄 Response format

All tools return JSON. Successful calls include `success: true` and a `timestamp`;
tweets are compacted to keep context small:

```json
{
  "success": true,
  "query": "from:NASA -is:retweet",
  "query_type": "Latest",
  "count": 2,
  "tweets": [
    {
      "id": "1941234567890123456",
      "url": "https://x.com/NASA/status/1941234567890123456",
      "text": "…",
      "created_at": "Thu, 11 Sep 2025 14:02:11 GMT",
      "lang": "en",
      "author": { "name": "NASA", "username": "NASA", "id": "14813427" },
      "metrics": { "likes": 1200, "retweets": 340, "replies": 55, "quotes": 21, "views": 1900000, "bookmarks": 800 },
      "is_reply": false
    }
  ],
  "timestamp": "2025-09-14T16:00:00"
}
```

`search_news_tweets` additionally returns `topic`, `query`, and `freshness_window_hours`.
When `include_media` is on, each tweet gains a `media` list.

### Error / not-found contract

Failures are machine-readable so you can branch on them:

| Situation | Shape |
|---|---|
| Missing user | `{"success": false, "code": "not_found", "resource": "user", "error": "..."}` |
| Bad input (empty query/username) | `{"success": false, "code": "invalid_input", "error": "..."}` |
| Topic too long (news) | `{"success": false, "code": "topic_too_long", "error": "..."}` |
| Unexpected | `{"success": false, "error": "..."}` |

## 🗂️ Project structure

```
.
├── tool-x_twitterapi_search_tool.py   # the tool — import this into Open WebUI
├── LICENSE                            # MIT
├── README.md
└── .gitignore                         # ignores .env
```

`.env` is git-ignored; put `TWITTERAPI_API_KEY=*** there if you prefer the
environment variable over the Valves panel.

## 🚀 Release

**v1.0.0** — initial public release.

- Four tools: `search_tweets`, `get_user_tweets`, `get_user_info`, `search_news_tweets`
- Full set of configuration Valves (defaults, news sources, freshness window)
- Compact tweet normalization, internal pagination, machine-readable error codes
- Single self-contained file, no OAuth required

## 📄 License

Distributed under the [MIT License](LICENSE).

## 👤 Author

**[zmail-tech](https://github.com/zmail-tech)** — zmail-tech@zmail.tech
