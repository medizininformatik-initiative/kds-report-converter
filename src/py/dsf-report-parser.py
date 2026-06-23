import json
import requests
import argparse
import logging
import yaml
from pathlib import Path
from site_report import SiteReport, generate_newest_report

DEFAULT_TIMEOUT = 30


def load_config(config_file="config/config.yml"):
    with open(config_file, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_reports(folder_path):
    reports = []
    folder_path = Path(folder_path)
    for file_path in folder_path.glob("*.json"):
        with file_path.open("r", encoding="utf-8") as f:
            reports.append(json.load(f))
    return reports


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


def get_site_identifiers(dsf_base_url, cert_file, key_file):
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


if __name__ == "__main__":
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

    config = load_config()
    activated_identifiers = []
    site_mapping = json.loads(config['site-mapping'])
    mii_relevant_resources = json.loads(config['mii-relevant-resources'])

    logging.getLogger().setLevel(log_level)
    site_identifiers = get_site_identifiers(dsf_base_url, cert_file, key_file)
    reports = get_reports("config/report-queries")

    for site_identifier in site_identifiers:
        if len(activated_identifiers) > 0 and site_identifier not in activated_identifiers:
            continue

        if site_identifier not in site_mapping:
            logging.info("No mapping for site - falling back to ident")
            site_mapping[site_identifier] = site_identifier

        site_name = site_mapping[site_identifier]

        dsf_report_url = (
            f'{dsf_base_url}/Bundle'
            f'?identifier=http://medizininformatik-initiative.de/sid/cds-report-identifier'
            f'|{site_identifier}&_format=json&_sort=-_lastUpdated'
        )
        resp = requests.get(dsf_report_url, cert=(cert_file, key_file), timeout=DEFAULT_TIMEOUT)

        report = generate_newest_report(reports, resp.json(), site_identifier, site_name, mii_relevant_resources)

        if report:
            logging.info(f'SUCCESS: Converted report for site {site_name} using version {report.version}')
            report.save()
        else:
            logging.error(f'No report version succeeded for site {site_name}')
