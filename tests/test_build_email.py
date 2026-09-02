"""Subject lines and HTML sections of the digest email."""

import pytest

from conftest import DEFAULT_EVENT, SECOND_EVENT
from daily_digest import build_email


def person(first, last, company="Acme"):
    return (first, last, company)


JAN, ELLA, WIM = person("Jan", "Peeters"), person("Ella", "Maes"), person("Wim", "Claes", "Umbrella")
SAM = person("Sam", "De Vos", "Initech")


@pytest.mark.parametrize("sections, expected", [
    ([(DEFAULT_EVENT, [JAN], [], 12)],
     "1 new registration for CTO Club"),
    ([(DEFAULT_EVENT, [JAN, ELLA], [], 12)],
     "2 new registrations for CTO Club"),
    ([(DEFAULT_EVENT, [JAN, ELLA], [WIM], 12)],
     "2 new, 1 cancellation for CTO Club"),
    ([(DEFAULT_EVENT, [], [WIM], 11)],
     "1 cancellation for CTO Club"),
    ([(DEFAULT_EVENT, [JAN], [], 12), (SECOND_EVENT, [SAM], [], 4)],
     "2 new registrations across 2 events"),
    ([(DEFAULT_EVENT, [JAN], [WIM], 12), (SECOND_EVENT, [], [SAM], 4)],
     "1 new, 2 cancellations across 2 events"),
])
def test_subject(sections, expected):
    subject, _ = build_email(sections)
    assert subject == expected


def test_lists_both_tables_when_there_are_new_and_cancelled():
    _, html = build_email([(DEFAULT_EVENT, [JAN], [WIM], 12)])
    assert "New registrations (1)" in html
    assert "Cancellations (1)" in html
    assert html.count("<table") == 2
    assert "Wim" in html and "Umbrella" in html


def test_omits_the_cancellations_table_when_there_are_none():
    _, html = build_email([(DEFAULT_EVENT, [JAN], [], 12)])
    assert "Cancellations" not in html
    assert html.count("<table") == 1


def test_omits_the_new_registrations_table_when_there_are_none():
    _, html = build_email([(DEFAULT_EVENT, [], [WIM], 11)])
    assert "New registrations" not in html
    assert html.count("<table") == 1


def test_shows_a_total_count_rather_than_the_full_roster():
    _, html = build_email([(DEFAULT_EVENT, [JAN], [], 12)])
    assert "Total registrations: <strong>12</strong>" in html
    assert "All registrations" not in html


def test_renders_one_section_per_event_separated_by_a_rule():
    _, html = build_email([(DEFAULT_EVENT, [JAN], [], 12), (SECOND_EVENT, [SAM], [], 4)])
    assert html.count("<h2") == 2
    assert html.count("<hr") == 1
    assert "CTO Club" in html and "AI Bot Night" in html
    assert "manage/events/111/attendees" in html
    assert "manage/events/222/attendees" in html


def test_styles_table_cells_inline_for_email_clients():
    _, html = build_email([(DEFAULT_EVENT, [JAN], [], 12)])
    assert 'style="border:1px solid #ccc;padding:6px 10px;"' in html
