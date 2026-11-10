"""
Email Dashboard Blueprint - Flask + Chart.js implementation
Replaces the old Dash-based email dashboard
"""
import os
import glob
from flask import Blueprint, render_template, request, redirect, url_for, jsonify
import pandas as pd

from app_pkg.auth import require_permissions, require_roles
from app_pkg.utils.uploads import save_upload, UploadError, flash_upload_summary
bp = Blueprint('email_dashboard', __name__, url_prefix='/email')

# Data directory
from app_pkg.paths import data_dir
DATA_DIR = data_dir('email')


def parse_campaign_csv(filepath):
    """Parse a single campaign CSV file and return structured data"""
    try:
        df = pd.read_csv(filepath, on_bad_lines='skip')
        data = {
            'filename': os.path.basename(filepath),
            'campaign_name': '',
            'sent_date': '',
            'total_sent': 0,
            'opened': 0,
            'clicked': 0,
            'click_to_open': 0,
            'unsubscribed': 0,
            'spam': 0,
            'hard_bounce': 0,
            'soft_bounce': 0,
            'desktop': 0,
            'mobile': 0,
            'webmail': 0,
            'email_clients': [],
            'top_links': []  # Not used but kept for compatibility
        }
        
        for _, row in df.iterrows():
            cat = str(row.get('Category', '')).strip()
            metric = str(row.get('Metric', '')).strip()
            value = str(row.get('Value', '')).strip()
            
            # Skip rows that don't have proper Category/Metric format
            if not cat or cat == 'nan' or cat == 'URL':
                continue
            
            try:
                # Campaign Details
                if cat == 'Campaign Details':
                    if metric == 'Report Name':
                        data['campaign_name'] = value
                    elif metric == 'Sent Date':
                        data['sent_date'] = value
                
                # Results
                elif cat == 'Results':
                    if metric == 'Total emails sent':
                        data['total_sent'] = int(float(value)) if value and value != 'nan' else 0
                    elif metric == 'Opened':
                        data['opened'] = float(value.replace('%', '')) if value and value != 'nan' else 0
                    elif metric == 'Clicked':
                        data['clicked'] = float(value.replace('%', '')) if value and value != 'nan' else 0
                    elif metric == 'Click to open rate':
                        data['click_to_open'] = float(value.replace('%', '')) if value and value != 'nan' else 0
                
                # Bad Statistics
                elif cat == 'Bad Statistics':
                    if metric == 'Unsubscribed':
                        data['unsubscribed'] = float(value.replace('%', '')) if value and value != 'nan' else 0
                    elif metric == 'Spam complaints':
                        data['spam'] = float(value.replace('%', '')) if value and value != 'nan' else 0
                    elif metric == 'Hard bounce':
                        data['hard_bounce'] = float(value.replace('%', '')) if value and value != 'nan' else 0
                    elif metric == 'Soft bounce':
                        data['soft_bounce'] = float(value.replace('%', '')) if value and value != 'nan' else 0
                
                # Reading Environments
                elif cat == 'Reading Environments':
                    if metric == 'Desktop':
                        data['desktop'] = float(value.replace('%', '')) if value and value != 'nan' else 0
                    elif metric == 'Mobile':
                        data['mobile'] = float(value.replace('%', '')) if value and value != 'nan' else 0
                    elif metric == 'Webmail':
                        data['webmail'] = float(value.replace('%', '')) if value and value != 'nan' else 0
                
                # Top Email Clients
                elif cat == 'Top Email Clients':
                    data['email_clients'].append({
                        'name': metric,
                        'percentage': float(value.replace('%', '')) if value and value != 'nan' else 0
                    })
            except (ValueError, AttributeError) as e:
                # Skip individual parsing errors
                continue
        
        return data
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
        return None


_EMAIL_CACHE = {'mtime': 0, 'campaigns': None}

def _get_email_dir_mtime():
    try:
        csv_files = glob.glob(os.path.join(DATA_DIR, '*.csv'))
        if not csv_files:
            return 0
        return max(os.path.getmtime(f) for f in csv_files)
    except Exception:
        return 0

def load_all_campaigns():
    """Load all campaign CSV files with mtime caching"""
    current_mtime = _get_email_dir_mtime()
    if _EMAIL_CACHE['campaigns'] is not None and _EMAIL_CACHE['mtime'] == current_mtime:
        return _EMAIL_CACHE['campaigns']

    campaigns = []
    csv_files = glob.glob(os.path.join(DATA_DIR, '*.csv'))
    csv_files.sort()
    
    for filepath in csv_files:
        campaign = parse_campaign_csv(filepath)
        if campaign:
            campaigns.append(campaign)
    
    _EMAIL_CACHE['campaigns'] = campaigns
    _EMAIL_CACHE['mtime'] = current_mtime
    return campaigns


