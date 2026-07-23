"""Comprehensive tests for ICS generation and New Outlook compatibility.

Covers:
- Line folding (RFC 5545 §3.1)
- X-MICROSOFT-CDO-BUSYSTATUS and X-MICROSOFT-CDO-INTENDEDSTATUS
- TRANSP consistency with busy status
- All busy statuses: Free, Tentative, Busy, Out of Office
- Teaching events vs. academic (other relevant) events
- VALARM placement
- CLASS/privacy
- CRLF line endings
- UID presence and determinism
- Categories escaping
- Long descriptions and multi-byte characters
"""
import sys
import os
import re

# Ensure the project root is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logic
from datetime import date, time
import pandas as pd
import io


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_minimal_calendar_df():
    """Create a minimal calendar DataFrame with a few M/T days and an academic event."""
    csv_text = (
        "Subject,Start Date,Start Time,End Date,End Time,All day event,"
        "Reminder on/off,Reminder Date,Reminder Time,Meeting Organizer,"
        "Required Attendees,Optional Attendees,Meeting Resources,"
        "Billing Information,Categories,Description,Location,Mileage,"
        "Priority,Private,Sensitivity,Show time as\n"
        # M-day and T-day rows (schedule drivers)
        "M1,8/12/2026,,8/12/2026,,True,False,,,,,,,,,,,Normal,False,Normal,3\n"
        "T1,8/13/2026,,8/13/2026,,True,False,,,,,,,,,,,Normal,False,Normal,3\n"
        # An academic event (other relevant event)
        "Parents' Weekend Begins,9/4/2026,12:00:00 AM,9/5/2026,12:00:00 AM,True,False,9/3/2026,11:45:00 PM,,,,,,,\"Big event\",Fairchild Hall,,Normal,False,Normal,3\n"
        # A timed academic event
        "Commandant Briefing,9/4/2026,2:00:00 PM,9/4/2026,3:00:00 PM,False,True,9/4/2026,1:45:00 PM,,,,,,,\"Briefing desc\",Arnold Hall,,Normal,False,Normal,3\n"
    )
    return pd.read_csv(io.StringIO(csv_text))


def make_course_rows():
    return [
        {
            "course": "Math 356",
            "periods": ["M1", "T1"],
            "location": "Fairchild 2E46",
            "description": "Linear Algebra",
            "categories": "Teaching",
        }
    ]


def generate_ics(busy_status="2", reminder_on=True, reminder_minutes=15,
                 private=False, academic_mode="all", course_rows=None,
                 calendar_df=None):
    """Helper to generate an ICS string with given parameters."""
    if calendar_df is None:
        calendar_df = make_minimal_calendar_df()
    if course_rows is None:
        course_rows = make_course_rows()
    events = logic.build_events(
        calendar_df, course_rows,
        reminder_on=reminder_on,
        reminder_minutes=reminder_minutes,
        busy_status=busy_status,
        private=private,
    )
    return logic.events_to_ics(
        events, calendar_df=calendar_df,
        academic_mode=academic_mode,
        timezone_name="America/Denver",
    ), events


def parse_vevents(ics_text):
    """Extract individual VEVENT blocks from ICS text, handling folded lines."""
    # First unfold: CRLF followed by a single space or tab
    unfolded = re.sub(r'\r\n[ \t]', '', ics_text)
    blocks = re.findall(r'BEGIN:VEVENT\r\n(.*?)\r\nEND:VEVENT', unfolded, re.DOTALL)
    result = []
    for block in blocks:
        props = {}
        in_sub = False  # Track if we're inside a sub-component like VALARM
        for line in block.split('\r\n'):
            if line.startswith('BEGIN:'):
                in_sub = True
                continue
            if line.startswith('END:'):
                in_sub = False
                continue
            if in_sub:
                continue  # Skip sub-component properties
            if ':' in line:
                key, _, value = line.partition(':')
                # Handle keys with parameters like DTSTART;VALUE=DATE
                base_key = key.split(';')[0]
                props[base_key] = value
        result.append(props)
    return result


# ---------------------------------------------------------------------------
# fold_ics_line tests
# ---------------------------------------------------------------------------

