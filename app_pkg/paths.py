"""Where the app keeps uploaded/imported business data (CSV/Excel files).

Everything lives under one data directory, `data/` in the project root by default,
or wherever SEAMASTER_DATA_DIR points. Each feature uses its own subfolder:

    data/hr/           HR-DATA-1.csv, people.xlsx
    data/email/        weekly email campaign CSVs
    data/performance/  Clarity.csv, Chart.csv, ... (web analytics exports)
    data/energy/       energy_dash.xlsx (sheets: آب, برق, گاز)
    data/events/       events-YYYY-MM.csv
    data/projects/     current_pm.xlsx (project plan)

The data directory is git-ignored; see data/README.md for the expected file formats.
"""
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_root():
    return os.path.abspath(os.getenv('SEAMASTER_DATA_DIR') or os.path.join(PROJECT_ROOT, 'data'))


SUBDIRS = ('hr', 'email', 'performance', 'energy', 'events', 'projects', 'budget')


def ensure_data_dirs():
    """Create the data directory and its feature subfolders (a fresh clone has none)."""
    for sub in SUBDIRS:
        try:
            os.makedirs(data_dir(sub), exist_ok=True)
        except OSError:
            pass


def data_dir(*parts):
    """Absolute path of a folder (or file) inside the data directory."""
    return os.path.join(data_root(), *parts)
