import json
import datetime
import requests
import argparse
from jsonschema import validate
from jsonschema import ValidationError
import logging
import yaml

CONFIG = None
CONFIG_FILE = "config/config.yml"


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
site_mapping = json.loads(CONFIG['site-mapping'])
mii_relevant_resources = json.loads(CONFIG['mii-relevant-resources'])


with open("config/report-queries.json", "r") as fp:
    site_report = json.load(fp)

status_query_name_lookup = {}
list_of_report_queries = set()

for query in site_report['statusQueries']:

    if query['type'] != 'year':
        status_query_name_lookup[query['query']] = query


def get_next_link(link_elem):
    for elem in link_elem:
        if elem["relation"] == "next":
            return elem["url"]

    return None


def page_through_results_and_collect(resp, dsf_cert_path, dsf_key_path):

    result_entry = []

    if resp.status_code != 200:
        return result_entry

    next_link = get_next_link(resp.json()["link"])
    if "entry" not in resp.json().keys():
        return result_entry
    if len(resp.json()["entry"]) > 0:
        result_entry = result_entry + resp.json()["entry"]

    if next_link:
        logging.debug(f"Getting next page {next_link}")
        resp = requests.get(next_link, cert=(dsf_cert_path, dsf_key_path))
        if "entry" not in resp.json().keys():
            return result_entry

        return result_entry + page_through_results_and_collect(resp, dsf_cert_path, dsf_key_path)

    return result_entry


def get_site_identifiers():

    site_identifiers = []

    organizations_req_res = requests.get(
        f"{dsf_base_url}/Organization?_format=json",
        cert=(cert_file, key_file),
        timeout=20,
    )

    organizations = page_through_results_and_collect(
        organizations_req_res, cert_file, key_file
    )

    for organization in organizations:
        for ident in organization['resource']['identifier']:
            if ident['system'] == 'http://dsf.dev/sid/organization-identifier':
                site_identifiers.append(ident['value'])

    return site_identifiers


def convert_leaf_to_json(leaf):
    value = ""
    attribs = leaf.attrib
    if "value" in attribs:
        value = attribs['value']

    obj = {
        leaf.tag: value
    }

    return obj


def convert_search_res_to_json(search_res, ns):

    obj = {}
    for child in search_res.findall("*", ns):
        child_json = convert_search_res_to_json(child, ns)
        key = list(child_json.keys())[0]
        insert_key = key.replace("{http://hl7.org/fhir}", "")

        if insert_key not in obj:
            obj[insert_key] = child_json[key]
        elif type(obj[insert_key]) is dict:
            new_list = [obj[insert_key]]
            obj[insert_key] = new_list
            obj[insert_key].append(child_json[key])
        elif type(obj[insert_key]) is str:
            new_list = [obj[insert_key]]
            obj[insert_key] = new_list
            obj[insert_key].append(child_json[key])
        else:
            obj[insert_key].append(child_json[key])

    if len(search_res.findall("*", ns)) == 0:
        return convert_leaf_to_json(search_res)

    tag = search_res.tag.replace("{http://hl7.org/fhir}", "")

    return {tag: obj}


def get_status_queries(entry_array):

    status_queries = []
    year_queries = {
        "sum-encounter-all-year": {
            "status": "success",
            "type": "year",
            "category": "profile",
            "name": "Jahresabfrage-Fall",
            "query": "/Encounter?_profile:below=https://www.medizininformatik-initiative.de/fhir/core/modul-fall/StructureDefinition/KontaktGesundheitseinrichtung&type=http://fhir.de/CodeSystem/Kontaktebene|einrichtungskontakt&_summary=count",
            "dateParam": "date",
            "responseByYear": []
        }
    }

    for entry in entry_array:

        resource = entry['resource']

        if resource['resourceType'] != 'Bundle':
            continue

        query_url = f'/{resource["link"][0]["url"]}'

        if "Encounter?date=" in query_url:
            date_index = query_url.find("date")
            cur_year = query_url[date_index + 7:date_index + 11]

            year_query_resp = {
              "year": int(cur_year),
              "response": resource['total'],
              "status": "success"
            }

            year_queries['sum-encounter-all-year']['responseByYear'].append(year_query_resp)
            list_of_report_queries.add('Jahresabfrage-Fall')
            continue

        status_query = status_query_name_lookup.get(query_url, None)

        if status_query is None:
            logging.debug(f'query with url {query_url} not a known status query => skipping')
            continue

        if entry['response']['status'] == '200' or entry['response']['status'] == '200 OK':
            status_query['status'] = "success"
        else:
            status_query['status'] = "failed"

        status_query['query'] = query_url
        status_query['response'] = resource['total']

        status_queries.append(status_query)
        list_of_report_queries.add(status_query['name'])

    status_queries.append(year_queries['sum-encounter-all-year'])
    return status_queries