class TestFoldIcsLine:

    def test_short_line_unchanged(self):
        line = "SUMMARY:Short"
        assert logic.fold_ics_line(line) == line

    def test_exactly_75_bytes_unchanged(self):
        line = "X" * 75
        assert logic.fold_ics_line(line) == line
        assert len(line.encode("utf-8")) == 75

    def test_76_bytes_folded(self):
        line = "X" * 76
        result = logic.fold_ics_line(line)
        assert "\r\n " in result
        parts = result.split("\r\n ")
        assert len(parts[0].encode("utf-8")) == 75
        assert len(parts[1].encode("utf-8")) == 1  # the remaining "X"

    def test_long_line_multiple_folds(self):
        line = "DESCRIPTION:" + "A" * 200
        result = logic.fold_ics_line(line)
        parts = result.split("\r\n ")
        # First part: 75 bytes
        assert len(parts[0].encode("utf-8")) == 75
        # Continuation parts: up to 74 bytes each (space prefix not included in content)
        for part in parts[1:]:
            assert len(part.encode("utf-8")) <= 74

    def test_multibyte_utf8_not_split(self):
        """Ensure multi-byte characters (e.g. emoji) are not split mid-character."""
        # Each emoji is 4 bytes. Fill to trigger a fold at a boundary.
        line = "SUMMARY:" + "🎓" * 25  # 8 + 100 = 108 bytes
        result = logic.fold_ics_line(line)
        # Unfolding should give us the original line back
        unfolded = result.replace("\r\n ", "")
        assert unfolded == line

    def test_empty_line(self):
        assert logic.fold_ics_line("") == ""

    def test_ascii_boundary(self):
        """A line of exactly 150 ASCII bytes should fold into 75 + 74 + 1."""
        line = "A" * 150
        result = logic.fold_ics_line(line)
        parts = result.split("\r\n ")
        assert len(parts) == 3
        assert len(parts[0].encode("utf-8")) == 75
        assert len(parts[1].encode("utf-8")) == 74
        assert len(parts[2].encode("utf-8")) == 1


# ---------------------------------------------------------------------------
# Busy status tests — Teaching events
# ---------------------------------------------------------------------------

class TestTeachingBusyStatus:

    def test_busy_status_free(self):
        ics, _ = generate_ics(busy_status="0")
        vevents = parse_vevents(ics)
        teaching = [v for v in vevents if "Math 356" in v.get("SUMMARY", "")]
        assert len(teaching) > 0
        for ev in teaching:
            assert ev["TRANSP"] == "TRANSPARENT"
            assert ev["X-MICROSOFT-CDO-BUSYSTATUS"] == "FREE"
            assert ev["X-MICROSOFT-CDO-INTENDEDSTATUS"] == "FREE"

    def test_busy_status_tentative(self):
        ics, _ = generate_ics(busy_status="1")
        vevents = parse_vevents(ics)
        teaching = [v for v in vevents if "Math 356" in v.get("SUMMARY", "")]
        for ev in teaching:
            assert ev["TRANSP"] == "OPAQUE"
            assert ev["X-MICROSOFT-CDO-BUSYSTATUS"] == "TENTATIVE"
            assert ev["X-MICROSOFT-CDO-INTENDEDSTATUS"] == "TENTATIVE"

    def test_busy_status_busy(self):
        ics, _ = generate_ics(busy_status="2")
        vevents = parse_vevents(ics)
        teaching = [v for v in vevents if "Math 356" in v.get("SUMMARY", "")]
        for ev in teaching:
            assert ev["TRANSP"] == "OPAQUE"
            assert ev["X-MICROSOFT-CDO-BUSYSTATUS"] == "BUSY"
            assert ev["X-MICROSOFT-CDO-INTENDEDSTATUS"] == "BUSY"

    def test_busy_status_out_of_office(self):
        ics, _ = generate_ics(busy_status="3")
        vevents = parse_vevents(ics)
        teaching = [v for v in vevents if "Math 356" in v.get("SUMMARY", "")]
        for ev in teaching:
            assert ev["TRANSP"] == "OPAQUE"
            assert ev["X-MICROSOFT-CDO-BUSYSTATUS"] == "OOF"
            assert ev["X-MICROSOFT-CDO-INTENDEDSTATUS"] == "OOF"


# ---------------------------------------------------------------------------
# Busy status tests — Academic (other relevant) events
# ---------------------------------------------------------------------------

class TestAcademicBusyStatus:

    def test_academic_events_always_free(self):
        """Academic events must always be Free, regardless of the busy_status setting."""
        for status in ["0", "1", "2", "3"]:
            ics, _ = generate_ics(busy_status=status, academic_mode="all")
            vevents = parse_vevents(ics)
            academic = [v for v in vevents if "Math 356" not in v.get("SUMMARY", "")
                        and v.get("SUMMARY", "").strip()
                        and not re.fullmatch(r"[MT]\d+", v.get("SUMMARY", "").strip())]
            assert len(academic) > 0, f"Expected academic events for status={status}"
            for ev in academic:
                assert ev["TRANSP"] == "TRANSPARENT", f"Academic event {ev['SUMMARY']} not TRANSPARENT for status={status}"
                assert ev["X-MICROSOFT-CDO-BUSYSTATUS"] == "FREE", f"Academic event {ev['SUMMARY']} not FREE for status={status}"
                assert ev["X-MICROSOFT-CDO-INTENDEDSTATUS"] == "FREE", f"Academic event {ev['SUMMARY']} missing INTENDEDSTATUS=FREE"


