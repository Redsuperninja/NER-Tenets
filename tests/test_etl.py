import json
from pathlib import Path

import pytest

from etl import extract, transform


def test_extract_require_env_raises_for_missing_value():
    with pytest.raises(RuntimeError, match="HUD_API_TOKEN"):
        extract._require_env("HUD_API_TOKEN", None)


def test_transform_hud_fmr_shapes_real_rows():
    hud_raw = json.loads(Path("etl/data/raw/hud_fmr_co_raw.json").read_text())

    rows = transform.transform_hud_fmr(hud_raw)

    assert len(rows) == len(hud_raw)
    assert rows[0]["county_fips"] == hud_raw[0]["county_fips"]
    assert all(isinstance(row["bedroom_count"], int) for row in rows)
    assert all(isinstance(row["fmr_amount"], float) for row in rows)
    assert all(row["source"] == "HUD_FMR_API" for row in rows)


def test_transform_acs_median_rent_shapes_real_rows():
    acs_raw = json.loads(Path("etl/data/raw/acs_median_rent_co_raw.json").read_text())

    rows = transform.transform_acs_median_rent(acs_raw)

    assert len(rows) == len(acs_raw)
    assert rows[0]["county_fips"] == acs_raw[0]["county_fips"]
    assert all(isinstance(row["median_gross_rent"], float) for row in rows)
    assert all(row["source"] == "CENSUS_ACS5_B25064" for row in rows)


def test_generate_synthetic_lease_concessions_is_deterministic():
    hud_raw = json.loads(Path("etl/data/raw/hud_fmr_co_raw.json").read_text())
    hud_rows = transform.transform_hud_fmr(hud_raw)

    first = transform.generate_synthetic_lease_concessions(hud_rows, seed=42)
    second = transform.generate_synthetic_lease_concessions(hud_rows, seed=42)

    assert first == second
    assert len(first) > 0
    assert all(row["is_synthetic"] is True for row in first)


def test_transform_all_writes_expected_outputs(tmp_path, monkeypatch):
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    raw_dir.mkdir()
    processed_dir.mkdir()

    hud_raw = json.loads(Path("etl/data/raw/hud_fmr_co_raw.json").read_text())
    acs_raw = json.loads(Path("etl/data/raw/acs_median_rent_co_raw.json").read_text())
    (raw_dir / "hud_fmr_co_raw.json").write_text(json.dumps(hud_raw))
    (raw_dir / "acs_median_rent_co_raw.json").write_text(json.dumps(acs_raw))

    monkeypatch.setattr(transform, "RAW_DATA_DIR", raw_dir)
    monkeypatch.setattr(transform, "PROCESSED_DATA_DIR", processed_dir)

    outputs = transform.transform_all()

    assert set(outputs.keys()) == {"hud_fmr", "acs_median_rent", "synthetic_lease_concessions"}
    assert all(path.exists() for path in outputs.values())
    assert len(json.loads(outputs["hud_fmr"].read_text())) == len(hud_raw)
    assert len(json.loads(outputs["acs_median_rent"].read_text())) == len(acs_raw)
    assert len(json.loads(outputs["synthetic_lease_concessions"].read_text())) > 0
