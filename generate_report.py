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
    python3 generate_report.py           # next upcoming event (+ badges)
    python3 generate_report.py --past    # all past events (no badges)
"""

import argparse
import csv
import io
import json
import os
import re
import sys
import unicodedata
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


def fetch_all_past_events(token: str, org_id: str) -> list[dict]:
    """Return all ended/completed events for the organization, oldest first."""
    events = []
    url = f"{API_BASE}/organizations/{org_id}/events/"
    params = {
        "status": "ended,completed",
        "order_by": "start_asc",
        "expand": "venue",
    }
    while url:
        response = requests.get(url, headers=get_headers(token), params=params)
        response.raise_for_status()
        data = response.json()
        events.extend(data.get("events", []))
        pagination = data.get("pagination", {})
        url = pagination.get("next_url") if pagination.get("has_more_items") else None
        params = {}
    return events


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
    params = {"expand": "answers"}

    while url:
        response = requests.get(url, headers=get_headers(token), params=params)
        if response.status_code == 400 and params.get("expand") == "answers":
            print("  Warning: expand=answers not supported, retrying without it.")
            params.pop("expand")
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
        writer.writerow(["#", "First Name", "Last Name", "Company", "Diet"])
        for i, attendee in enumerate(attendees, start=1):
            profile = attendee.get("profile", {})
            writer.writerow([
                i,
                profile.get("first_name", ""),
                profile.get("last_name", ""),
                profile.get("company", ""),
                _get_diet_answer(attendee),
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
        "| # | First Name | Last Name | Company | Diet |",
        "|---|------------|-----------|---------|------|",
    ]

    confirmed.sort(key=lambda a: a.get("profile", {}).get("first_name", "").lower())

    for i, attendee in enumerate(confirmed, start=1):
        profile = attendee.get("profile", {})
        first = profile.get("first_name", "—") or "—"
        last = profile.get("last_name", "—") or "—"
        company = profile.get("company", "—") or "—"
        diet = _get_diet_answer(attendee)
        lines.append(f"| {i} | {first} | {last} | {company} | {diet} |")

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


def load_name_mappings() -> dict[str, tuple[str, str]]:
    """Load name_mappings.json and return a dict of normalized_key -> (first, last)."""
    path = Path("name_mappings.json")
    if not path.exists():
        return {}
    mappings = {}
    for typo, canonical in json.loads(path.read_text(encoding="utf-8")).items():
        parts = canonical.strip().split(None, 1)
        first = parts[0] if parts else ""
        last  = parts[1] if len(parts) > 1 else ""
        mappings[_normalize_name(typo)] = (first, last)
    return mappings


def _normalize_name(s: str) -> str:
    """Lowercase and strip diacritics for deduplication keys."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def _get_diet_answer(attendee: dict) -> str:
    """Return the diet restriction answer for an attendee, or '—' if none."""
    for answer in attendee.get("answers", []):
        question = answer.get("question", "")
        if "dieet" in question.lower():
            text = answer.get("answer", "").strip()
            return text if text else "—"
    return "—"


def build_attendance_report(token: str, org_id: str) -> tuple[str, list[dict]]:
    """Return a Markdown report and sorted rows of attendance counts per person."""
    print("Fetching all past events...")
    events = fetch_all_past_events(token, org_id)
    if not events:
        sys.exit("No past events found for your organization.")
    print(f"Found {len(events)} past event(s). Fetching attendees...\n")

    name_mappings = load_name_mappings()

    # Keyed by normalized full name for deduplication
    counts: dict[str, dict] = {}

    for event in events:
        title = event.get("name", {}).get("text", event["id"])
        event_date = event.get("start", {}).get("local", "")[:10]
        print(f"  {event_date}  {title}")

        attendees = fetch_all_attendees(token, event["id"])

        for attendee in attendees:
            if attendee.get("status", "").lower() not in ("attending", "checked_in"):
                continue
            profile = attendee.get("profile", {})
            first = profile.get("first_name", "").strip()
            last  = profile.get("last_name", "").strip()
            key = f"{_normalize_name(first)} {_normalize_name(last)}".strip()
            if not key:
                continue
            # Apply typo mapping if present
            if key in name_mappings:
                first, last = name_mappings[key]
                key = f"{_normalize_name(first)} {_normalize_name(last)}".strip()
            if key not in counts:
                counts[key] = {
                    "first_name": first,
                    "last_name":  last,
                    "company":    profile.get("company", ""),
                    "count":      0,
                }
            elif not counts[key]["company"] and profile.get("company"):
                # Fill in company if we didn't have it yet
                counts[key]["company"] = profile.get("company", "")
            counts[key]["count"] += 1

    rows = sorted(
        counts.values(),
        key=lambda r: (-r["count"], r["first_name"].lower()),
    )
    total_people = len(rows)
    total_events = len(events)

    lines = [
        "# Attendance Overview",
        "",
        f"**Total events:** {total_events}  ",
        f"**Total unique attendees:** {total_people}  ",
        "",
        "---",
        "",
        "## Attendees by number of events",
        "",
        "| # | First Name | Last Name | Company | Events attended |",
        "|---|------------|-----------|---------|-----------------|",
    ]
    for i, row in enumerate(rows, start=1):
        lines.append(
            f"| {i} | {row['first_name']} | {row['last_name']} | {row['company']} | {row['count']} |"
        )

    lines += [
        "",
        "---",
        "",
        f"*Report generated on {datetime.now().strftime('%Y-%m-%d at %H:%M')}*",
    ]

    return "\n".join(lines), rows


