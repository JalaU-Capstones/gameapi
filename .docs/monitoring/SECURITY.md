# Monitoring stack security model

This document documents the security boundaries for the local observability stack that overlays the existing GameAPI Docker Compose environment.

## Assets in scope

- Prometheus time-series data and retention history.
- Grafana dashboards and admin credentials.
- Container and process metrics exposed by cAdvisor.
- PostgreSQL health and performance metrics from the exporter.
- API reachability and health checks from the blackbox exporter.

## Trust boundaries

- The developer machine is trusted.
- The `monitoring` network is trusted for the containers placed on it.
- The `frontend` network is not trusted by monitoring; no monitoring component joins it.
- The `backend` network is trusted only for read-only PostgreSQL scraping.

## Threat model

### Threat 1: an attacker on the LAN reaches Grafana

Mitigation: Grafana is bound to `127.0.0.1:3001`, not `0.0.0.0`. This is documented in the overlay and asserted in the Compose configuration for the local-only stack.

### Threat 2: an attacker on the LAN reaches `/metrics` through the public API port

Mitigation: this is accepted as a known limitation in the MVP. The public API remains reachable on `:8080`, and a future reverse proxy or ingress rule should 404 or block `/metrics` before the end of the public path. This is a future improvement planned for Prompt 6.

### Threat 3: an attacker gains code execution inside a monitoring container

Mitigations:

- `no-new-privileges: true`
- `cap_drop: ALL`
- `read_only: true` where supported
- non-root user for containers
- no host PID or host network namespace
- no broad host path mounts beyond the minimum required for cAdvisor

### Threat 4: cAdvisor requires access to the Docker socket or `/var/lib/docker`

Decision: the socket is not mounted in the secure default. Only the minimum read-only system paths necessary for container inspection are planned to be mounted. If deeper access is required for a specific exporter, that deviation must be documented explicitly in the prompt that introduces it, along with the compensating controls that reduce the risk.

### Threat 5: accidental deployment to Render

Mitigation: the monitoring stack lives in a separate Compose overlay, is never referenced from `render.yaml`, and is intended for local development only. A CI or pre-commit check can later grep for `docker-compose.monitoring.yml` in deployment manifests to prevent accidental inclusion.

## Hardening checklist

| Control | Value | Applies to | Rationale |
|---|---|---|---|
| No published ports except Grafana | `127.0.0.1:3001` | Grafana | Keeps access local to the developer machine. Prompt 3. |
| `no-new-privileges` | `true` | All monitoring services | Prevents privilege escalation inside containers. Prompt 3. |
| `cap_drop` | `ALL` | All monitoring services | Removes Linux capabilities by default. Prompt 3. |
| `read_only` | `true` | Monitoring services that support it | Reduces the writable filesystem attack surface. Prompt 3. |
| `restart: unless-stopped` | Enabled | All monitoring services | Minimal resilience for developer environments. Prompt 3. |
| Retention limit | `PROMETHEUS_RETENTION` | Prometheus | Keeps local disk usage bounded. Prompt 3. |
| Grafana auth | Admin credentials from `.env.monitoring` | Grafana | Ensures local authentication for the dashboard UI. Prompt 3. |

## What is explicitly out of scope

- Zeek or packet-capture profiling in the default stack.
- TLS termination for Grafana, because this is local-only development infrastructure.
- Authentication for Prometheus endpoints, because the stack is local-only and not internet-exposed.
- Multi-user Grafana or SSO, because the project does not yet require them.

## Review cadence

Review before every demo or public presentation.
