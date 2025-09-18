FROM python:3.13

COPY docker/requirements.txt /tmp/requirements.txt
RUN pip3 install -r /tmp/requirements.txt
RUN useradd -r -s /bin/false 10001
RUN mkdir opt/reportclient

WORKDIR /opt/reportclient

COPY dsf-report-parser.py /opt/reportclient/dsf-report-parser.py
COPY kds-report-v2-schema.json /opt/reportclient/kds-report-v2-schema.json
COPY docker/docker-entrypoint.sh /usr/local/bin/
COPY config /opt/reportclient/config
RUN chown -R 10001:10001 /opt/reportclient
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER 10001

ENTRYPOINT ["docker-entrypoint.sh"]