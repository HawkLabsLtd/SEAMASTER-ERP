import io

import pytest
from werkzeug.datastructures import FileStorage

from conftest import csrf_headers


def storage(name, data=b'a,b\n1,2\n'):
    return FileStorage(stream=io.BytesIO(data), filename=name)


def test_safe_filename_keeps_persian():
    from app_pkg.utils.uploads import safe_filename
    assert safe_filename('اطلاعات پرسنل.xlsx') == 'اطلاعات_پرسنل.xlsx'
    assert safe_filename('../../etc/passwd.csv') == 'passwd.csv'
    assert safe_filename('..\\..\\evil.CSV') == 'evil.csv'
    assert safe_filename('.csv').startswith('upload_') and safe_filename('.csv').endswith('.csv')


def test_save_upload_validates_extension(tmp_path):
    from app_pkg.utils.uploads import save_upload, UploadError
    assert save_upload(storage('هفته ۴۱.csv'), tmp_path, {'csv'}).endswith('هفته_۴۱.csv')
    with pytest.raises(UploadError):
        save_upload(storage('shell.php'), tmp_path, {'csv'})
    with pytest.raises(UploadError):
        save_upload(storage(''), tmp_path, {'csv'})


def test_save_upload_forced_name(tmp_path):
    from app_pkg.utils.uploads import save_upload
    path = save_upload(storage('whatever.csv'), tmp_path, {'csv'}, filename='Chart.csv')
    assert path.endswith('Chart.csv') and (tmp_path / 'Chart.csv').exists()


def test_every_home_page_endpoint_exists(app):
    from flask import url_for
    from app_pkg.auth import HOME_PAGES
    with app.test_request_context():
        for _, endpoint in HOME_PAGES:
            url_for(endpoint)  # raises BuildError for a wrong endpoint name


def test_email_upload_keeps_persian_name(app, login, monkeypatch, tmp_path):
    import app_pkg.blueprints.email_dashboard as email
    monkeypatch.setattr(email, 'DATA_DIR', str(tmp_path))
    c = login('manager')
    r = c.post('/email/update', data={'csv_files': [storage('کمپین ۴۱.csv')], **{'csrf_token': csrf_headers(c)['X-CSRFToken']}},
               content_type='multipart/form-data')
    assert r.status_code == 302
    assert (tmp_path / 'کمپین_۴۱.csv').exists()


def test_email_campaign_lookup_rejects_paths(login):
    c = login('staff')
    assert c.get('/email/api/campaign/..%5C..%5Capp.py').status_code == 404
    assert c.get('/email/api/campaign/missing.csv').status_code == 404


def test_recording_download_is_scoped_to_meeting(login):
    c = login('staff')
    assert c.get('/meetings/1/audio/recordings/meeting_2_20260101_000000.webm').status_code == 404
