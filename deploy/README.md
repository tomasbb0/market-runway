# Deploying Runway (single host, Docker Compose)

    /opt/runway/.env        RUNWAY_PASS, RUNWAY_SECRET  (chmod 600, never committed)
    /opt/runway/Caddyfile   copy of Caddyfile.ip (HTTP on the IP) or Caddyfile.domain (HTTPS)
    /opt/runway/app         this repository

Update:

    cd /opt/runway/app && git pull && docker compose -f deploy/docker-compose.yml up -d --build

Workspaces persist in the `runway-workspaces` volume across rebuilds.
