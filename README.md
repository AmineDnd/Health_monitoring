# SmartLab Health Monitoring

SmartLab is a healthcare monitoring platform built with Odoo 17, PostgreSQL, and a FastAPI AI service. It manages patients, wards, vitals, clinical alerts, dashboards, and AI-assisted anomaly detection.

## Current Stabilization Status

The project is being stabilized phase by phase.

Completed:

- Phase 1: security and deployment blockers

Next:

- Phase 2: permissions and clinical safety
- Phase 3: vitals and monitoring reliability
- Phase 4: AI and alert lifecycle
- Phase 5: dashboard accuracy

Do not mix future-phase fixes into the current phase unless they are required to keep the platform stable.

## Architecture

Services:

- `odoo`: Odoo 17 ERP application
- `db`: PostgreSQL 15 database
- `ai_service`: FastAPI service for vitals anomaly analysis

Internal service flow:

```text
Odoo -> FastAPI AI service -> anomaly result -> Odoo vitals and alerts
```

The AI service is intended to stay private inside the Docker network. It is not published on host port `8000` in the default compose file.

## Environment Setup

Create a local `.env` file from the example:

```bash
cp .env.example .env
```

Then replace every placeholder value.

Required variables:

```env
POSTGRES_USER=replace_me
POSTGRES_PASSWORD=replace_with_long_random_password
POSTGRES_DB=smartlab_db
ODOO_MASTER_PASSWORD=replace_with_long_random_master_password
AI_SERVICE_URL=http://ai_service:8000
AI_SERVICE_TOKEN=replace_with_long_random_service_token
ENVIRONMENT=production
ALLOWED_ORIGINS=http://localhost:8069
```

Security notes:

- Never commit `.env`.
- Use long random values for `POSTGRES_PASSWORD`, `ODOO_MASTER_PASSWORD`, and `AI_SERVICE_TOKEN`.
- Rotate any credentials that were previously committed, shared, or used in demos.
- Keep `ENVIRONMENT=production` for production-like deployments.
- Only expose the AI service port in a separate local development override.

## Start The Platform

Build and start all services:

```bash
docker compose up -d --build
```

Check service status:

```bash
docker compose ps
```

View logs:

```bash
docker compose logs -f odoo
docker compose logs -f ai_service
docker compose logs -f db
```

Open Odoo:

```text
http://localhost:8069
```

## Odoo Module

The healthcare module is located at:

```text
odoo/addons/health_monitoring
```

Important areas:

- `models/`: patients, vitals, alerts, wards, handoffs, dashboards
- `views/`: Odoo XML views and actions
- `security/`: access rights and record rules
- `static/src/js`: OWL dashboard logic
- `static/src/xml`: OWL dashboard templates
- `wizard/`: clinical workflow wizards
- `data/cron.xml`: scheduled jobs

Demo data is opt-in through Odoo demo loading. It is not installed during a normal production module install.

## AI Service

The AI service lives in:

```text
ai_service
```

Protected endpoints:

- `POST /analyze`
- `POST /retrain`
- `GET /thresholds`
- `GET /model-info`

These endpoints require the `X-SmartLab-Token` header. Odoo sends this header using `AI_SERVICE_TOKEN`.

Public endpoint:

- `GET /`

If `ENVIRONMENT=production` and `AI_SERVICE_TOKEN` is missing, protected endpoints fail closed.

## Deployment Validation

Validate Docker Compose configuration:

```bash
docker compose --env-file .env config --quiet
```

Check for accidental public AI exposure:

```bash
docker compose --env-file .env config | findstr 8000
```

Check Odoo logs after startup:

```bash
docker compose logs --tail=100 odoo
```

Check AI service logs:

```bash
docker compose logs --tail=100 ai_service
```

## Production Checklist

Before production:

- Replace all placeholder secrets in `.env`.
- Confirm `.env` is not committed.
- Confirm the AI service is not exposed publicly.
- Confirm demo data is not installed.
- Confirm Odoo database listing is disabled.
- Confirm reverse proxy TLS is configured outside Docker Compose.
- Confirm backups are configured for PostgreSQL and Odoo filestore.
- Confirm monitoring exists for Odoo, PostgreSQL, and AI service health.
- Confirm role-based permissions are audited before clinical use.

## Development Notes

For local AI service debugging, create a separate Docker Compose override that publishes port `8000` and mounts source code. Do not add those development-only settings to the production compose file.

Recommended local override pattern:

```yaml
services:
  ai_service:
    ports:
      - "8000:8000"
    volumes:
      - ./ai_service:/app
```

## Stabilization Roadmap

Phase 1: security and deployment blockers

- Remove hardcoded production secrets.
- Keep AI service internal by default.
- Add shared-token protection to AI endpoints.
- Move demo hospital data out of normal production loading.
- Align Docker Compose with environment-driven deployment.

Phase 2: permissions and clinical safety

- Audit doctor, nurse, and admin access rights.
- Verify record rules for patients, vitals, alerts, chat, and dashboards.
- Prevent unauthorized alert claiming, resolving, editing, and deletion.

Phase 3: vitals and monitoring reliability

- Stabilize monitoring interval logic.
- Validate overdue, due soon, and up-to-date calculations.
- Prevent stale patient status and duplicate alert behavior.

Phase 4: AI and alert lifecycle

- Review scoring, severity mapping, alert deduplication, and re-analysis.
- Add safer retraining controls and model lifecycle safeguards.

Phase 5: dashboard accuracy

- Rebuild dashboard KPIs from backend truth.
- Verify filters, date ranges, ward statistics, and SLA calculations.

Phase 6: notifications and escalation

- Harden Telegram delivery, retries, queueing, and duplicate suppression.

Phase 7: patient data integrity

- Strengthen DOB, age, duplicate patient, admission, and ward assignment validation.

Phase 8: performance and scalability

- Reduce dashboard query cost.
- Remove avoidable N+1 queries.
- Add safe indexing and aggregation strategies.

Phase 9: UI and UX maturity

- Improve dashboard consistency, navigation clarity, accessibility, and loading states.

Phase 10: testing and production operations

- Add regression tests, permission tests, deployment checks, backup validation, and monitoring.
