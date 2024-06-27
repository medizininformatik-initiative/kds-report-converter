#!/bin/bash

SITE_IDENTIFIER=${SITE_IDENTIFIER:-"http://highmed.org/sid/organization-identifier|ukhd.de"}
DSF_BASE_URL=${DSF_BASE_URL:-"https://dsf.forschen-fuer-gesundheit.de/fhir/Bundle?identifier="}
LOG_LEVEL=${LOG_LEVEL:-"INFO"}

python3 dsf-report-parser.py  --siteidents $SITE_IDENTIFIER --dsfbaseurl $DSF_BASE_URL --loglevel $LOG_LEVEL