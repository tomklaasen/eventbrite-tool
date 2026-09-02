"""End-to-end behaviour of daily_digest.main(), with network and SMTP stubbed."""

import json

from conftest import DEFAULT_EVENT, SECOND_EVENT, attendee, cancelled


JAN = attendee(1, "Jan", "Peeters")
ELLA = attendee(2, "Ella", "Maes")
WIM = attendee(3, "Wim", "Claes", "Umbrella")
TESTER = attendee(4, "Test", "TestTom", "Testing")


def test_first_run_reports_everyone_as_new(run_digest):
    run = run_digest([JAN, ELLA, WIM])
    assert run.subject == "3 new registrations for CTO Club"


def test_a_run_with_no_changes_sends_nothing(run_digest):
    run_digest([JAN, ELLA])
    run = run_digest([JAN, ELLA])
    assert not run.sent
    assert "No changes" in run.output


def test_reports_a_known_attendee_who_cancels(run_digest):
    run_digest([JAN, ELLA, WIM])
    run = run_digest([JAN, ELLA, cancelled(WIM)])
    assert run.subject == "1 cancellation for CTO Club"
    assert "Wim" in run.html


def test_reports_someone_who_registered_and_cancelled_between_two_runs(run_digest):
    """The case a snapshot diff alone cannot see: they were never confirmed."""
    run_digest([JAN, ELLA])
    run = run_digest([JAN, ELLA, cancelled(TESTER)])
    assert run.subject == "1 cancellation for CTO Club"
    assert "TestTom" in run.html and "Testing" in run.html


def test_reports_each_cancellation_only_once(run_digest):
    run_digest([JAN, ELLA])
    run_digest([JAN, ELLA, cancelled(TESTER)])
    run = run_digest([JAN, ELLA, cancelled(TESTER)])
    assert not run.sent


def test_reports_a_record_that_vanishes_from_the_api(run_digest):
    run_digest([JAN, ELLA])
    run = run_digest([JAN])
    assert run.subject == "1 cancellation for CTO Club"
    assert "Ella" in run.html


def test_a_re_registration_counts_as_new_again(run_digest):
    run_digest([JAN, WIM])
    run_digest([JAN, cancelled(WIM)])
    run = run_digest([JAN, WIM])
    assert run.subject == "1 new registration for CTO Club"
    assert "Wim" in run.html


def test_a_second_cancellation_is_reported_again(run_digest):
    run_digest([JAN, WIM])
    run_digest([JAN, cancelled(WIM)])
    run_digest([JAN, WIM])
    run = run_digest([JAN, cancelled(WIM)])
    assert run.subject == "1 cancellation for CTO Club"
    assert "Wim" in run.html


def test_reports_new_and_cancelled_together(run_digest):
    run_digest([JAN, WIM])
    run = run_digest([JAN, ELLA, cancelled(WIM)])
    assert run.subject == "1 new, 1 cancellation for CTO Club"
    assert "Ella" in run.html and "Wim" in run.html


def test_treats_a_non_attending_status_as_cancelled(run_digest):
    run_digest([JAN, WIM])
    run = run_digest([JAN, attendee(3, "Wim", "Claes", "Umbrella", status="Not Attending")])
    assert run.subject == "1 cancellation for CTO Club"


def test_combines_several_events_into_one_email(run_digest):
    events = (DEFAULT_EVENT, SECOND_EVENT)
    run = run_digest({"111": [JAN, ELLA], "222": [WIM]}, events=events)
    assert run.subject == "3 new registrations across 2 events"
    assert "CTO Club" in run.html and "AI Bot Night" in run.html


def test_an_event_without_changes_is_left_out_of_the_email(run_digest):
    events = (DEFAULT_EVENT, SECOND_EVENT)
    run_digest({"111": [JAN], "222": [WIM]}, events=events)
    run = run_digest({"111": [JAN, ELLA], "222": [WIM]}, events=events)
    assert run.subject == "1 new registration for CTO Club"
    assert "AI Bot Night" not in run.html


def test_an_empty_fetch_is_treated_as_a_problem_not_a_mass_cancellation(run_digest, snapshot_path):
    run_digest([JAN, ELLA])
    before = snapshot_path.read_text()

    run = run_digest([])

    assert not run.sent
    assert snapshot_path.read_text() == before
    assert "assuming a fetch problem" in run.output


def test_no_live_events_does_nothing(run_digest):
    run = run_digest([], events=())
    assert not run.sent
    assert "No upcoming events" in run.output


def test_reads_a_pre_cancellation_snapshot_and_upgrades_it(run_digest, snapshot_path):
    """Snapshots written before cancellation tracking are a flat attendee map."""
    snapshot_path.parent.mkdir(exist_ok=True)
    snapshot_path.write_text(json.dumps({
        "1": {"first_seen": "2026-01-01", "first_name": "Jan",
              "last_name": "Peeters", "company": "Acme"},
    }))

    run = run_digest([JAN, ELLA])

    assert run.subject == "1 new registration for CTO Club"
    assert "Ella" in run.html
    assert "Jan" not in run.html

    upgraded = json.loads(snapshot_path.read_text())
    assert set(upgraded) == {"attendees", "cancelled"}
    assert set(upgraded["attendees"]) == {"1", "2"}


def test_records_company_from_the_custom_question(run_digest, snapshot_path):
    run_digest([attendee(9, "Bea", "Janssens", "Contoso")])
    stored = json.loads(snapshot_path.read_text())["attendees"]["9"]
    assert stored["company"] == "Contoso"
