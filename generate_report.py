#!/usr/bin/env python3
"""
Generates a Markdown report for your next upcoming Eventbrite event.

Requirements:
    python3 -m venv .venv
    source .venv/bin/activate
    pip install requests python-dotenv markdown weasyprint

Usage:
    cp .env.example .env
    # Edit .env and fill in your token
    python3 generate_report.py
"""

import csv
import io
import os
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Missing dependency: run  pip3 install requests python-dotenv")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    sys.exit("Missing dependency: run  pip install requests python-dotenv markdown weasyprint")

try:
    import markdown
    from weasyprint import HTML
except ImportError:
    sys.exit("Missing dependency: run  pip install requests python-dotenv markdown weasyprint")


API_BASE = "https://www.eventbriteapi.com/v3"


def get_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def fetch_organization_id(token: str) -> str:
    """Return the first organization ID for the authenticated user."""
    url = f"{API_BASE}/users/me/organizations/"
    response = requests.get(url, headers=get_headers(token))
    response.raise_for_status()
    orgs = response.json().get("organizations", [])
    if not orgs:
        sys.exit("No organizations found for your account.")
    return orgs[0]["id"]


def fetch_next_event(token: str, org_id: str) -> dict:
    """Return the soonest upcoming event for the given organization."""
    url = f"{API_BASE}/organizations/{org_id}/events/"
    params = {
        "status": "live,started",
        "order_by": "start_asc",
        "page_size": 1,
        "expand": "venue",
    }
    response = requests.get(url, headers=get_headers(token), params=params)
    response.raise_for_status()
    data = response.json()

    events = data.get("events", [])
    if not events:
        sys.exit("No upcoming events found for your organization.")

    return events[0]


def fetch_all_attendees(token: str, event_id: str) -> list[dict]:
    """Fetch every attendee for the given event, handling pagination."""
    attendees = []
    url = f"{API_BASE}/events/{event_id}/attendees/"
    params = {}

    while url:
        response = requests.get(url, headers=get_headers(token), params=params)
        response.raise_for_status()
        data = response.json()

        attendees.extend(data.get("attendees", []))

        pagination = data.get("pagination", {})
        url = pagination.get("next_url") if not pagination.get("has_more_items") is False else None
        # Prefer next_url when provided; fall back to has_more_items logic
        if pagination.get("has_more_items"):
            url = pagination.get("next_url")
        else:
            url = None

        params = {}  # params are already encoded in next_url

    return attendees


def format_date(iso_string: str) -> str:
    """Convert an ISO 8601 datetime string to a human-readable format."""
    try:
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        return dt.strftime("%A, %B %-d %Y at %H:%M")
    except (ValueError, AttributeError):
        return iso_string


def write_csv(attendees: list[dict], csv_path: Path) -> None:
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["#", "First Name", "Last Name", "Company"])
        for i, attendee in enumerate(attendees, start=1):
            profile = attendee.get("profile", {})
            writer.writerow([
                i,
                profile.get("first_name", ""),
                profile.get("last_name", ""),
                profile.get("company", ""),
            ])


