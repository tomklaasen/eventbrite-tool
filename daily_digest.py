#!/usr/bin/env python3
"""
Sends a daily digest email when new registrations have come in for the next
upcoming Eventbrite event.

Compares current attendees against a snapshot from the previous run.
Only sends an email if there are new registrations since the last run.

Setup:
    Add to .env:
        GMAIL_USER=you@gmail.com
        GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx   # Gmail App Password
        DIGEST_TO=recipient@example.com

    Schedule with cron (once daily at 18:00):
        0 18 * * * /path/to/eventbrite-tool/start_digest.sh

Requirements: same as generate_report.py (requests, python-dotenv)
"""

import json
import os
import smtplib
import sys
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Missing dependency: run  pip install requests python-dotenv")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    sys.exit("Missing dependency: run  pip install requests python-dotenv")


API_BASE = "https://www.eventbriteapi.com/v3"
SNAPSHOT_DIR = Path("output")


def get_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def fetch_organization_id(token: str) -> str:
    url = f"{API_BASE}/users/me/organizations/"
    r = requests.get(url, headers=get_headers(token))
    r.raise_for_status()
    orgs = r.json().get("organizations", [])
    if not orgs:
        sys.exit("No organizations found for your account.")
    return orgs[0]["id"]


def fetch_next_event(token: str, org_id: str) -> dict:
    url = f"{API_BASE}/organizations/{org_id}/events/"
    params = {"status": "live,started", "order_by": "start_asc", "page_size": 1, "expand": "venue"}
    r = requests.get(url, headers=get_headers(token), params=params)
    r.raise_for_status()
    events = r.json().get("events", [])
    if not events:
        sys.exit("No upcoming events found.")
    return events[0]


def fetch_all_attendees(token: str, event_id: str) -> list[dict]:
    attendees = []
    url = f"{API_BASE}/events/{event_id}/attendees/"
    params = {}
    while url:
        r = requests.get(url, headers=get_headers(token), params=params)
        r.raise_for_status()
        data = r.json()
        attendees.extend(data.get("attendees", []))
        pagination = data.get("pagination", {})
        url = pagination.get("next_url") if pagination.get("has_more_items") else None
        params = {}
    return attendees


def load_snapshot(event_id: str) -> dict:
    path = SNAPSHOT_DIR / f"snapshot_{event_id}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_snapshot(event_id: str, snapshot: dict) -> None:
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    path = SNAPSHOT_DIR / f"snapshot_{event_id}.json"
    path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_email(event: dict, new_attendees: list[dict], all_confirmed: list[dict]) -> tuple[str, str]:
    """Return (subject, html_body)."""
    title = event.get("name", {}).get("text", "Untitled Event")
    event_date = event.get("start", {}).get("local", "")[:10]
    total = len(all_confirmed)
    count = len(new_attendees)

    subject = f"{count} new registration{'s' if count != 1 else ''} for {title}"

    def attendee_rows(attendees: list[dict]) -> str:
        rows = []
        for i, a in enumerate(attendees, start=1):
            p = a.get("profile", {})
            first = p.get("first_name", "") or ""
            last = p.get("last_name", "") or ""
            company = p.get("company", "") or ""
            rows.append(
                f"<tr><td>{i}</td><td>{first}</td><td>{last}</td><td>{company}</td></tr>"
            )
        return "\n".join(rows)

    table_style = (
        "border-collapse:collapse;width:100%;font-size:13px;"
    )
    th_style = (
        "background:#f0f0f0;border:1px solid #ccc;padding:6px 10px;text-align:left;"
    )
    td_style = "border:1px solid #ccc;padding:6px 10px;"

    def make_table(attendees: list[dict]) -> str:
        return f"""
<table style="{table_style}">
  <thead>
    <tr>
      <th style="{th_style}">#</th>
      <th style="{th_style}">First Name</th>
      <th style="{th_style}">Last Name</th>
      <th style="{th_style}">Company</th>
    </tr>
  </thead>
  <tbody>
    {attendee_rows(attendees)}
  </tbody>
</table>"""

    # Inject td style via a quick replace since we're building HTML as strings
    new_table = make_table(new_attendees).replace("<td>", f'<td style="{td_style}">')
    all_table = make_table(all_confirmed).replace("<td>", f'<td style="{td_style}">')

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:sans-serif;font-size:14px;color:#111;margin:0;padding:20px;">
  <h2 style="margin-bottom:4px;">{title}</h2>
  <p style="color:#666;margin-top:0;">{event_date}</p>

  <h3>New registrations ({count})</h3>
  {new_table}

  <h3 style="margin-top:32px;">All registrations ({total})</h3>
  {all_table}

  <p style="color:#999;font-size:11px;margin-top:32px;">
    Sent by eventbrite-tool on {datetime.now().strftime('%Y-%m-%d at %H:%M')}
  </p>
</body>
</html>"""

    return subject, html


def ping_healthchecks(url: str, suffix: str = "") -> None:
    """Ping a healthchecks.io URL. suffix is '' for success, '/fail' for failure."""
    if not url:
        return
    try:
        requests.get(url.rstrip("/") + suffix, timeout=10)
    except Exception as e:
        print(f"Warning: healthchecks.io ping failed: {e}")


def send_email(subject: str, html: str, gmail_user: str, app_password: str, to: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = to
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(gmail_user, app_password)
        server.sendmail(gmail_user, to, msg.as_string())


def main():
    token = os.environ.get("EVENTBRITE_TOKEN")
    gmail_user = os.environ.get("GMAIL_USER")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    digest_to = os.environ.get("DIGEST_TO")
    healthchecks_url = os.environ.get("HEALTHCHECKS_URL")

    missing = [k for k, v in {
        "EVENTBRITE_TOKEN": token,
        "GMAIL_USER": gmail_user,
        "GMAIL_APP_PASSWORD": app_password,
        "DIGEST_TO": digest_to,
    }.items() if not v]
    if missing:
        sys.exit(f"Missing environment variable(s): {', '.join(missing)}")

    ping_healthchecks(healthchecks_url, "/start")

    try:
        org_id = fetch_organization_id(token)
        event = fetch_next_event(token, org_id)
        event_id = event["id"]
        title = event.get("name", {}).get("text", event_id)
        print(f"Event: {title} (ID: {event_id})")

        snapshot = load_snapshot(event_id)
        known_ids = set(snapshot.keys())

        attendees = fetch_all_attendees(token, event_id)
        confirmed = [
            a for a in attendees
            if a.get("status", "").lower() in ("attending", "checked_in")
        ]
        confirmed.sort(key=lambda a: a.get("profile", {}).get("first_name", "").lower())

        new_attendees = [a for a in confirmed if a["id"] not in known_ids]

        if not new_attendees:
            print("No new registrations since last run. No email sent.")
            ping_healthchecks(healthchecks_url)
            return

        print(f"New registrations: {len(new_attendees)}")

        # Update snapshot with all current confirmed attendees
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for a in confirmed:
            if a["id"] not in snapshot:
                p = a.get("profile", {})
                snapshot[a["id"]] = {
                    "first_seen": today,
                    "first_name": p.get("first_name", ""),
                    "last_name": p.get("last_name", ""),
                    "company": p.get("company", ""),
                }
        save_snapshot(event_id, snapshot)

        subject, html = build_email(event, new_attendees, confirmed)
        send_email(subject, html, gmail_user, app_password, digest_to)
        print(f"Email sent to {digest_to}: {subject}")
        ping_healthchecks(healthchecks_url)

    except Exception as e:
        ping_healthchecks(healthchecks_url, "/fail")
        raise


if __name__ == "__main__":
    main()