# ---------------------------------------------------------------------------
# Reminder (VALARM) tests
# ---------------------------------------------------------------------------

class TestReminders:

    def test_teaching_reminder_on(self):
        ics, _ = generate_ics(reminder_on=True, reminder_minutes=15)
        vevents = parse_vevents(ics)
        teaching = [v for v in vevents if "Math 356" in v.get("SUMMARY", "")]
        # Check raw ICS for VALARM blocks inside teaching events
        # Unfold first
        unfolded = re.sub(r'\r\n[ \t]', '', ics)
        teaching_blocks = re.findall(
            r'BEGIN:VEVENT\r\n(.*?Math 356.*?)\r\nEND:VEVENT', unfolded, re.DOTALL
        )
        assert len(teaching_blocks) > 0
        for block in teaching_blocks:
            assert "BEGIN:VALARM" in block
            assert "TRIGGER:-PT15M" in block
            assert "ACTION:DISPLAY" in block

    def test_teaching_reminder_off(self):
        ics, _ = generate_ics(reminder_on=False)
        unfolded = re.sub(r'\r\n[ \t]', '', ics)
        teaching_blocks = re.findall(
            r'BEGIN:VEVENT\r\n(.*?Math 356.*?)\r\nEND:VEVENT', unfolded, re.DOTALL
        )
        for block in teaching_blocks:
            assert "BEGIN:VALARM" not in block

    def test_academic_events_no_reminder_by_default(self):
        """Academic events from the test CSV have Reminder on/off=False, so no VALARM."""
        ics, _ = generate_ics(academic_mode="all")
        unfolded = re.sub(r'\r\n[ \t]', '', ics)
        # Extract individual VEVENT blocks and check only the one containing "Parents"
        all_blocks = re.findall(
            r"BEGIN:VEVENT\r\n(.*?)\r\nEND:VEVENT", unfolded, re.DOTALL
        )
        parents_blocks = [b for b in all_blocks if "Parents" in b]
        assert len(parents_blocks) > 0, "Expected at least one Parents' Weekend event"
        for block in parents_blocks:
            assert "BEGIN:VALARM" not in block

    def test_valarm_placement_before_end_vevent(self):
        """VALARM should appear after properties, before END:VEVENT."""
        ics, _ = generate_ics(reminder_on=True, reminder_minutes=30)
        unfolded = re.sub(r'\r\n[ \t]', '', ics)
        teaching_blocks = re.findall(
            r'BEGIN:VEVENT\r\n(.*?Math 356.*?)\r\nEND:VEVENT', unfolded, re.DOTALL
        )
        for block in teaching_blocks:
            valarm_pos = block.find("BEGIN:VALARM")
            summary_pos = block.find("SUMMARY:")
            assert valarm_pos > summary_pos, "VALARM should appear after SUMMARY"

    def test_different_reminder_minutes(self):
        for minutes in [0, 5, 30, 60, 120]:
            ics, _ = generate_ics(reminder_on=True, reminder_minutes=minutes)
            unfolded = re.sub(r'\r\n[ \t]', '', ics)
            assert f"TRIGGER:-PT{minutes}M" in unfolded


# ---------------------------------------------------------------------------
# Privacy / CLASS tests
# ---------------------------------------------------------------------------

class TestPrivacy:

    def test_private_true(self):
        ics, _ = generate_ics(private=True)
        vevents = parse_vevents(ics)
        teaching = [v for v in vevents if "Math 356" in v.get("SUMMARY", "")]
        for ev in teaching:
            assert ev["CLASS"] == "PRIVATE"

    def test_private_false(self):
        ics, _ = generate_ics(private=False)
        vevents = parse_vevents(ics)
        teaching = [v for v in vevents if "Math 356" in v.get("SUMMARY", "")]
        for ev in teaching:
            assert ev["CLASS"] == "PUBLIC"


# ---------------------------------------------------------------------------
# CRLF and structural tests
# ---------------------------------------------------------------------------

