import copy
import json
import datetime
import requests
import argparse
from jsonschema import validate
from jsonschema import ValidationError
import logging
import yaml
import re
from pathlib import Path

CONFIG = None
CONFIG_FILE = "config/config.yml"

DEFAULT_TIMEOUT = 30


def load_config():
    global CONFIG
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        CONFIG = yaml.safe_load(f)


parser = argparse.ArgumentParser()
parser.add_argument('--dsfbaseurl', help='base url of your local fhir server', default="https://dsf.fdpg.test.forschen-fuer-gesundheit.de/fhir")
parser.add_argument('--certfile', help='dsf client cert cert filepath', nargs="?", default="./certs/cert.pem")
parser.add_argument('--keyfile', help='dsf client cert key filepath', nargs="?", default="./certs/key.pem")
parser.add_argument('--loglevel', help='log level - possible values: DEBUG,INFO,WARNING,ERROR,CRITICAL ', nargs="?", default="INFO")
args = vars(parser.parse_args())

dsf_base_url = args["dsfbaseurl"]
log_level = args["loglevel"]
cert_file = args["certfile"]
key_file = args["keyfile"]

load_config()
activated_identifiers = []
site_mapping = json.loads(CONFIG['site-mapping'])
mii_relevant_resources = json.loads(CONFIG['mii-relevant-resources'])
reports = []


def get_reports(folder_path):
    folder_path = Path(folder_path)
    for file_path in folder_path.glob("*.json"):
        with file_path.open("r", encoding="utf-8") as f:
            reports.append(json.load(f))


def build_year_queries(site_report):
    """Returns a fresh year_queries dict for one site, with empty responseByYear lists."""
    year_queries = {}
    for query in site_report['statusQueries']:
        if query['type'] == 'year':
            q = dict(query)
            q['responseByYear'] = []
            year_queries[q['name']] = q
    return year_queries


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


def get_next_link(link_elem):

    if not link_elem:
        return None
    for elem in link_elem:
        if isinstance(elem, dict) and elem.get("relation") == "next":
            return elem.get("url")
    return None


def page_through_results_and_collect(resp, dsf_cert_path, dsf_key_path):

    result_entry = []

    while True:
        if resp.status_code != 200:
            break

        body = resp.json()
        entries = body.get("entry", [])
        if entries:
            result_entry.extend(entries)

        next_link = get_next_link(body.get("link"))
        if not next_link:
            break

        logging.debug(f"Getting next page {next_link}")
        resp = requests.get(
            next_link,
            cert=(dsf_cert_path, dsf_key_path),
            timeout=DEFAULT_TIMEOUT,
        )

    return result_entry


def get_site_identifiers():
    site_identifiers = []

    organizations_req_res = requests.get(
        f"{dsf_base_url}/Organization?_format=json",
        cert=(cert_file, key_file),
        timeout=DEFAULT_TIMEOUT,
    )

    organizations = page_through_results_and_collect(
        organizations_req_res, cert_file, key_file
    )

    for organization in organizations:
        for ident in organization['resource']['identifier']:
            if ident['system'] == 'http://dsf.dev/sid/organization-identifier':
                site_identifiers.append(ident['value'])

    return site_identifiers


def get_status_queries(entry_array, status_query_name_lookup, year_query_name_lookup, year_queries):

    status_queries = []
    list_of_report_queries = set()

    for entry in entry_array:
        resource = entry['resource']

        if resource['resourceType'] != 'Bundle':
            continue

        query_url = f'/{resource["link"][0]["url"]}'
        query_lookup_url = re.sub(r'date=[^&]*&', '', query_url)

        year_query = year_query_name_lookup.get(query_lookup_url)

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
                year_queries[query_name]['responseByYear'].append(year_query_resp)
                year_queries[query_name]['status'] = 'success'
                list_of_report_queries.add(query_name)
                continue

        status_query = status_query_name_lookup.get(query_url)

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

    for value in year_queries.values():

        if 'status' not in value:
            value['status'] = "failed"

        status_queries.append(value)

    return status_queries, list_of_report_queries


def get_capability_statement(entry_array):

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

            if res_type not in mii_relevant_resources:
                continue

            rest_resource = {
                'type': res_type,
                'searchParam': rest_res.get('searchParam', []),
            }
            rest_resources.append(rest_resource)

    cap_stat["restResources"] = rest_resources
    return cap_stat


