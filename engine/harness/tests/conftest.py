"""Session fixtures for the catalog and query tests: estate A loaded once, and the generated company's catalog."""

import pytest

from engine.harness.catalog import load_catalog
from engine.harness.evidence import load
from engine.harness.tests.test_evidence_support import estate_dirs
from engine.harness.tests.test_query_support import CATALOG_PATH


@pytest.fixture(scope="session")
def estate():
    return load(estate_dirs())


@pytest.fixture(scope="session")
def cat():
    return load_catalog(CATALOG_PATH)
