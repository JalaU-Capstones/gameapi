# Demo script — Observability stack

A reproducible walkthrough for a 10-minute presentation.

## Pre-demo checklist (do 15 minutes before)

1. Run `cp .env.monitoring.example .env.monitoring` if `.env.monitoring` does not already exist.
2. Set a strong `GRAFANA_ADMIN_PASSWORD` in `.env.monitoring`.
3. Start clean with `make monitoring-clean && make monitoring-up`.
4. Check `docker compose -f docker-compose.yml -f docker-compose.monitoring.yml --env-file .env.monitoring ps` and wait until the API, database, Prometheus, Grafana, and exporters report healthy.
5. Generate a few minutes of background API traffic in a second terminal:
   ```bash
   while true; do curl -s -o /dev/null http://localhost:8080/api/v2/auth/me; sleep 1; done
   ```
   Leave this running during the demo. This endpoint returns an unauthenticated response, which is still counted by the API request metrics.

## Live walkthrough

### 1. Show the stack running (30 seconds)

Run:

```bash
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml --env-file .env.monitoring ps
```

Point out that Grafana is the only service exposing a port, bound to `127.0.0.1:3001`.

### 2. Open Grafana (1 minute)

Open `http://localhost:3001` and log in using the credentials in `.env.monitoring`.

Prometheus is pre-provisioned as the datasource, and all four dashboards are already present. No manual dashboard or datasource setup is needed.

### 3. GameAPI Overview (2 minutes)

- Point out the request-rate activity from the background traffic.
- Hover over the p95 latency panel.
- Show the status-code distribution, including the unauthenticated responses from the traffic generator.

### 4. GameAPI Containers (2 minutes)

- Show the cgroup selector and the CPU, memory, network, and filesystem panels.
- This cAdvisor setup intentionally has no Docker socket. On the current host it exposes the root cgroup (`/`), not individual containers, so the dashboard cannot filter specifically to `game-api`.
- Point out that avoiding the Docker socket avoids granting cAdvisor root-equivalent control of the host Docker daemon.

### 5. GameAPI PostgreSQL (2 minutes)

- Show the active connections.
- Show the cache hit ratio.
- Open **Table sizes (live tuples)**. This is a row-count fallback because the installed exporter does not expose `pg_total_relation_size_bytes`.

### 6. GameAPI Health (1 minute)

- Show the probe status and successful health checks.
- Stop the API from another terminal:
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.monitoring.yml --env-file .env.monitoring stop api
  ```
- Wait up to 30 seconds for the blackbox scrape and dashboard refresh; the **Probe status** panel should turn red.
- Restart the API:
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.monitoring.yml --env-file .env.monitoring start api
  ```
  The panel should turn green within 30 seconds.

### Optional: capture API traffic (1 minute)

This is an opt-in demonstration. The capture service shares the API container's network namespace and captures port 8080 only; it does not capture host traffic. The pcap may contain request data and credentials, so do not commit or share it.

In a separate terminal, run `make monitoring-capture`. Generate an API request from another terminal, then press Ctrl+C to stop tcpdump:

```bash
curl -i http://localhost:8080/health
```

Export and inspect the pcap with Wireshark:

```bash
make monitoring-capture-export
wireshark capture/api.pcap
```

Afterward, remove the local pcap and the volume-backed capture:

```bash
rm capture/api.pcap
make monitoring-capture-clean
```

### 7. Render (30 seconds)

Open `https://gameapi-9vos.onrender.com/docs` in a browser.

Explain that the production API runs the same application code, but `/metrics` is disabled by default. The local monitoring overlay is not deployed to Render.

## Post-demo cleanup

Stop the background traffic loop with Ctrl+C, then run:

```bash
make monitoring-capture-clean
make monitoring-clean
```

If you exported a pcap, remove `capture/api.pcap` separately. The capture-clean target clears its container and volume; monitoring-clean removes the Prometheus and Grafana data volumes while preserving PostgreSQL data.
