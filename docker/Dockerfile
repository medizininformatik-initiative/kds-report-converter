FROM python:3.13

COPY docker/requirements.txt /tmp/requirements.txt
RUN pip3 install -r /tmp/requirements.txt
RUN useradd -r -u 10001 -s /bin/false appuser
RUN mkdir opt/reportclient
RUN mkdir opt/reportclient/config

WORKDIR /opt/reportclient

COPY dsf-report-parser.py /opt/reportclient/dsf-report-parser.py
COPY kds-report-v2-schema.json /opt/reportclient/kds-report-v2-schema.json
COPY docker/docker-entrypoint.sh /usr/local/bin/
COPY config/config.default /opt/reportclient/config/config.yml
RUN chown -R 10001:10001 /opt/reportclient
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER 10001

ENTRYPOINT ["docker-entrypoint.sh"]