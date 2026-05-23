"""Tests for src/ingestion/csv_reader.py"""
import tempfile
import textwrap
from pathlib import Path

import pytest
from src.ingestion.csv_reader import read_leads


def write_csv(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8"
    )
    f.write(textwrap.dedent(content))
    f.close()
    return Path(f.name)


# 3-row CSV: good, missing email, no https://
FIXTURE_CSV = """\
    first_name,last_name,email,company,website,linkedin_url,role
    Alice,Smith,alice@acme.com,Acme,acme.com,https://linkedin.com/in/alice,CEO
    Bob,Jones,,BobCo,http://bobco.com,https://linkedin.com/in/bob,CTO
    Carol,Lee,carol@carol.io,CarolCo,carol.io,https://linkedin.com/in/carol,VP Sales
"""


def test_reads_valid_rows_only(caplog):
    path = write_csv(FIXTURE_CSV)
    with caplog.at_level("WARNING"):
        leads = read_leads(path)

    # Row with missing email is skipped — should get 2 leads
    assert len(leads) == 2
    emails = {l["email"] for l in leads}
    assert "alice@acme.com" in emails
    assert "carol@carol.io" in emails
    assert "" not in emails


def test_missing_email_generates_warning(caplog):
    path = write_csv(FIXTURE_CSV)
    with caplog.at_level("WARNING"):
        read_leads(path)
    assert any("missing email" in r.message.lower() for r in caplog.records)


def test_https_prepended_when_missing():
    path = write_csv(FIXTURE_CSV)
    leads = read_leads(path)
    alice = next(l for l in leads if l["email"] == "alice@acme.com")
    assert alice["website"].startswith("https://")

    carol = next(l for l in leads if l["email"] == "carol@carol.io")
    assert carol["website"].startswith("https://")


def test_lead_id_is_16_chars():
    path = write_csv(FIXTURE_CSV)
    leads = read_leads(path)
    for lead in leads:
        assert len(lead["lead_id"]) == 16


def test_email_is_lowercased():
    csv_content = """\
        first_name,last_name,email,company,website,linkedin_url,role
        Dave,Foo,DAVE@Example.COM,FooCo,https://foo.com,https://li.com/in/dave,CTO
    """
    path = write_csv(csv_content)
    leads = read_leads(path)
    assert leads[0]["email"] == "dave@example.com"


def test_missing_required_field_skips_row(caplog):
    csv_content = """\
        first_name,last_name,email,company,website,linkedin_url,role
        ,Smith,eve@eve.com,EveCo,https://eve.com,https://li.com/in/eve,CFO
    """
    path = write_csv(csv_content)
    with caplog.at_level("WARNING"):
        leads = read_leads(path)
    assert len(leads) == 0
    assert any("missing required field" in r.message.lower() for r in caplog.records)
