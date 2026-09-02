"""Shared test fixtures.

Living at the repo root so pytest puts the root on sys.path, which is how the
test modules import `daily_digest`.
"""

import contextlib
import io

import pytest

import daily_digest


DEFAULT_EVENT = {
    "id": "111",
    "name": {"text": "CTO Club"},
    "start": {"local": "2026-09-15T19:00:00"},
}
SECOND_EVENT = {
    "id": "222",
    "name": {"text": "AI Bot Night"},
    "start": {"local": "2026-10-02T18:30:00"},
}


def attendee(attendee_id, first, last, company="Acme", status="Attending"):
    """Build an attendee record shaped like the Eventbrite API returns."""
    return {
        "id": str(attendee_id),
        "status": status,
        "cancelled": status != "Attending",
        "profile": {"first_name": first, "last_name": last},
        "answers": [{"question": "Bedrijf", "answer": company}],
    }


def cancelled(record):
    """Eventbrite keeps returning cancelled records, flagged not-attending."""
    return dict(record, status="Not Attending", cancelled=True, refunded=True)


class DigestRun:
    """What one `main()` run did: what it printed and what it emailed."""

    def __init__(self, output, mail):
        self.output = output
        self.mail = mail

    @property
    def sent(self):
        return self.mail is not None

    @property
    def subject(self):
        return self.mail[0] if self.mail else None

    @property
    def html(self):
        return self.mail[1] if self.mail else None


@pytest.fixture
def run_digest(monkeypatch, tmp_path):
    """Run daily_digest.main() with the network and SMTP stubbed out.

    Call with a list of attendees for a single default event, or a dict of
    {event_id: [attendees]} to exercise several events at once. Snapshots are
    written under tmp_path, so runs accumulate state exactly as in production.
    """
    monkeypatch.setattr(daily_digest, "SNAPSHOT_DIR", tmp_path)
    for name, value in {
        "EVENTBRITE_TOKEN": "token",
        "GMAIL_USER": "me@example.com",
        "GMAIL_APP_PASSWORD": "secret",
        "DIGEST_TO": "you@example.com",
    }.items():
        monkeypatch.setenv(name, value)

    def run(attendees, events=(DEFAULT_EVENT,)):
        if isinstance(attendees, dict):
            by_event = attendees
        else:
            by_event = {events[0]["id"]: attendees} if events else {}
        sent = []

        monkeypatch.setattr(daily_digest, "fetch_organization_id", lambda token: "org")
        monkeypatch.setattr(daily_digest, "fetch_all_live_events", lambda token, org: list(events))
        monkeypatch.setattr(
            daily_digest, "fetch_all_attendees",
            lambda token, event_id: by_event.get(event_id, []),
        )
        monkeypatch.setattr(
            daily_digest, "send_email",
            lambda subject, html, user, password, to: sent.append((subject, html)),
        )
        monkeypatch.setattr(daily_digest, "ping_healthchecks", lambda url, suffix="": None)

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            daily_digest.main()
        return DigestRun(buffer.getvalue(), sent[0] if sent else None)

    return run


@pytest.fixture
def snapshot_path(tmp_path):
    """Path of the default event's snapshot file."""
    return tmp_path / f"snapshot_{DEFAULT_EVENT['id']}.json"
