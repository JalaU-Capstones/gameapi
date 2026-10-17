# Monitoring stack security model

This document documents the security boundaries for the local observability stack that overlays the existing GameAPI Docker Compose environment.

## Assets in scope

- Prometheus time-series data and retention history.
- Grafana dashboards and admin credentials.
- Container and process metrics exposed by cAdvisor.
- PostgreSQL health and performance metrics from the exporter.
- API reachability and health checks from the blackbox exporter.
- API packets captured locally when the opt-in `capture` profile is explicitly started.

## Trust boundaries

- The developer machine is trusted.
- The `monitoring` network is trusted for the containers placed on it.
- The `frontend` network is not trusted by monitoring; no monitoring component joins it.
- The `backend` network is trusted only for read-only PostgreSQL scraping.

## Threat model

### Threat 1: an attacker on the LAN reaches Grafana

Mitigation: Grafana is bound to `127.0.0.1:3001`, not `0.0.0.0`. This is documented in the overlay and asserted in the Compose configuration for the local-only stack.

### Threat 2: an attacker on the LAN reaches `/metrics` through the public API port

Mitigation: this is accepted as a known limitation in the MVP. The public API remains reachable on `:8080`, and a future reverse proxy or ingress rule should 404 or block `/metrics` before the end of the public path. This limitation is tracked separately; the opt-in capture profile does not change API exposure.

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

### Threat 6: a developer forgets to set Grafana credentials

Mitigation: the Compose overlay fails fast when `.env.monitoring` is missing or incomplete. The Grafana container requires `GF_SECURITY_ADMIN_PASSWORD`, and the value is interpolated from `.env.monitoring`, which is gitignored and never tracked by the repository. This prevents a default or empty password from being accepted by the official image.

### Threat 7: a container on the monitoring network calls Prometheus reload endpoints

Mitigation: Prometheus is started with `--web.enable-lifecycle`, which enables the `POST /-/reload` endpoint for dynamic config reloads. This is acceptable in a local-only developer workflow because Prometheus is not published and only containers on the `monitoring` network can reach it.

### Threat 8: cAdvisor exposes host information or gains elevated access

Mitigations and accepted limitations: cAdvisor has no Docker socket mount because access to the Docker socket is effectively root-equivalent on the host, even when the mount is read-only, since it permits control of the Docker daemon. cAdvisor receives only read-only mounts of `/sys`, `/proc`, `/var/lib/docker`, `/dev/disk`, and `/etc/machine-id`. It requires `SYS_PTRACE`, `/dev/kmsg`, and a writable container root filesystem for its memory-mapped paths. The `/var/lib/docker` host mount remains read-only. This local-only trade-off can reduce metrics visibility or cause cAdvisor to degrade gracefully on newer kernels; if it fails without the socket, keep the socket unmounted and revisit with an explicitly approved, documented deviation.

The PostgreSQL exporter connects with the least-privilege `gameapi_app` runtime role, not the migrator role. `sslmode=disable` is used only on the isolated local `backend` bridge because the bundled PostgreSQL service does not have TLS configured.

### Threat 9: packet captures expose API data or credentials

Mitigations and accepted limitations: packet capture is disabled unless the `capture` Compose profile is explicitly requested. The capture service shares the API container's network namespace and captures port 8080 only; it does not use host networking and cannot see unrelated host traffic. Its filesystem is read-only except for the dedicated named pcap volume and `/tmp` tmpfs. It drops all capabilities before adding only `NET_ADMIN` and `NET_RAW`, has no Docker socket or host bind mounts, and does not restart automatically. However, port 8080 traffic is not encrypted inside this local Compose setup, so a pcap may contain personally identifiable information, request/response bodies, authorization headers, JWTs, or other credentials. Keep captures local, never commit or share them, and delete both the exported file and the named volume after inspection.

## Prompt 3 — Prometheus and Grafana hardening

| Control | Value | Service | Rationale |
|---|---|---|---|
| Port binding | `127.0.0.1:3001:3000` | Grafana | Loopback only; not reachable from the LAN |
| No published port | — | Prometheus | Reachable only from the `monitoring` network |
| `read_only: true` | Both | Prometheus, Grafana | Filesystem is immutable except for named volumes and tmpfs |
| `no-new-privileges:true` | Both | Prometheus, Grafana | Blocks setuid/setgid escalation |
| `cap_drop: [ALL]` | Both | Prometheus, Grafana | No Linux capabilities |
| Non-root user | `65534:65534` / `472:472` | Prometheus, Grafana | Official image UIDs |
| Fail-fast on missing password | `:?` in Compose | Grafana | Prevents starting with a default or empty admin password |
| Anonymous access | Disabled | Grafana | `GF_AUTH_ANONYMOUS_ENABLED=false` |
| Self-registration | Disabled | Grafana | `GF_USERS_ALLOW_SIGN_UP=false` |
| Editable datasource | Disabled | Grafana | Provisioned state cannot drift from the file |
| Editable dashboards | Disabled | Grafana | Provisioned JSON is the source of truth |
| Retention | 7 days | Prometheus | Caps disk usage for a laptop workflow |
| Provisioned dashboards | JSON files, `allowUiUpdates: false` | Grafana | The repo is the source of truth; UI edits are ephemeral |

