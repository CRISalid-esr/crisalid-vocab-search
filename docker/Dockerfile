# syntax=docker/dockerfile:1

FROM opensearchproject/opensearch:3

# root needed to install plugins and write config files
USER root

ARG CONCEPTS_SRC

RUN opensearch-plugin install --batch analysis-icu

# Write opensearch.yml
RUN mkdir -p /usr/share/opensearch/config && \
    tee /usr/share/opensearch/config/opensearch.yml >/dev/null <<'YAML' && \
    chown -R opensearch:opensearch /usr/share/opensearch/config
plugins.security.disabled: true
discovery.type: single-node
bootstrap.memory_lock: true
network.host: 0.0.0.0
http.port: 9200
YAML

COPY index/settings.json /opt/os-config/settings.json
COPY index/mappings.body.json /opt/os-config/mappings.body.json
RUN chown -R opensearch:opensearch /opt/os-config

# ---------- Select the vocabulary at build time ----------
# Example: --build-arg CONCEPTS_SRC=build/jel/concepts.ndjson.gz
COPY ${CONCEPTS_SRC} /data/concepts.ndjson.gz

COPY build/jel/concepts.ndjson.gz /data/concepts.ndjson.gz
RUN chown -R opensearch:opensearch /data

COPY --chmod=0755 docker/entrypoint.sh /usr/local/bin/thesaurus-entrypoint.sh

USER opensearch

EXPOSE 9200 9600
ENTRYPOINT ["/usr/local/bin/thesaurus-entrypoint.sh"]