class TestIcsStructure:

    def test_crlf_line_endings(self):
        ics, _ = generate_ics()
        # Every line ending should be CRLF, not bare LF
        # Remove all CRLF first, then check no bare LF remains
        stripped = ics.replace("\r\n", "")
        assert "\n" not in stripped, "Found bare LF not preceded by CR"

    def test_begins_with_vcalendar(self):
        ics, _ = generate_ics()
        assert ics.startswith("BEGIN:VCALENDAR\r\n")

    def test_ends_with_vcalendar(self):
        ics, _ = generate_ics()
        assert ics.strip().endswith("END:VCALENDAR")

    def test_required_headers_present(self):
        ics, _ = generate_ics()
        unfolded = re.sub(r'\r\n[ \t]', '', ics)
        assert "VERSION:2.0" in unfolded
        assert "PRODID:" in unfolded
        assert "CALSCALE:GREGORIAN" in unfolded
        assert "METHOD:PUBLISH" in unfolded

    def test_all_lines_within_75_octets(self):
        """After folding, no raw line should exceed 75 octets (excluding CRLF)."""
        ics, _ = generate_ics()
        raw_lines = ics.split("\r\n")
        for i, line in enumerate(raw_lines):
            byte_len = len(line.encode("utf-8"))
            assert byte_len <= 75, (
                f"Line {i+1} exceeds 75 octets ({byte_len}): {line[:80]}..."
            )

    def test_uid_present_and_unique(self):
        ics, _ = generate_ics()
        vevents = parse_vevents(ics)
        uids = [ev.get("UID") for ev in vevents]
        assert all(uid is not None for uid in uids), "All events should have UIDs"
        assert len(uids) == len(set(uids)), "All UIDs should be unique"

    def test_uid_deterministic(self):
        """Same inputs should produce the same UIDs."""
        ics1, _ = generate_ics()
        ics2, _ = generate_ics()
        vevents1 = parse_vevents(ics1)
        vevents2 = parse_vevents(ics2)
        uids1 = sorted(ev.get("UID") for ev in vevents1)
        uids2 = sorted(ev.get("UID") for ev in vevents2)
        assert uids1 == uids2


# ---------------------------------------------------------------------------
# Line folding in real ICS output
# ---------------------------------------------------------------------------

class TestLineFoldingInOutput:

    def test_long_description_folds(self):
        """A long description should be properly folded in the output."""
        course_rows = [{
            "course": "Math 356",
            "periods": ["M1"],
            "location": "Fairchild 2E46",
            "description": "This is a very long description " * 10,
            "categories": "Teaching",
        }]
        ics, _ = generate_ics(course_rows=course_rows)
        # Check no raw line exceeds 75 octets
        for line in ics.split("\r\n"):
            assert len(line.encode("utf-8")) <= 75

        # But when unfolded, the full description should be there
        unfolded = re.sub(r'\r\n[ \t]', '', ics)
        assert "This is a very long description" in unfolded

    def test_long_location_folds(self):
        course_rows = [{
            "course": "Math 356",
            "periods": ["M1"],
            "location": "Very Long Building Name Room 123 Wing B Section C " * 3,
            "description": "",
            "categories": "Teaching",
        }]
        ics, _ = generate_ics(course_rows=course_rows)
        for line in ics.split("\r\n"):
            assert len(line.encode("utf-8")) <= 75

    def test_long_subject_folds(self):
        course_rows = [{
            "course": "Advanced Topics in Mathematical Analysis and Applied Mathematics",
            "periods": ["M1"],
            "location": "Room",
            "description": "",
            "categories": "Teaching",
        }]
        ics, _ = generate_ics(course_rows=course_rows)
        for line in ics.split("\r\n"):
            assert len(line.encode("utf-8")) <= 75

    def test_unfolding_roundtrip(self):
        """Folded lines should unfold back to the original content."""
        long_desc = "ABCDEFGHIJ" * 20  # 200 chars
        course_rows = [{
            "course": "CS 110",
            "periods": ["T1"],
            "location": "Room 101",
            "description": long_desc,
            "categories": "Teaching",
        }]
        ics, _ = generate_ics(course_rows=course_rows)
        unfolded = re.sub(r'\r\n[ \t]', '', ics)
        vevents = parse_vevents(ics)
        teaching = [v for v in vevents if "CS 110" in v.get("SUMMARY", "")]
        assert len(teaching) > 0
        for ev in teaching:
            # The description in the ICS has escaping, so check it contains the content
            assert long_desc.replace(",", "\\,").replace(";", "\\;") in ev.get("DESCRIPTION", "")


# ---------------------------------------------------------------------------
# Academic mode tests
# ---------------------------------------------------------------------------

