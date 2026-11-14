FROM private-apt-rebuild-amd64:local
USER root
COPY packages/ /packages/
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends git patch diffutils /packages/*.deb \
    && rm -rf /var/lib/apt/lists/* /packages
COPY source.tar.gz /source.tar.gz
COPY smoke.py /smoke.py
COPY check-upstream.py /check-upstream.py
ARG USER_ID
ARG GROUP_ID
USER ${USER_ID}:${GROUP_ID}
ENV HOME=/tmp
WORKDIR /tmp
RUN python3 /smoke.py \
    && mkdir upstream \
    && tar -xzf /source.tar.gz -C upstream \
    && python3 /check-upstream.py /tmp/upstream/diffofdiffs-1.1.0