def process_event(token: str, event: dict, output_dir: Path, badges: bool = False) -> None:
    """Fetch attendees and write all report files for a single event."""
    title = event.get("name", {}).get("text", event["id"])
    print(f"  Processing: {title}")

    attendees = fetch_all_attendees(token, event["id"])
    attendees.append({
        "status": "Attending",
        "profile": {"first_name": "Tom", "last_name": "Klaasen", "company": "SoftwareCaptains"},
    })

    report = build_report(event, attendees)

    safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in title)
    safe_title = safe_title.strip().replace(" ", "_")[:60]
    event_date = event.get("start", {}).get("local", "")[:10]
    output_path = output_dir / f"report_{event_date}_{safe_title}.md"
    output_path.write_text(report, encoding="utf-8")
    print(f"    Markdown: {output_path}")

    markdown_to_pdf(report, output_path.with_suffix(".pdf"))
    print(f"    PDF:      {output_path.with_suffix('.pdf')}")

    confirmed = sorted(
        (a for a in attendees if a.get("status", "").lower() in ("attending", "checked_in")),
        key=lambda a: a.get("profile", {}).get("first_name", "").lower(),
    )
    write_csv(confirmed, output_path.with_suffix(".csv"))
    print(f"    CSV:      {output_path.with_suffix('.csv')}")

    if badges:
        # Fixed filename so P-touch Editor retains its CSV access permission
        # across runs (macOS security-scoped bookmark stored by P-touch is path-based).
        generate_badges(confirmed, output_dir, "badges")
        print(f"    Badges:   {output_dir / 'badges'}.lbx")


def main():
    parser = argparse.ArgumentParser(description="Generate Eventbrite event reports.")
    parser.add_argument(
        "--past", action="store_true",
        help="Generate reports for all past events instead of the next upcoming one.",
    )
    parser.add_argument(
        "--attendance", action="store_true",
        help="Generate an attendance overview report across all past events.",
    )
    args = parser.parse_args()

    token = os.environ.get("EVENTBRITE_TOKEN")
    if not token:
        sys.exit(
            "Error: EVENTBRITE_TOKEN is not set.\n"
            "Copy .env.example to .env and fill in your private token.\n"
            "You can create a token at https://www.eventbrite.com/platform/api-keys"
        )

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    org_id = fetch_organization_id(token)

    if args.attendance:
        report, rows = build_attendance_report(token, org_id)
        output_path = output_dir / "attendance_report.md"
        output_path.write_text(report, encoding="utf-8")
        print(f"\nMarkdown written to: {output_path}")

        markdown_to_pdf(report, output_path.with_suffix(".pdf"))
        print(f"PDF written to:      {output_path.with_suffix('.pdf')}")

        csv_path = output_path.with_suffix(".csv")
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["#", "First Name", "Last Name", "Company", "Events attended"])
            for i, row in enumerate(rows, start=1):
                writer.writerow([i, row["first_name"], row["last_name"], row["company"], row["count"]])
        print(f"CSV written to:      {csv_path}")

    elif args.past:
        print("Fetching all past events...")
        events = fetch_all_past_events(token, org_id)
        if not events:
            sys.exit("No past events found for your organization.")
        print(f"Found {len(events)} past event(s).\n")
        for event in events:
            process_event(token, event, output_dir, badges=False)
            print()
    else:
        print("Fetching your next event...")
        event = fetch_next_event(token, org_id)
        process_event(token, event, output_dir, badges=True)


if __name__ == "__main__":
    main()
