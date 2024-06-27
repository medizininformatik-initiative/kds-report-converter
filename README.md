# kds-report-converter

This python script downloads the latest report for each site from the DSF FHIR mailbox as a FHIR bundle and converts the search response bundle into 
a dic dashboard report. It then saves the response in the reports folder.

## Run

1. Copy the .env.default to .env
2. Copy the config.default.yml to config.yml
3. Change the environment variables and config to your setup
4. execute the docker-compose
```sh
docker compose -f docker/docker-compose.yml up
```

## Environment Variables

| Name                          | Default                                                       | Description                            |
|:------------------------------|:--------------------------------------------------------------|:---------------------------------------|
| DSF_CERT_PATH                 | ./cert/dsf-cert.cer                                           | The local path of the DSF certificate. |
| DSF_KEY_PATH                  | ./cert/dsf-key.key                                            | The local path of the DSF key.         |
| DSF_BASE_URL                  | https://dsf.datenportal.dev.forschen-fuer-gesundheit.de/fhir  | Base url of the DSF FHIR mailbox       |
| LOG_LEVEL                     | INFO                                                          | Log level                              |

### Config

Additionally, the following fields in the [config.yml](config/config.yml) can be configured:

| Name                          | Description                                                                                                              | 
|:------------------------------|:-------------------------------------------------------------------------------------------------------------------------|
| site-mapping                  | Mapping from dsf site ident to abbreviation used by dic dashboard                                                        |
| mii-relevant-resources        | The resources currently relevant to the MII - used to extract relevant rest endpoints from capability statement          |


