"""
Energy Dashboard Blueprint - Energy & Sustainability Analytics
Reads Excel dataset from data/energy/energy_dash.xlsx (Water, Electricity, Natural Gas)
Provides interactive analytics, KPI metrics, Chart.js visualizations, and multi-criteria filters.
"""
import os
import re
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
import pandas as pd

from app_pkg.auth import require_permissions, require_roles
bp = Blueprint('energy_dashboard', __name__, url_prefix='/energy')

from app_pkg.paths import data_dir
EXCEL_PATH = data_dir('energy', 'energy_dash.xlsx')

# Cached Data & Timestamp
_CACHED_DATA = None
_CACHE_MTIME = 0

MONTH_NAMES_FA = {
    1: 'فروردین', 2: 'اردیبهشت', 3: 'خرداد',
    4: 'تیر', 5: 'مرداد', 6: 'شهریور',
    7: 'مهر', 8: 'آبان', 9: 'آذر',
    10: 'دی', 11: 'بهمن', 12: 'اسفند'
}

MONTH_MAP_BY_NAME = {
    'فروردین': 1, 'اردیبهشت': 2, 'خرداد': 3,
    'تیر': 4, 'مرداد': 5, 'شهریور': 6,
    'مهر': 7, 'آبان': 8, 'آذر': 9,
    'دی': 10, 'بهمن': 11, 'اسفند': 12, 'اسقند': 12
}


def normalize_building_name(name):
    """Normalize various building string aliases to standard historical names"""
    if not name or pd.isna(name):
        return 'نامشخص'
    s = str(name).strip()
    # Normalize Persian / Arabic numbers
    s = s.replace('1', '۱').replace('2', '۲').replace('3', '۳')
    if 'کمال اسماعیل' in s or 'کمال اسمائیل' in s or 'همدانیان' in s:
        return 'ساختمان برادران همدانیان'
    elif 'روابط عمومی' in s:
        return 'ساختمان روابط عمومی'
    elif '۲' in s or '2' in s or 'امین الضرب' in s or 'امین‌الضرب' in s:
        return 'ساختمان امین‌الضرب'
    elif '۱' in s or '1' in s or 'دهش' in s or 'فضلالله' in s or 'فضل‌الله' in s:
        return 'ساختمان فضل‌الله دهش'
    return s


def parse_shamsi_date(date_val):
    """Extract (year, month, day, formatted_str) from Shamsi date string or value"""
    if pd.isna(date_val) or not date_val:
        return None, None, None, ''
    s = str(date_val).strip()
    match = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', s)
    if match:
        y = int(match.group(1))
        m = int(match.group(2))
        d = int(match.group(3))
        return y, m, d, f"{y}/{m:02d}/{d:02d}"
    return None, None, None, s


