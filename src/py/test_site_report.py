import copy
import importlib.util
import json
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load the hyphen-named module by file path
_spec = importlib.util.spec_from_file_location(
    "dsf_report_parser",
    os.path.join(REPO_ROOT, "src", "py", "dsf-report-parser.py"),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
SiteReport = _mod.SiteReport

TEST_DATA = os.path.join(REPO_ROOT, "src", "resources", "test-data")
CONFIG_DIR = os.path.join(REPO_ROOT, "config", "report-queries")

MII_RELEVANT_RESOURCES = [
    "Patient", "Encounter", "Observation", "Procedure", "Consent",
    "Medication", "MedicationStatement", "MedicationAdministration", "Condition",
    "Specimen", "DiagnosticReport", "ResearchSubject", "ServiceRequest",
]


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

def load_template(version):
    with open(os.path.join(CONFIG_DIR, f"report_v{version}.json")) as f:
        return json.load(f)


def load_test_bundle():
    with open(os.path.join(TEST_DATA, "test-report-bundle.json")) as f:
        return json.load(f)


def make_count_entry(query_url, total=0):
    return {
        "resource": {
            "resourceType": "Bundle",
            "type": "searchset",
            "total": total,
            "link": [{"relation": "self", "url": query_url.lstrip("/")}],
        },
        "response": {"status": "200"},
    }


def make_year_entries(query_url, years=(2022, 2023)):
    resource_type, params = query_url.lstrip("/").split("?", 1)
    return [
        {
            "resource": {
                "resourceType": "Bundle",
                "type": "searchset",
                "total": year * 10,
                "link": [{"relation": "self", "url": f"{resource_type}?date=eq{year}&{params}"}],
            },
            "response": {"status": "200"},
        }
        for year in years
    ]


def make_capability_statement_entry():
    return {
        "resource": {
            "resourceType": "CapabilityStatement",
            "software": {"name": "Test FHIR Server", "version": "1.0.0"},
            "rest": [{"resource": []}],
        },
        "response": {"status": "200"},
    }


def wrap_as_dsf_result(inner_resource):
    return {"entry": [{"resource": inner_resource}]}


def build_resource_from_entries(entries, last_updated="2026-01-01T12:00:00.000+00:00"):
    return {"meta": {"lastUpdated": last_updated}, "entry": entries}


def build_dsf_result_for_template(template):
    """Produce a minimal, complete DSF search result from a report template."""
    entries = []
    for query in template["statusQueries"]:
        if query["type"] == "count":
            entries.append(make_count_entry(query["query"]))
        else:
            entries.extend(make_year_entries(query["query"]))
    entries.append(make_capability_statement_entry())
    return wrap_as_dsf_result(build_resource_from_entries(entries))


def make_report(version):
    return SiteReport(load_template(version), "test-site.de", "TestSite", MII_RELEVANT_RESOURCES)


@pytest.fixture(autouse=True)
def repo_root_cwd():
    """validate() and save() open paths relative to cwd — pin to repo root."""
    original = os.getcwd()
    os.chdir(REPO_ROOT)
    yield
    os.chdir(original)


# ---------------------------------------------------------------------------
# DSF search result inputs — one per report version
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def dsf_result_v201():
    """v2.0.1 input: the real test bundle wrapped as a DSF search result."""
    return wrap_as_dsf_result(load_test_bundle())


@pytest.fixture(scope="module")
def dsf_result_v210():
    """v2.1.0 input: generated from the v2.1.0 template (covers all its queries)."""
    return build_dsf_result_for_template(load_template("2.1.0"))


# ---------------------------------------------------------------------------
# generate()
# ---------------------------------------------------------------------------

class TestGenerate:

    def test_returns_false_when_result_has_no_entry(self):
        report = make_report("2.0.1")
        assert report.generate({}) is False

    def test_v201_returns_true_with_test_bundle(self, dsf_result_v201):
        report = make_report("2.0.1")
        assert report.generate(dsf_result_v201) is True

    def test_v210_returns_true_with_generated_input(self, dsf_result_v210):
        report = make_report("2.1.0")
        assert report.generate(dsf_result_v210) is True

    def test_datetime_parsed_from_result(self, dsf_result_v201):
        report = make_report("2.0.1")
        report.generate(dsf_result_v201)
        assert report._report["datetime"] == "2026-05-22T08:28:22"

    def test_site_name_set_on_report(self, dsf_result_v201):
        report = make_report("2.0.1")
        report.generate(dsf_result_v201)
        assert report._report["siteName"] == "TestSite"

    def test_status_queries_populated(self, dsf_result_v201):
        report = make_report("2.0.1")
        report.generate(dsf_result_v201)
        assert len(report._report["statusQueries"]) > 0

    def test_capability_statement_populated(self, dsf_result_v201):
        report = make_report("2.0.1")
        report.generate(dsf_result_v201)
        cap = report._report["capabilityStatement"]
        assert "software" in cap
        assert "restResources" in cap

    def test_year_query_accumulates_responses_by_year(self, dsf_result_v201):
        report = make_report("2.0.1")
        report.generate(dsf_result_v201)
        year_queries = [q for q in report._report["statusQueries"] if q["type"] == "year"]
        assert len(year_queries) > 0
        assert len(year_queries[0]["responseByYear"]) > 0


# ---------------------------------------------------------------------------
# validate()
# ---------------------------------------------------------------------------

class TestValidate:

    def test_v201_passes_with_test_bundle(self, dsf_result_v201):
        report = make_report("2.0.1")
        report.generate(dsf_result_v201)
        assert report.validate() is True

    def test_v210_passes_with_generated_input(self, dsf_result_v210):
        report = make_report("2.1.0")
        report.generate(dsf_result_v210)
        assert report.validate() is True

    def test_fails_when_a_query_is_missing_from_response(self):
        template = load_template("2.0.1")
        entries = []
        for query in template["statusQueries"]:
            if query["type"] == "count":
                entries.append(make_count_entry(query["query"]))
            else:
                entries.extend(make_year_entries(query["query"]))
        entries.append(make_capability_statement_entry())
        entries.pop(0)  # drop one count query

        report = SiteReport(template, "test-site.de", "TestSite", MII_RELEVANT_RESOURCES)
        report.generate(wrap_as_dsf_result(build_resource_from_entries(entries)))
        assert report.validate() is False

    def test_fails_when_year_query_missing_from_response(self):
        template = load_template("2.0.1")
        entries = [
            make_count_entry(q["query"])
            for q in template["statusQueries"]
            if q["type"] == "count"
        ]
        entries.append(make_capability_statement_entry())
        # no year entries at all

        report = SiteReport(template, "test-site.de", "TestSite", MII_RELEVANT_RESOURCES)
        report.generate(wrap_as_dsf_result(build_resource_from_entries(entries)))
        assert report.validate() is False


# ---------------------------------------------------------------------------
# Isolation — two sites from the same template must not share state
# ---------------------------------------------------------------------------

class TestIsolation:

    def test_two_sites_do_not_share_query_state(self, dsf_result_v201):
        template = load_template("2.0.1")

        site_a = SiteReport(template, "site-a.de", "SiteA", MII_RELEVANT_RESOURCES)
        site_b = SiteReport(template, "site-b.de", "SiteB", MII_RELEVANT_RESOURCES)

        site_a.generate(dsf_result_v201)
        site_b.generate(dsf_result_v201)

        assert site_a._report["siteName"] == "SiteA"
        assert site_b._report["siteName"] == "SiteB"

        # statusQueries for each site are independent lists
        a_queries = site_a._report["statusQueries"]
        b_queries = site_b._report["statusQueries"]
        assert a_queries is not b_queries

    def test_two_sites_validate_independently(self, dsf_result_v201):
        template = load_template("2.0.1")

        good = SiteReport(template, "good.de", "Good", MII_RELEVANT_RESOURCES)
        good.generate(dsf_result_v201)

        entries = [make_count_entry(q["query"]) for q in template["statusQueries"] if q["type"] == "count"]
        entries.append(make_capability_statement_entry())
        bad_result = wrap_as_dsf_result(build_resource_from_entries(entries))
        bad = SiteReport(template, "bad.de", "Bad", MII_RELEVANT_RESOURCES)
        bad.generate(bad_result)

        assert good.validate() is True
        assert bad.validate() is False


# ---------------------------------------------------------------------------
# save()
# ---------------------------------------------------------------------------

class TestSave:

    def test_writes_json_file_to_reports_dir(self, tmp_path, monkeypatch):
        (tmp_path / "reports").mkdir()
        (tmp_path / "src" / "resources").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        import shutil
        shutil.copy(os.path.join(REPO_ROOT, "src", "resources", "kds-report-v2-schema.json"), tmp_path / "src" / "resources")

        template = load_template("2.0.1")
        dsf_result = build_dsf_result_for_template(template)
        report = SiteReport(template, "test-site.de", "TestSite", MII_RELEVANT_RESOURCES)
        report.generate(dsf_result)
        report.save()

        saved = list((tmp_path / "reports").glob("*.json"))
        assert len(saved) == 1
        with open(saved[0]) as f:
            data = json.load(f)
        assert data["siteName"] == "TestSite"
        assert data["version"] == "2.0.1"

    def test_filename_contains_version_and_site(self, tmp_path, monkeypatch):
        (tmp_path / "reports").mkdir()
        (tmp_path / "src" / "resources").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        import shutil
        shutil.copy(os.path.join(REPO_ROOT, "src", "resources", "kds-report-v2-schema.json"), tmp_path / "src" / "resources")

        template = load_template("2.0.1")
        report = SiteReport(template, "test-site.de", "TestSite", MII_RELEVANT_RESOURCES)
        report.generate(build_dsf_result_for_template(template))
        report.save()

        saved = list((tmp_path / "reports").glob("*.json"))
        assert "2.0.1" in saved[0].name
        assert "TestSite" in saved[0].name
