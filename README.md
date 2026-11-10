# SeaMaster

An open-source Persian (RTL) management portal for organizations: meetings and resolutions,
projects (WBS/Gantt), operational tasks, kanban, timeline, agreements (MoU), org chart, member
birthdays, events, the HR / email / website-performance / energy dashboards, a Plotly Dash budget
dashboard, and the "Kaveh" Gemini chat assistant. Dates are shown in the Jalali calendar.

Flask + SQLAlchemy, SQLite by default (`DATABASE_URL` can point at PostgreSQL).

## Run locally

```bash
python -m pip install -r requirements-dev.txt
cp .env.example .env              # then fill in GEMINI_API_KEY etc.
python -m flask --app app init-db
python -m flask --app app create-admin your-name
python -m flask --app app run --debug
```

On Windows, `run-seamaster.bat` does the same (install, `init-db`, run on port 5000).

## Commands

| Command | What it does |
|---|---|
| `flask --app app init-db` | Create or migrate the schema. Safe to repeat; deploy scripts run it. |
| `flask --app app create-admin NAME` | Create an admin, or reset its password (`SEAMASTER_ADMIN_PASSWORD` or prompt). |
| `flask --app app ingest-pm [FILE] [--code --title --manager]` | Import/refresh a project plan (default `data/projects/current_pm.xlsx`). |
| `flask --app app db migrate -m "..."` | After changing `app_pkg/models.py`: generate a migration, review it, commit it. |
| `python -m pytest -q` | Test suite (uses a throwaway database, never `instance/`). |

## Configuration (environment or `.env`)

See `.env.example`. The important ones:

- `DATABASE_URL`: defaults to `sqlite:///instance/seamaster.db`
- `SECRET_KEY`: if unset, one is generated once into `instance/.secret_key`
- `FLASK_ENV`: `production` (default) or `development`
- `TRUSTED_PROXY_COUNT`: proxies in front of the app (nginx = 1, the default; 0 when run directly)
- `GEMINI_API_KEY`: enables the chat assistant
- `ORG_NAME`, `APP_TITLE`: your organization's name and the portal title shown in the UI
- `SEAMASTER_DATA_DIR`: where dashboard data files live (default `data/`)
- `ALLOW_SELF_REGISTRATION`, `ALLOW_DESTRUCTIVE_SEED`: off by default

## Access control

- Every page requires login (`app_pkg/auth.py`, `login_gate`).
- Pages are guarded by permission keys (`PERMISSIONS` in `app_pkg/auth.py`), ticked per user under
  **مسئولان اجرایی**. No permissions means no access; admins bypass all checks.
- Changes (creating meetings/resolutions, uploads, kanban moves, user management) also need the
  `manager` or `admin` role. Project tasks are limited to the project's members, its manager, and
  assignees.
- All POSTs need a CSRF token. Forms get it automatically, and `fetch()` calls from pages that
  extend `base.html` send it as a header.

## Layout

```
app.py                  WSGI entry (app = create_app())
app_pkg/
  __init__.py           app factory
  auth.py               login gate, permissions, require_access/require_roles/require_permissions
  security.py           CSRF (Flask-WTF), security headers, ProxyFix
  config.py             config classes, secret key loading
  db_setup.py           flask CLI: init-db, create-admin, ingest-pm
  models.py             SQLAlchemy models
  dash_mount.py         mounts dashboards/budget at /dash/budget (admin/manager only)
  paths.py              location of the data directory
  blueprints/           one module per feature
  services/             logic shared by blueprints (projects, AI, notifications, PM import)
  utils/                Jalali dates, uploads, sanitising
migrations/             Alembic migrations (Flask-Migrate)
templates/, static/     Jinja templates (all extend base.html) and assets
dashboards/budget/      the Plotly Dash budget dashboard
data/                   your CSV/Excel data (git-ignored; formats in data/README.md)
deploy/                 server provisioning/deploy scripts, nginx and systemd units
scripts/                setup, database backup and connection helpers
tests/                  pytest suite
```

Data files (`*.csv`, `*.xlsx`), databases, recordings and `.env` are not in git.

## Branding

Set `ORG_NAME` and `APP_TITLE` in `.env`, and replace `static/logo-dark.svg` with your own logo.

## License

MIT © HawkLabs Ltd. Free to use, modify and redistribute, including commercially, as long as the copyright notice and license are kept. See [LICENSE](LICENSE).
