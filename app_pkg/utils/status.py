def status_label_fa(status_code: str) -> str:
    mapping = {
        'pending': 'در انتظار',
        'approved': 'تأییدشده',
        'in_progress': 'در حال انجام',
        'completed': 'تکمیل‌شده',
    }
    return mapping.get((status_code or '').strip(), status_code)

