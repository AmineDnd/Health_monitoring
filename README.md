# SmartLab — AI-Powered Clinical Monitoring Platform

> **Real-time patient vitals monitoring with ML anomaly detection, automated clinical alerts, and Telegram notifications — built on Odoo 17.**

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Telegram Bot Setup](#telegram-bot-setup)
- [User Roles](#user-roles)
- [Module Structure](#module-structure)
- [AI Service](#ai-service)
- [Alert & Escalation Pipeline](#alert--escalation-pipeline)
- [Production Checklist](#production-checklist)

---

## Overview

SmartLab is a healthcare SaaS platform that monitors patient vital signs in real time, runs an Isolation Forest AI model to detect anomalies, and automatically routes clinical alerts to the right medical staff via Odoo notifications and Telegram bots.

**Key capabilities:**

| Feature | Detail |
|---|---|
| Patient Management | Admission, discharge, ward assignment, triage routing |
| Vitals Recording | Heart rate, BP, SpO₂, temperature, glucose, respiratory rate |
| AI Anomaly Detection | Isolation Forest model with per-patient demographic thresholds |
| Clinical Alerts | Severity-tiered (Low → Critical) with AI clinical narrative |
| Alert Escalation | 3-level auto-escalation cron with Telegram + Odoo notifications |
| Telegram Bots | Doctor bot (new alerts) · Admin bot (unhandled escalations) |
| Dashboards | Role-specific OWL dashboards for Admin, Doctor, and Nurse |
| Shift Handoffs | Structured nurse handoff notes per ward |
| Analytics | Vital trend graphs, alert distribution pivot, SLA tracking |

---

## Architecture

```
                        ┌─────────────────────────────┐
                        │        Browser / Client      │
                        └──────────────┬──────────────┘
                                       │ HTTP :8069
                        ┌──────────────▼──────────────┐
                        │         Odoo 17 ERP          │
                        │   health_monitoring module   │
                        └──────┬───────────┬──────────┘
                               │           │
              XML-RPC / ORM    │           │ HTTP (internal)
                               │           │
                  ┌────────────▼──┐   ┌────▼──────────────┐
                  │  PostgreSQL   │   │  FastAPI AI Service │
                  │     15        │   │  (Isolation Forest) │
                  └───────────────┘   └─────────────────────┘
```

**Services:**

| Service | Image | Port |
|---|---|---|
| `odoo` | `odoo:17.0` | `8069` (public) |
| `db` | `postgres:15-alpine` | internal only |
| `ai_service` | custom FastAPI | internal only |

The AI service is **not** exposed to the host by default — Odoo communicates with it over the internal Docker network.

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Docker Engine + Compose v2)
- A Telegram account with two bots created via [@BotFather](https://t.me/BotFather)

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/AmineDnd/Health_monitoring.git
cd Health_monitoring
```

### 2. Create your environment file

```bash
cp .env.example .env
```

Open `.env` and fill in every value (see [Configuration](#configuration)).

### 3. Start all services

```bash
docker compose up -d --build
```

Wait ~30 seconds for PostgreSQL and Odoo to finish initializing, then check:

```bash
docker compose ps          # all services should show "running"
docker compose logs odoo   # watch for "Modules loaded"
```

### 4. Open Odoo

```
http://localhost:8069
```

Log in with:
- **Login:** `admin`
- **Password:** your Odoo master password (set during first-run setup)

### 5. Install the module

Go to **Apps → Search "Health Monitoring"** and click **Install**.

> The module installs automatically if you run the container with `-d smartlab_db` as configured in `odoo.conf`.

### 6. Set up Telegram bots

See the [Telegram Bot Setup](#telegram-bot-setup) section below.

---

## Configuration

Copy `.env.example` to `.env` and set the following variables:

```env
# PostgreSQL
POSTGRES_USER=odoo
POSTGRES_PASSWORD=<long-random-password>
POSTGRES_DB=smartlab_db

# Odoo master password (database manager page)
ODOO_MASTER_PASSWORD=<long-random-password>

# AI service — 'ai_service' is the Docker container name, NOT localhost
AI_SERVICE_URL=http://ai_service:8000

# Shared secret between Odoo and the AI service
AI_SERVICE_TOKEN=<long-random-token>

# FastAPI environment
ENVIRONMENT=production

# CORS origins allowed by the AI service
ALLOWED_ORIGINS=http://localhost:8069
```

> **Never commit `.env`** — it is listed in `.gitignore`.

---

## Telegram Bot Setup

SmartLab uses **two separate Telegram bots**:

| Bot | Purpose |
|---|---|
| 🩺 **Doctor bot** | New HIGH/CRITICAL alerts · Level-1 escalations → sent to doctors |
| 🔐 **Admin bot** | Level-2 and Level-3 escalations → sent to administrators |

### Step 1 — Create the bots

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` twice to create two bots
3. Copy both **HTTP API tokens**

### Step 2 — Save tokens in Odoo

Log in as admin and go to:

```
Settings → Technical → Parameters → System Parameters
```

Create (or update) these two keys:

| Key | Value |
|---|---|
| `health_monitoring.telegram_bot_token` | Doctor bot HTTP API token |
| `health_monitoring.telegram_admin_bot_token` | Admin bot HTTP API token |

### Step 3 — Link your Telegram account to a user

Each user (admin, doctor) must verify their Telegram Chat ID:

1. Open Telegram and message [@userinfobot](https://t.me/userinfobot) — send `/start` to get your numeric **Chat ID**.
2. In Odoo go to **Settings → Users → [your user] → Telegram Notifications tab**.
3. Paste your Chat ID, click **Send Verification Code**.
4. The Doctor bot will send a 6-digit code — enter it and click **Confirm Code**.

Once verified, that user will receive Telegram notifications through the appropriate bot.

---

## User Roles

| Role | Group | Capabilities |
|---|---|---|
| **Admin** | `group_health_admin` | Full access: wards, all patients, all alerts, analytics, user management, escalation notifications |
| **Doctor** | `group_health_doctor` | Own ward patients and alerts, vitals, alert claiming/resolving, clinical dashboards |
| **Nurse** | `group_health_nurse` | Vitals recording, patient list (read), shift handoffs |

---

## Module Structure

```
odoo/addons/health_monitoring/
├── models/
│   ├── health_patient.py          # Patient model, admission, ward logic
│   ├── health_vital_record.py     # Vitals recording + AI scoring trigger
│   ├── health_alert.py            # Alert lifecycle + Telegram notifications
│   ├── health_dashboard.py        # Role-specific dashboard KPIs
│   ├── health_ward.py             # Ward management
│   ├── health_handoff.py          # Shift handoff notes
│   ├── health_notification_log.py # Audit log for all notifications
│   ├── health_ai_analysis_job.py  # Async AI analysis job tracker
│   └── res_users.py               # Telegram verification fields + flow
├── views/                         # XML Odoo views and actions
├── wizard/                        # Clinical workflow wizards
├── security/                      # Groups, record rules, access CSV
├── static/src/
│   ├── js/                        # OWL dashboard components
│   ├── xml/                       # OWL templates
│   └── scss/                      # Custom SmartLab theme
└── data/
    ├── cron.xml                   # Scheduled escalation cron job
    └── demo_hospital_data.xml     # Demo data (opt-in only)
```

---

## AI Service

Located in `ai_service/`. Runs as a FastAPI application using an **Isolation Forest** model trained on patient vitals.

**Endpoints:**

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/` | Public | Health check |
| `POST` | `/analyze` | Token | Analyze a vitals reading for anomalies |
| `POST` | `/retrain` | Token | Retrain the model on recent data |
| `GET` | `/thresholds` | Token | Current dynamic thresholds |
| `GET` | `/model-info` | Token | Model metadata |

Protected endpoints require the `X-SmartLab-Token` header matching `AI_SERVICE_TOKEN`.

**How it works:**

1. A nurse records vitals → Odoo calls `POST /analyze`
2. The AI returns an anomaly score (0–100%) and detected anomalies
3. If score exceeds the threshold, Odoo creates a `health.alert` record
4. The alert severity (Low/Medium/High/Critical) is determined by the score
5. HIGH and CRITICAL alerts immediately notify doctors via Telegram

---

## Alert & Escalation Pipeline

```
Vitals recorded
      │
      ▼
AI /analyze called
      │
      ▼
Anomaly score ≥ threshold?
      │ YES
      ▼
health.alert created (HIGH or CRITICAL)
      │
      ├──▶ Odoo chatter ping  →  assigned doctor(s)
      └──▶ Telegram Doctor bot →  assigned doctor(s)
                │
                │ (cron runs every 5 min)
                │
      ┌─────────▼─────────┐
      │ Still unresolved? │
      └─────────┬─────────┘
                │
         ┌──────▼──────┐
         │  Level 1    │  → Doctor bot  → doctor re-pinged
         │  5–15 min   │
         └──────▼──────┘
         ┌──────▼──────┐
         │  Level 2    │  → Admin bot   → all admins notified
         │  15–30 min  │
         └──────▼──────┘
         ┌──────▼──────┐
         │  Level 3    │  → Admin bot   → all admins notified
         │  30+ min    │
         └─────────────┘
```

---

## Production Checklist

- [ ] All placeholders in `.env` replaced with strong random values
- [ ] `.env` is **not** committed to git
- [ ] AI service port `8000` is **not** published on the host
- [ ] Odoo `list_db = False` in `odoo.conf`
- [ ] Reverse proxy (nginx/Caddy) with TLS configured in front of Odoo
- [ ] PostgreSQL and Odoo filestore backups scheduled
- [ ] Telegram bot tokens stored only in Odoo System Parameters
- [ ] All clinical users have verified their Telegram Chat IDs
- [ ] Demo data **not** installed in production

---

## License

LGPL-3.0 — see [LICENSE](LICENSE) for details.