class TestAcademicMode:

    def test_academic_mode_none_excludes_academic(self):
        ics, _ = generate_ics(academic_mode="none")
        vevents = parse_vevents(ics)
        summaries = [v.get("SUMMARY", "") for v in vevents]
        assert not any("Parents" in s for s in summaries)

    def test_academic_mode_all_includes_academic(self):
        ics, _ = generate_ics(academic_mode="all")
        vevents = parse_vevents(ics)
        summaries = [v.get("SUMMARY", "") for v in vevents]
        assert any("Parents" in s for s in summaries)

    def test_academic_mode_academic_only(self):
        """Mode 'academic' includes academic events (same as 'all')."""
        ics, _ = generate_ics(academic_mode="academic")
        vevents = parse_vevents(ics)
        summaries = [v.get("SUMMARY", "") for v in vevents]
        assert any("Parents" in s for s in summaries)


# ---------------------------------------------------------------------------
# CSV export tests (Show time as)
# ---------------------------------------------------------------------------

class TestCsvExport:

    def test_teaching_csv_show_time_as(self):
        """Teaching event CSV should have the user's selected busy status."""
        for status in ["0", "1", "2", "3"]:
            calendar_df = make_minimal_calendar_df()
            course_rows = make_course_rows()
            events = logic.build_events(calendar_df, course_rows, True, 15, status, False)
            for e in events:
                row = logic.teaching_event_to_csv_row(e)
                assert row["Show time as"] == status

    def test_academic_csv_always_free(self):
        """Academic event CSV rows should always have Show time as = 0."""
        calendar_df = make_minimal_calendar_df()
        for _, row in logic.filter_academic_rows(calendar_df, "all").iterrows():
            csv_row = logic.academic_row_to_csv_row(row)
            assert csv_row["Show time as"] == "0"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_empty_description(self):
        course_rows = [{
            "course": "Math 101",
            "periods": ["M1"],
            "location": "Room A",
            "description": "",
            "categories": "Teaching",
        }]
        ics, _ = generate_ics(course_rows=course_rows)
        assert "DESCRIPTION:" in re.sub(r'\r\n[ \t]', '', ics)

    def test_special_characters_in_description(self):
        course_rows = [{
            "course": "Math 101",
            "periods": ["M1"],
            "location": "Room A",
            "description": "Use formula: f(x) = x^2; see chapter 3, pg. 42",
            "categories": "Teaching",
        }]
        ics, _ = generate_ics(course_rows=course_rows)
        unfolded = re.sub(r'\r\n[ \t]', '', ics)
        # Semicolons and commas should be escaped
        assert "\\;" in unfolded
        assert "\\," in unfolded

    def test_multiple_categories(self):
        course_rows = [{
            "course": "Math 101",
            "periods": ["M1"],
            "location": "Room A",
            "description": "",
            "categories": "Teaching, Math, Core",
        }]
        ics, _ = generate_ics(course_rows=course_rows)
        unfolded = re.sub(r'\r\n[ \t]', '', ics)
        vevents = parse_vevents(ics)
        teaching = [v for v in vevents if "Math 101" in v.get("SUMMARY", "")]
        assert len(teaching) > 0
        for ev in teaching:
            cats = ev.get("CATEGORIES", "")
            assert "Teaching" in cats
            assert "Math" in cats
            assert "Core" in cats

    def test_no_courses_academic_only(self):
        """Should work with no teaching courses, just academic events."""
        ics = logic.events_to_ics(
            [],
            calendar_df=make_minimal_calendar_df(),
            academic_mode="academic",
        )
        vevents = parse_vevents(ics)
        assert len(vevents) > 0
        # All should be academic
        for ev in vevents:
            assert ev["X-MICROSOFT-CDO-BUSYSTATUS"] == "FREE"
            assert ev["X-MICROSOFT-CDO-INTENDEDSTATUS"] == "FREE"

    def test_intendedstatus_matches_busystatus(self):
        """INTENDEDSTATUS should always match BUSYSTATUS for all event types."""
        for status in ["0", "1", "2", "3"]:
            ics, _ = generate_ics(busy_status=status, academic_mode="all")
            vevents = parse_vevents(ics)
            for ev in vevents:
                assert ev["X-MICROSOFT-CDO-INTENDEDSTATUS"] == ev["X-MICROSOFT-CDO-BUSYSTATUS"], (
                    f"Mismatch for {ev.get('SUMMARY')}: "
                    f"INTENDED={ev.get('X-MICROSOFT-CDO-INTENDEDSTATUS')} vs "
                    f"BUSY={ev.get('X-MICROSOFT-CDO-BUSYSTATUS')}"
                )


# ---------------------------------------------------------------------------
# Run with pytest
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