def get_capability_statement(entry_array):

    cap_stat = {}
    restResources = []

    for entry in entry_array:

        if entry['response']['status'] != '200':
            continue

        resource = entry['resource']
        if resource['resourceType'] != 'CapabilityStatement':
            continue

        cap_stat = {
            "software": {
                "name": resource['software']['name'],
                "version": resource['software']['version']
            },
            "instantiates": []
        }

        search_resources = resource['rest'][0]['resource']
        for resource in search_resources:
            if resource['type'] not in mii_relevant_resources:
                continue

            rest_resource = {}
            rest_resource['type'] = resource['type']
            rest_resource['searchParam'] = resource['searchParam']
            restResources.append(rest_resource)

    cap_stat["restResources"] = restResources
    return cap_stat


def generate_report(json_report_search_result, site_ident):
    with open("config/report-queries.json", "r") as fp:
        site_report = json.load(fp)

    site_report['siteName'] = site_ident

    if "entry" not in json_report_search_result:
        logging.warning(f'No report for site {site_ident} found - not converting')
        return None

    json_report = json_report_search_result['entry'][0]

    site_report['datetime'] = datetime.datetime.fromisoformat(json_report['resource']['meta']['lastUpdated']).strftime("%Y-%m-%dT%H:%M:%S")
    site_report['statusQueries'] = get_status_queries(json_report['resource']['entry'])
    site_report['capabilityStatement'] = get_capability_statement(json_report['resource']['entry'])
    return site_report


def ensure_all_queries(site_report):

    valid = True

    for query in status_query_name_lookup.values():

        if query['name'] not in list_of_report_queries:
            logging.debug(f"VALIDATION ERROR: query {query['name']} missing from report")
            valid = False

    if not valid:
        logging.error('VALIDATION ERROR: at least one query missing from report')

    return valid


def validate_report(site_report):

    with open("kds-report-v2-schema.json", "r") as schema_file:
        kds_schema = json.load(schema_file)

    try:
        validate(instance=site_report, schema=kds_schema)
    except ValidationError as validationError:
        logging.error("VALIDATION ERROR: Schema not fulfilled")
        logging.error(validationError.message)
        return False

    return ensure_all_queries(site_report)


if __name__ == "__main__":

    logging.getLogger().setLevel(log_level)
    site_identifiers = get_site_identifiers()

    for site_identifier in site_identifiers:

        logging.info(f'##### Report for site: {site_identifier}')


        if site_identifier not in site_mapping:
            logging.info("No mapping for site - falling back to ident")
            site_mapping[site_identifier] = site_identifier

        site_ident = site_mapping[site_identifier]
        logging.info(f'Converting report for site {site_ident}')

        dsf_report_url = f'{dsf_base_url}/Bundle?identifier=http://medizininformatik-initiative.de/sid/cds-report-identifier|{site_identifier}&_format=json&_sort=-_lastUpdated'
        resp = requests.get(dsf_report_url, cert=(cert_file, key_file))

        site_report = generate_report(resp.json(), site_ident)
        if site_report is None:
            continue

        if validate_report(site_report) is False:
            logging.error(f'Report for site {site_ident} did not validate => not saving to file')
            continue


        logging.info(f'SUCCESS: Converted report for site {site_ident}')
        with open(f'reports/mii-report-site-{site_ident}_{site_report["datetime"]}.json', "w+") as fp:
            json.dump(site_report, fp)
