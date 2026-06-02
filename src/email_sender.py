import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from string import Template
from pathlib import Path


def send_digest(subject: str, html_body: str, plain_body: str) -> None:
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    sender = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    recipient = os.environ["DIGEST_RECIPIENT_EMAIL"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(host, port) as server:
        server.ehlo()
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())
    print(f"[OK] Email sent to {recipient}")


def _action_card_html(action: dict, accent_color: str) -> str:
    """Renders the 'Prova questa settimana' card. Shared by both templates."""
    if not action:
        return ""
    return f"""
    <div style="background:#1a2235;border-left:4px solid {accent_color};padding:20px;margin:16px 0;border-radius:4px;">
      <p style="margin:0 0 6px 0;font-size:11px;color:{accent_color};text-transform:uppercase;letter-spacing:1px;">🎯 Prova questa settimana</p>
      <h3 style="margin:0 0 10px 0;color:#f1f5f9;font-size:18px;">{action.get('title','')}</h3>
      <p style="margin:0 0 8px 0;color:#cbd5e1;">{action.get('what','')}</p>
      <p style="margin:0 0 12px 0;color:#94a3b8;font-size:14px;"><em>Perché: {action.get('why','')}</em></p>
      <span style="display:inline-block;background:{accent_color};color:#0f172a;font-size:12px;font-weight:bold;padding:4px 10px;border-radius:12px;">⏱ {action.get('time_required','')}</span>
    </div>"""


def render_engineer_template(digest: dict | None, articles: list, date_str: str) -> tuple[str, str]:
    template_path = Path(__file__).parent.parent / "templates" / "email.html"
    template = Template(template_path.read_text(encoding="utf-8"))

    if digest:
        highlights_html = ""
        for h in digest.get("highlights", []):
            highlights_html += f"""
            <div style="background:#1e293b;padding:20px;margin:12px 0;border-radius:6px;border-left:3px solid #6366f1;">
              <div style="font-size:11px;color:#6366f1;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;">{h['source']}</div>
              <h3 style="margin:0 0 8px 0;"><a href="{h['url']}" style="color:#818cf8;text-decoration:none;">{h['title']}</a></h3>
              <p style="color:#cbd5e1;margin:0 0 8px 0;">{h['summary']}</p>
              <p style="color:#94a3b8;font-size:13px;margin:0;">💡 {h['relevance']}</p>
            </div>"""

        action_html = _action_card_html(digest.get("action_of_the_week"), "#6366f1")

        html = template.substitute(
            date=date_str,
            intro=digest.get("intro", ""),
            highlights=highlights_html,
            tip=digest.get("tip_of_the_week", ""),
            action_of_the_week=action_html,
            article_count=len(articles)
        )
        plain = f"Weekly AI Digest — {date_str}\n\n{digest.get('intro','')}\n\n" + \
                "\n".join([f"- {h['title']} ({h['source']})\n  {h['url']}"
                           for h in digest.get('highlights', [])]) + \
                f"\n\n🎯 PROVA QUESTA SETTIMANA: {digest.get('action_of_the_week',{}).get('title','')}\n" + \
                digest.get('action_of_the_week',{}).get('what','')
    else:
        links = "\n".join([f"- [{a['feed_name']}] {a['title']}\n  {a['link']}" for a in articles])
        html = f"<h2>Weekly AI Digest — {date_str}</h2><p>AI summary unavailable.</p><pre>{links}</pre>"
        plain = f"Weekly AI Digest — {date_str}\n\n{links}"

    return html, plain