def calculate_kpis(campaigns):
    """Calculate aggregate KPIs from all campaigns"""
    if not campaigns:
        return {
            'total_campaigns': 0,
            'total_sent': 0,
            'avg_open_rate': 0,
            'avg_click_rate': 0,
            'avg_bounce_rate': 0
        }
    
    total_sent = sum(c['total_sent'] for c in campaigns)
    avg_open = sum(c['opened'] for c in campaigns) / len(campaigns)
    avg_click = sum(c['clicked'] for c in campaigns) / len(campaigns)
    avg_bounce = sum(c['hard_bounce'] + c['soft_bounce'] for c in campaigns) / len(campaigns)
    
    return {
        'total_campaigns': len(campaigns),
        'total_sent': total_sent,
        'avg_open_rate': round(avg_open, 2),
        'avg_click_rate': round(avg_click, 2),
        'avg_bounce_rate': round(avg_bounce, 2)
    }


def aggregate_reading_env(campaigns):
    """Aggregate reading environment data"""
    if not campaigns:
        return {'desktop': 0, 'mobile': 0, 'webmail': 0}
    
    return {
        'desktop': round(sum(c['desktop'] for c in campaigns) / len(campaigns), 2),
        'mobile': round(sum(c['mobile'] for c in campaigns) / len(campaigns), 2),
        'webmail': round(sum(c['webmail'] for c in campaigns) / len(campaigns), 2)
    }


def aggregate_email_clients(campaigns):
    """Aggregate email client data"""
    client_totals = {}
    for c in campaigns:
        for client in c['email_clients']:
            name = client['name']
            if name not in client_totals:
                client_totals[name] = []
            client_totals[name].append(client['percentage'])
    
    # Calculate averages
    result = []
    for name, values in client_totals.items():
        result.append({
            'name': name,
            'percentage': round(sum(values) / len(values), 2)
        })
    
    # Sort by percentage descending
    result.sort(key=lambda x: x['percentage'], reverse=True)
    return result[:8]  # Top 8


@bp.route('/')
@require_permissions('email.view')
def index():
    """Main email dashboard page"""
    campaigns = load_all_campaigns()
    kpis = calculate_kpis(campaigns)
    reading_env = aggregate_reading_env(campaigns)
    email_clients = aggregate_email_clients(campaigns)
    
    # Prepare trend data for chart
    trend_data = {
        'labels': [],
        'opened': [],
        'clicked': [],
        'sent': []
    }
    
    for i, c in enumerate(campaigns):
        # Use short label based on filename (e.g., "31th_email.csv" -> "هفته ۳۱")
        filename = c['filename']
        # Extract week number from filename
        import re
        match = re.search(r'(\d+)', filename)
        if match:
            week_num = match.group(1)
            label = f"هفته {week_num}"
        else:
            label = f"کمپین {i+1}"
        trend_data['labels'].append(label)
        trend_data['opened'].append(c['opened'])
        trend_data['clicked'].append(c['clicked'])
        trend_data['sent'].append(c['total_sent'])
    
    # Get list of files for upload reference
    existing_files = [os.path.basename(f) for f in glob.glob(os.path.join(DATA_DIR, '*.csv'))]
    
    return render_template('email_dashboard/index.html',
                           kpis=kpis,
                           campaigns=campaigns,
                           trend_data=trend_data,
                           reading_env=reading_env,
                           email_clients=email_clients,
                           existing_files=existing_files)


@bp.route('/api/campaign/<filename>')
@require_permissions('email.view')
def get_campaign(filename):
    """API endpoint for single campaign data"""
    if filename != os.path.basename(filename.replace('\\', '/')) or not filename.lower().endswith('.csv'):
        return jsonify({'error': 'Campaign not found'}), 404
    filepath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({'error': 'Campaign not found'}), 404
    
    campaign = parse_campaign_csv(filepath)
    return jsonify(campaign)


@bp.route('/update', methods=['POST'])
@require_roles('manager', 'admin')
def update_data():
    """Handle CSV file upload"""
    saved, errors = 0, []
    for file in request.files.getlist('csv_files'):
        try:
            save_upload(file, DATA_DIR, {'csv'})
            saved += 1
        except UploadError as e:
            errors.append(str(e))
    flash_upload_summary(saved, errors)
    return redirect(url_for('email_dashboard.index'))
