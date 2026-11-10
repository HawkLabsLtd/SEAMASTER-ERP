# Data directory

The dashboards read CSV/Excel files from here. Everything in this folder except this README is
git-ignored, so your organization's data never ends up in the repository. Point
`SEAMASTER_DATA_DIR` somewhere else to keep it outside the checkout.

Most files can also be uploaded from the app itself, and the app saves them into the matching
subfolder.

| Folder | Files | Used by |
|---|---|---|
| `hr/` | `HR-DATA-1.csv` (or `.xlsx`), `people.xlsx` | HR dashboard, org chart import (`/hr`) |
| `email/` | one CSV per campaign/week, e.g. `31th_email.csv` | Email dashboard (`/email`) |
| `performance/` | `Clarity.csv`, `Chart.csv`, `Pages.csv`, `Queries.csv`, `Countries.csv`, `Devices.csv`, ... and optional `sections.json` | Website performance (`/performance`) |
| `energy/` | `energy_dash.xlsx` with sheets `آب`, `برق`, `گاز` | Energy dashboard (`/energy`) |
| `events/` | `events-YYYY-MM.csv` | Events calendar and Today view |
| `projects/` | `current_pm.xlsx` | `flask --app app ingest-pm` and the projects page |
| `budget/` | `budget_report_1399-1400.csv` (raw) or `cleaned_budget_long.csv` | Budget Dash app (`/dash/budget`) |

## Formats

**hr/HR-DATA-1.csv**: one row per employee. Columns used: `کد پرسنلی کارمند`, `نام کارمند`,
`نام خانوادگی کارمند`, `جنسیت کارمند`, `تاریخ تولد کارمند`, `نام واحد`, `سمت`,
`عنوان نوع استخدام`, `محل استخدام`, `مقطع تحصیلی مدرک تحصیلی`, `وضعیت تأهل وضعیت تاهل`,
`نوع قرارداد`, `مدت قرارداد`.

**email/*.csv**: rows of `Category,Metric,Value`.

**performance/*.csv**: exports from Microsoft Clarity (`Clarity.csv`) and Google Search Console
(the other files, under their default export names). `sections.json` maps a section label to the
URL prefix of its pages, e.g.

```json
{"اخبار": "https://example.com/news/", "خدمات": "https://example.com/services/"}
```

**events/events-YYYY-MM.csv**: columns `Title,Start,End,Location,Host,Owner,Manager,Responsible,
Attendees,Status,MeetingStatus,Catering,Hospitality,MeetLink,CalendarLink`.

**projects/current_pm.xlsx**: first sheet, task rows from row 12 on, columns
A–H = WBS, title, assignee, predecessor, start (Jalali), end (Jalali), duration (days),
progress (0–1 or 0–100). Assignees are matched to users by name.

**budget/cleaned_budget_long.csv**: columns `year,category,measure,value`. If only the raw
report is present, `dashboards/budget/clean_budget.py` produces it.
