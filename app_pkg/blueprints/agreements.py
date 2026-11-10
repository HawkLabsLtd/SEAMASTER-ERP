from flask import Blueprint, render_template, request
from app_pkg.models import MoU
from sqlalchemy import desc
from collections import Counter
import jdatetime

from app_pkg.auth import require_permissions
bp = Blueprint('agreements', __name__, url_prefix='/agreements')

def get_jalali_now():
    return jdatetime.datetime.now()

# Translation Mappings
SENDER_TYPE_MAP = {
    'University': 'دانشگاه',
    'Company': 'شرکت',
    'Government': 'دولتی',
    'Association': 'تشکل',
    'Other': 'سایر'
}

STATUS_MAP = {
    'New': 'جدید',
    'Under Review': 'در حال بررسی',
    'Signed': 'امضا شده',
    'Archived': 'بایگانی'
}

def translate_dict_keys(d, mapping):
    return {mapping.get(k, k): v for k, v in d.items()}

@bp.route('/')
@require_permissions('agreements.view')
def index():
    # Filter Parameters
    filter_priority = request.args.get('priority')
    filter_sender = request.args.get('sender')
    filter_status = request.args.get('status')
    search_query = request.args.get('search')

    # Base Query
    query = MoU.query

    # Apply Filters
    if filter_priority and filter_priority != 'All':
        query = query.filter(MoU.priority == filter_priority)
    if filter_sender:
        query = query.filter(MoU.sender.contains(filter_sender))
    if filter_status and filter_status != 'All':
        query = query.filter(MoU.status == filter_status)
    if search_query:
        query = query.filter(
            (MoU.subject.contains(search_query)) |
            (MoU.sender.contains(search_query)) |
            (MoU.receiver.contains(search_query))
        )

    # Fetch Data for Analytics (All matching records)
    all_agreements = query.order_by(desc(MoU.date)).all()
    total_agreements = len(all_agreements)
    print(f"DEBUG Agreements: total_agreements={total_agreements}")

    # Analytics Logic
    now_jalali = get_jalali_now()
    current_month_str = now_jalali.strftime('%Y/%m')
    
    # KPIs
    this_month_count = 0
    urgent_pending_count = 0
    
    priority_counts = Counter()
    sender_type_counts = Counter()
    status_counts = Counter()
    
    months = []
    
    for a in all_agreements:
        # Priority
        if a.priority:
            priority_counts[a.priority] += 1
            
        # Sender Type
        if a.sender_type:
            sender_type_counts[a.sender_type] += 1
            
        # Status
        if a.status:
            status_counts[a.status] += 1
            
        # Date processing
        if a.date and len(a.date) >= 7:
            month_str = a.date[:7] # 1404/09
            months.append(month_str)
            
            if month_str == current_month_str:
                this_month_count += 1
        
        # Urgent & Pending
        if a.priority in ['فوري', 'آني'] and a.status in ['New', 'Under Review']:
            urgent_pending_count += 1

    # Monthly Trend
    monthly_counts = sorted(Counter(months).items())

    # Top Senders
    senders = [a.sender for a in all_agreements if a.sender]
    top_senders = Counter(senders).most_common(5)

    # Top Receivers
    receivers = [a.receiver for a in all_agreements if a.receiver]
    top_receivers = Counter(receivers).most_common(5)

    # Alerts (Urgent items pending)
    alerts = []
    if urgent_pending_count > 0:
        alerts.append({
            'type': 'warning',
            'message': f'{urgent_pending_count} مورد فوری در انتظار بررسی است.'
        })

    # Prepare translated data for charts
    sender_type_counts_fa = translate_dict_keys(dict(sender_type_counts), SENDER_TYPE_MAP)
    status_counts_fa = translate_dict_keys(dict(status_counts), STATUS_MAP)

    # Pagination for Table
    page = request.args.get('page', 1, type=int)
    per_page = 10
    pagination = query.order_by(desc(MoU.date)).paginate(page=page, per_page=per_page, error_out=False)
    agreements = pagination.items

    return render_template('agreements/index.html',
                           agreements=agreements,
                           pagination=pagination,
                           total_agreements=total_agreements,
                           this_month_count=this_month_count,
                           urgent_pending_count=urgent_pending_count,
                           priority_counts=dict(priority_counts),
                           sender_type_counts=sender_type_counts_fa,
                           status_counts=status_counts_fa,
                           monthly_counts=monthly_counts,
                           top_senders=top_senders,
                           top_receivers=top_receivers,
                           filter_priority=filter_priority,
                           filter_status=filter_status,
                           search_query=search_query,
                           alerts=alerts,
                           sender_type_map=SENDER_TYPE_MAP,
                           status_map=STATUS_MAP)
