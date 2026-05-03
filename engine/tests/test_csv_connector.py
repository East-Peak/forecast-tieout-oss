# engine/tests/test_csv_connector.py
"""TDD tests for CSVConnector — written before implementation."""
import os
import pytest
import tempfile
import shutil
from datetime import date, datetime

from engine.connectors.interface import (
    Deal, Company, Contact, TeamMember, StageTransition,
    ConnectorInterface, ConnectorCapabilities,
)
from engine.connectors.csv_connector import CSVConnector


@pytest.fixture
def data_dir(tmp_path):
    """Create a temp directory with required + optional CSV files."""
    # deals.csv — required
    (tmp_path / "deals.csv").write_text(
        "id,name,amount,stage,close_date,owner_id,type,created_date,segment,source,is_closed,is_won\n"
        "D001,Acme Corp - Enterprise,250000,Technical Evaluation,2026-06-30,U001,New Business,2026-01-15,Enterprise,Outbound,false,false\n"
        "D002,Beta Inc - Expansion,80000,Discovery,2026-07-15,U002,Expansion,2026-02-01,Mid-Market,Inbound,false,false\n"
        "D003,Gamma LLC - Closed,,Closed Won,2026-03-01,U001,New Business,2025-11-01,Enterprise,Outbound,true,true\n"
    )

    # team_members.csv — required
    (tmp_path / "team_members.csv").write_text(
        "id,name,role,segment,start_date,is_active,manager_id\n"
        "U001,Alice Johnson,AE,Enterprise,2025-06-01,true,M001\n"
        "U002,Bob Smith,AE,Mid-Market,2025-09-15,true,M001\n"
    )

    # companies.csv — optional
    (tmp_path / "companies.csv").write_text(
        "id,name,segment,industry,employee_count\n"
        "C001,Acme Corp,Enterprise,Technology,5000\n"
        "C002,Beta Inc,Mid-Market,Finance,500\n"
    )

    # contacts.csv — optional
    (tmp_path / "contacts.csv").write_text(
        "id,name,email,company_id,title\n"
        "CT001,Jane Doe,jane@acme.example,C001,VP Engineering\n"
        "CT002,John Roe,john@beta.example,C002,CTO\n"
    )

    # stage_history.csv — optional
    (tmp_path / "stage_history.csv").write_text(
        "deal_id,from_stage,to_stage,transition_date\n"
        "D001,,Discovery,2026-01-15T10:00:00\n"
        "D001,Discovery,Technical Evaluation,2026-02-20T14:30:00\n"
        "D002,,Discovery,2026-02-01T09:00:00\n"
    )

    return tmp_path


@pytest.fixture
def minimal_dir(tmp_path):
    """Directory with only the two required files, no optional ones."""
    (tmp_path / "deals.csv").write_text(
        "id,name,amount,stage,close_date,owner_id\n"
        "D001,Acme Corp,100000,Discovery,2026-06-30,U001\n"
    )
    (tmp_path / "team_members.csv").write_text(
        "id,name,role\n"
        "U001,Alice Johnson,AE\n"
    )
    return tmp_path


# ── Test 1: Loading deals from CSV ──────────────────────────────────

def test_load_deals(data_dir):
    conn = CSVConnector(data_dir)
    deals = conn.fetch_deals()
    assert len(deals) == 3
    # Verify first deal field values
    d = deals[0]
    assert d.id == "D001"
    assert d.name == "Acme Corp - Enterprise"
    assert d.amount == 250000.0
    assert d.stage == "Technical Evaluation"
    assert d.close_date == date(2026, 6, 30)
    assert d.owner_id == "U001"
    assert d.type == "New Business"
    assert d.created_date == date(2026, 1, 15)
    assert d.segment == "Enterprise"
    assert d.source == "Outbound"
    assert d.is_closed is False
    assert d.is_won is False


# ── Test 2: Missing/empty amount → None, not crash ─────────────────

