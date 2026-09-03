# Production notes — Service Center ERP

## Deploy

On the Windows/Linux server next to other company services:

```bash
cd <repo>
cp .env.example .env
# edit SECRET_KEY, SEED_*_PASSWORD, DATABASE_URL if external Postgres,
# PROXY_API_URL / PROXY_API_TOKEN

docker compose -f deploy/docker-compose.prod.yml --env-file .env up -d --build
```

App listens on host port **8080**. Put nginx/Caddy in front if needed (TLS, basic auth for extra safety).

## Backup

Postgres data is in Docker volume `scerp_prod_pgdata`:

```bash
docker run --rm -v scerp_prod_pgdata:/var/lib/postgresql/data -v ${PWD}:/backup alpine \
  tar czf /backup/scerp-pg-$(date +%F).tgz -C /var/lib/postgresql/data .
```

## After first boot

1. Login as `admin`, change workflow passwords (re-seed only creates missing users — rotate via DB or add password-change later).
2. Run Excel import from a machine that has the xlsx.
3. Sync ERP catalog when proxy is reachable.