def load_energy_data(force_reload=False):
    """Load and normalize Excel data from data/energy/energy_dash.xlsx with caching"""
    global _CACHED_DATA, _CACHE_MTIME
    
    if not os.path.exists(EXCEL_PATH):
        return {
            'water': pd.DataFrame(),
            'electricity': pd.DataFrame(),
            'gas': pd.DataFrame(),
            'buildings': [],
            'years': [],
            'error': 'فایل اکسل energy_dash.xlsx در پوشه data/energy یافت نشد.'
        }
    
    current_mtime = os.path.getmtime(EXCEL_PATH)
    if not force_reload and _CACHED_DATA is not None and _CACHE_MTIME == current_mtime:
        return _CACHED_DATA

    try:
        xls = pd.ExcelFile(EXCEL_PATH)
        
        # 1. WATER (آب)
        df_water = pd.read_excel(xls, sheet_name='آب') if 'آب' in xls.sheet_names else pd.DataFrame()
        if not df_water.empty:
            df_water.columns = [c.replace('\xa0', ' ').strip() for c in df_water.columns]
            df_water['ساختمان_خام'] = df_water['ساختمان']
            df_water['ساختمان_استاندارد'] = df_water['ساختمان'].apply(normalize_building_name)
            parsed_dates = df_water['تاریخ قرائت'].apply(parse_shamsi_date)
            df_water['سال'] = [p[0] for p in parsed_dates]
            df_water['ماه_عدد'] = [p[1] for p in parsed_dates]
            df_water['ماه_نام'] = df_water['ماه_عدد'].map(MONTH_NAMES_FA)
            df_water['تاریخ_شمسی'] = [p[3] for p in parsed_dates]
            df_water['مصرف_متر_مکعب'] = pd.to_numeric(df_water.get('مصرف به متر مکعب', 0), errors='coerce').fillna(0)
            df_water['متوسط_مصرف_ماهیانه'] = pd.to_numeric(df_water.get('متوسط مصرف ماهیانه', 0), errors='coerce').fillna(0)
            df_water['تعداد_روز'] = pd.to_numeric(df_water.get('تعداد روز', 0), errors='coerce').fillna(0)
            df_water['شناسه_قبض'] = df_water['شناسه قبض'].astype(str)

        # 2. ELECTRICITY (برق)
        df_elec = pd.read_excel(xls, sheet_name='برق') if 'برق' in xls.sheet_names else pd.DataFrame()
        if not df_elec.empty:
            df_elec.columns = [c.replace('\xa0', ' ').strip() for c in df_elec.columns]
            df_elec['ساختمان_خام'] = df_elec['ساختمان']
            df_elec['ساختمان_استاندارد'] = df_elec['ساختمان'].apply(normalize_building_name)
            parsed_dates = df_elec['تاریخ قرائت'].apply(parse_shamsi_date)
            df_elec['سال_محاسباتی'] = [p[0] for p in parsed_dates]
            df_elec['ماه_عدد'] = [p[1] for p in parsed_dates]
            
            # Fill Year from date if missing
            if 'سال' in df_elec.columns:
                df_elec['سال'] = pd.to_numeric(df_elec['سال'], errors='coerce').fillna(df_elec['سال_محاسباتی']).astype(int)
            else:
                df_elec['سال'] = df_elec['سال_محاسباتی']
                
            df_elec['ماه_نام'] = df_elec['ماه_عدد'].map(MONTH_NAMES_FA)
            df_elec['تاریخ_شمسی'] = [p[3] for p in parsed_dates]
            df_elec['کم_باری'] = pd.to_numeric(df_elec.get('کم باری', 0), errors='coerce').fillna(0)
            df_elec['میان_باری'] = pd.to_numeric(df_elec.get('میان باری', 0), errors='coerce').fillna(0)
            df_elec['پرباری'] = pd.to_numeric(df_elec.get('پرباری', 0), errors='coerce').fillna(0)
            df_elec['مجموع_مصرف_kwh'] = df_elec['کم_باری'] + df_elec['میان_باری'] + df_elec['پرباری']
            df_elec['شناسه_قبض'] = df_elec['شناسه قبض'].astype(str)

        # 3. GAS (گاز)
        df_gas = pd.read_excel(xls, sheet_name='گاز') if 'گاز' in xls.sheet_names else pd.DataFrame()
        if not df_gas.empty:
            df_gas.columns = [c.replace('\xa0', ' ').strip() for c in df_gas.columns]
            df_gas['ساختمان_خام'] = df_gas['ساختمان']
            df_gas['ساختمان_استاندارد'] = df_gas['ساختمان'].apply(normalize_building_name)
            parsed_dates = df_gas['تاریخ قرائت'].apply(parse_shamsi_date)
            df_gas['سال'] = [p[0] for p in parsed_dates]
            df_gas['ماه_عدد'] = [p[1] for p in parsed_dates]
            df_gas['ماه_نام'] = df_gas['ماه_عدد'].map(MONTH_NAMES_FA)
            df_gas['تاریخ_شمسی'] = [p[3] for p in parsed_dates]
            df_gas['کارکرد_متر_مکعب'] = pd.to_numeric(df_gas.get('کارکرد شمارش گر', 0), errors='coerce').fillna(0)
            df_gas['شناسه_قبض'] = df_gas['شناسه قبض'].astype(str)

        # Collect distinct building names and years
        buildings = sorted(list(set(
            df_water['ساختمان_استاندارد'].dropna().unique().tolist() +
            df_elec['ساختمان_استاندارد'].dropna().unique().tolist() +
            df_gas['ساختمان_استاندارد'].dropna().unique().tolist()
        )))

        years = sorted(list(set(
            [int(y) for y in df_water['سال'].dropna().unique().tolist() if y] +
            [int(y) for y in df_elec['سال'].dropna().unique().tolist() if y] +
            [int(y) for y in df_gas['سال'].dropna().unique().tolist() if y]
        )), reverse=True)

        _CACHED_DATA = {
            'water': df_water,
            'electricity': df_elec,
            'gas': df_gas,
            'buildings': buildings,
            'years': years,
            'error': None
        }
        _CACHE_MTIME = current_mtime
        return _CACHED_DATA
    except Exception as e:
        return {
            'water': pd.DataFrame(),
            'electricity': pd.DataFrame(),
            'gas': pd.DataFrame(),
            'buildings': [],
            'years': [],
            'error': f'خطا در بارگذاری داده‌های اکسل انرژی: {str(e)}'
        }