def test_empty_amount_is_none(data_dir):
    conn = CSVConnector(data_dir)
    deals = conn.fetch_deals()
    d3 = [d for d in deals if d.id == "D003"][0]
    assert d3.amount is None


# ── Test 3: Loading team members ────────────────────────────────────

def test_load_team_members(data_dir):
    conn = CSVConnector(data_dir)
    members = conn.fetch_team_members()
    assert len(members) == 2
    m = members[0]
    assert m.id == "U001"
    assert m.name == "Alice Johnson"
    assert m.role == "AE"
    assert m.segment == "Enterprise"
    assert m.start_date == date(2025, 6, 1)
    assert m.is_active is True
    assert m.manager_id == "M001"


# ── Test 4: Capabilities — without optional files (all False) ───────

def test_capabilities_minimal(minimal_dir):
    conn = CSVConnector(minimal_dir)
    caps = conn.capabilities()
    assert caps.has_stage_history is False
    assert caps.has_contacts is False
    assert caps.has_companies is False


# ── Test 5: Capabilities — with optional files (all True) ──────────

def test_capabilities_full(data_dir):
    conn = CSVConnector(data_dir)
    caps = conn.capabilities()
    assert caps.has_stage_history is True
    assert caps.has_contacts is True
    assert caps.has_companies is True


# ── Test 6: Missing required file → FileNotFoundError ──────────────

def test_missing_required_file(tmp_path):
    # Only team_members, no deals
    (tmp_path / "team_members.csv").write_text(
        "id,name,role\n"
        "U001,Alice,AE\n"
    )
    with pytest.raises(FileNotFoundError, match="deals.csv"):
        CSVConnector(tmp_path)


# ── Test 7: Missing required column → ValueError ──────────────────

def test_missing_required_column(tmp_path):
    # deals.csv missing 'amount' column
    (tmp_path / "deals.csv").write_text(
        "id,name,stage,close_date,owner_id\n"
        "D001,Acme,Discovery,2026-06-30,U001\n"
    )
    (tmp_path / "team_members.csv").write_text(
        "id,name,role\n"
        "U001,Alice,AE\n"
    )
    with pytest.raises(ValueError, match="amount"):
        CSVConnector(tmp_path)


# ── Test 8: Stage history with deal_id filtering ───────────────────

def test_stage_history_filtering(data_dir):
    conn = CSVConnector(data_dir)
    # All history
    all_history = conn.fetch_stage_history()
    assert len(all_history) == 3

    # Filter to D001 only
    d001_history = conn.fetch_stage_history(deal_ids=["D001"])
    assert len(d001_history) == 2
    assert all(t.deal_id == "D001" for t in d001_history)

    # Verify field values on first transition
    first = d001_history[0]
    assert first.from_stage is None or first.from_stage == ""
    assert first.to_stage == "Discovery"
    assert isinstance(first.transition_date, datetime)


# ── Test 9: Optional files return empty list when absent ───────────

def test_optional_files_return_empty(minimal_dir):
    conn = CSVConnector(minimal_dir)
    assert conn.fetch_companies() == []
    assert conn.fetch_contacts() == []
    assert conn.fetch_stage_history() == []


# ── Additional edge cases ──────────────────────────────────────────

def test_connector_is_instance_of_interface(data_dir):
    conn = CSVConnector(data_dir)
    assert isinstance(conn, ConnectorInterface)


def test_deal_boolean_parsing(data_dir):
    """Closed Won deal should have is_closed=True, is_won=True."""
    conn = CSVConnector(data_dir)
    deals = conn.fetch_deals()
    d3 = [d for d in deals if d.id == "D003"][0]
    assert d3.is_closed is True
    assert d3.is_won is True


def test_companies_loading(data_dir):
    conn = CSVConnector(data_dir)
    companies = conn.fetch_companies()
    assert len(companies) == 2
    c = companies[0]
    assert c.id == "C001"
    assert c.name == "Acme Corp"
    assert c.employee_count == 5000


def test_contacts_loading(data_dir):
    conn = CSVConnector(data_dir)
    contacts = conn.fetch_contacts()
    assert len(contacts) == 2
    c = contacts[0]
    assert c.id == "CT001"
    assert c.email == "jane@acme.example"


