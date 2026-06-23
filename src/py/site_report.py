import copy
import json
import datetime
from jsonschema import validate
from jsonschema import ValidationError
import logging
import re


def build_query_lookups(site_report):
    """
    Returns fresh, independent lookup dicts for one report template.
    Does NOT mutate site_report — caller gets clean copies.
    """
    status_query_name_lookup = {}
    year_query_name_lookup = {}
    year_queries = {}

    for query in site_report['statusQueries']:
        q = dict(query)
        if q['type'] != 'year':
            status_query_name_lookup[q['query']] = q
        else:
            year_query_name_lookup[q['query']] = q
            year_queries[q['name']] = q
            year_queries[q['name']]["responseByYear"] = []

    return status_query_name_lookup, year_query_name_lookup, year_queries


class SiteReport:
    """Handles generating, validating, and saving a KDS report for one site and report version."""

    def __init__(self, report_template, site_identifier, site_name, mii_relevant_resources):
        self.site_identifier = site_identifier
        self.site_name = site_name
        self.version = report_template['version']
        self._mii_relevant_resources = mii_relevant_resources

        self._report = copy.deepcopy(report_template)
        self._report['siteName'] = site_name
        self._status_query_lookup, self._year_query_lookup, self._year_queries = build_query_lookups(self._report)
        self._found_query_names = set()

    def _get_status_queries(self, entry_array):
        status_queries = []
        list_of_report_queries = set()

        for entry in entry_array:
            resource = entry['resource']

            if resource['resourceType'] != 'Bundle':
                continue

            query_url = f'/{resource["link"][0]["url"]}'
            query_lookup_url = re.sub(r'date=[^&]*&', '', query_url)

            year_query = self._year_query_lookup.get(query_lookup_url)

            if year_query is not None:
                if "Encounter?date=" in query_url:
                    date_index = query_url.find("date")
                    cur_year = query_url[date_index + 7:date_index + 11]

                    year_query_resp = {
                        "year": int(cur_year),
                        "response": resource['total'],
                        "status": "success"
                    }

                    query_name = year_query['name']
                    self._year_queries[query_name]['responseByYear'].append(year_query_resp)
                    self._year_queries[query_name]['status'] = 'success'
                    list_of_report_queries.add(query_name)
                    continue

            status_query = self._status_query_lookup.get(query_url)

            if status_query is None:
                logging.debug(f'query with url {query_url} not a known status query => skipping')
                continue

            resp_status = entry['response']['status']
            if resp_status == '200' or resp_status == '200 OK':
                status_query['status'] = "success"
            else:
                status_query['status'] = "failed"

            status_query['query'] = query_url
            status_query['response'] = resource['total']

            status_queries.append(status_query)
            list_of_report_queries.add(status_query['name'])

        for value in self._year_queries.values():
            if 'status' not in value:
                value['status'] = "failed"
            status_queries.append(value)

        return status_queries, list_of_report_queries

    def _get_capability_statement(self, entry_array):
        cap_stat = {
            "software": {},
            "instantiates": [],
            "restResources": [],
        }
        rest_resources = []

        for entry in entry_array:
            if entry['response']['status'] != '200':
                continue

            resource = entry['resource']
            if resource['resourceType'] != 'CapabilityStatement':
                continue

            cap_stat["software"] = {
                "name": resource.get('software', {}).get('name', ""),
                "version": resource.get('software', {}).get('version', "")
            }

            search_resources = resource.get('rest', [{}])[0].get('resource', [])

            if not search_resources:
                logging.debug("No rest resources found - leaving empty")
                continue

            for rest_res in search_resources:
                res_type = rest_res.get('type', '')

                if res_type not in self._mii_relevant_resources:
                    continue

                rest_resource = {
                    'type': res_type,
                    'searchParam': rest_res.get('searchParam', []),
                }
                rest_resources.append(rest_resource)

        cap_stat["restResources"] = rest_resources
        return cap_stat

    def generate(self, json_result):
        """Populate the report from a DSF search result. Returns False if no report found."""
        if "entry" not in json_result:
            logging.warning(f'No report for site {self.site_name} found - not converting')
            return False

        json_report = json_result['entry'][0]
        self._report['datetime'] = (
            datetime.datetime.fromisoformat(json_report['resource']['meta']['lastUpdated'])
            .strftime("%Y-%m-%dT%H:%M:%S")
        )

        entries = json_report['resource']['entry']
        status_queries, self._found_query_names = self._get_status_queries(entries)
        self._report['statusQueries'] = status_queries
        self._report['capabilityStatement'] = self._get_capability_statement(entries)
        return True

    def validate(self):
        """Validate the report against the JSON schema and verify all expected queries are present."""
        with open("src/resources/kds-report-v2-schema.json", "r") as schema_file:
            kds_schema = json.load(schema_file)

        try:
            validate(instance=self._report, schema=kds_schema)
        except ValidationError as e:
            logging.error("VALIDATION ERROR: Schema not fulfilled")
            logging.error(e.message)
            return False

        return self._all_queries_present()

    def _all_queries_present(self):
        valid = True

        for query in self._status_query_lookup.values():
            if query['name'] not in self._found_query_names:
                logging.debug(f"VALIDATION ERROR: query {query['name']} missing from report")
                valid = False

        for query_name in self._year_queries:
            if query_name not in self._found_query_names:
                logging.debug(f"VALIDATION ERROR: year query {query_name} missing from report")
                valid = False

        if not valid:
            logging.error('VALIDATION ERROR: at least one query missing from report')

        return valid

    def save(self):
        """Write the generated report to a JSON file in the reports directory."""
        filename = f'reports/mii-report-site-{self.site_name}_{self._report["datetime"]}.json'
        with open(filename, "w+") as fp:
            json.dump(self._report, fp)


def generate_newest_report(templates, dsf_result, site_identifier, site_name, mii_relevant_resources):
    """Try templates newest-first, return the first SiteReport that generates and validates, or None."""
    sorted_templates = sorted(templates, key=lambda r: tuple(int(x) for x in r['version'].split('.')), reverse=True)
    for template in sorted_templates:
        report = SiteReport(template, site_identifier, site_name, mii_relevant_resources)
        if not report.generate(dsf_result):
            break
        if report.validate():
            return report
    return None
