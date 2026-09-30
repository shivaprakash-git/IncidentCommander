from pathlib import Path

from engine.pipeline import ingest

FIXTURE = Path(__file__).parent / "fixtures" / "mini_sumlog.txt"


def test_synthetic_source(tmp_path):
    o = ingest("synthetic", db_path=tmp_path / "e.db")
    assert [d["source"] for d in o["demo_incidents"]] == ["synthetic"] * 3


def test_real_with_too_few_candidates_tops_up_with_synthetic(tmp_path):
    o = ingest("real", file=FIXTURE, db_path=tmp_path / "e.db")
    src = sorted(d["source"] for d in o["demo_incidents"])
    assert src == ["real", "synthetic", "synthetic"]       # 1 real candidate + 2 synthetic
