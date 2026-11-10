import json

import os
import csv
import pandas as pd
from flask import Blueprint, render_template, flash, redirect, url_for, request
from app_pkg.utils.dates_fa import to_farsi_digits

from app_pkg.auth import require_permissions, require_roles
from app_pkg.utils.uploads import save_upload, UploadError, flash_upload_summary
bp = Blueprint('performance_bp', __name__, url_prefix='/performance')

from app_pkg.paths import data_dir
DATA_DIR = data_dir('performance')

# Site sections for the per-section breakdown: {label: URL prefix of its pages}.
# Put your own mapping in data/performance/sections.json; these are placeholders.
DEFAULT_SUBSECTIONS = {
    'صفحه اصلی': 'https://example.com/',
    'اخبار': 'https://example.com/news/',
    'خدمات': 'https://example.com/services/',
    'درباره ما': 'https://example.com/about/',
}


def get_subsections():
    path = os.path.join(DATA_DIR, 'sections.json')
    try:
        with open(path, encoding='utf-8') as f:
            sections = json.load(f)
        if isinstance(sections, dict) and sections:
            return {str(k): str(v) for k, v in sections.items()}
    except (OSError, ValueError):
        pass
    return DEFAULT_SUBSECTIONS

_PERF_CACHE = {'mtime': 0, 'data': None, 'clarity': None}

def _get_data_dir_mtime():
    try:
        if not os.path.exists(DATA_DIR):
            return 0
        return max(os.path.getmtime(os.path.join(DATA_DIR, f)) for f in os.listdir(DATA_DIR) if f.endswith('.csv'))
    except Exception:
        return 0

def load_clarity_data():
    """Load and parse Clarity.csv with mtime caching."""
    current_mtime = _get_data_dir_mtime()
    if _PERF_CACHE['clarity'] is not None and _PERF_CACHE['mtime'] == current_mtime:
        return _PERF_CACHE['clarity']

    clarity_data = {
        'sessions': {},
        'insights': [],
        'top_pages': [],
        'scroll_depth': '0'
    }
    path = os.path.join(DATA_DIR, 'Clarity.csv')
    if not os.path.exists(path):
        _PERF_CACHE['clarity'] = clarity_data
        return clarity_data

    try:
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            rows = list(reader)
            
            current_section = None
            for row in rows:
                if not row or all((not (c or '').strip()) for c in row):
                     continue
                
                if row[0].strip() == 'Metric':
                    current_section = (row[1] or '').strip()
                    continue
                
                if not current_section:
                    continue
                    
                # Parsing logic based on section
                if current_section == 'Sessions' and len(row) >= 3:
                    if row[1].strip() == 'Total sessions':
                        clarity_data['sessions']['Total sessions'] = row[2].strip()
                elif current_section == 'Insights' and len(row) >= 3:
                     # e.g. Rage clicks, Dead clicks
                     clarity_data['insights'].append({
                         'name': row[1].strip(),
                         'value': row[2].strip(),
                         'percent': row[3].strip() if len(row) > 3 else ''
                     })
                elif current_section == 'Top pages' and len(row) >= 3:
                     clarity_data['top_pages'].append({
                         'url': row[1].strip(),
                         'sessions': row[2].strip()
                     })
                elif current_section == 'Scroll depth':
                     if len(row) >= 3 and row[2].strip():
                         clarity_data['scroll_depth'] = row[2].strip()

    except Exception as e:
        print(f"Error loading Clarity CSV: {e}")
        
    _PERF_CACHE['clarity'] = clarity_data
    _PERF_CACHE['mtime'] = current_mtime
    return clarity_data