# ── Stage normalization tests  ─────────────────────────────


@pytest.fixture
def field_mapping_file(tmp_path):
    """Field mappings file with stage_mapping for the test deals."""
    path = tmp_path / "field_mappings.yaml"
    path.write_text(
        "opportunity:\n"
        "  amount:\n"
        "    sf_field: Amount\n"
        "  stage:\n"
        "    sf_field: StageName\n"
        "    stage_mapping:\n"
        "      Discovery: S1\n"
        "      Technical Evaluation: S3\n"
        "      Closed Won: Won\n"
        "  close_date:\n"
        "    sf_field: CloseDate\n"
        "  owner_id:\n"
        "    sf_field: OwnerId\n"
    )
    return path


def test_no_field_mapping_passes_stages_through(data_dir):
    """Without field_mapping_path, stages are pass-through (legacy behavior)."""
    conn = CSVConnector(data_dir)
    deals = conn.fetch_deals()
    d = [d for d in deals if d.id == "D001"][0]
    assert d.stage == "Technical Evaluation"  # raw value preserved
    assert d.raw_stage is None  # no mapping was applied


def test_field_mapping_normalizes_deal_stages(data_dir, field_mapping_file):
    """With field_mapping_path, Deal.stage is model vocabulary; raw_stage preserves source."""
    # Move field_mapping_file out of data_dir so CSVConnector doesn't try to
    # read it as a deals/team file.
    fm_dir = data_dir.parent / "fm-deals"
    fm_dir.mkdir(exist_ok=True)
    fm_path = fm_dir / "field_mappings.yaml"
    fm_path.write_text(field_mapping_file.read_text())

    conn = CSVConnector(data_dir, field_mapping_path=fm_path)
    deals = conn.fetch_deals()

    by_id = {d.id: d for d in deals}
    assert by_id["D001"].stage == "S3"
    assert by_id["D001"].raw_stage == "Technical Evaluation"
    assert by_id["D002"].stage == "S1"
    assert by_id["D002"].raw_stage == "Discovery"
    assert by_id["D003"].stage == "Won"
    assert by_id["D003"].raw_stage == "Closed Won"


def test_field_mapping_normalizes_stage_history(data_dir, field_mapping_file):
    fm_dir = data_dir.parent / "fm-history"
    fm_dir.mkdir(exist_ok=True)
    fm_path = fm_dir / "field_mappings.yaml"
    fm_path.write_text(field_mapping_file.read_text())

    conn = CSVConnector(data_dir, field_mapping_path=fm_path)
    history = conn.fetch_stage_history(deal_ids=["D001"])

    # D001: empty -> Discovery (S1), then Discovery (S1) -> Technical Evaluation (S3)
    assert history[0].to_stage == "S1"
    assert history[0].raw_to_stage == "Discovery"
    assert history[0].from_stage is None
    assert history[1].to_stage == "S3"
    assert history[1].raw_to_stage == "Technical Evaluation"
    assert history[1].from_stage == "S1"
    assert history[1].raw_from_stage == "Discovery"


def test_missing_field_mapping_file_raises(tmp_path):
    """field_mapping_path pointing to a non-existent file is fail-loud."""
    (tmp_path / "deals.csv").write_text(
        "id,name,amount,stage,close_date,owner_id\n"
        "D001,X,1,Discovery,2026-06-30,U001\n"
    )
    (tmp_path / "team_members.csv").write_text("id,name,role\nU001,X,AE\n")
    bogus = tmp_path / "nonexistent.yaml"
    with pytest.raises(FileNotFoundError, match="field_mappings.yaml"):
        CSVConnector(tmp_path, field_mapping_path=bogus)


