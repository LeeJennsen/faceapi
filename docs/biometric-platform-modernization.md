# Biometric Platform Modernization Blueprint

## Intent

This repository currently runs, but it is still organized around legacy "face" terminology and route-centric backend structure. The safest path to an original portfolio-grade platform is a staged migration that preserves behavior while introducing a new domain model, new UI shell, and clean internal boundaries.

Proposed platform name:

- `Sentari Biometric Analytics`

Unified domain vocabulary:

- `identity`
- `analysis`
- `profile`
- `observation`
- `device`
- `camera`
- `session`

## Target Folder Structure

### Frontend

```text
frontend/
  src/
    components/
      ui/
      charts/
      tables/
      feedback/
    pages/
      Overview/
      Operations/
      Identities/
      Observations/
      Devices/
      Settings/
      Auth/
    services/
      api.ts
      auth.service.ts
      analytics.service.ts
      settings.service.ts
    hooks/
      useAuth.ts
      useRealtime.ts
      useSettings.ts
      usePagination.ts
    utils/
      format.ts
      dates.ts
      export.ts
    theme/
      tokens.css
      themes.css
```

### Backend

```text
flask_face_api/
  app/
    config/
    controllers/
    services/
    repositories/
    models/
    middleware/
    monitoring/
    db/
    schemas/
    routes/
```

## Domain Renaming Map

| Legacy | Target |
| --- | --- |
| `face` | `identity` |
| `faces-mongo` | `identity-events` |
| `faces-mysql` | `identity-records` |
| `face_unique_id` | `identity_id` |
| `detect_face` | `analyze_identity` |
| `face_persons` | `identity_profiles` |
| `face_tracking` | `identity_observations` |
| `face_quality_score` | `analysis_quality_score` |
| `full-record` | `identity-summary` |
| `tracking` | `observations` |

## Target API Surface

Legacy endpoints should remain temporarily as compatibility aliases while the UI migrates to:

- `GET /api/v2/overview`
- `GET /api/v2/operations/overview`
- `GET /api/v2/identities`
- `GET /api/v2/identities/{identity_id}`
- `POST /api/v2/identities/analyze`
- `GET /api/v2/observations`
- `GET /api/v2/devices`
- `GET /api/v2/settings`
- `PUT /api/v2/settings`
- `GET /api/v2/auth/me`
- `GET /api/v2/export/observations.csv`
- `GET /api/v2/export/observations.json`

## Target Data Model

### `identity_profiles`

- `id`
- `identity_id`
- `display_name`
- `profile_status`
- `reference_images_json`
- `created_at`
- `updated_at`

### `identity_observations`

- `id`
- `identity_id`
- `observation_id`
- `captured_at`
- `camera_id`
- `device_id`
- `location`
- `analysis_confidence`
- `analysis_quality_score`
- `attention_seconds`
- `dwell_seconds`
- `attributes_json`
- `snapshot_url`

### `system_settings`

- `id`
- `theme_mode`
- `default_threshold`
- `landing_page`
- `auto_refresh_seconds`
- `dashboard_filters_json`
- `updated_by`
- `updated_at`

## First Safe Migration Slice

1. Introduce `controllers`, `services`, and `repositories` alongside the current `routes` package.
2. Add a new `api/v2` namespace using the new identity vocabulary.
3. Keep existing `/api/v1/faces-*` endpoints as compatibility wrappers.
4. Move dashboard data aggregation into a service layer instead of template-side orchestration.
5. Build a new `Operations` and `Overview` UI shell with explicit loading, empty, and error states.
6. Move settings persistence into Redis-backed server storage with localStorage cache on the client.

## UI Direction

- Replace the current single-template dashboard with a reusable app shell.
- Add light/dark themes via design tokens.
- Standardize `Button`, `Input`, `Card`, `Modal`, `Table`, and `Toast`.
- Add skeleton loading for charts and tables.
- Add explicit empty-state cards when no observations exist.
- Add retry actions for failed API calls.

## Performance And Observability

- Cache expensive overview aggregations in Redis.
- Keep Prometheus, Loki, Grafana, and Alertmanager as the observability spine.
- Add request latency, error rate, throughput, and queue depth metrics under the new service name.
- Add export endpoints that stream CSV instead of building large payloads in memory.

## Manual Migration Steps

1. Create new tables or views for `identity_profiles`, `identity_observations`, and `system_settings`.
2. Backfill legacy `face_*` records into the new schema.
3. Run the v1 and v2 APIs in parallel during migration.
4. Migrate the UI to v2 endpoints page by page.
5. Remove v1 compatibility routes only after dashboards, exports, and tests pass.
