FROM pgvector/pgvector:0.8.7-pg18@sha256:c29f30688a9ad961691bdf0ec1650717cc132a5814619d80f80463d6e4c42e47
# pgaudit, plus the Debian 12 security fixes for apt (pinned exactly).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-18-pgaudit=18.0-3.pgdg12+1 apt=2.6.2 libapt-pkg6.0=2.6.2 \
    && rm -rf /var/lib/apt/lists/*
# Replaces the Go gosu binary with a setpriv shim (see the file).
COPY --chmod=0755 infra/postgres/gosu /usr/local/bin/gosu
# Hands the role passwords to the init scripts on first start (see the script).
COPY --chmod=0755 infra/postgres/tr-entrypoint.sh /usr/local/bin/tr-entrypoint.sh
ENTRYPOINT ["tr-entrypoint.sh"]