## Prompt 4 — Exporter hardening and deviations

| Control | Value | Service | Rationale |
|---|---|---|---|
| No published port | — | cAdvisor, postgres-exporter, blackbox-exporter | Reachable only from the `monitoring` network |
| `read_only: true` | Yes | postgres-exporter, blackbox-exporter | Filesystem immutable |
| `read_only: true` | **No** — deviation | cAdvisor | cAdvisor writes to memory-mapped paths; the `/var/lib/docker` host mount itself remains read-only |
| `cap_drop: [ALL]` | Yes | All three | Minimal capabilities |
| `cap_add: [SYS_PTRACE]` | **Deviation** | cAdvisor | Needed to inspect `/proc` of other processes |
| Container user | Root (image default) | cAdvisor | Host-path and device access increase impact; keep this service local-only |
| Host mounts | Read-only: `/sys`, `/proc`, `/var/lib/docker`, `/dev/disk`, `/etc/machine-id` | cAdvisor | Restricts host filesystem access to the required paths |
| `/dev/kmsg` device | `rwm` — deviation | cAdvisor | Required by cAdvisor for kernel log reads |
| Docker socket | **Not mounted** | cAdvisor | Avoids root-equivalent access to the host Docker daemon |
| DB credentials | `gameapi_app` | postgres-exporter | Least-privilege runtime role |
| `sslmode=disable` | Yes | postgres-exporter | Acceptable on the isolated `backend` network; revisit if TLS is added |
| Non-root user | `65534:65534` | postgres-exporter, blackbox-exporter | Runs exporters as an unprivileged user |
| Healthcheck | Yes | All three | Detects early failures |

## Prompt 5 — Dashboards

The four dashboards are provisioned as JSON files under `.docs/monitoring/grafana/provisioning/dashboards/`. Grafana is configured with `allowUiUpdates: false`, so a dashboard edited through the UI will not persist. This is intentional: the JSON files are the single source of truth, which means a compromised Grafana session cannot silently alter the dashboards that will be restored on the next provisioning cycle.

## Prompt 6 — Optional packet capture

| Control | Value | Service | Rationale |
|---|---|---|---|
| Activation | Explicit `capture` profile | capture | Packet capture never starts in the default Compose profile |
| Network namespace | `service:api` | capture | Limits visibility to traffic on the API container's interfaces, not host traffic |
| Capture filter | `port 8080` | capture | Captures API HTTP traffic only |
| Linux capabilities | `NET_ADMIN`, `NET_RAW`; all others dropped | capture | Provides tcpdump capture permissions with a narrow capability set |
| Filesystem | Read-only with `/tmp` tmpfs | capture | Limits writable paths to temporary storage and the dedicated pcap volume |
| Pcap storage | Named volume `gameapi_capture_data` | capture | Keeps capture data in Docker-managed storage, separate from the repository workspace until explicitly exported |
| Docker socket / host mounts | None | capture | Prevents access to the host daemon and host filesystem |
| Restart policy | `no` | capture | Prevents capture from restarting after it is stopped |
| PII / credentials | May be present in packets | Exported pcap | Treat as secret data; do not commit or share, and delete after use |

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
| cAdvisor host mounts | Read-only host paths; no Docker socket | cAdvisor | Limits host visibility while avoiding Docker daemon control. Prompt 4. |
| Capture profile | Disabled unless explicitly requested | capture | Prevents packet collection by default. Prompt 6. |
| Capture data | Local only; gitignored; removable with `make monitoring-capture-clean` | capture | Prevents accidental pcap commits and supports cleanup. Prompt 6. |

## What is explicitly out of scope

- Packet capture in the default stack; the opt-in API-only capture profile is documented in Prompt 6.
- TLS termination for Grafana, because this is local-only development infrastructure.
- Authentication for Prometheus endpoints, because the stack is local-only and not internet-exposed.
- Multi-user Grafana or SSO, because the project does not yet require them.

## Review cadence

Review before every demo or public presentation.
