#!/bin/bash

DSF_BASE_URL=${DSF_BASE_URL:-"https://dsf.forschen-fuer-gesundheit.de/fhir/Bundle?identifier="}
LOG_LEVEL=${LOG_LEVEL:-"INFO"}

python3 dsf-report-parser.py --dsfbaseurl $DSF_BASE_URL --loglevel $LOG_LEVEL