def render_builder_template(digest: dict | None, articles: list, date_str: str) -> tuple[str, str]:
    template_path = Path(__file__).parent.parent / "templates" / "email_builder.html"
    template = Template(template_path.read_text(encoding="utf-8"))

    if digest:
        ideas_html = ""
        for idea in digest.get("business_ideas", []):
            effort_color = {"basso": "#22c55e", "medio": "#f59e0b", "alto": "#ef4444"}.get(idea.get("effort", ""), "#6366f1")
            idea_url = idea.get("source_url") or "#"
            ideas_html += f"""
            <div style="background:#111827;padding:20px;margin:12px 0;border-radius:6px;border-left:3px solid #f59e0b;">
              <span style="display:inline-block;background:{effort_color};color:#0a0f1e;font-size:11px;font-weight:bold;padding:3px 8px;border-radius:10px;margin-bottom:10px;">Effort: {idea.get('effort','?')}</span>
              <h3 style="margin:0 0 8px 0;color:#f1f5f9;">{idea['title']}</h3>
              <p style="color:#cbd5e1;margin:0 0 8px 0;">{idea['description']}</p>
              <p style="color:#cbd5e1;margin:0 0 8px 0;"><strong style="color:#f59e0b;">⚡ Perché ora:</strong> {idea['why_now']}</p>
              <p style="color:#cbd5e1;margin:0 0 12px 0;border-left:3px solid #10b981;padding-left:10px;">🇮🇹 <strong>Italy angle:</strong> {idea['italy_angle']}</p>
              <a href="{idea_url}" style="color:#fbbf24;font-size:13px;">Leggi la fonte →</a>
            </div>"""

        pattern = digest.get("agentic_pattern", {})
        tools_list = "".join([f"<li style='color:#cbd5e1;margin:4px 0;'>{t}</li>" for t in pattern.get("tools", [])])
        pattern_html = f"""
        <div style="background:#111827;padding:20px;margin:12px 0;border-radius:6px;border-left:3px solid #10b981;">
          <h3 style="margin:0 0 10px 0;color:#f1f5f9;">🤖 {pattern.get('title','Pattern della settimana')}</h3>
          <p style="color:#cbd5e1;margin:0 0 8px 0;">{pattern.get('description','')}</p>
          <p style="color:#cbd5e1;margin:0 0 8px 0;"><strong style="color:#10b981;">Use case:</strong> {pattern.get('use_case','')}</p>
          <ul style="margin:8px 0;padding-left:20px;">{tools_list}</ul>
        </div>"""

        case = digest.get("case_study", {})
        case_url = case.get("source_url") or "#"
        case_html = f"""
        <div style="background:#111827;padding:20px;margin:12px 0;border-radius:6px;border-left:3px solid #f59e0b;">
          <h3 style="margin:0 0 10px 0;color:#f1f5f9;">📖 {case.get('title','Caso Studio')}</h3>
          <p style="color:#cbd5e1;margin:0 0 8px 0;">{case.get('summary','')}</p>
          <p style="color:#94a3b8;font-size:14px;margin:0 0 12px 0;font-style:italic;">💡 {case.get('lesson','')}</p>
          <a href="{case_url}" style="color:#fbbf24;font-size:13px;">Leggi →</a>
        </div>"""

        action_html = _action_card_html(digest.get("action_of_the_week"), "#f59e0b")

        html = template.substitute(
            date=date_str,
            intro=digest.get("intro", ""),
            business_ideas=ideas_html,
            agentic_pattern=pattern_html,
            case_study=case_html,
            tip=digest.get("tip_of_the_week", ""),
            action_of_the_week=action_html,
            article_count=len(articles)
        )
        plain = f"Weekly Builder Digest — {date_str}\n\n{digest.get('intro','')}\n\n" + \
                "\n".join([f"- {a['title']} ({a['feed_name']})\n  {a['link']}" for a in articles]) + \
                f"\n\n🎯 PROVA QUESTA SETTIMANA: {digest.get('action_of_the_week',{}).get('title','')}\n" + \
                digest.get('action_of_the_week',{}).get('what','')
    else:
        links = "\n".join([f"- [{a['feed_name']}] {a['title']}\n  {a['link']}" for a in articles])
        html = f"<h2>Weekly Builder Digest — {date_str}</h2><pre>{links}</pre>"
        plain = f"Weekly Builder Digest — {date_str}\n\n{links}"

    return html, plain