def test_missing_stage_mapping_block_raises(tmp_path):
    """Architectural decision: configured field_mapping_path with no stage_mapping is fail-loud.

    Silent pass-through would leave Deal.stage in raw vocabulary, which
    is the failure mode ARCHITECTURE.md explicitly prevents.
    """
    (tmp_path / "deals.csv").write_text(
        "id,name,amount,stage,close_date,owner_id\n"
        "D001,X,1,Discovery,2026-06-30,U001\n"
    )
    (tmp_path / "team_members.csv").write_text("id,name,role\nU001,X,AE\n")
    fm_path = tmp_path / "field_mappings.yaml"
    fm_path.write_text(
        "opportunity:\n"
        "  stage:\n"
        "    sf_field: StageName\n"  # no stage_mapping block
    )
    with pytest.raises(ValueError, match="stage_mapping is required"):
        CSVConnector(tmp_path, field_mapping_path=fm_path)


def test_empty_stage_mapping_raises(tmp_path):
    """Configured but empty stage_mapping is fail-loud ."""
    (tmp_path / "deals.csv").write_text(
        "id,name,amount,stage,close_date,owner_id\n"
        "D001,X,1,Discovery,2026-06-30,U001\n"
    )
    (tmp_path / "team_members.csv").write_text("id,name,role\nU001,X,AE\n")
    fm_path = tmp_path / "field_mappings.yaml"
    fm_path.write_text(
        "opportunity:\n"
        "  stage:\n"
        "    stage_mapping: {}\n"
    )
    with pytest.raises(ValueError, match="empty"):
        CSVConnector(tmp_path, field_mapping_path=fm_path)


def test_from_stage_whitespace_stripped(data_dir, field_mapping_file):
    """Whitespace in stage_history.csv from_stage values must be stripped
    before normalization, mirroring to_stage behavior. Otherwise " Discovery "
    wouldn't normalize the same as "Discovery".
    """
    history_path = data_dir / "stage_history.csv"
    history_path.write_text(
        "deal_id,from_stage,to_stage,transition_date\n"
        "D001,, Discovery ,2026-01-15T10:00:00\n"
        "D001, Discovery , Technical Evaluation ,2026-02-20T14:30:00\n"
    )
    fm_dir = data_dir.parent / "fm-strip"
    fm_dir.mkdir(exist_ok=True)
    fm_path = fm_dir / "field_mappings.yaml"
    fm_path.write_text(field_mapping_file.read_text())

    conn = CSVConnector(data_dir, field_mapping_path=fm_path)
    history = conn.fetch_stage_history(deal_ids=["D001"])
    # Both transitions normalize despite the whitespace
    assert history[0].to_stage == "S1"
    assert history[1].from_stage == "S1"
    assert history[1].to_stage == "S3"


def test_unmapped_stage_is_passed_through(tmp_path, field_mapping_file):
    """A stage value not in the mapping passes through unchanged. Engine
    code can detect/report unknown stages downstream; we don't silently
    drop information.
    """
    (tmp_path / "deals.csv").write_text(
        "id,name,amount,stage,close_date,owner_id\n"
        "D001,X,100,Some Custom Stage,2026-06-30,U001\n"
    )
    (tmp_path / "team_members.csv").write_text("id,name,role\nU001,X,AE\n")

    fm_path = tmp_path.parent / "fm-unmapped" / "field_mappings.yaml"
    fm_path.parent.mkdir(parents=True, exist_ok=True)
    fm_path.write_text(field_mapping_file.read_text())

    conn = CSVConnector(tmp_path, field_mapping_path=fm_path)
    deals = conn.fetch_deals()
    assert deals[0].stage == "Some Custom Stage"  # unchanged
    assert deals[0].raw_stage == "Some Custom Stage"  # raw preserved


# ── first_s2_entry_date population (ARCHITECTURE.md) ──────────────


