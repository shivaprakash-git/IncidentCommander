from datetime import datetime
from pathlib import Path

from engine.parser import SliceSpec, parse_file, summarize

FIXTURE = Path(__file__).parent / "fixtures" / "mini_sumlog.txt"


def events():
    return parse_file(FIXTURE, SliceSpec(max_records=100))


def by_kw(evs, kw):
    return [e for e in evs if e.raw_type_keyword == kw]


def test_segments_both_header_formats_and_skips_blocks():
    evs = events()
    # NO SUMLOG banner, BOJ, OPEN, TIME, keyword-less SECURITY VIOLATION, LOGON, DIAG, LIB
    assert [e.raw_type_keyword for e in evs] == [
        "INFO", "BOJ", "OPEN", "TIME", "INFO", "LOGON", "DIAG", "LIB",
    ]


def test_halt_load_block_is_not_glued_onto_previous_record():
    open_ev = by_kw(events(), "OPEN")[0]
    assert "HALT/LOAD" not in open_ev.raw_text
    assert "LINEINFO" not in open_ev.raw_text


def test_mapping_table():
    evs = events()
    assert (by_kw(evs, "BOJ")[0].major_type, by_kw(evs, "BOJ")[0].minor_type) == ("1", "1")
    assert (by_kw(evs, "OPEN")[0].major_type, by_kw(evs, "OPEN")[0].minor_type) == ("1", "5")
    assert (by_kw(evs, "LOGON")[0].major_type, by_kw(evs, "LOGON")[0].minor_type) == ("4", "1")
    assert (by_kw(evs, "TIME")[0].major_type, by_kw(evs, "TIME")[0].minor_type) == ("SYSTEM", "TIME_MSG")
    diag = by_kw(evs, "DIAG")[0]
    assert (diag.major_type, diag.minor_type) == ("UNMAPPED", "DIAG")
    lib = by_kw(evs, "LIB")[0]
    assert lib.major_type == "UNMAPPED"


def test_keywordless_header_is_info_with_job():
    sv = [e for e in events() if "SECURITY VIOLATION" in e.raw_text][0]
    assert sv.raw_type_keyword == "INFO"
    assert sv.major_type == "INFO"
    assert sv.task_id == "6619"
    assert sv.severity == "CRIT"


def test_banner_header_without_number_is_info_and_not_warn():
    banner = events()[0]
    assert banner.raw_type_keyword == "INFO"
    assert banner.task_id is None
    assert banner.severity == "INFO"  # "DISCARDED" banner is noise


def test_timestamps_use_day_header_and_fractions():
    evs = events()
    assert evs[0].timestamp == datetime(2023, 8, 10, 23, 58, 59)
    assert by_kw(evs, "TIME")[0].timestamp == datetime(2023, 8, 10, 23, 59, 2, 527100)
    assert by_kw(evs, "LOGON")[0].timestamp == datetime(2023, 8, 11, 0, 0, 5)  # day rollover


def test_fields_job_task_session():
    op = by_kw(events(), "OPEN")[0]
    assert op.task_id == "6584"
    assert op.job_id == "6507"  # from "ACTOR ... JOB 6507" text
    assert op.raw_fields["INT NAME"] == "ACTIONFILE"
    assert op.raw_fields["FRAMESIZE"] == "48"
    boj = by_kw(events(), "BOJ")[0]
    assert boj.session_id == "MCS1/LSN21"
    assert boj.raw_fields["USERCODE"] == "MLS"
    assert boj.raw_fields["CHARGECODE"] == "ASW"


def test_event_ids_are_line_numbers():
    evs = events()
    assert evs[0].event_id == "L000007"
    assert len({e.event_id for e in evs}) == len(evs)


def test_slice_max_records_and_time_and_line():
    assert len(parse_file(FIXTURE, SliceSpec(max_records=3))) == 3
    t = parse_file(FIXTURE, SliceSpec(start_time=datetime(2023, 8, 11, 0, 0, 0)))
    assert [e.raw_type_keyword for e in t] == ["LOGON", "DIAG", "LIB"]
    ln = parse_file(FIXTURE, SliceSpec(start_line=8, end_line=12))
    assert [e.raw_type_keyword for e in ln] == ["BOJ", "OPEN"]


def test_default_slice_is_bounded():
    assert SliceSpec().effective_max() == 5000
    assert SliceSpec(start_line=1).effective_max() is None


def test_summary_counts_unmapped():
    s = summarize(events())
    assert s["total"] == 8
    assert s["by_major"]["UNMAPPED"] == 2
    assert s["unmapped_pct"] == 25.0


def test_dated_header_and_hyphenated_keyword():
    lines = [
        "Thursday, August 10, 2023",
        "08/10/2023 11:24:29.7595   6272 BNAV2",
        "                                HEADER CONTROL LEVEL = 1    SOURCE HOST        = JETD",
        "   11:14:43    P-DS  6520 *SYSTEM/LOGANALYZER.",
    ]
    from engine.parser import parse_lines
    evs = parse_lines(lines)
    assert evs[0].timestamp == datetime(2023, 8, 10, 11, 24, 29, 759500)
    assert evs[0].task_id == "6272" and "BNAV2" in evs[0].raw_text
    assert (evs[1].major_type, evs[1].minor_type) == ("UNMAPPED", "P-DS")
