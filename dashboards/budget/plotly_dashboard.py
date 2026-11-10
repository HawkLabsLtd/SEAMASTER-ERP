import dash
from dash import dcc, html, Input, Output, callback, dash_table, State, no_update
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path
from sklearn.linear_model import LinearRegression
import base64
import io
from datetime import datetime
import hashlib
import os
from flask import session

# Brand color palette and chart utilities (local version)
BRAND_COLORS = {
    'primary': '#1e3a8a',
    'secondary': '#3b82f6',
    'accent': '#f59e0b',
    'success': '#10b981',
    'warning': '#f59e0b',
    'danger': '#ef4444',
    'info': '#06b6d4',
    'light': '#f8fafc',
    'medium': '#64748b',
    'dark': '#1e293b',
    'white': '#ffffff',
    'gradient_start': '#1e3a8a',
    'gradient_end': '#3b82f6'
}

def get_brand_color_palette(n_colors=10):
    base_colors = [
        BRAND_COLORS['primary'], BRAND_COLORS['secondary'], BRAND_COLORS['accent'],
        BRAND_COLORS['success'], BRAND_COLORS['info'], BRAND_COLORS['warning'],
        BRAND_COLORS['danger'], '#8b5cf6', '#06b6d4', '#84cc16'
    ]
    return base_colors[:n_colors] if n_colors <= len(base_colors) else base_colors * (n_colors // len(base_colors) + 1)

def get_brand_chart_template():
    return {
        'layout': {
            'colorway': get_brand_color_palette(),
            'font': {'family': 'IRANSans, Vazir, Tahoma, Arial, sans-serif'},
            'paper_bgcolor': BRAND_COLORS['white'],
            'plot_bgcolor': BRAND_COLORS['light'],
            'title': {'font': {'color': BRAND_COLORS['dark']}},
            'xaxis': {'gridcolor': BRAND_COLORS['medium'], 'linecolor': BRAND_COLORS['medium']},
            'yaxis': {'gridcolor': BRAND_COLORS['medium'], 'linecolor': BRAND_COLORS['medium']}
        }
    }


# Custom CSS for better Farsi font support
FARSI_FONT_CSS = {
    'fontFamily': 'IRANSans, Tahoma, Arial, sans-serif',
    'direction': 'rtl',
    'textAlign': 'right'
}

# Logo shown in the dashboard header: the portal's static/logo-dark.svg
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ORG_NAME = os.getenv('ORG_NAME', 'سازمان نمونه')


def encode_logo():
    """Base64 data URI for the portal logo, or None when it is missing."""
    logo_path = PROJECT_ROOT / "static" / "logo-dark.svg"
    try:
        return "data:image/svg+xml;base64," + base64.b64encode(logo_path.read_bytes()).decode()
    except OSError:
        return None

# Initialize Dash app with external CSS for Farsi fonts
external_stylesheets = [
    'https://fonts.googleapis.com/css2?family=Vazir:wght@400;700&display=swap',
    'https://cdn.jsdelivr.net/gh/rastikerdar/vazir-font@v30.1.0/dist/font-face.css'
]

# Prefix configuration for embedding under DispatcherMiddleware
PREFIX = os.getenv('BUDGET_DASH_PREFIX', '')
print(f"[Budget Dash] BUDGET_DASH_PREFIX={PREFIX!r}")

# When mounted under /dash/budget via DispatcherMiddleware, set routes to root
# so Dash serves endpoints correctly at the mount point, while assets/scripts
# resolve under the prefix via requests_pathname_prefix.
app = dash.Dash(
    __name__,
    external_stylesheets=external_stylesheets,
    requests_pathname_prefix=(PREFIX or None),
    routes_pathname_prefix=('/' if PREFIX else None),
)
print(f"[Budget Dash] requests_pathname_prefix={app.config.requests_pathname_prefix!r}, routes_pathname_prefix={app.config.routes_pathname_prefix!r}")
app.title = "Budget Dashboard"

# Debug toggle
BUDGET_DEBUG = str(os.getenv('BUDGET_DEBUG', '')).lower() in ('1', 'true', 'yes')

# Add responsive CSS for grid layout
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            /* Responsive grid styles */
            @media (max-width: 768px) {
                .chart-container {
                    width: 98% !important;
                    display: block !important;
                    margin: 10px 1% !important;
                }
                .chart-row {
                    display: block !important;
                }
            }
            
            @media (max-width: 1200px) and (min-width: 769px) {
                .chart-container {
                    width: 98% !important;
                    display: block !important;
                    margin: 10px 1% !important;
                }
            }
            
            /* Ensure charts maintain aspect ratio */
            .chart-container .js-plotly-plot {
                width: 100% !important;
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

# Authentication configuration
# Force-disable authentication so the login page never appears
DISABLE_AUTH = True
app.server.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production')

# Authentication credentials (change these for production)
USERNAME = os.environ.get('DASHBOARD_USERNAME', 'admin').strip()

# For security, password must be set via environment variable
# If no password is set, generate a random one and display it
if not DISABLE_AUTH:
    dashboard_password = os.environ.get('DASHBOARD_PASSWORD')
    if dashboard_password:
        dashboard_password = dashboard_password.strip()
        PASSWORD_HASH = hashlib.sha256(dashboard_password.encode()).hexdigest()
    else:
        # Generate a secure random password if none is provided
        import secrets
        import string
        random_password = ''.join(secrets.choice(string.ascii_letters + string.digits + '!@#$%^&*') for _ in range(12))
        PASSWORD_HASH = hashlib.sha256(random_password.encode()).hexdigest()
        print(f"⚠️  WARNING: No DASHBOARD_PASSWORD environment variable set!")
        print(f"🔑 Generated temporary password: {random_password}")
        print(f"📝 Please set DASHBOARD_PASSWORD environment variable for production use.")
else:
    PASSWORD_HASH = None  # No password needed when auth is disabled
    print("🔓 Authentication is DISABLED - Dashboard is publicly accessible!")

# Data lives in <data dir>/budget (SEAMASTER_DATA_DIR, default data/); see data/README.md
ROOT = Path(os.getenv('SEAMASTER_DATA_DIR') or PROJECT_ROOT / 'data') / 'budget'
LONG_CSV = ROOT / "cleaned_budget_long.csv"

# Attempt to generate cleaned data if missing
try:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from clean_budget import cleanse_and_normalize
except Exception:
    cleanse_and_normalize = None

# Persian label mappings
MEASURE_FA_MAP = {
    "budget": "بودجه مصوب شده",
    "approved": "بودجه مصوب شده",
    "actual": "هزینه های انجام شده",
    "expenses": "هزینه های انجام شده",
    "incurred": "هزینه های انجام شده",
    "variance": "تفریغ بودجه",
    "deduction": "تفریغ بودجه",
}

CATEGORY_FA_MAP = {
    "Administrative fee": "هزینه اداری",
    "Personnel costs": "هزینه های پرسنلی",
    "capital": "سرمایه گذاری",
    "Support organizations": "حمایت تشکل ها",
    "Project cost": "هزینه پروژه",
    "total sum": "جمع کل",
}

# Farsi canonical measure names for KPIs
BUDGET_FA = "بودجه مصوب شده"
ACTUAL_FA = "هزینه های انجام شده"
VAR_FA = "تفریغ بودجه"

def load_data(path_str: str) -> pd.DataFrame:
    """Load and process budget data"""
    path = Path(path_str)
    print(f"🔍 Looking for data file: {path.absolute()}")
    print(f"📁 Current working directory: {Path.cwd()}")
    print(f"📂 Script directory: {Path(__file__).parent}")
    
    if not path.exists() and cleanse_and_normalize is not None:
        print("📝 Data file not found, attempting to generate...")
        try:
            cleanse_and_normalize()
        except Exception as e:
            print(f"❌ Error generating cleaned data: {e}")
            return pd.DataFrame()
    
    if not path.exists():
        print(f"❌ Data file not found: {path.absolute()}")
        print(f"📋 Files in directory: {list(ROOT.glob('*.csv'))}")
        return pd.DataFrame()
    
    try:
        df = pd.read_csv(path)
        
        # Ensure required columns exist
        required_cols = ['year', 'category', 'measure', 'value']
        if not all(col in df.columns for col in required_cols):
            print(f"Missing required columns. Found: {df.columns.tolist()}")
            return pd.DataFrame()
        
        # Data cleaning and processing
        df = df.dropna(subset=['value'])
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        df = df.dropna(subset=['value'])
        
        # Normalize measure names
        df['measure'] = df['measure'].str.lower().str.strip()
        df['measure'] = df['measure'].replace(MEASURE_FA_MAP)
        
        # Normalize category names
        df['category'] = df['category'].replace(CATEGORY_FA_MAP)
        
        return df
    except Exception as e:
        print(f"Error loading data: {e}")
        return pd.DataFrame()

def format_money(value):
    """Format money values in Persian style"""
    if pd.isna(value) or value == 0:
        return "0"
    
    # Convert to billions for readability
    value_billions = value / 1_000_000_000
    
    if abs(value_billions) >= 1:
        return f"{value_billions:,.1f} میلیارد ریال"
    else:
        value_millions = value / 1_000_000
        return f"{value_millions:,.0f} میلیون ریال"

def format_percentage(value):
    """Format percentage values"""
    if pd.isna(value):
        return "N/A"
    return f"{value:.1f}%"

# Load initial data
df = load_data(str(LONG_CSV))

# Separate total rows to avoid double counting in KPIs/aggregations (same as Streamlit)
if not df.empty:
    is_total = df["category"].str.strip().str.lower().eq("total sum") | df["category"].eq("جمع کل")
    df_total = df[is_total].copy()
    df_cat = df[~is_total].copy()
else:
    df_total = pd.DataFrame()
    df_cat = pd.DataFrame()

# Startup data validation warning banner
BUDGET_DATA_WARNING = None if not df_cat.empty else "داده بودجه یافت نشد یا ستون‌های مورد نیاز ناقص است"

# Get unique values for filters (use category data, not totals)
years = sorted(df['year'].unique()) if not df.empty else []
measures = sorted(df['measure'].unique()) if not df.empty else []
categories = sorted(df_cat['category'].unique()) if not df_cat.empty else []

# Authentication functions
def check_authentication():
    """Check if user is authenticated"""
    if DISABLE_AUTH:
        return True  # Skip authentication if disabled
    return session.get('authenticated', False)

def login_layout():
    """Return login page layout"""
    return html.Div([
        html.Div([
            html.Div([
                html.Img(src=encode_logo(), style={
                    'height': '80px', 
                    'marginBottom': '20px',
                    'display': 'block',
                    'margin': '0 auto'
                }),
                html.H2("ورود به داشبورد بودجه", style={
                    'textAlign': 'center',
                    'color': '#2c3e50',
                    'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif',
                    'direction': 'rtl',
                    'marginBottom': '30px'
                }),
                html.Div([
                    html.Label("نام کاربری:", style={
                        'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif',
                        'direction': 'rtl',
                        'display': 'block',
                        'marginBottom': '5px'
                    }),
                    dcc.Input(
                        id='username-input',
                        type='text',
                        placeholder='نام کاربری را وارد کنید',
                        style={
                            'width': '100%',
                            'padding': '10px',
                            'marginBottom': '15px',
                            'border': '1px solid #ddd',
                            'borderRadius': '4px',
                            'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif'
                        }
                    )
                ]),
                html.Div([
                    html.Label("رمز عبور:", style={
                        'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif',
                        'direction': 'rtl',
                        'display': 'block',
                        'marginBottom': '5px'
                    }),
                    dcc.Input(
                        id='password-input',
                        type='password',
                        placeholder='رمز عبور را وارد کنید',
                        style={
                            'width': '100%',
                            'padding': '10px',
                            'marginBottom': '20px',
                            'border': '1px solid #ddd',
                            'borderRadius': '4px',
                            'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif'
                        }
                    )
                ]),
                html.Button(
                    'ورود',
                    id='login-button',
                    n_clicks=0,
                    style={
                        'width': '100%',
                        'padding': '12px',
                        'backgroundColor': BRAND_COLORS['primary'],
                        'color': 'white',
                        'border': 'none',
                        'borderRadius': '4px',
                        'fontSize': '16px',
                        'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif',
                        'cursor': 'pointer'
                    }
                ),
                html.Div(id='login-output', style={'marginTop': '15px'})
            ], style={
                'maxWidth': '400px',
                'margin': '100px auto',
                'padding': '40px',
                'backgroundColor': 'white',
                'borderRadius': '8px',
                'boxShadow': '0 4px 6px rgba(0, 0, 0, 0.1)'
            })
        ], style={
            'backgroundColor': '#f8f9fa',
            'minHeight': '100vh',
            'padding': '20px'
        })
    ])

def main_dashboard_layout():
    """Return main dashboard layout"""
    return html.Div([
    # Header with logo
    html.Div([
        html.Div([
            html.Img(src=encode_logo(), style={
                'height': '60px', 
                'marginRight': '20px',
                'verticalAlign': 'middle'
            }) if encode_logo() else None,
            html.H1(f"داشبورد بودجه {ORG_NAME}", 
                    style={
                        'display': 'inline-block',
                        'verticalAlign': 'middle',
                        'color': BRAND_COLORS['white'], 
                        'margin': '0',
                        'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif',
                        'fontWeight': 'bold',
                        'direction': 'rtl'
                    })
        ], style={
            'textAlign': 'center', 
            'marginBottom': '30px',
            'padding': '20px',
            'background': f'linear-gradient(135deg, {BRAND_COLORS["gradient_start"]}, {BRAND_COLORS["gradient_end"]})',
            'borderRadius': '10px',
            'boxShadow': '0 4px 8px rgba(0,0,0,0.15)'
        })
    ]),
    (html.Div([
        html.Div(BUDGET_DATA_WARNING, style={'color': BRAND_COLORS['danger'], 'textAlign': 'center', 'padding': '8px', 'border': f"1px solid {BRAND_COLORS['danger']}", 'borderRadius': '8px'})
    ], style={'margin': '10px 0'}) if BUDGET_DATA_WARNING else None),
    
    # Sidebar
    html.Div([
        html.Div([
            html.H3("فیلترها", style={'color': BRAND_COLORS['primary'], 'marginBottom': '20px', 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif', 'direction': 'rtl', 'textAlign': 'right'}),
            
            # Year selection
            html.Label("انتخاب سال‌ها:", style={'fontWeight': 'bold', 'marginBottom': '5px', 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif', 'direction': 'rtl', 'textAlign': 'right'}),
            dcc.Dropdown(
                id='year-dropdown',
                options=[{'label': str(year), 'value': year} for year in years],
                value=years[-2:] if len(years) >= 2 else years,
                multi=True,
                style={'marginBottom': '20px', 'direction': 'rtl'}
            ),
            
            # Measure selection
            html.Label("انتخاب شاخص‌ها:", style={'fontWeight': 'bold', 'marginBottom': '5px', 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif', 'direction': 'rtl', 'textAlign': 'right'}),
            dcc.Dropdown(
                id='measure-dropdown',
                options=[{'label': measure, 'value': measure} for measure in measures],
                value=[BUDGET_FA, ACTUAL_FA] if BUDGET_FA in measures and ACTUAL_FA in measures else measures[:2],
                multi=True,
                style={'marginBottom': '20px', 'direction': 'rtl'}
            ),
            
            # Category selection
            html.Label("انتخاب دسته‌بندی‌ها:", style={'fontWeight': 'bold', 'marginBottom': '5px', 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif', 'direction': 'rtl', 'textAlign': 'right'}),
            dcc.Dropdown(
                id='category-dropdown',
                options=[{'label': cat, 'value': cat} for cat in categories],
                value=categories[:10] if len(categories) > 10 else categories,
                multi=True,
                style={'marginBottom': '20px', 'direction': 'rtl'}
            ),
            
            # Top N categories
            html.Label("تعداد دسته‌ :", style={'fontWeight': 'bold', 'marginBottom': '5px', 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif', 'direction': 'rtl', 'textAlign': 'right'}),
            dcc.Slider(
                id='top-n-slider',
                min=5,
                max=20,
                step=1,
                value=10,
                marks={i: str(i) for i in range(5, 21, 5)},
                tooltip={"placement": "bottom", "always_visible": True}
            ),
            
        ], style={
            'width': '25%', 
            'display': 'inline-block', 
            'verticalAlign': 'top',
            'padding': '20px',
            'backgroundColor': '#f8f9fa',
            'borderRadius': '10px',
            'margin': '10px'
        }),
        
        # Main content area
        html.Div([
            # KPI Cards
            html.Div(id='kpi-cards', style={'marginBottom': '30px'}),
            
            # Charts section - Grid Layout
            html.Div([
                # First row - Two charts side by side
                html.Div([
                    html.Div([
                        dcc.Graph(id='top-categories-chart')
                    ], style={
                        'width': '48%', 
                        'display': 'inline-block', 
                        'margin': '1%',
                        'verticalAlign': 'top',
                        'minWidth': '300px'
                    }, className='chart-container'),
                    html.Div([
                        dcc.Graph(id='year-over-year-chart')
                    ], style={
                        'width': '48%', 
                        'display': 'inline-block', 
                        'margin': '1%',
                        'verticalAlign': 'top',
                        'minWidth': '300px'
                    }, className='chart-container')
                ], style={'width': '100%', 'marginBottom': '20px'}, className='chart-row'),
                
                # Second row - Two charts side by side
                html.Div([
                    html.Div([
                        dcc.Graph(id='execution-rate-heatmap')
                    ], style={
                        'width': '48%', 
                        'display': 'inline-block', 
                        'margin': '1%',
                        'verticalAlign': 'top',
                        'minWidth': '300px'
                    }, className='chart-container'),
                    html.Div([
                        dcc.Graph(id='budget-vs-actual-scatter')
                    ], style={
                        'width': '48%', 
                        'display': 'inline-block', 
                        'margin': '1%',
                        'verticalAlign': 'top',
                        'minWidth': '300px'
                    }, className='chart-container')
                ], style={'width': '100%', 'marginBottom': '20px'}, className='chart-row'),
                
                # Third row - Two charts side by side
                html.Div([
                    html.Div([
                        dcc.Graph(id='pie-chart')
                    ], style={
                        'width': '48%', 
                        'display': 'inline-block', 
                        'margin': '1%',
                        'verticalAlign': 'top',
                        'minWidth': '300px'
                    }, className='chart-container'),
                    html.Div([
                        dcc.Graph(id='trend-analysis-chart')
                    ], style={
                        'width': '48%', 
                        'display': 'inline-block', 
                        'margin': '1%',
                        'verticalAlign': 'top',
                        'minWidth': '300px'
                    }, className='chart-container')
                ], style={'width': '100%', 'marginBottom': '20px'}, className='chart-row'),
                
                # Budget forecasting section
                html.Div([
                    html.H3("پیش‌بینی بودجه", style={'color': '#34495e', 'marginBottom': '20px', 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif', 'direction': 'rtl', 'textAlign': 'right'}),
                    html.Div([
                        html.Div([
                            html.Label("انتخاب دسته‌بندی برای پیش‌بینی:", style={'fontWeight': 'bold', 'marginBottom': '5px', 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif'})
                        ], style={'direction': 'rtl', 'textAlign': 'right', 'marginBottom': '5px'}),
                        dcc.Dropdown(
                            id='forecast-category-dropdown',
                            options=[{'label': cat, 'value': cat} for cat in categories],
                            value='سرمایه گذاری' if 'سرمایه گذاری' in categories else (categories[0] if categories else None),
                            style={'marginBottom': '20px', 'direction': 'rtl'}
                        ),
                        html.Div([
                            html.Label("انتخاب شاخص برای پیش‌بینی:", style={'fontWeight': 'bold', 'marginBottom': '5px', 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif'})
                        ], style={'direction': 'rtl', 'textAlign': 'right', 'marginBottom': '5px'}),
                        dcc.Dropdown(
                            id='forecast-measure-dropdown',
                            options=[{'label': measure, 'value': measure} for measure in measures],
                            value=BUDGET_FA if BUDGET_FA in measures else measures[0] if measures else None,
                            style={'marginBottom': '20px', 'direction': 'rtl'}
                        ),
                        html.Div([
                            html.Label("تعداد سال‌های پیش‌بینی:", style={'fontWeight': 'bold', 'marginBottom': '5px', 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif'})
                        ], style={'direction': 'rtl', 'textAlign': 'right', 'marginBottom': '5px'}),
                        dcc.Slider(
                            id='forecast-years-slider',
                            min=1,
                            max=5,
                            step=1,
                            value=3,
                            marks={i: str(i) for i in range(1, 6)},
                            tooltip={"placement": "bottom", "always_visible": True}
                        ),
                    ], style={'marginBottom': '20px', 'direction': 'rtl'}),
                    dcc.Graph(id='forecast-chart'),
                    html.Div(id='forecast-metrics', style={'marginTop': '20px'})
                ], style={'marginTop': '30px', 'padding': '20px', 'backgroundColor': '#f8f9fa', 'borderRadius': '10px'}),
                
                # New Advanced Charts Section
                html.Div([
                    html.H3("نمودارهای تحلیلی پیشرفته", style={'color': '#34495e', 'marginBottom': '20px', 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif', 'direction': 'rtl', 'textAlign': 'right'}),
                    
                    # Fourth row - Time Series and Bar Chart
                    html.Div([
                        html.Div([
                            dcc.Graph(id='time-series-chart')
                        ], style={
                            'width': '48%', 
                            'display': 'inline-block', 
                            'margin': '1%',
                            'verticalAlign': 'top',
                            'minWidth': '300px'
                        }, className='chart-container'),
                        html.Div([
                            dcc.Graph(id='bar-comparison-chart')
                        ], style={
                            'width': '48%', 
                            'display': 'inline-block', 
                            'margin': '1%',
                            'verticalAlign': 'top',
                            'minWidth': '300px'
                        }, className='chart-container')
                    ], style={'width': '100%', 'marginBottom': '20px'}, className='chart-row'),
                    
                    # Fifth row - Waterfall and Gauge Charts
                    html.Div([
                        html.Div([
                            dcc.Graph(id='waterfall-chart')
                        ], style={
                            'width': '48%', 
                            'display': 'inline-block', 
                            'margin': '1%',
                            'verticalAlign': 'top',
                            'minWidth': '300px'
                        }, className='chart-container'),
                        html.Div([
                            dcc.Graph(id='gauge-chart')
                        ], style={
                            'width': '48%', 
                            'display': 'inline-block', 
                            'margin': '1%',
                            'verticalAlign': 'top',
                            'minWidth': '300px'
                        }, className='chart-container')
                    ], style={'width': '100%', 'marginBottom': '20px'}, className='chart-row'),
                    
                    # Sixth row - Box Plot (full width)
                    html.Div([
                        html.Div([
                            dcc.Graph(id='box-plot-chart')
                        ], style={
                            'width': '96%', 
                            'margin': '2%',
                            'minWidth': '300px'
                        }, className='chart-container')
                    ], style={'width': '100%', 'marginBottom': '20px'}, className='chart-row')
                    
                ], style={'marginTop': '30px', 'padding': '20px', 'backgroundColor': '#f8f9fa', 'borderRadius': '10px'}),
                
            ], style={'marginTop': '20px'})
            
        ], style={
            'width': '70%', 
            'display': 'inline-block', 
            'verticalAlign': 'top',
            'padding': '20px'
        })
    ], style={'display': 'flex', 'flexDirection': 'row'}),
    
    # Footer
    html.Div([
        html.Hr(),
        html.P(f"داشبورد تحلیل بودجه {ORG_NAME} - قدرت گرفته از Plotly Dash", 
               style={'textAlign': 'center', 'color': '#7f8c8d', 'marginTop': '20px', 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif', 'direction': 'rtl'})
    ])
    ])

# Dynamic layout will be set later after callbacks

# Callback for KPI cards
@app.callback(
    Output('kpi-cards', 'children'),
    [Input('year-dropdown', 'value'),
     Input('measure-dropdown', 'value'),
     Input('category-dropdown', 'value')]
)
def update_kpi_cards(selected_years, selected_measures, selected_categories):
    if not selected_years or not selected_measures or not selected_categories:
        return html.Div("Please select filters to view KPIs")
    
    # Use total rows for KPIs (same approach as Streamlit dashboard)
    kpi_df = df_total[df_total['year'].isin(selected_years)]
    
    if kpi_df.empty:
        return html.Div("No data available for selected filters")
    
    # Calculate KPIs from total rows only (correct approach)
    totals = kpi_df.groupby('measure')['value'].sum()
    kpis = []
    
    # Total Budget
    if BUDGET_FA in selected_measures:
        total_budget = totals.get(BUDGET_FA, 0)
        kpis.append({
            'title': 'مجموع بودجه',
            'value': format_money(total_budget),
            'color': BRAND_COLORS['info']
        })
    
    # Total Actual
    if ACTUAL_FA in selected_measures:
        total_actual = totals.get(ACTUAL_FA, 0)
        kpis.append({
            'title': 'مجموع هزینه‌ها',
            'value': format_money(total_actual),
            'color': BRAND_COLORS['danger']
        })
    
    # Execution Rate
    if BUDGET_FA in selected_measures and ACTUAL_FA in selected_measures:
        budget_total = totals.get(BUDGET_FA, 0)
        actual_total = totals.get(ACTUAL_FA, 0)
        
        if budget_total > 0:
            execution_rate = (actual_total / budget_total) * 100
            kpis.append({
                'title': 'نرخ اجرا',
                'value': format_percentage(execution_rate),
                'color': BRAND_COLORS['success'] if execution_rate <= 100 else BRAND_COLORS['warning']
            })
    
    # Variance
    if BUDGET_FA in selected_measures and ACTUAL_FA in selected_measures:
        budget_total = totals.get(BUDGET_FA, 0)
        actual_total = totals.get(ACTUAL_FA, 0)
        variance = budget_total - actual_total
        kpis.append({
            'title': 'تفاوت بودجه',
            'value': format_money(variance),
            'color': BRAND_COLORS['success'] if variance >= 0 else BRAND_COLORS['danger']
        })
    
    # Create KPI cards
    kpi_cards = []
    for kpi in kpis:
        card = html.Div([
            html.H4(kpi['title'], style={'margin': '0', 'color': '#2c3e50', 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif'}),
            html.H2(kpi['value'], style={'margin': '10px 0', 'color': kpi['color'], 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif'})
        ], style={
            'backgroundColor': 'white',
            'padding': '20px',
            'borderRadius': '10px',
            'boxShadow': '0 2px 4px rgba(0,0,0,0.1)',
            'textAlign': 'center',
            'margin': '10px',
            'minWidth': '200px'
        })
        kpi_cards.append(card)
    
    return html.Div(kpi_cards, style={'display': 'flex', 'flexWrap': 'wrap', 'justifyContent': 'space-around'})

# Callback for top categories chart
@app.callback(
    Output('top-categories-chart', 'figure'),
    [Input('year-dropdown', 'value'),
     Input('measure-dropdown', 'value'),
     Input('category-dropdown', 'value'),
     Input('top-n-slider', 'value')]
)
def update_top_categories_chart(selected_years, selected_measures, selected_categories, top_n):
    if not selected_years or not selected_measures or not selected_categories:
        fig = go.Figure()
        fig.update_layout(template=get_brand_chart_template())
        fig.add_annotation(text='داده‌ای برای نمایش وجود ندارد', x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False)
        return fig
    
    # Use the most recent year for top categories
    recent_year = max(selected_years)
    measure = selected_measures[0] if selected_measures else BUDGET_FA
    
    filtered_df = df_cat[
        (df_cat['year'] == recent_year) &
        (df_cat['measure'] == measure) &
        (df_cat['category'].isin(selected_categories))
    ]
    
    if filtered_df.empty:
        fig = go.Figure()
        fig.update_layout(template=get_brand_chart_template())
        fig.add_annotation(text='پس از فیلتر، داده‌ای یافت نشد', x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False)
        return fig
    
    # Get top N categories
    top_categories = filtered_df.nlargest(top_n, 'value')
    
    fig = px.bar(
        top_categories,
        x='value',
        y='category',
        orientation='h',
        labels={'value': 'مبلغ (ریال)', 'category': 'دسته‌بندی'},
        color_discrete_sequence=get_brand_color_palette()
    )
    
    fig.update_layout(
        height=500,
        yaxis={'categoryorder': 'total ascending'},
        template=get_brand_chart_template(),
        font=dict(family='IRANSans, Vazir, Tahoma, Arial, sans-serif'),
        title=dict(
            text='بودجه مصوب هر دسته',
            x=0.5,
            xanchor='center',
            font=dict(
                family='IRANSans, Vazir, Tahoma, Arial, sans-serif',
                size=16
            )
        ),
        title_x=0.5
    )
    
    return fig

# Callback for year-over-year chart
@app.callback(
    Output('year-over-year-chart', 'figure'),
    [Input('year-dropdown', 'value'),
     Input('measure-dropdown', 'value'),
     Input('category-dropdown', 'value')]
)
def update_year_over_year_chart(selected_years, selected_measures, selected_categories):
    if not selected_years or not selected_measures or not selected_categories or len(selected_years) < 2:
        fig = go.Figure()
        fig.update_layout(template=get_brand_chart_template())
        fig.add_annotation(text='برای مقایسه، حداقل دو سال انتخاب کنید', x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False)
        return fig
    
    filtered_df = df_cat[
        (df_cat['year'].isin(selected_years)) &
        (df_cat['measure'].isin(selected_measures)) &
        (df_cat['category'].isin(selected_categories))
    ]
    
    if filtered_df.empty:
        fig = go.Figure()
        fig.update_layout(template=get_brand_chart_template())
        fig.add_annotation(text='پس از فیلتر، داده‌ای یافت نشد', x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False)
        return fig
    
    # Aggregate by year and measure
    yearly_totals = filtered_df.groupby(['year', 'measure'])['value'].sum().reset_index()
    
    fig = px.line(
        yearly_totals,
        x='year',
        y='value',
        color='measure',
        labels={'value': 'مبلغ (ریال)', 'year': 'سال', 'measure': 'شاخص'},
        color_discrete_sequence=get_brand_color_palette()
    )
    
    fig.update_layout(
        height=400,
        template=get_brand_chart_template(),
        font=dict(family='IRANSans, Vazir, Tahoma, Arial, sans-serif'),
        title=dict(
            text='مقایسه سال به سال',
            x=0.5,
            xanchor='center',
            font=dict(
                family='IRANSans, Vazir, Tahoma, Arial, sans-serif',
                size=16
            )
        ),
        title_x=0.5
    )
    
    return fig

# Callback for execution rate heatmap
@app.callback(
    Output('execution-rate-heatmap', 'figure'),
    [Input('year-dropdown', 'value'),
     Input('category-dropdown', 'value')]
)
def update_execution_rate_heatmap(selected_years, selected_categories):
    if BUDGET_DEBUG:
        print('[Budget Debug] heatmap filters years=', selected_years, 'cats=', selected_categories)
    if not selected_years or not selected_categories:
        fig = go.Figure(); fig.update_layout(template=get_brand_chart_template()); fig.add_annotation(text='لطفاً سال و دسته‌ها را انتخاب کنید', x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False); return fig
    
    # Calculate execution rates
    budget_df = df_cat[
        (df_cat['year'].isin(selected_years)) &
        (df_cat['measure'] == BUDGET_FA) &
        (df_cat['category'].isin(selected_categories))
    ]
    
    actual_df = df_cat[
        (df_cat['year'].isin(selected_years)) &
        (df_cat['measure'] == ACTUAL_FA) &
        (df_cat['category'].isin(selected_categories))
    ]
    
    if BUDGET_DEBUG:
        print('[Budget Debug] heatmap budget rows=', len(budget_df), 'actual rows=', len(actual_df))
    if budget_df.empty or actual_df.empty:
        fig = go.Figure(); fig.update_layout(template=get_brand_chart_template()); fig.add_annotation(text='پس از فیلتر، داده‌ای یافت نشد', x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False); return fig
    
    # Merge and calculate execution rates
    merged = pd.merge(
        budget_df[['year', 'category', 'value']].rename(columns={'value': 'budget'}),
        actual_df[['year', 'category', 'value']].rename(columns={'value': 'actual'}),
        on=['year', 'category'],
        how='inner'
    )
    
    merged['execution_rate'] = (merged['actual'] / merged['budget']) * 100
    
    # Create pivot table for heatmap
    heatmap_data = merged.pivot(index='category', columns='year', values='execution_rate')
    
    # Create custom color scale with better representation for values above 100%
    # Using brand colors for better visual consistency
    fig = px.imshow(
        heatmap_data,
        labels={'x': 'سال', 'y': 'دسته‌بندی', 'color': 'نرخ اجرا (%)'},
        color_continuous_scale=[
            [0.0, BRAND_COLORS['danger']],     # Red for very low execution (0-20%)
            [0.2, BRAND_COLORS['warning']],    # Amber for low execution (20-40%)
            [0.4, '#fef3c7'],                   # Light amber for moderate execution (40-60%)
            [0.6, '#d1fae5'],                   # Light emerald for good execution (60-80%)
            [0.8, BRAND_COLORS['success']],    # Emerald for high execution (80-100%)
            [1.0, BRAND_COLORS['primary']]     # Primary blue for over-execution (>100%)
        ],
        aspect='auto',
        zmin=0,
        zmax=max(200, heatmap_data.max().max() if not heatmap_data.empty else 200)  # Dynamic max, minimum 200%
    )
    
    # Add text annotations showing the exact percentages
    fig.update_traces(
        text=heatmap_data.round(1),
        texttemplate="%{text}%",
        textfont={"size": 10},
        hovertemplate='<b>%{y}</b><br>سال: %{x}<br>نرخ اجرا: %{z:.1f}%<extra></extra>'
    )
    
    fig.update_layout(
        height=520,
        template=get_brand_chart_template(),
        font=dict(family='IRANSans, Vazir, Tahoma, Arial, sans-serif'),
        title=dict(
            text='نقشه حرارتی نرخ اجرا (%)*',
            x=0.5,
            xanchor='center',
            font=dict(
                family='IRANSans, Vazir, Tahoma, Arial, sans-serif',
                size=16
            )
        ),
        title_x=0.5,
        coloraxis_colorbar=dict(
            title="نرخ اجرا (%)",
            tickvals=[0, 50, 100, 150, 200],
            ticktext=["0%", "50%", "100%<br>(بودجه)", "150%", "200%+"]
        ),
        annotations=[
            dict(
                text="* بیش از ۱۰۰٪ یعنی بیش از بودجه",
                x=0.5,
                y=-0.15,
                xref="paper",
                yref="paper",
                xanchor="center",
                yanchor="top",
                showarrow=False,
                font=dict(
                    family='IRANSans, Vazir, Tahoma, Arial, sans-serif',
                    size=12,
                    color="gray"
                )
            )
        ]
    )
    
    return fig

# Callback for budget vs actual scatter plot
@app.callback(
    Output('budget-vs-actual-scatter', 'figure'),
    [Input('year-dropdown', 'value'),
     Input('category-dropdown', 'value')]
)
def update_budget_vs_actual_scatter(selected_years, selected_categories):
    if BUDGET_DEBUG:
        print('[Budget Debug] scatter filters years=', selected_years, 'cats=', selected_categories)
    if not selected_years or not selected_categories:
        fig = go.Figure(); fig.update_layout(template=get_brand_chart_template()); fig.add_annotation(text='لطفاً سال و دسته‌ها را انتخاب کنید', x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False); return fig
    
    # Filter data for selected years and categories
    filtered_df = df_cat[
        (df_cat['year'].isin(selected_years)) &
        (df_cat['category'].isin(selected_categories)) &
        (df_cat['measure'].isin([BUDGET_FA, ACTUAL_FA]))
    ].copy()
    
    if BUDGET_DEBUG:
        print('[Budget Debug] scatter filtered rows=', len(filtered_df))
    if filtered_df.empty:
        fig = go.Figure(); fig.update_layout(template=get_brand_chart_template()); fig.add_annotation(text='پس از فیلتر، داده‌ای یافت نشد', x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False); return fig
    
    # Create separate dataframes for budget and actual
    budget_df = filtered_df[filtered_df['measure'] == BUDGET_FA].copy()
    actual_df = filtered_df[filtered_df['measure'] == ACTUAL_FA].copy()
    
    # Group by category and year, then sum values
    budget_grouped = budget_df.groupby(['category', 'year'])['value'].sum().reset_index()
    actual_grouped = actual_df.groupby(['category', 'year'])['value'].sum().reset_index()
    
    # Merge budget and actual data
    merged_data = pd.merge(
        budget_grouped, 
        actual_grouped, 
        on=['category', 'year'], 
        how='inner',
        suffixes=('_budget', '_actual')
    )
    
    # Remove rows with NaN values
    merged_data = merged_data.dropna()
    
    if merged_data.empty:
        fig = go.Figure(); fig.update_layout(template=get_brand_chart_template()); fig.add_annotation(text='پس از ادغام بودجه/واقعی، داده‌ای یافت نشد', x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False); return fig
    
    # Convert to billions (میلیارد) for better readability
    merged_data['budget_billions'] = merged_data['value_budget'] / 1e9
    merged_data['actual_billions'] = merged_data['value_actual'] / 1e9
    
    # Create hover text with category and year information
    merged_data['hover_text'] = merged_data.apply(
        lambda row: f"دسته‌بندی: {row['category']}<br>سال: {row['year']}<br>بودجه: {row['budget_billions']:.1f} میلیارد ریال<br>واقعی: {row['actual_billions']:.1f} میلیارد ریال", 
        axis=1
    )
    
    # Create scatter plot
    fig = px.scatter(
        merged_data,
        x='budget_billions',
        y='actual_billions',
        color='category',
        size='budget_billions',
        size_max=15,  # Limit maximum point size
        hover_name='hover_text',
        labels={
            'budget_billions': 'بودجه (میلیارد ریال)', 
            'actual_billions': 'واقعی (میلیارد ریال)',
            'category': 'دسته‌بندی'
        },
        title='بودجه در مقابل هزینه‌های واقعی*',
        color_discrete_sequence=get_brand_color_palette()
    )
    
    # Add diagonal line (perfect execution line)
    if not merged_data.empty:
        max_val = max(
            merged_data['budget_billions'].max(), 
            merged_data['actual_billions'].max()
        )
        fig.add_shape(
            type="line",
            x0=0, y0=0, x1=max_val, y1=max_val,
            line=dict(color=BRAND_COLORS['danger'], width=2, dash="dash"),
            name="خط اجرای کامل"
        )
    
    # Update layout
    fig.update_layout(
        height=450,
        template=get_brand_chart_template(),
        font=dict(family='IRANSans, Vazir, Tahoma, Arial, sans-serif'),
        title=dict(
            text='بودجه در مقابل هزینه‌های واقعی*',
            x=0.5,
            xanchor='center',
            font=dict(
                family='IRANSans, Vazir, Tahoma, Arial, sans-serif',
                size=16
            )
        ),
        title_x=0.5,
        annotations=[
            dict(
                text="* نقاط روی خط قرمز: اجرای کامل بودجه، نقاط بالای خط: بیش از بودجه، نقاط زیر خط: کمتر از بودجه",
                x=0.5,
                y=-0.15,
                xref="paper",
                yref="paper",
                xanchor="center",
                yanchor="top",
                showarrow=False,
                font=dict(
                    family='IRANSans, Vazir, Tahoma, Arial, sans-serif',
                    size=12,
                    color="gray"
                )
            )
        ]
    )
    
    # Update traces for better visibility
    fig.update_traces(
        marker=dict(
            sizemin=6,  # Minimum point size
            line=dict(width=1, color='white'),
            opacity=0.8
        ),
        hovertemplate='%{hovertext}<extra></extra>'
    )
    
    return fig

# Callback for pie chart
@app.callback(
    Output('pie-chart', 'figure'),
    [Input('year-dropdown', 'value'),
     Input('measure-dropdown', 'value'),
     Input('category-dropdown', 'value')]
)
def update_pie_chart(selected_years, selected_measures, selected_categories):
    if BUDGET_DEBUG:
        print('[Budget Debug] pie filters years=', selected_years, 'measures=', selected_measures, 'cats=', selected_categories)
    if not selected_years or not selected_measures or not selected_categories:
        fig = go.Figure(); fig.update_layout(template=get_brand_chart_template()); fig.add_annotation(text='لطفاً فیلترها را کامل کنید', x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False); return fig
    
    # Use the most recent year and first measure
    recent_year = max(selected_years)
    measure = selected_measures[0] if selected_measures else BUDGET_FA
    
    filtered_df = df_cat[
        (df_cat['year'] == recent_year) &
        (df_cat['measure'] == measure) &
        (df_cat['category'].isin(selected_categories))
    ]
    
    if filtered_df.empty:
        fig = go.Figure(); fig.update_layout(template=get_brand_chart_template()); fig.add_annotation(text='پس از فیلتر، داده‌ای یافت نشد', x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False); return fig
    
    fig = px.pie(
        filtered_df,
        values='value',
        names='category',
        color_discrete_sequence=get_brand_color_palette()
    )
    
    fig.update_layout(
        height=400,
        template=get_brand_chart_template(),
        font=dict(family='IRANSans, Vazir, Tahoma, Arial, sans-serif'),
        title=dict(
            text=f'توزیع بر اساس دسته‌بندی - {measure} ({recent_year})',
            x=0.5,
            xanchor='center',
            font=dict(
                family='IRANSans, Vazir, Tahoma, Arial, sans-serif',
                size=16
            )
        ),
        title_x=0.5
    )
    
    return fig

# Callback for trend analysis
@app.callback(
    Output('trend-analysis-chart', 'figure'),
    [Input('year-dropdown', 'value'),
     Input('measure-dropdown', 'value'),
     Input('category-dropdown', 'value')]
)
def update_trend_analysis_chart(selected_years, selected_measures, selected_categories):
    if BUDGET_DEBUG:
        print('[Budget Debug] trend filters years=', selected_years, 'measures=', selected_measures, 'cats=', selected_categories)
    if not selected_years or not selected_measures or not selected_categories or len(selected_years) < 2:
        fig = go.Figure(); fig.update_layout(template=get_brand_chart_template()); fig.add_annotation(text='برای تحلیل روند حداقل دو سال انتخاب کنید', x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False); return fig
    
    measure = selected_measures[0] if selected_measures else BUDGET_FA
    
    filtered_df = df_cat[
        (df_cat['year'].isin(selected_years)) &
        (df_cat['measure'] == measure) &
        (df_cat['category'].isin(selected_categories))
    ]
    
    if filtered_df.empty:
        fig = go.Figure(); fig.update_layout(template=get_brand_chart_template()); fig.add_annotation(text='پس از فیلتر، داده‌ای یافت نشد', x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False); return fig
    
    fig = px.line(
        filtered_df,
        x='year',
        y='value',
        color='category',
        labels={'value': 'مبلغ (ریال)', 'year': 'سال', 'category': 'دسته‌بندی'},
        color_discrete_sequence=get_brand_color_palette()
    )
    
    fig.update_layout(
        height=500,
        template=get_brand_chart_template(),
        font=dict(family='IRANSans, Vazir, Tahoma, Arial, sans-serif'),
        title=dict(
            text=f'تحلیل روند - {measure}',
            x=0.5,
            xanchor='center',
            font=dict(
                family='IRANSans, Vazir, Tahoma, Arial, sans-serif',
                size=16
            )
        ),
        title_x=0.5
    )
    
    return fig

# Callback for budget forecasting
@app.callback(
    [Output('forecast-chart', 'figure'),
     Output('forecast-metrics', 'children')],
    [Input('forecast-category-dropdown', 'value'),
     Input('forecast-measure-dropdown', 'value'),
     Input('forecast-years-slider', 'value')]
)
def update_forecast(selected_category, selected_measure, forecast_years):
    if not selected_category or not selected_measure:
        return go.Figure(), html.Div("Please select category and measure for forecasting")
    
    # Filter data for the selected category and measure
    forecast_df = df_cat[
        (df_cat['category'] == selected_category) &
        (df_cat['measure'] == selected_measure)
    ].copy()
    
    if forecast_df.empty or len(forecast_df) < 3:
        return go.Figure(), html.Div("Insufficient data for forecasting (minimum 3 years required)")
    
    # Sort by year
    forecast_df = forecast_df.sort_values('year')
    
    # Prepare data for linear regression
    X = forecast_df['year'].values.reshape(-1, 1)
    y = forecast_df['value'].values
    
    try:
        # Train linear regression model
        model = LinearRegression()
        model.fit(X, y)
        
        # Calculate R² score
        r2_score = model.score(X, y)
        
        # Generate future years
        last_year = forecast_df['year'].max()
        future_years = np.arange(last_year + 1, last_year + forecast_years + 1)
        future_X = future_years.reshape(-1, 1)
        
        # Make predictions
        future_predictions = model.predict(future_X)
        
        # Create figure
        fig = go.Figure()
        
        # Add historical data
        fig.add_trace(go.Scatter(
            x=forecast_df['year'],
            y=forecast_df['value'],
            mode='lines+markers',
            name='داده‌های تاریخی',
            line=dict(color='blue', width=3),
            marker=dict(size=8)
        ))
        
        # Add predictions with connection to last historical point
        # Include the last historical point to connect the lines
        last_historical_year = forecast_df['year'].iloc[-1]
        last_historical_value = forecast_df['value'].iloc[-1]
        
        # Combine last historical point with predictions for smooth connection
        prediction_years = np.concatenate([[last_historical_year], future_years])
        prediction_values = np.concatenate([[last_historical_value], future_predictions])
        
        fig.add_trace(go.Scatter(
            x=prediction_years,
            y=prediction_values,
            mode='lines+markers',
            name='پیش‌بینی',
            line=dict(color=BRAND_COLORS['danger'], width=3, dash='dash'),
            marker=dict(size=8, symbol='diamond')
        ))
        
        # Add trend line for historical data
        historical_trend = model.predict(X)
        fig.add_trace(go.Scatter(
            x=forecast_df['year'],
            y=historical_trend,
            mode='lines',
            name='خط روند',
            line=dict(color=BRAND_COLORS['success'], width=2, dash='dot'),
            opacity=0.7
        ))
        
        fig.update_layout(
            title=dict(
                text=f'پیش‌بینی بودجه: {selected_category} - {selected_measure}',
                x=0.5,
                xanchor='center',
                font=dict(
                    family='IRANSans, Vazir, Tahoma, Arial, sans-serif',
                    size=16
                )
            ),
            xaxis=dict(
                title=dict(
                    text='سال',
                    font=dict(
                        family='IRANSans, Vazir, Tahoma, Arial, sans-serif',
                        size=14
                    )
                )
            ),
            yaxis=dict(
                title=dict(
                    text='مبلغ (ریال)',
                    font=dict(
                        family='IRANSans, Vazir, Tahoma, Arial, sans-serif',
                        size=14
                    )
                )
            ),
            height=500,
            template=get_brand_chart_template(),
            hovermode='x unified',
            font=dict(family='IRANSans, Vazir, Tahoma, Arial, sans-serif'),
            title_x=0.5
        )
        
        # Create metrics
        avg_growth = (future_predictions[-1] - forecast_df['value'].iloc[-1]) / forecast_years
        total_growth = ((future_predictions[-1] - forecast_df['value'].iloc[-1]) / forecast_df['value'].iloc[-1]) * 100
        
        metrics = html.Div([
            html.H4("معیارهای پیش‌بینی", style={'color': '#34495e', 'marginBottom': '15px', 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif', 'direction': 'rtl', 'textAlign': 'right'}),
            html.Div([
                html.Div([
                    html.H5("دقت مدل (R²)", style={'margin': '0', 'color': '#2c3e50', 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif', 'direction': 'rtl'}),
                    html.H3(f"{r2_score:.3f}", style={'margin': '5px 0', 'color': BRAND_COLORS['success'] if r2_score > 0.7 else BRAND_COLORS['warning'], 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif'})
                ], style={
                    'backgroundColor': 'white',
                    'padding': '15px',
                    'borderRadius': '8px',
                    'boxShadow': '0 2px 4px rgba(0,0,0,0.1)',
                    'textAlign': 'center',
                    'margin': '5px'
                }),
                html.Div([
                     html.H5("میانگین رشد سالانه", style={'margin': '0', 'color': '#2c3e50', 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif', 'direction': 'rtl'}),
                     html.H3(format_money(avg_growth), style={'margin': '5px 0', 'color': BRAND_COLORS['info'], 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif'})
                 ], style={
                     'backgroundColor': 'white',
                     'padding': '15px',
                     'borderRadius': '8px',
                     'boxShadow': '0 2px 4px rgba(0,0,0,0.1)',
                     'textAlign': 'center',
                     'margin': '5px'
                 }),
                 html.Div([
                     html.H5("نرخ رشد کل", style={'margin': '0', 'color': '#2c3e50', 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif', 'direction': 'rtl'}),
                     html.H3(format_percentage(total_growth), style={'margin': '5px 0', 'color': BRAND_COLORS['danger'] if total_growth < 0 else BRAND_COLORS['success'], 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif'})
                 ], style={
                     'backgroundColor': 'white',
                     'padding': '15px',
                     'borderRadius': '8px',
                     'boxShadow': '0 2px 4px rgba(0,0,0,0.1)',
                     'textAlign': 'center',
                     'margin': '5px'
                 }),
                 html.Div([
                     html.H5(f"پیش‌بینی {last_year + forecast_years}", style={'margin': '0', 'color': '#2c3e50', 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif', 'direction': 'rtl'}),
                     html.H3(format_money(future_predictions[-1]), style={'margin': '5px 0', 'color': '#9b59b6', 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif'})
                 ], style={
                     'backgroundColor': 'white',
                     'padding': '15px',
                     'borderRadius': '8px',
                     'boxShadow': '0 2px 4px rgba(0,0,0,0.1)',
                     'textAlign': 'center',
                     'margin': '5px'
                 })
            ], style={'display': 'flex', 'flexWrap': 'wrap', 'justifyContent': 'space-around'}),
            
            # Warning for low accuracy
            html.Div([
                html.P("هشدار: دقت مدل پایین (R² < 0.7). پیش‌بینی‌ها ممکن است قابل اعتماد نباشند.", 
                       style={'color': BRAND_COLORS['danger'], 'fontWeight': 'bold', 'textAlign': 'center', 'margin': '10px 0', 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif', 'direction': 'rtl'})
            ], style={'display': 'block' if r2_score < 0.7 else 'none'})
        ])
        
        return fig, metrics
        
    except Exception as e:
        error_msg = html.Div([
            html.H4("خطا در پیش‌بینی", style={'color': BRAND_COLORS['danger'], 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif', 'direction': 'rtl', 'textAlign': 'right'}),
            html.P(f"خطا: {str(e)}", style={'color': '#7f8c8d', 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif', 'direction': 'rtl', 'textAlign': 'right'})
        ])
        return go.Figure(), error_msg

# Callback for Time Series Line Chart
@app.callback(
    Output('time-series-chart', 'figure'),
    [Input('year-dropdown', 'value'),
     Input('measure-dropdown', 'value'),
     Input('category-dropdown', 'value')]
)
def update_time_series_chart(selected_years, selected_measures, selected_categories):
    if BUDGET_DEBUG:
        print('[Budget Debug] time-series filters years=', selected_years, 'measures=', selected_measures, 'cats=', selected_categories)
    if not selected_years or not selected_measures or not selected_categories:
        fig = go.Figure(); fig.update_layout(template=get_brand_chart_template()); fig.add_annotation(text='لطفاً فیلترها را کامل کنید', x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False); return fig
    
    # Filter data for selected categories and years
    filtered_df = df_cat[
        (df_cat['year'].isin(selected_years)) &
        (df_cat['category'].isin(selected_categories)) &
        (df_cat['measure'].isin(selected_measures))
    ]
    
    if filtered_df.empty:
        fig = go.Figure(); fig.update_layout(template=get_brand_chart_template()); fig.add_annotation(text='پس از فیلتر، داده‌ای یافت نشد', x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False); return fig
    
    # Group by year and measure, sum values
    time_series_data = filtered_df.groupby(['year', 'measure'])['value'].sum().reset_index()
    
    # Create figure
    fig = go.Figure()
    
    # Add line for each measure
    for measure in selected_measures:
        measure_data = time_series_data[time_series_data['measure'] == measure]
        if not measure_data.empty:
            fig.add_trace(go.Scatter(
                x=measure_data['year'],
                y=measure_data['value'] / 1e9,  # Convert to billions
                mode='lines+markers',
                name=measure,
                line=dict(width=3),
                marker=dict(size=8),
                hovertemplate=f'<b>{measure}</b><br>' +
                             'سال: %{x}<br>' +
                             'مقدار: %{y:.1f} میلیارد ریال<extra></extra>'
            ))
    
    # Update layout
    fig.update_layout(
        title=dict(
            text='روند زمانی بودجه و هزینه‌های واقعی',
            x=0.5,
            xanchor='center',
            font=dict(
                family='IRANSans, Vazir, Tahoma, Arial, sans-serif',
                size=16
            )
        ),
        xaxis_title='سال',
        yaxis_title='مقدار (میلیارد ریال)',
        template=get_brand_chart_template(),
        font=dict(family='IRANSans, Vazir, Tahoma, Arial, sans-serif'),
        height=450,
        hovermode='x unified'
    )
    
    return fig

# Callback for Bar Chart Comparison
@app.callback(
    Output('bar-comparison-chart', 'figure'),
    [Input('year-dropdown', 'value'),
     Input('measure-dropdown', 'value'),
     Input('category-dropdown', 'value'),
     Input('top-n-slider', 'value')]
)
def update_bar_comparison_chart(selected_years, selected_measures, selected_categories, top_n):
    if BUDGET_DEBUG:
        print('[Budget Debug] bar-comparison filters years=', selected_years, 'measures=', selected_measures, 'cats=', selected_categories, 'top_n=', top_n)
    if not selected_years or not selected_measures or not selected_categories:
        fig = go.Figure(); fig.update_layout(template=get_brand_chart_template()); fig.add_annotation(text='لطفاً فیلترها را کامل کنید', x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False); return fig
    
    # Filter data
    filtered_df = df_cat[
        (df_cat['year'].isin(selected_years)) &
        (df_cat['category'].isin(selected_categories)) &
        (df_cat['measure'].isin(selected_measures))
    ]
    
    if filtered_df.empty:
        fig = go.Figure(); fig.update_layout(template=get_brand_chart_template()); fig.add_annotation(text='پس از فیلتر، داده‌ای یافت نشد', x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False); return fig
    
    # Group by category and measure, sum values
    bar_data = filtered_df.groupby(['category', 'measure'])['value'].sum().reset_index()
    
    # Get top N categories by total value
    category_totals = bar_data.groupby('category')['value'].sum().sort_values(ascending=False).head(top_n)
    top_categories = category_totals.index.tolist()
    bar_data = bar_data[bar_data['category'].isin(top_categories)]
    
    # Create figure
    fig = go.Figure()
    
    # Add bar for each measure
    for measure in selected_measures:
        measure_data = bar_data[bar_data['measure'] == measure]
        if not measure_data.empty:
            fig.add_trace(go.Bar(
                x=measure_data['category'],
                y=measure_data['value'] / 1e9,  # Convert to billions
                name=measure,
                hovertemplate=f'<b>{measure}</b><br>' +
                             'دسته‌بندی: %{x}<br>' +
                             'مقدار: %{y:.1f} میلیارد ریال<extra></extra>'
            ))
    
    # Update layout
    fig.update_layout(
        title=dict(
            text='مقایسه دسته‌بندی‌ها',
            x=0.5,
            xanchor='center',
            font=dict(
                family='IRANSans, Vazir, Tahoma, Arial, sans-serif',
                size=16
            )
        ),
        xaxis_title='دسته‌بندی',
        yaxis_title='مقدار (میلیارد ریال)',
        template=get_brand_chart_template(),
        font=dict(family='IRANSans, Vazir, Tahoma, Arial, sans-serif'),
        height=450,
        barmode='group',
        xaxis=dict(tickangle=45)
    )
    
    return fig

# Callback for Waterfall Chart
@app.callback(
    Output('waterfall-chart', 'figure'),
    [Input('year-dropdown', 'value'),
     Input('category-dropdown', 'value')]
)
def update_waterfall_chart(selected_years, selected_categories):
    if BUDGET_DEBUG:
        print('[Budget Debug] waterfall filters years=', selected_years, 'cats=', selected_categories)
    if not selected_years or not selected_categories:
        fig = go.Figure(); fig.update_layout(template=get_brand_chart_template()); fig.add_annotation(text='لطفاً سال و دسته‌ها را انتخاب کنید', x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False); return fig
    
    # Get budget and actual data for the latest year
    latest_year = max(selected_years)
    
    # Filter data for budget and actual
    budget_data = df_cat[
        (df_cat['year'] == latest_year) &
        (df_cat['category'].isin(selected_categories)) &
        (df_cat['measure'] == BUDGET_FA)
    ]
    
    actual_data = df_cat[
        (df_cat['year'] == latest_year) &
        (df_cat['category'].isin(selected_categories)) &
        (df_cat['measure'] == ACTUAL_FA)
    ]
    
    if budget_data.empty or actual_data.empty:
        fig = go.Figure(); fig.update_layout(template=get_brand_chart_template()); fig.add_annotation(text='پس از فیلتر، داده‌ای یافت نشد', x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False); return fig
    
    # Calculate variances
    budget_sum = budget_data.groupby('category')['value'].sum()
    actual_sum = actual_data.groupby('category')['value'].sum()
    
    # Get top 5 categories by budget
    top_categories = budget_sum.sort_values(ascending=False).head(5)
    
    # Prepare waterfall data
    categories = ['بودجه کل']
    values = [top_categories.sum() / 1e9]  # Convert to billions
    measures = ['absolute']
    
    for cat in top_categories.index:
        variance = (actual_sum.get(cat, 0) - budget_sum.get(cat, 0)) / 1e9
        categories.append(f'تغییر {cat}')
        values.append(variance)
        measures.append('relative')
    
    categories.append('هزینه واقعی')
    values.append(actual_sum[top_categories.index].sum() / 1e9)
    measures.append('total')
    
    # Create waterfall chart
    fig = go.Figure(go.Waterfall(
        name="تحلیل واریانس",
        orientation="v",
        measure=measures,
        x=categories,
        y=values,
        connector={"line": {"color": BRAND_COLORS['medium']}},
        hovertemplate='%{x}<br>مقدار: %{y:.1f} میلیارد ریال<extra></extra>'
    ))
    
    # Update layout
    fig.update_layout(
        title=dict(
            text=f'تحلیل واریانس بودجه - سال {latest_year}',
            x=0.5,
            xanchor='center',
            font=dict(
                family='IRANSans, Vazir, Tahoma, Arial, sans-serif',
                size=16
            )
        ),
        yaxis_title='مقدار (میلیارد ریال)',
        template=get_brand_chart_template(),
        font=dict(family='IRANSans, Vazir, Tahoma, Arial, sans-serif'),
        height=450,
        xaxis=dict(tickangle=45)
    )
    
    return fig

# Callback for Gauge Chart
@app.callback(
    Output('gauge-chart', 'figure'),
    [Input('year-dropdown', 'value'),
     Input('category-dropdown', 'value')]
)
def update_gauge_chart(selected_years, selected_categories):
    if BUDGET_DEBUG:
        print('[Budget Debug] gauge filters years=', selected_years, 'cats=', selected_categories)
    if not selected_years or not selected_categories:
        fig = go.Figure(); fig.update_layout(template=get_brand_chart_template()); fig.add_annotation(text='لطفاً سال و دسته‌ها را انتخاب کنید', x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False); return fig
    
    # Get latest year data
    latest_year = max(selected_years)
    
    # Calculate total budget and actual for selected categories
    budget_total = df_cat[
        (df_cat['year'] == latest_year) &
        (df_cat['category'].isin(selected_categories)) &
        (df_cat['measure'] == BUDGET_FA)
    ]['value'].sum()
    
    actual_total = df_cat[
        (df_cat['year'] == latest_year) &
        (df_cat['category'].isin(selected_categories)) &
        (df_cat['measure'] == ACTUAL_FA)
    ]['value'].sum()
    
    if budget_total == 0:
        execution_rate = 0
    else:
        execution_rate = (actual_total / budget_total) * 100
    
    # Create gauge chart
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=execution_rate,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': f"نرخ اجرای بودجه - سال {latest_year}"},
        delta={'reference': 100},
        gauge={
            'axis': {'range': [None, 150]},
            'bar': {'color': BRAND_COLORS['primary']},
            'steps': [
                {'range': [0, 50], 'color': BRAND_COLORS['light']},
                {'range': [50, 100], 'color': BRAND_COLORS['medium']}
            ],
            'threshold': {
                'line': {'color': BRAND_COLORS['danger'], 'width': 4},
                'thickness': 0.75,
                'value': 100
            }
        }
    ))
    
    # Update layout
    fig.update_layout(
        template=get_brand_chart_template(),
        font=dict(family='IRANSans, Vazir, Tahoma, Arial, sans-serif'),
        height=450
    )
    
    return fig

# Callback for Box Plot
@app.callback(
    Output('box-plot-chart', 'figure'),
    [Input('year-dropdown', 'value'),
     Input('measure-dropdown', 'value'),
     Input('category-dropdown', 'value')]
)
def update_box_plot_chart(selected_years, selected_measures, selected_categories):
    if BUDGET_DEBUG:
        print('[Budget Debug] box-plot filters years=', selected_years, 'measures=', selected_measures, 'cats=', selected_categories)
    if not selected_years or not selected_measures or not selected_categories:
        fig = go.Figure(); fig.update_layout(template=get_brand_chart_template()); fig.add_annotation(text='لطفاً فیلترها را کامل کنید', x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False); return fig
    
    # Filter data
    filtered_df = df_cat[
        (df_cat['year'].isin(selected_years)) &
        (df_cat['category'].isin(selected_categories)) &
        (df_cat['measure'].isin(selected_measures))
    ]
    
    if filtered_df.empty:
        fig = go.Figure(); fig.update_layout(template=get_brand_chart_template()); fig.add_annotation(text='پس از فیلتر، داده‌ای یافت نشد', x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False); return fig
    
    # Create figure
    fig = go.Figure()
    
    # Add box plot for each measure
    for measure in selected_measures:
        measure_data = filtered_df[filtered_df['measure'] == measure]
        if not measure_data.empty:
            fig.add_trace(go.Box(
                y=measure_data['value'] / 1e9,  # Convert to billions
                name=measure,
                boxpoints='outliers',
                hovertemplate=f'<b>{measure}</b><br>' +
                             'مقدار: %{y:.1f} میلیارد ریال<extra></extra>'
            ))
    
    # Update layout
    fig.update_layout(
        title=dict(
            text='توزیع آماری مقادیر',
            x=0.5,
            xanchor='center',
            font=dict(
                family='IRANSans, Vazir, Tahoma, Arial, sans-serif',
                size=16
            )
        ),
        yaxis_title='مقدار (میلیارد ریال)',
        template=get_brand_chart_template(),
        font=dict(family='IRANSans, Vazir, Tahoma, Arial, sans-serif'),
        height=450
    )
    
    return fig

# Login callback
@app.callback(
    [Output('login-output', 'children'),
     Output('url', 'pathname', allow_duplicate=True)],
    [Input('login-button', 'n_clicks')],
    [State('username-input', 'value'),
     State('password-input', 'value')],
    prevent_initial_call=True
)
def authenticate_user(n_clicks, username, password):
    """Authenticate user and manage session"""
    if n_clicks and username and password:
        uname = (username or '').strip()
        pwd = (password or '').strip()
        password_hash = hashlib.sha256(pwd.encode()).hexdigest()
        
        # Check credentials
        if uname == USERNAME and password_hash == PASSWORD_HASH:
            session['authenticated'] = True
            return html.Div("ورود موفقیت‌آمیز! در حال انتقال...", 
                          style={'color': 'green', 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif', 'direction': 'rtl'}), '/'
        else:
            return html.Div("نام کاربری یا رمز عبور اشتباه است", 
                          style={'color': 'red', 'fontFamily': 'IRANSans, Vazir, Tahoma, Arial, sans-serif', 'direction': 'rtl'}), no_update
    
    return no_update, no_update

# Add URL component for navigation
app.layout = html.Div([
    dcc.Location(id='url', refresh=True),
    html.Div(id='page-content')
])

# Suppress callback exceptions for better UX
app.config.suppress_callback_exceptions = True

# Page content callback
@app.callback(
    Output('page-content', 'children'),
    [Input('url', 'pathname')]
)
def display_page(pathname):
    """Display appropriate page based on authentication"""
    if check_authentication():
        return main_dashboard_layout()
    else:
        return login_layout()

if __name__ == '__main__':
    app.run(debug=True, port=8050)

# For WSGI deployment (PythonAnywhere)
server = app.server