def markdown_to_pdf(md_text: str, pdf_path: Path) -> None:
    html_body = markdown.markdown(md_text, extensions=["tables"])
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: sans-serif; font-size: 13px; margin: 40px; color: #111; }}
  h1 {{ font-size: 22px; margin-bottom: 4px; }}
  h2 {{ font-size: 16px; margin-top: 24px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 8px; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; }}
  th {{ background: #f0f0f0; }}
  hr {{ border: none; border-top: 1px solid #ddd; margin: 16px 0; }}
  em {{ color: #666; }}
</style>
</head>
<body>{html_body}</body>
</html>"""
    HTML(string=html).write_pdf(pdf_path)


def build_report(event: dict, attendees: list[dict]) -> str:
    title = event.get("name", {}).get("text", "Untitled Event")
    start_iso = event.get("start", {}).get("local", "")
    date_str = format_date(start_iso)

    venue = event.get("venue")
    location = (
        venue.get("name", "") if venue else "Online / TBD"
    )

    # Only count attendees who actually completed their order
    confirmed = [
        a for a in attendees
        if a.get("status", "").lower() in ("attending", "checked_in")
    ]
    total = len(confirmed)

    lines = [
        f"# {title}",
        "",
        f"**Date:** {date_str}  ",
        f"**Location:** {location}  ",
        f"**Registrations:** {total}  ",
        "",
        "---",
        "",
        "## Attendees",
        "",
        "| # | First Name | Last Name | Company |",
        "|---|------------|-----------|---------|",
    ]

    confirmed.sort(key=lambda a: a.get("profile", {}).get("first_name", "").lower())

    for i, attendee in enumerate(confirmed, start=1):
        profile = attendee.get("profile", {})
        first = profile.get("first_name", "—") or "—"
        last = profile.get("last_name", "—") or "—"
        company = profile.get("company", "—") or "—"
        lines.append(f"| {i} | {first} | {last} | {company} |")

    lines += [
        "",
        "---",
        "",
        f"*Report generated on {datetime.now().strftime('%Y-%m-%d at %H:%M')}*",
    ]

    return "\n".join(lines)


def generate_badges(attendees: list[dict], output_dir: Path, stem: str) -> None:
    """Generate a badges CSV and matching .lbx file for P-touch Editor.

    The .lbx is a copy of the template with its database reference updated to
    point to the CSV sitting next to it. Open the .lbx in P-touch Editor and
    use Print > Print All Records to print every badge.
    """
    lbx_template = Path("badges.lbx")
    if not lbx_template.exists():
        print("badges.lbx not found — skipping badge generation.")
        return

    # Write the badges CSV with the column names the template expects
    csv_path = output_dir / f"{stem}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["First Name", "Surname", "Company"])
        for attendee in attendees:
            profile = attendee.get("profile", {})
            writer.writerow([
                profile.get("first_name", ""),
                profile.get("last_name", ""),
                profile.get("company", ""),
            ])

    # Build a new .lbx pointing to the CSV — replace only the path attributes
    # using string substitution to keep the original XML structure intact.
    with zipfile.ZipFile(lbx_template, "r") as zin:
        xml = zin.read("label.xml").decode("utf-8")
        other_files = {n: zin.read(n) for n in zin.namelist() if n != "label.xml"}

    abs_csv = str(csv_path.resolve())
    xml = re.sub(r'databasePath="[^"]*"', f'databasePath="{abs_csv}"', xml)
    xml = re.sub(r'mergeTable="[^"]*"', f'mergeTable="{csv_path.name}"', xml)
    xml = re.sub(
        r'(<database:dbTable name=")[^"]*(")',
        rf'\g<1>{csv_path.name}\g<2>',
        xml,
    )

    lbx_path = output_dir / f"{stem}.lbx"
    with zipfile.ZipFile(lbx_path, "w", zipfile.ZIP_DEFLATED) as zout:
        zout.writestr("label.xml", xml.encode("utf-8"))
        for name, data in other_files.items():
            zout.writestr(name, data)


def main():
    token = os.environ.get("EVENTBRITE_TOKEN")
    if not token:
        sys.exit(
            "Error: EVENTBRITE_TOKEN is not set.\n"
            "Copy .env.example to .env and fill in your private token.\n"
            "You can create a token at https://www.eventbrite.com/platform/api-keys"
        )

    print("Fetching your next event...")
    org_id = fetch_organization_id(token)
    event = fetch_next_event(token, org_id)
    event_id = event["id"]
    title = event.get("name", {}).get("text", event_id)

    print(f"Found: {title}")
    print("Fetching attendees...")
    attendees = fetch_all_attendees(token, event_id)
    attendees.append({
        "status": "Attending",
        "profile": {"first_name": "Tom", "last_name": "Klaasen", "company": "SoftwareCaptains"},
    })

    report = build_report(event, attendees)

    # Write report to a file named after the event id
    safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in title)
    safe_title = safe_title.strip().replace(" ", "_")[:60]
    event_date = event.get("start", {}).get("local", "")[:10]  # YYYY-MM-DD
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"report_{event_date}_{safe_title}.md"
    output_path.write_text(report, encoding="utf-8")
    print(f"Markdown written to: {output_path}")

    pdf_path = output_path.with_suffix(".pdf")
    markdown_to_pdf(report, pdf_path)
    print(f"PDF written to:      {pdf_path}")

    csv_path = output_path.with_suffix(".csv")
    confirmed = sorted(
        (a for a in attendees if a.get("status", "").lower() in ("attending", "checked_in")),
        key=lambda a: a.get("profile", {}).get("first_name", "").lower(),
    )
    write_csv(confirmed, csv_path)
    print(f"CSV written to:      {csv_path}")

    # Fixed filename so P-touch Editor retains its CSV access permission
    # across runs (macOS security-scoped bookmark stored by P-touch is path-based).
    generate_badges(confirmed, output_dir, "badges")
    print(f"Badges written to:   {output_dir / 'badges'}.lbx")


if __name__ == "__main__":
    main()
