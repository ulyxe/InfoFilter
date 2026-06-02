import feedparser
from datetime import datetime, timezone, timedelta

def fetch_recent_articles(feeds_config: list, days: int = 7) -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    articles = []

    for feed_cfg in feeds_config:
        try:
            d = feedparser.parse(feed_cfg['url'])
            for entry in d.entries:
                pub = entry.get('published_parsed') or entry.get('updated_parsed')
                if not pub:
                    continue
                pub_dt = datetime(*pub[:6], tzinfo=timezone.utc)
                if pub_dt < cutoff:
                    continue
                articles.append({
                    'title': entry.get('title', 'No title'),
                    'link': entry.get('link', ''),
                    'summary': entry.get('summary', '')[:500],
                    'published_iso': pub_dt.isoformat(),
                    'feed_name': feed_cfg['name'],
                    'tags': feed_cfg.get('tags', [])
                })
        except Exception as e:
            print(f"[WARN] Feed {feed_cfg['name']} failed: {e}")
            continue

    articles.sort(key=lambda x: x['published_iso'], reverse=True)
    return articles[:20]