def generate_report(json_report_search_result, site_ident, site_report,
                    status_query_name_lookup, year_query_name_lookup, year_queries):

    site_report['siteName'] = site_ident

    if "entry" not in json_report_search_result:
        logging.warning(f'No report for site {site_ident} found - not converting')
        return None, set()

    json_report = json_report_search_result['entry'][0]

    site_report['datetime'] = (
        datetime.datetime.fromisoformat(json_report['resource']['meta']['lastUpdated'])
        .strftime("%Y-%m-%dT%H:%M:%S")
    )
    status_queries, list_of_report_queries = get_status_queries(
        json_report['resource']['entry'],
        status_query_name_lookup,
        year_query_name_lookup,
        year_queries,
    )

    site_report['statusQueries'] = status_queries
    site_report['capabilityStatement'] = get_capability_statement(json_report['resource']['entry'])
    return site_report, list_of_report_queries


def ensure_all_queries(site_report, status_query_name_lookup, year_queries, list_of_report_queries):

    valid = True

    for query in status_query_name_lookup.values():
        if query['name'] not in list_of_report_queries:
            logging.debug(f"VALIDATION ERROR: query {query['name']} missing from report")
            valid = False

    for query_name in year_queries:
        if query_name not in list_of_report_queries:
            logging.debug(f"VALIDATION ERROR: year query {query_name} missing from report")
            valid = False

    if not valid:
        logging.error('VALIDATION ERROR: at least one query missing from report')

    return valid


def validate_report(site_report, status_query_name_lookup, year_queries, list_of_report_queries):

    with open("kds-report-v2-schema.json", "r") as schema_file:
        kds_schema = json.load(schema_file)

    try:
        validate(instance=site_report, schema=kds_schema)
    except ValidationError as validationError:
        logging.error("VALIDATION ERROR: Schema not fulfilled")
        logging.error(validationError.message)
        return False

    return ensure_all_queries(site_report, status_query_name_lookup, year_queries, list_of_report_queries)


def get_matching_reports_for_report(site_identifiers, report, report_version):

    status_query_name_lookup, year_query_name_lookup, _ = build_query_lookups(report)

    for site_identifier in site_identifiers:

        if len(activated_identifiers) > 0 and site_identifier not in activated_identifiers:
            continue

        logging.info(f'##### Report for site: {site_identifier}')

        if site_identifier not in site_mapping:
            logging.info("No mapping for site - falling back to ident")
            site_mapping[site_identifier] = site_identifier

        site_ident = site_mapping[site_identifier]
        logging.info(f'Converting report for site {site_ident}')

        site_report = copy.deepcopy(report)
        site_year_queries = build_year_queries(site_report)

        dsf_report_url = (
            f'{dsf_base_url}/Bundle'
            f'?identifier=http://medizininformatik-initiative.de/sid/cds-report-identifier'
            f'|{site_identifier}&_format=json&_sort=-_lastUpdated'
        )
        resp = requests.get(
            dsf_report_url,
            cert=(cert_file, key_file),
            timeout=DEFAULT_TIMEOUT,
        )

        site_report, list_of_report_queries = generate_report(
            resp.json(),
            site_ident,
            site_report,
            status_query_name_lookup,
            year_query_name_lookup,
            site_year_queries,
        )

        if site_report is None:
            continue

        if not validate_report(site_report, status_query_name_lookup, site_year_queries, list_of_report_queries):
            logging.error(f'Report for site {site_ident} did not validate => not saving to file')
            continue

        logging.info(f'SUCCESS: Converted report for site {site_ident}')
        with open(f'reports/mii-report-site-version{report_version}-{site_ident}_{site_report["datetime"]}.json', "w+") as fp:
            json.dump(site_report, fp)


if __name__ == "__main__":
    logging.getLogger().setLevel(log_level)
    site_identifiers = get_site_identifiers()
    get_reports("config/report-queries")

    for report in reports:
        report_version = report['version']

        logging.info(f'############# Getting reports in report version: -- {report_version} -- #############')
        get_matching_reports_for_report(site_identifiers, report, report_version)
