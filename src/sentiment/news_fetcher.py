"""News fetching from multiple free sources."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote

import feedparser
import httpx
import structlog

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)


@dataclass
class NewsArticle:
    title: str
    source: str
    url: str
    summary: str
    published_at: Optional[datetime]
    relevance_score: float = 0.0


class NewsFetcher:
    """Fetches news from GDELT, NewsAPI, Google News RSS, and Reddit."""

    def __init__(self) -> None:
        settings = get_settings()
        self._news_api_key = settings.news_api_key
        self._gdelt_url = settings.gdelt_api_url
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(20.0),
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def fetch_all(self, query: str, max_per_source: int = 10) -> list[NewsArticle]:
        """Fetch news from all available sources."""
        results: list[NewsArticle] = []

        sources = [
            self._fetch_google_news_rss(query, max_per_source),
            self._fetch_gdelt(query, max_per_source),
            self._fetch_reddit(query, max_per_source),
            self._fetch_hackernews(query, max_per_source),
        ]

        if self._news_api_key:
            sources.append(self._fetch_newsapi(query, max_per_source))

        import asyncio
        gathered = await asyncio.gather(*sources, return_exceptions=True)

        for result in gathered:
            if isinstance(result, list):
                results.extend(result)
            elif isinstance(result, Exception):
                logger.warning("news_source_error", error=str(result))

        results.sort(key=lambda a: a.relevance_score, reverse=True)
        return results

    async def _fetch_google_news_rss(self, query: str, limit: int) -> list[NewsArticle]:
        """Fetch from Google News RSS feed."""
        try:
            url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
            client = await self._get_client()
            resp = await client.get(url)
            resp.raise_for_status()

            feed = feedparser.parse(resp.text)
            articles: list[NewsArticle] = []

            for entry in feed.entries[:limit]:
                pub_date = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    except (ValueError, TypeError):
                        pass

                articles.append(
                    NewsArticle(
                        title=entry.get("title", ""),
                        source="Google News",
                        url=entry.get("link", ""),
                        summary=entry.get("summary", "")[:500],
                        published_at=pub_date,
                        relevance_score=0.7,
                    )
                )
            return articles
        except Exception as exc:
            logger.warning("google_news_error", error=str(exc))
            return []

    async def _fetch_gdelt(self, query: str, limit: int) -> list[NewsArticle]:
        """Fetch from GDELT API."""
        try:
            client = await self._get_client()
            params = {
                "query": query,
                "mode": "ArtList",
                "maxrecords": str(limit),
                "format": "json",
                "timespan": "7d",
            }
            resp = await client.get(self._gdelt_url, params=params)
            resp.raise_for_status()
            data = resp.json()

            articles: list[NewsArticle] = []
            for art in data.get("articles", [])[:limit]:
                pub_date = None
                if art.get("seendate"):
                    try:
                        pub_date = datetime.strptime(
                            art["seendate"][:14], "%Y%m%d%H%M%S"
                        ).replace(tzinfo=timezone.utc)
                    except (ValueError, TypeError):
                        pass

                articles.append(
                    NewsArticle(
                        title=art.get("title", ""),
                        source="GDELT",
                        url=art.get("url", ""),
                        summary=art.get("title", ""),
                        published_at=pub_date,
                        relevance_score=0.6,
                    )
                )
            return articles
        except Exception as exc:
            logger.warning("gdelt_error", error=str(exc))
            return []

    async def _fetch_newsapi(self, query: str, limit: int) -> list[NewsArticle]:
        """Fetch from NewsAPI.org."""
        try:
            client = await self._get_client()
            from_date = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
            params = {
                "q": query,
                "from": from_date,
                "sortBy": "relevancy",
                "pageSize": str(limit),
                "apiKey": self._news_api_key,
                "language": "en",
            }
            resp = await client.get("https://newsapi.org/v2/everything", params=params)
            resp.raise_for_status()
            data = resp.json()

            articles: list[NewsArticle] = []
            for art in data.get("articles", [])[:limit]:
                pub_date = None
                if art.get("publishedAt"):
                    try:
                        pub_date = datetime.fromisoformat(
                            art["publishedAt"].replace("Z", "+00:00")
                        )
                    except (ValueError, TypeError):
                        pass

                articles.append(
                    NewsArticle(
                        title=art.get("title", ""),
                        source=art.get("source", {}).get("name", "NewsAPI"),
                        url=art.get("url", ""),
                        summary=(art.get("description") or "")[:500],
                        published_at=pub_date,
                        relevance_score=0.8,
                    )
                )
            return articles
        except Exception as exc:
            logger.warning("newsapi_error", error=str(exc))
            return []

    async def _fetch_reddit(self, query: str, limit: int) -> list[NewsArticle]:
        """Fetch from Reddit search (public JSON API)."""
        try:
            client = await self._get_client()
            url = f"https://www.reddit.com/search.json?q={quote(query)}&sort=relevance&t=week&limit={limit}"
            headers = {"User-Agent": "PolymarketBot/1.0"}
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            articles: list[NewsArticle] = []
            for child in data.get("data", {}).get("children", [])[:limit]:
                post = child.get("data", {})
                pub_date = None
                if post.get("created_utc"):
                    try:
                        pub_date = datetime.fromtimestamp(
                            post["created_utc"], tz=timezone.utc
                        )
                    except (ValueError, TypeError, OSError):
                        pass

                articles.append(
                    NewsArticle(
                        title=post.get("title", ""),
                        source=f"Reddit r/{post.get('subreddit', 'unknown')}",
                        url=f"https://reddit.com{post.get('permalink', '')}",
                        summary=(post.get("selftext") or "")[:500],
                        published_at=pub_date,
                        relevance_score=0.5,
                    )
                )
            return articles
        except Exception as exc:
            logger.warning("reddit_error", error=str(exc))
            return []

    async def _fetch_hackernews(self, query: str, limit: int) -> list[NewsArticle]:
        """Fetch from Hacker News Algolia API."""
        try:
            client = await self._get_client()
            params = {"query": query, "tags": "story", "hitsPerPage": str(limit)}
            resp = await client.get(
                "https://hn.algolia.com/api/v1/search_by_date", params=params
            )
            resp.raise_for_status()
            data = resp.json()

            articles: list[NewsArticle] = []
            for hit in data.get("hits", [])[:limit]:
                pub_date = None
                if hit.get("created_at"):
                    try:
                        pub_date = datetime.fromisoformat(
                            hit["created_at"].replace("Z", "+00:00")
                        )
                    except (ValueError, TypeError):
                        pass

                articles.append(
                    NewsArticle(
                        title=hit.get("title", ""),
                        source="Hacker News",
                        url=hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}",
                        summary=hit.get("title", ""),
                        published_at=pub_date,
                        relevance_score=0.4,
                    )
                )
            return articles
        except Exception as exc:
            logger.warning("hackernews_error", error=str(exc))
            return []

    def build_news_context(self, articles: list[NewsArticle], max_articles: int = 5) -> str:
        """Build a news context string for AI analysis."""
        if not articles:
            return "No recent news found."

        lines: list[str] = []
        for art in articles[:max_articles]:
            date_str = art.published_at.strftime("%Y-%m-%d") if art.published_at else "recent"
            lines.append(f"- [{date_str}] {art.title} (via {art.source})")
            if art.summary and art.summary != art.title:
                lines.append(f"  {art.summary[:200]}")

        return "\n".join(lines)
