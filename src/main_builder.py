from datetime import datetime, timezone
import yaml
from pathlib import Path
from feed_reader import fetch_recent_articles
from summarizer_builder import summarize_builder
from email_sender import send_digest, render_builder_template


def main() -> None:
    config_path = Path(__file__).parent.parent / "config" / "feeds_builder.yaml"
    feeds = yaml.safe_load(config_path.read_text())["feeds"]

    articles = fetch_recent_articles(feeds, days=7)
    print(f"[Builder] Found {len(articles)} articles")

    date_str = datetime.now(timezone.utc).strftime("%d %B %Y")
    subject = f"💡 Weekly Builder Digest — {date_str}"

    if not articles:
        send_digest(subject, "<p>No updates this week.</p>", "No updates.")
        return

    digest = summarize_builder(articles)
    html, plain = render_builder_template(digest, articles, date_str)
    send_digest(subject, html, plain)
    print(f"[Builder] Sent. Articles: {len(articles)}, AI digest: {'yes' if digest else 'no (fallback)'}")


if __name__ == "__main__":
    main()
