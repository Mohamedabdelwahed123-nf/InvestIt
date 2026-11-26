"""The SAMPLE dataset is valid, clearly labelled and reproducible."""

from collections import defaultdict
from pathlib import Path

from backend.data.load_csv import parse_funds, parse_navs
from backend.data.sample.generate import write_csvs
from backend.db.domain import Category


def test_sample_is_valid_and_labelled(sample_dir: Path) -> None:
    funds = parse_funds(sample_dir / "funds.csv")
    navs = parse_navs(sample_dir / "nav_prices.csv", {f.code for f in funds})

    per_category = defaultdict(int)
    for f in funds:
        per_category[f.category] += 1
        assert f.name.startswith("SAMPLE")
        assert f.code.startswith("SMP-")
        assert f.currency == "TND"
    assert all(per_category[c] >= 2 for c in Category)
    assert {n.source for n in navs} == {"SAMPLE"}

    dates = defaultdict(list)
    for n in navs:
        dates[n.fund_code].append(n.date)
    for code in (f.code for f in funds):
        span = max(dates[code]) - min(dates[code])
        assert span.days >= 730, code
        assert len(dates[code]) >= 500, code


def test_sample_generator_is_deterministic(sample_dir: Path, tmp_path: Path) -> None:
    write_csvs(tmp_path)
    for name in ("funds.csv", "nav_prices.csv"):
        assert (tmp_path / name).read_bytes() == (sample_dir / name).read_bytes(), name


def test_sample_readme_warns_it_is_synthetic(sample_dir: Path) -> None:
    text = (sample_dir / "README.md").read_text(encoding="utf-8")
    assert "synthetic" in text
    assert "must be replaced by real CMF data" in text