def load_data():
    """Load and process data from CSV files with mtime caching."""
    current_mtime = _get_data_dir_mtime()
    if _PERF_CACHE['data'] is not None and _PERF_CACHE['mtime'] == current_mtime:
        return _PERF_CACHE['data']

    data = {}
    
    # --- Chart.csv (Time Series Data) ---
    chart_path = os.path.join(DATA_DIR, 'Chart.csv')
    if os.path.exists(chart_path):
        try:
            df_chart = pd.read_csv(chart_path)
            # Normalize columns
            if 'Date' in df_chart.columns:
                df_chart['Date'] = pd.to_datetime(df_chart['Date'])
                df_chart = df_chart.sort_values('Date')
                data['chart_data'] = df_chart.to_dict(orient='list')
                # Strings for JSON
                data['chart_data']['Date_Str'] = [d.strftime('%Y-%m-%d') for d in df_chart['Date']]
                
                # Heatmap Data Preparation
                df_heat = df_chart.copy()
                df_heat['DayOfWeek'] = df_heat['Date'].dt.day_name()
                df_heat['WeekNum'] = df_heat['Date'].dt.isocalendar().week
                
                day_map = {
                    'Saturday': 'شنبه', 'Sunday': 'یکشنبه', 'Monday': 'دوشنبه', 
                    'Tuesday': 'سه‌شنبه', 'Wednesday': 'چهارشنبه', 'Thursday': 'پنج‌شنبه', 'Friday': 'جمعه'
                }
                df_heat['DayOfWeek_Fa'] = df_heat['DayOfWeek'].map(day_map)
                
                # Group by WeekNum and DayOfWeek_Fa
                heatmap_grouped = df_heat.groupby(['WeekNum', 'DayOfWeek_Fa', 'DayOfWeek'])['Clicks'].sum().reset_index()
                
                # Custom day sort order
                day_order = ['شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنج‌شنبه', 'جمعه']
                heatmap_grouped['DayOrder'] = heatmap_grouped['DayOfWeek_Fa'].apply(lambda x: day_order.index(x) if x in day_order else 99)
                heatmap_grouped = heatmap_grouped.sort_values(['WeekNum', 'DayOrder'])
                
                data['heatmap'] = heatmap_grouped.to_dict(orient='records')
            else:
                data['chart_data'] = {}
        except Exception as e:
            data['chart_data'] = {}
    else:
        data['chart_data'] = {}

    # --- Other CSVs ---
    for name in ['Devices', 'Countries', 'Queries', 'Pages']:
        path = os.path.join(DATA_DIR, f'{name}.csv')
        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
                data[name.lower()] = df.to_dict(orient='records')
            except:
                data[name.lower()] = []
        data.setdefault(name.lower(), [])
    
    # Clarity
    data['clarity'] = load_clarity_data()
    
    _PERF_CACHE['data'] = data
    _PERF_CACHE['mtime'] = current_mtime
    return data

@bp.route('/')
@require_permissions('performance.view')
def index():
    try:
        data = load_data()
        
        # --- Subsection Filtering ---
        selected_section = request.args.get('section', next(iter(get_subsections())))
        subsection_data = {}
        
        if 'pages' in data:
            prefix = get_subsections().get(selected_section, '')
            # Filter pages list
            filtered_pages = [
                p for p in data['pages'] 
                if str(p.get('Top pages', '')).startswith(prefix) or str(p.get('Page', '')).startswith(prefix)
            ]
            
            # Calculate Subsection KPIs
            sub_clicks = sum(p.get('Clicks', 0) for p in filtered_pages)
            sub_impr = sum(p.get('Impressions', 0) for p in filtered_pages)
            if filtered_pages:
                sub_ctr = sum(float(str(p.get('CTR', '0')).replace('%','')) for p in filtered_pages) / len(filtered_pages)
            else:
                sub_ctr = 0
            
            subsection_data = {
                'name': selected_section,
                'clicks': sub_clicks,
                'impressions': sub_impr,
                'ctr': sub_ctr,
                'pages': filtered_pages[:10] # Top 10
            }

        # --- Main KPIs ---
        # Re-calculating carefully
        chart_ts = data.get('chart_data', {})
        main_kpis = {
            'clicks': 0, 'impressions': 0, 'ctr': 0, 'position': 0
        }
        if chart_ts and 'Clicks' in chart_ts:
             main_kpis['clicks'] = sum(chart_ts['Clicks'])
             main_kpis['impressions'] = sum(chart_ts['Impressions'])
             
             # CTR might be strings or floats in the list
             ctrs = chart_ts.get('CTR', [])
             clean_ctrs = []
             for c in ctrs:
                 if isinstance(c, str):
                     clean_ctrs.append(float(c.replace('%','')))
                 else:
                     clean_ctrs.append(float(c))
             
             if clean_ctrs:
                 main_kpis['ctr'] = sum(clean_ctrs) / len(clean_ctrs)
             
             pos = chart_ts.get('Position', [])
             if pos:
                 main_kpis['position'] = sum(pos) / len(pos)

        # Prepare Charts
        chart_data = {
            'labels': data.get('chart_data', {}).get('Date_Str', []),
            'clicks': data.get('chart_data', {}).get('Clicks', []),
            'impressions': data.get('chart_data', {}).get('Impressions', [])
        }
        
        print(f"DEBUG chart_data: labels={len(chart_data['labels'])}, clicks={len(chart_data['clicks'])}, impressions={len(chart_data['impressions'])}")
        if chart_data['labels']:
            print(f"DEBUG first label: {chart_data['labels'][0]}, first click: {chart_data['clicks'][0]}")

        # Heatmap Process for Template
        # We need distinct Weeks and Days for the grid
        heatmap_weeks = sorted(list(set(d['WeekNum'] for d in data.get('heatmap', [])))) if 'heatmap' in data else []
        days_order = ['شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنج‌شنبه', 'جمعه']
        
        # Create a grid dictionary
        heatmap_grid = {} # (day, week) -> value
        for item in data.get('heatmap', []):
            heatmap_grid[(item['DayOfWeek_Fa'], item['WeekNum'])] = item['Clicks']

        return render_template('performance/index.html', 
                               kpis=main_kpis, 
                               data=data,
                               chart_data=chart_data,
                               subsection_data=subsection_data,
                               subsections_list=get_subsections().keys(),
                               selected_section=selected_section,
                               heatmap_weeks=heatmap_weeks,
                               heatmap_days=days_order,
                               heatmap_grid=heatmap_grid,
                               to_farsi_digits=to_farsi_digits)
                               
    except Exception as e:
        import traceback
        traceback.print_exc()
        flash(f'خطا در بارگذاری داده‌ها: {str(e)}', 'danger')
        return render_template('performance/index.html', 
            kpis={'clicks': 0, 'impressions': 0, 'ctr': 0, 'position': 0},
            data={'pages': [], 'queries': [], 'devices': [], 'countries': [], 'clarity': {}},
            chart_data={'labels': [], 'clicks': [], 'impressions': []}, subsection_data={}, 
            subsections_list=[], heatmap_weeks=[], heatmap_days=[], heatmap_grid={})

