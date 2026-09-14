import os
import json
import time
from datetime import datetime

import requests
from pydantic import BaseModel, Field


class Tools:
    def __init__(self):
        self.valves = self.Valves()

    # Tool configuration, editable in the Open WebUI "Valves" panel.
    # The API key is entered here (or via TWITTERAPI_API_KEY); the rest act as
    # defaults/overrides for the results the tools return.
    class Valves(BaseModel):
        twitterapi_api_key: str = Field(
            default="",
            description=(
                "twitterapi.io API key (get one at https://twitterapi.io/dashboard). "
                "Sent as the X-API-Key header on every request."
            ),
        )
        # ---- defaults (used when the model does not specify the parameter) ----
        default_max_results: int = Field(
            default=15,
            description="Default number of results per call (1-100) when not specified.",
        )
        default_query_type: str = Field(
            default="Latest",
            description="Default sort order: 'Latest' (newest) or 'Top' (most engaging).",
        )
        default_include_media: bool = Field(
            default=False,
            description="Include media image URLs by default when not specified.",
        )
        default_include_replies: bool = Field(
            default=False,
            description="For get_user_tweets, include replies by default when not specified.",
        )
        # ---- news search ----
        news_freshness_hours: int = Field(
            default=24,
            description="How far back search_news_tweets looks, in hours (keeps results fresh).",
        )
        news_accounts: str = Field(
            default=(
                "BBCBreaking CNN Reuters AP nytimes washingtonpost guardian "
                "ABCNews NBCNews CBSNews NPR WSJ TIME Bloomberg"
            ),
            description=(
                "Space- or comma-separated X handles of the news outlets used by "
                "search_news_tweets."
            ),
        )

    BASE_URL = "https://api.twitterapi.io"
    # Fallback values used when the corresponding Valve is empty/invalid.
    DEFAULT_NEWS_FRESHNESS_HOURS = 24
    DEFAULT_NEWS_ACCOUNTS = [
        "BBCBreaking",
        "CNN",
        "Reuters",
        "AP",
        "nytimes",
        "washingtonpost",
        "guardian",
        "ABCNews",
        "NBCNews",
        "CBSNews",
        "NPR",
        "WSJ",
        "TIME",
        "Bloomberg",
    ]

    # ------------------------------------------------------------- internals

    def _get_api_key(self) -> str:
        key = (self.valves.twitterapi_api_key or "").strip()
        if not key:
            key = (os.getenv("TWITTERAPI_API_KEY") or "").strip()
        if not key:
            raise ValueError(
                "No API key configured. Set 'twitterapi_api_key' in the tool Valves "
                "(get a key at https://twitterapi.io/dashboard) or the TWITTERAPI_API_KEY "
                "environment variable."
            )
        return key

    def _request(self, path: str, params: dict) -> dict:
        key = self._get_api_key()
        headers = {"X-API-Key": key}
        clean = {k: v for k, v in params.items() if v not in (None, "")}
        resp = requests.get(
            self.BASE_URL + path, params=clean, headers=headers, timeout=30
        )
        try:
            data = resp.json()
        except Exception:
            raise RuntimeError(
                f"API returned non-JSON (HTTP {resp.status_code}): {resp.text[:300]}"
            )
        if resp.status_code != 200:
            msg = data.get("message") if isinstance(data, dict) else resp.text[:300]
            raise RuntimeError(f"API error (HTTP {resp.status_code}): {msg}")
        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(f"API error: {data.get('message') or data.get('error')}")
        return data

    @staticmethod
    def _resolve(value, fallback=None):
        """Return the effective value for a parameter.

        Some tool runtimes pass the raw ``FieldInfo`` descriptor (or None) when the
        model omits an optional parameter. In that case return ``fallback`` — which we
        drive from the Valves so panel settings act as the defaults. Otherwise return
        the value the model explicitly provided.
        """
        if value is None or type(value).__name__ == "FieldInfo":
            return fallback
        return value

    # ---- Valve-driven configuration (robust parsing of panel values) ----

    def _cfg_max_results(self) -> int:
        try:
            n = int(self.valves.default_max_results)
        except (TypeError, ValueError):
            n = 15
        return max(1, min(n, 100))

    def _cfg_query_type(self) -> str:
        qt = (self.valves.default_query_type or "").strip()
        return qt if qt in ("Latest", "Top") else "Latest"

    def _cfg_include_media(self) -> bool:
        return bool(self.valves.default_include_media)

    def _cfg_include_replies(self) -> bool:
        return bool(self.valves.default_include_replies)

    def _news_freshness_hours(self) -> int:
        try:
            h = int(self.valves.news_freshness_hours)
        except (TypeError, ValueError):
            h = self.DEFAULT_NEWS_FRESHNESS_HOURS
        return max(1, min(h, 168))

    def _news_accounts(self) -> list:
        raw = (self.valves.news_accounts or "").replace(",", " ")
        seen, out = set(), []
        for part in raw.split():
            acc = part.strip().lstrip("@")
            if acc and acc not in seen:
                seen.add(acc)
                out.append(acc)
        return out or self.DEFAULT_NEWS_ACCOUNTS

    @staticmethod
    def _to_unix(value):
        if value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            return int(value)
        s = str(value).strip()
        if s.isdigit():
            return int(s)
        for fmt in (
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
        ):
            try:
                return int(datetime.strptime(s, fmt).timestamp())
            except ValueError:
                pass
        try:
            return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
        except Exception:
            raise ValueError(
                f"Unrecognized date format: {value!r} "
                "(use YYYY-MM-DD, an ISO datetime, or a unix timestamp)"
            )

    @staticmethod
    def _clamp_max(value, default: int = 15):
        """Clamp max_results into [1, 100]; return (clamped, note_or_None).

        The clamp is reported via a note so callers never see a silent change.
        """
        try:
            n = int(value)
        except (TypeError, ValueError):
            n = default
        note = None
        if n > 100:
            note = f"max_results clamped from {n} to 100 (the maximum allowed)."
            n = 100
        elif n < 1:
            note = f"max_results clamped from {n} to 1 (the minimum allowed)."
            n = 1
        return n, note

    @staticmethod
    def _format_tweet(t: dict, include_media: bool = False) -> dict:
        author = t.get("author") or {}
        out = {
            "id": t.get("id"),
            "url": t.get("url"),
            "text": t.get("text"),
            "created_at": t.get("createdAt"),
            "lang": t.get("lang"),
            "author": {
                "name": author.get("name"),
                "username": author.get("userName"),
                "id": author.get("id"),
            },
            "metrics": {
                "likes": t.get("likeCount", 0),
                "retweets": t.get("retweetCount", 0),
                "replies": t.get("replyCount", 0),
                "quotes": t.get("quoteCount", 0),
                "views": t.get("viewCount", 0),
                "bookmarks": t.get("bookmarkCount", 0),
            },
            "is_reply": t.get("isReply", False),
        }
        if include_media:
            media = (t.get("extendedEntities") or {}).get("media") or []
            out["media"] = [
                m.get("media_url_https") for m in media if m.get("media_url_https")
            ]
        return out

    @staticmethod
    def _extract_tweets(resp: dict) -> list:
        """Locate the tweet array; its location differs by endpoint.

        advanced_search: top-level ``tweets``. last_tweets: nested ``data.tweets``.
        """
        if not isinstance(resp, dict):
            return []
        if isinstance(resp.get("tweets"), list):
            return resp["tweets"]
        data = resp.get("data")
        if isinstance(data, dict) and isinstance(data.get("tweets"), list):
            return data["tweets"]
        if isinstance(data, list):
            return data
        return []

    def _paginate_tweets(
        self, path: str, base_params: dict, max_results: int, include_media: bool = False
    ) -> list:
        collected = []
        cursor = ""
        for _ in range(20):  # hard safety cap on pages
            params = dict(base_params)
            params["cursor"] = cursor
            data = self._request(path, params)
            tweets = self._extract_tweets(data)
            collected.extend(tweets)
            if len(collected) >= max_results:
                break
            if not data.get("has_next_page") or not data.get("next_cursor"):
                break
            if not tweets:
                break
            cursor = data.get("next_cursor")
        raw = collected[:max_results]
        return [self._format_tweet(t, include_media=include_media) for t in raw]

    @staticmethod
    def _ok(payload: dict) -> str:
        out = dict(payload)
        out["success"] = True
        out["timestamp"] = datetime.now().isoformat()
        return json.dumps(out, ensure_ascii=False, indent=2)

    @staticmethod
    def _err(message: str, code: str = None) -> str:
        out = {"success": False, "error": message}
        if code:
            out["code"] = code
        return json.dumps(out, ensure_ascii=False)

    @staticmethod
    def _not_found(resource: str, name: str) -> str:
        """Consistent machine-readable 'missing resource' response.

        Every endpoint uses this shape so callers can branch on
        ``success == False and code == "not_found"``.
        """
        return json.dumps(
            {
                "success": False,
                "code": "not_found",
                "resource": resource,
                "error": f"{resource.capitalize()} '{name}' was not found.",
            },
            ensure_ascii=False,
        )

    # ---------------------------------------------------------- public tools

    def search_tweets(
        self,
        query: str = Field(
            ...,
            description=(
                "Search query. Supports operators like from:user, to:user, -is:retweet, "
                "min_faves:100, and OR."
            ),
        ),
        query_type: str = Field(
            "Latest", description="Sort order: 'Latest' (newest) or 'Top' (most engaging)."
        ),
        max_results: int = Field(
            15, description="Number of tweets to return (1-100). Paginated internally."
        ),
        lang: str = Field(
            "", description="Optional language filter, e.g. 'en'. Leave empty for no filter."
        ),
        since: str = Field(
            "",
            description="Optional start date (YYYY-MM-DD, ISO datetime, or unix timestamp).",
        ),
        until: str = Field(
            "",
            description="Optional end date (YYYY-MM-DD, ISO datetime, or unix timestamp).",
        ),
        include_media: bool = Field(
            False, description="If true, include media image URLs for each tweet."
        ),
    ) -> str:
        """
        Search recent posts on X (Twitter) using the twitterapi.io advanced search endpoint.
        Supports advanced operators, an optional language filter, and an optional date range.
        max_results is clamped to 1-100; a "note" is added whenever clamping occurs.
        """
        try:
            # Unwrap any FieldInfo defaults the runtime may pass through when the
            # model omits an optional parameter.
            query = self._resolve(query, "")
            query_type = self._resolve(query_type, self._cfg_query_type())
            max_results = self._resolve(max_results, self._cfg_max_results())
            lang = self._resolve(lang, "")
            since = self._resolve(since, "")
            until = self._resolve(until, "")
            include_media = self._resolve(include_media, self._cfg_include_media())
            query = (query or "").strip()
            if not query:
                return self._err("Query cannot be empty.")
            query_type = (query_type or "Latest").strip()
            if query_type not in ("Latest", "Top"):
                query_type = "Latest"
            max_results, clamp_note = self._clamp_max(max_results, self._cfg_max_results())

            final_query = query
            if lang:
                final_query += f" lang:{lang.strip()}"
            since_unix = self._to_unix(since)
            if since_unix:
                final_query += f" since_time:{since_unix}"
            until_unix = self._to_unix(until)
            if until_unix:
                final_query += f" until_time:{until_unix}"

            params = {"query": final_query, "queryType": query_type}
            tweets = self._paginate_tweets(
                "/twitter/tweet/advanced_search", params, max_results, include_media
            )
            payload = {
                "query": final_query,
                "query_type": query_type,
                "count": len(tweets),
                "tweets": tweets,
            }
            if clamp_note:
                payload["note"] = clamp_note
            return self._ok(payload)
        except Exception as e:
            return self._err(f"Search failed: {str(e)}")

    def get_user_tweets(
        self,
        username: str = Field(..., description="Username without the @ symbol."),
        max_results: int = Field(15, description="Number of tweets to return (1-100)."),
        include_replies: bool = Field(
            False, description="Whether to include replies."
        ),
        include_media: bool = Field(
            False, description="If true, include media image URLs for each tweet."
        ),
    ) -> str:
        """
        Get the latest tweets from a specific X (Twitter) user.
        If the user does not exist, returns success:false with code "not_found".
        max_results is clamped to 1-100 (a "note" is added when clamping occurs).
        """
        try:
            username = self._resolve(username, "")
            max_results = self._resolve(max_results, self._cfg_max_results())
            include_replies = self._resolve(include_replies, self._cfg_include_replies())
            include_media = self._resolve(include_media, self._cfg_include_media())
            username = (username or "").strip().lstrip("@")
            if not username:
                return self._err("Username cannot be empty.", code="invalid_input")
            max_results, clamp_note = self._clamp_max(max_results, self._cfg_max_results())
            params = {"userName": username, "includeReplies": bool(include_replies)}
            tweets = self._paginate_tweets(
                "/twitter/user/last_tweets", params, max_results, include_media
            )
            notes = [clamp_note] if clamp_note else []
            if not tweets:
                # last_tweets returns an empty list for both a missing user and a
                # real user with no recent tweets; disambiguate via /info.
                info = self._request("/twitter/user/info", {"userName": username})
                ok = isinstance(info, dict) and info.get("status") == "success"
                if not (ok and (info.get("data") or None)):
                    return self._not_found("user", username)
                notes.append("User exists but no recent tweets were returned.")
            payload = {"username": username, "count": len(tweets), "tweets": tweets}
            if notes:
                payload["note"] = " ".join(notes)
            return self._ok(payload)
        except Exception as e:
            return self._err(f"Failed to get user tweets: {str(e)}")

    def get_user_info(
        self,
        username: str = Field(..., description="Username without the @ symbol."),
    ) -> str:
        """
        Get detailed profile information about an X (Twitter) user.
        If the user does not exist, returns success:false with code "not_found".
        """
        try:
            username = self._resolve(username, "")
            username = (username or "").strip().lstrip("@")
            if not username:
                return self._err("Username cannot be empty.", code="invalid_input")
            data = self._request("/twitter/user/info", {"userName": username})
            ok = isinstance(data, dict) and data.get("status") == "success"
            u = (data or {}).get("data") if ok else None
            if not ok or not u:
                return self._not_found("user", username)
            info = {
                "id": u.get("id"),
                "username": u.get("userName"),
                "name": u.get("name"),
                "url": u.get("url"),
                "verified": u.get("isBlueVerified", False),
                "verified_type": u.get("verifiedType"),
                "description": u.get("description"),
                "location": u.get("location"),
                "followers": u.get("followers"),
                "following": u.get("following"),
                "favourites": u.get("favouritesCount"),
                "statuses": u.get("statusesCount"),
                "media_count": u.get("mediaCount"),
                "created_at": u.get("createdAt"),
                "profile_picture": u.get("profilePicture"),
            }
            return self._ok({"user": info})
        except Exception as e:
            return self._err(f"Failed to get user info: {str(e)}")

    def search_news_tweets(
        self,
        topic: str = Field("breaking news", description="Topic / keywords."),
        max_results: int = Field(15, description="Number of results (1-100)."),
        lang: str = Field("en", description="Language code."),
        query_type: str = Field("Latest", description="Sort order: 'Latest' or 'Top'."),
    ) -> str:
        """
        Search recent news tweets about a topic from major news accounts.

        Sources and lookback window are configurable via the news_accounts and
        news_freshness_hours valves (default 24h). The topic is always injected
        verbatim into the query (echoed in the "query" field); if it matches nothing
        in that window, the result is empty (count 0) with an explanatory "note".
        """
        try:
            topic = self._resolve(topic, "breaking news")
            max_results = self._resolve(max_results, self._cfg_max_results())
            lang = self._resolve(lang, "en")
            query_type = self._resolve(query_type, self._cfg_query_type())

            # Normalize the topic: collapse whitespace and drop characters that
            # would unbalance the (topic) group. It is always injected verbatim.
            topic = str(topic or "")
            topic = " ".join(topic.replace("(", " ").replace(")", " ").replace('"', " ").split())
            topic = topic or "breaking news"
            if len(topic) > 160:
                return self._err(
                    f"Topic too long ({len(topic)} chars, max 160). Shorten it and retry.",
                    code="topic_too_long",
                )
            max_results, clamp_note = self._clamp_max(max_results, self._cfg_max_results())
            if (query_type or "").strip() not in ("Latest", "Top"):
                query_type = "Latest"

            accounts_query = " OR ".join(f"from:{acc}" for acc in self._news_accounts())
            lang_suffix = f" lang:{lang.strip()}" if (lang or "").strip() else ""
            freshness_hours = self._news_freshness_hours()
            since_unix = int(time.time()) - freshness_hours * 3600

            # Single source of truth: this exact query is run and echoed back.
            query = f"({topic}) ({accounts_query}){lang_suffix} since_time:{since_unix}"
            tweets = self._paginate_tweets(
                "/twitter/tweet/advanced_search",
                {"query": query, "queryType": query_type},
                max_results,
                include_media=False,
            )

            payload = {
                "topic": topic,
                "query": query,
                "query_type": query_type,
                "freshness_window_hours": freshness_hours,
                "count": len(tweets),
                "tweets": tweets,
            }
            notes = [clamp_note] if clamp_note else []
            if not tweets:
                notes.append(
                    f"No tweets matched topic '{topic}' from the configured outlets "
                    f"in the last {freshness_hours}h. Try a broader topic, "
                    f"a different language, or search_tweets with a wider date range."
                )
            if notes:
                payload["note"] = " ".join(notes)
            return self._ok(payload)
        except Exception as e:
            return self._err(f"News search failed: {str(e)}")
