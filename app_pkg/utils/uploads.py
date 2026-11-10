"""Saving user-uploaded files.

werkzeug's secure_filename() drops every non-ASCII character, so a Persian name such as
'اطلاعات پرسنل.xlsx' became just 'xlsx' (no extension, and every upload overwrote the last).
safe_filename() keeps Unicode letters and digits instead.
"""
import os
import re
from datetime import datetime

from flask import flash


class UploadError(ValueError):
    pass


def safe_filename(name, fallback='upload'):
    """Basename with only Unicode letters/digits and - _ . kept; spaces become '_'."""
    name = os.path.basename((name or '').replace('\\', '/'))
    stem, ext = os.path.splitext(name)
    if not ext and stem.startswith('.'):  # '.csv' -> no name, extension 'csv'
        stem, ext = '', stem
    stem = re.sub(r'[^\w\-.]+', '_', stem, flags=re.UNICODE).strip('._')
    ext = re.sub(r'[^\w]+', '', ext, flags=re.UNICODE).lower()
    if not stem:
        stem = f"{fallback}_{datetime.utcnow():%Y%m%d_%H%M%S}"
    return f"{stem}.{ext}" if ext else stem


def extension_of(filename):
    return os.path.splitext(filename or '')[1].lower().lstrip('.')


def save_upload(file, dest_dir, allowed_exts, filename=None):
    """Validate and save a werkzeug FileStorage. Returns the saved path.

    `filename` forces the stored name (e.g. 'Chart.csv'); otherwise a safe version of the
    uploaded name is used. Raises UploadError for a missing file or a disallowed extension.
    """
    if not file or not file.filename:
        raise UploadError('فایلی انتخاب نشده است.')
    ext = extension_of(file.filename)
    allowed = {e.lower().lstrip('.') for e in allowed_exts}
    if ext not in allowed:
        raise UploadError(f'{file.filename}: فقط فایل‌های {", ".join(sorted(allowed))} مجاز است.')
    name = filename or safe_filename(file.filename)
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, name)
    if os.path.dirname(os.path.abspath(path)) != os.path.abspath(dest_dir):
        raise UploadError('نام فایل نامعتبر است.')
    file.save(path)
    return path


def flash_upload_summary(saved_count, errors, saved_msg='{n} فایل با موفقیت آپلود شد.'):
    if saved_count:
        flash(saved_msg.format(n=saved_count), 'success')
    if errors:
        flash('خطا در آپلود: ' + '، '.join(errors), 'danger')
    if not saved_count and not errors:
        flash('هیچ فایلی انتخاب نشده است.', 'warning')