def test_first_s2_entry_date_populated_from_stage_history(data_dir):
    """When stage_history.csv exists, Deal.first_s2_entry_date is the
    earliest transition where to_stage normalizes to 'S2'.
    """
    # Add S2 transitions to the test fixture.
    history_path = data_dir / "stage_history.csv"
    history_path.write_text(
        "deal_id,from_stage,to_stage,transition_date\n"
        "D001,,Discovery,2026-01-15T10:00:00\n"
        "D001,Discovery,Qualification,2026-02-01T10:00:00\n"
        "D001,Qualification,Technical Evaluation,2026-02-20T14:30:00\n"
        "D002,,Discovery,2026-02-01T09:00:00\n"
        "D002,Discovery,Qualification,2026-03-15T09:00:00\n"
        "D002,Qualification,Qualification,2026-04-01T09:00:00\n"
    )

    fm_path = data_dir.parent / "fm-firsts2" / "field_mappings.yaml"
    fm_path.parent.mkdir(parents=True, exist_ok=True)
    fm_path.write_text(
        "opportunity:\n"
        "  amount:\n"
        "    sf_field: Amount\n"
        "  stage:\n"
        "    sf_field: StageName\n"
        "    stage_mapping:\n"
        "      Discovery: S1\n"
        "      Qualification: S2\n"
        "      Technical Evaluation: S3\n"
        "      Closed Won: Won\n"
        "  close_date:\n"
        "    sf_field: CloseDate\n"
        "  owner_id:\n"
        "    sf_field: OwnerId\n"
    )

    conn = CSVConnector(data_dir, field_mapping_path=fm_path)
    deals = conn.fetch_deals()
    by_id = {d.id: d for d in deals}

    # D001 entered S2 (Qualification) on 2026-02-01
    assert by_id["D001"].first_s2_entry_date == date(2026, 2, 1)
    # D002 entered S2 on 2026-03-15 (earliest of two transitions)
    assert by_id["D002"].first_s2_entry_date == date(2026, 3, 15)
    # D003 has no stage_history entries -> None
    assert by_id["D003"].first_s2_entry_date is None


def test_first_s2_entry_date_none_without_stage_history(minimal_dir):
    """No stage_history.csv -> first_s2_entry_date is None for every deal."""
    conn = CSVConnector(minimal_dir)
    deals = conn.fetch_deals()
    assert all(d.first_s2_entry_date is None for d in deals)


# ── New optional Deal fields (the engine) ──────────────────────────────


def test_optional_arr_fields_default_to_none(data_dir):
    """If CSV doesn't include year_1_arr/arr/nacv/non_recurring, fields are None."""
    conn = CSVConnector(data_dir)
    deals = conn.fetch_deals()
    d = deals[0]
    assert d.year_1_arr is None
    assert d.arr is None
    assert d.nacv is None
    assert d.non_recurring is None
    assert d.effective_start_date is None
    assert d.effective_end_date is None
    assert d.revenue_type is None
    assert d.owner_name is None
    assert d.forecast_category is None
    assert d.source_stream is None


def test_optional_arr_fields_read_from_csv_when_present(tmp_path):
    """When CSV includes the optional ARR/finance/inventory columns, they're populated."""
    (tmp_path / "deals.csv").write_text(
        "id,name,amount,stage,close_date,owner_id,"
        "year_1_arr,arr,nacv,non_recurring,"
        "effective_start_date,effective_end_date,revenue_type,"
        "owner_name,forecast_category,source_stream\n"
        "D001,X,300000,Discovery,2026-06-30,U001,"
        "100000,200000,180000,20000,"
        "2026-07-01,2027-06-30,new_logo,"
        "Alice Johnson,Commit,Outbound\n"
    )
    (tmp_path / "team_members.csv").write_text(
        "id,name,role\nU001,Alice Johnson,AE\n"
    )

    conn = CSVConnector(tmp_path)
    deals = conn.fetch_deals()
    d = deals[0]
    assert d.year_1_arr == 100000.0
    assert d.arr == 200000.0
    assert d.nacv == 180000.0
    assert d.non_recurring == 20000.0
    assert d.effective_start_date == date(2026, 7, 1)
    assert d.effective_end_date == date(2027, 6, 30)
    assert d.revenue_type == "new_logo"
    assert d.owner_name == "Alice Johnson"
    assert d.forecast_category == "Commit"
    assert d.source_stream == "Outbound"