def compute_energy_kpis(data, selected_building=None, selected_year=None):
    """Compute high-level KPI cards and breakdown statistics for selected filters"""
    df_w = data['water']
    df_e = data['electricity']
    df_g = data['gas']

    if selected_building and selected_building != 'all':
        df_w = df_w[df_w['ساختمان_استاندارد'] == selected_building] if not df_w.empty else df_w
        df_e = df_e[df_e['ساختمان_استاندارد'] == selected_building] if not df_e.empty else df_e
        df_g = df_g[df_g['ساختمان_استاندارد'] == selected_building] if not df_g.empty else df_g

    if selected_year and selected_year != 'all':
        try:
            yr = int(selected_year)
            df_w = df_w[df_w['سال'] == yr] if not df_w.empty else df_w
            df_e = df_e[df_e['سال'] == yr] if not df_e.empty else df_e
            df_g = df_g[df_g['سال'] == yr] if not df_g.empty else df_g
        except ValueError:
            pass

    # 1. Electricity KPIs
    elec_total = float(df_e['مجموع_مصرف_kwh'].sum()) if not df_e.empty else 0.0
    elec_offpeak = float(df_e['کم_باری'].sum()) if not df_e.empty else 0.0
    elec_midpeak = float(df_e['میان_باری'].sum()) if not df_e.empty else 0.0
    elec_peak = float(df_e['پرباری'].sum()) if not df_e.empty else 0.0
    elec_peak_pct = round((elec_peak / elec_total * 100), 1) if elec_total > 0 else 0
    elec_bills_count = len(df_e)

    # 2. Gas KPIs
    gas_total = float(df_g['کارکرد_متر_مکعب'].sum()) if not df_g.empty else 0.0
    gas_bills_count = len(df_g)
    gas_avg_bill = round(gas_total / gas_bills_count, 1) if gas_bills_count > 0 else 0

    # 3. Water KPIs
    water_total = float(df_w['مصرف_متر_مکعب'].sum()) if not df_w.empty else 0.0
    water_monthly_avg_sum = float(df_w['متوسط_مصرف_ماهیانه'].sum()) if not df_w.empty else 0.0
    water_bills_count = len(df_w)
    water_avg_monthly = round(water_monthly_avg_sum / water_bills_count, 1) if water_bills_count > 0 else 0

    # Building Share Distribution for Charts
    b_elec = {}
    if not df_e.empty:
        grouped = df_e.groupby('ساختمان_استاندارد')['مجموع_مصرف_kwh'].sum()
        b_elec = {k: float(v) for k, v in grouped.items()}

    b_gas = {}
    if not df_g.empty:
        grouped = df_g.groupby('ساختمان_استاندارد')['کارکرد_متر_مکعب'].sum()
        b_gas = {k: float(v) for k, v in grouped.items()}

    b_water = {}
    if not df_w.empty:
        grouped = df_w.groupby('ساختمان_استاندارد')['مصرف_متر_مکعب'].sum()
        b_water = {k: float(v) for k, v in grouped.items()}

    # Top consumer building
    top_elec_building = max(b_elec.items(), key=lambda x: x[1])[0] if b_elec else '—'
    top_elec_share = round(b_elec[top_elec_building] / elec_total * 100, 1) if b_elec and elec_total > 0 else 0

    # Timeline trends (by year/month or chronological)
    timeline_elec = []
    if not df_e.empty:
        df_e_sorted = df_e.sort_values('تاریخ_شمسی')
        t_grp = df_e_sorted.groupby('تاریخ_شمسی').agg({
            'مجموع_مصرف_kwh': 'sum',
            'کم_باری': 'sum',
            'میان_باری': 'sum',
            'پرباری': 'sum'
        }).reset_index()
        for _, r in t_grp.iterrows():
            timeline_elec.append({
                'date': r['تاریخ_شمسی'],
                'total': float(r['مجموع_مصرف_kwh']),
                'offpeak': float(r['کم_باری']),
                'midpeak': float(r['میان_باری']),
                'peak': float(r['پرباری'])
            })

    timeline_gas = []
    if not df_g.empty:
        df_g_sorted = df_g.sort_values('تاریخ_شمسی')
        g_grp = df_g_sorted.groupby('تاریخ_شمسی')['کارکرد_متر_مکعب'].sum().reset_index()
        for _, r in g_grp.iterrows():
            timeline_gas.append({
                'date': r['تاریخ_شمسی'],
                'total': float(r['کارکرد_متر_مکعب'])
            })

    timeline_water = []
    if not df_w.empty:
        df_w_sorted = df_w.sort_values('تاریخ_شمسی')
        w_grp = df_w_sorted.groupby('تاریخ_شمسی')['مصرف_متر_مکعب'].sum().reset_index()
        for _, r in w_grp.iterrows():
            timeline_water.append({
                'date': r['تاریخ_شمسی'],
                'total': float(r['مصرف_متر_مکعب'])
            })

    return {
        'elec_total': elec_total,
        'elec_offpeak': elec_offpeak,
        'elec_midpeak': elec_midpeak,
        'elec_peak': elec_peak,
        'elec_peak_pct': elec_peak_pct,
        'elec_bills_count': elec_bills_count,
        'gas_total': gas_total,
        'gas_bills_count': gas_bills_count,
        'gas_avg_bill': gas_avg_bill,
        'water_total': water_total,
        'water_bills_count': water_bills_count,
        'water_avg_monthly': water_avg_monthly,
        'top_elec_building': top_elec_building,
        'top_elec_share': top_elec_share,
        'building_elec': b_elec,
        'building_gas': b_gas,
        'building_water': b_water,
        'timeline_elec': timeline_elec,
        'timeline_gas': timeline_gas,
        'timeline_water': timeline_water
    }


