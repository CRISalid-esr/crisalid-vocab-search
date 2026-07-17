# syntax=docker/dockerfile:1

FROM opensearchproject/opensearch:3

# root needed to install plugins and write config files
USER root

# ---------- Select the embedded vocabularies at build time ----------
# Comma-separated list of vocabularies to embed. Defaults to all available.
# Example: --build-arg VOCABS="jel,acm"
ARG VOCABS="jel,acm,aat,elsst,pactols,euroscivoc"

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

COPY os-vocabs/index/settings.json /opt/os-config/settings.json
COPY os-vocabs/index/mappings.body.json /opt/os-config/mappings.body.json
RUN chown -R opensearch:opensearch /opt/os-config

# Copy all prebuilt vocabularies, then keep only the selected ones
COPY os-vocabs/build/ /tmp/vocabs-build/
RUN set -eu; \
    mkdir -p /data; \
    for vocab in $(echo "$VOCABS" | tr ',' ' '); do \
      src="/tmp/vocabs-build/${vocab}/concepts.ndjson.gz"; \
      if [ ! -f "$src" ]; then \
        echo "ERROR: no prebuilt data for vocabulary '${vocab}' (${src} missing)" >&2; \
        exit 1; \
      fi; \
      mkdir -p "/data/${vocab}"; \
      cp "$src" "/data/${vocab}/concepts.ndjson.gz"; \
      echo "$vocab" >> /data/vocabs.list; \
    done; \
    rm -rf /tmp/vocabs-build; \
    chown -R opensearch:opensearch /data

COPY --chmod=0755 os-vocabs/docker/entrypoint.sh /usr/local/bin/thesaurus-entrypoint.sh

# Bound the JVM heap by default (override with -e OPENSEARCH_JAVA_OPTS=... at run time)
ENV OPENSEARCH_JAVA_OPTS="-Xms1g -Xmx1g"

USER opensearch

EXPOSE 9200 9600
ENTRYPOINT ["/usr/local/bin/thesaurus-entrypoint.sh"]
