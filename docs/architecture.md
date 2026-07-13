# Arsitektur Jepret

## Runtime foundation

```mermaid
flowchart TD
  PWA["Mobile-first Next.js PWA"] --> Caddy
  Caddy -->|/| Web[Next.js]
  Caddy -->|/api/v1/*| API[FastAPI]
  Caddy -->|/ws/*| API
  API --> DB[(PostgreSQL)]
  API --> MinIO
  API -. opsional .-> Redis
```

## ADR-001: Same-origin Caddy gateway

**Status:** Accepted

Caddy menjadi entry point tunggal agar cookie, CSRF, REST, dan WebSocket memiliki perilaku origin yang konsisten. PostgreSQL dan MinIO tetap internal; direct debug port memakai compose override eksplisit.