@bp.route('/')
@require_permissions('energy.view')
def index():
    """Main Energy Dashboard page"""
    data = load_energy_data()
    selected_building = request.args.get('building', 'all')
    selected_year = request.args.get('year', 'all')
    active_tab = request.args.get('tab', 'overview')

    kpis = compute_energy_kpis(data, selected_building, selected_year)

    # Filter dataframes for detailed tables
    df_w = data['water']
    df_e = data['electricity']
    df_g = data['gas']

    if selected_building != 'all':
        df_w = df_w[df_w['ساختمان_استاندارد'] == selected_building] if not df_w.empty else df_w
        df_e = df_e[df_e['ساختمان_استاندارد'] == selected_building] if not df_e.empty else df_e
        df_g = df_g[df_g['ساختمان_استاندارد'] == selected_building] if not df_g.empty else df_g

    if selected_year != 'all':
        try:
            yr = int(selected_year)
            df_w = df_w[df_w['سال'] == yr] if not df_w.empty else df_w
            df_e = df_e[df_e['سال'] == yr] if not df_e.empty else df_e
            df_g = df_g[df_g['سال'] == yr] if not df_g.empty else df_g
        except ValueError:
            pass

    water_records = df_w.sort_values('تاریخ_شمسی', ascending=False).to_dict('records') if not df_w.empty else []
    elec_records = df_e.sort_values('تاریخ_شمسی', ascending=False).to_dict('records') if not df_e.empty else []
    gas_records = df_g.sort_values('تاریخ_شمسی', ascending=False).to_dict('records') if not df_g.empty else []

    return render_template(
        'energy_dashboard/index.html',
        kpis=kpis,
        buildings=data['buildings'],
        years=data['years'],
        selected_building=selected_building,
        selected_year=selected_year,
        active_tab=active_tab,
        water_records=water_records,
        elec_records=elec_records,
        gas_records=gas_records,
        error_msg=data['error']
    )


@bp.route('/api/data')
@require_permissions('energy.view')
def api_data():
    """JSON API endpoint returning filtered energy metrics for dynamic Chart.js updating"""
    data = load_energy_data()
    selected_building = request.args.get('building', 'all')
    selected_year = request.args.get('year', 'all')
    kpis = compute_energy_kpis(data, selected_building, selected_year)
    return jsonify({
        'status': 'ok',
        'kpis': kpis,
        'buildings': data['buildings'],
        'years': data['years']
    })


@bp.route('/reload', methods=['POST'])
@require_roles('manager', 'admin')
def reload_data():
    """Force reloads data from Excel file"""
    load_energy_data(force_reload=True)
    flash('اطلاعات مصرف انرژی با موفقیت از فایل اکسل بازخوانی و همگام شد.', 'success')
    return redirect(url_for('energy_dashboard.index'))