@bp.route('/update', methods=['POST'])
@require_roles('manager', 'admin')
def update_data():
    """Handle CSV file uploads; each form field replaces one fixed data file."""
    file_map = {
        'chart_file': 'Chart.csv',
        'clarity_file': 'Clarity.csv',
        'countries_file': 'Countries.csv',
        'devices_file': 'Devices.csv',
        'pages_file': 'Pages.csv',
        'queries_file': 'Queries.csv',
        'filters_file': 'Filters.csv',
        'dates_file': 'Dates.csv'
    }
    saved, errors = 0, []
    for field_name, target_filename in file_map.items():
        file = request.files.get(field_name)
        if not file or not file.filename:
            continue
        try:
            save_upload(file, DATA_DIR, {'csv'}, filename=target_filename)
            saved += 1
        except UploadError as e:
            errors.append(str(e))
    flash_upload_summary(saved, errors)
    return redirect(url_for('performance_bp.index'))


@bp.route('/api/subsection/<section_name>')
@require_permissions('performance.view')
def get_subsection_data(section_name):
    """API endpoint for AJAX subsection data loading"""
    from flask import jsonify
    
    data = load_data()
    
    if section_name not in get_subsections():
        return jsonify({'error': 'Section not found'}), 404
    
    prefix = get_subsections().get(section_name, '')
    filtered_pages = [
        p for p in data.get('pages', [])
        if str(p.get('Top pages', '')).startswith(prefix) or str(p.get('Page', '')).startswith(prefix)
    ]
    
    sub_clicks = sum(p.get('Clicks', 0) for p in filtered_pages)
    sub_impr = sum(p.get('Impressions', 0) for p in filtered_pages)
    if filtered_pages:
        sub_ctr = sum(float(str(p.get('CTR', '0')).replace('%','')) for p in filtered_pages) / len(filtered_pages)
    else:
        sub_ctr = 0
    
    # Format pages for JSON
    pages_list = []
    for p in filtered_pages[:10]:
        pages_list.append({
            'url': p.get('Top pages', p.get('Page', '')),
            'clicks': p.get('Clicks', 0),
            'impressions': p.get('Impressions', 0)
        })
    
    return jsonify({
        'name': section_name,
        'clicks': sub_clicks,
        'impressions': sub_impr,
        'ctr': round(sub_ctr, 2),
        'pages': pages_list
    })


