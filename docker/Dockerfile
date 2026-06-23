FROM python:3.13

COPY docker/requirements.txt /tmp/requirements.txt
RUN pip3 install -r /tmp/requirements.txt
RUN useradd -r -u 10001 -s /bin/false appuser
RUN mkdir -p /opt/reportclient/config /opt/reportclient/src/py /opt/reportclient/src/resources /opt/reportclient/reports

WORKDIR /opt/reportclient

COPY src/py/ /opt/reportclient/src/py/
COPY src/resources/kds-report-v2-schema.json /opt/reportclient/src/resources/kds-report-v2-schema.json
COPY docker/docker-entrypoint.sh /usr/local/bin/
COPY config/config.default.yml /opt/reportclient/config/config.yml
COPY config/report-queries /opt/reportclient/config/report-queries
RUN chown -R 10001:10001 /opt/reportclient
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER 10001

ENTRYPOINT ["docker-entrypoint.sh"]
