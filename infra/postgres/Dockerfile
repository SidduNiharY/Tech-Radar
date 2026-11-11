FROM pgvector/pgvector:0.8.7-pg18@sha256:c29f30688a9ad961691bdf0ec1650717cc132a5814619d80f80463d6e4c42e47
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-18-pgaudit && rm -rf /var/lib/apt/lists/*
# Hands the role passwords to the init scripts on first start (see the script).
COPY --chmod=0755 infra/postgres/tr-entrypoint.sh /usr/local/bin/tr-entrypoint.sh
ENTRYPOINT ["tr-entrypoint.sh"]
