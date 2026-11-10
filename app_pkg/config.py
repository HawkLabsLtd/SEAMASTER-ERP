import os
import secrets


def load_secret_key(instance_dir):
    """SECRET_KEY from the environment, else a random key persisted in instance/.secret_key.

    Never falls back to a hardcoded value, so sessions can't be forged with a known key.
    """
    key = (os.getenv('SECRET_KEY') or '').strip()
    if key:
        return key
    path = os.path.join(instance_dir, '.secret_key')
    try:
        with open(path, encoding='utf-8') as f:
            key = f.read().strip()
    except FileNotFoundError:
        key = ''
    if not key:
        key = secrets.token_hex(32)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(key)
    return key


class Config:
    DEBUG = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    # Branding shown in the UI and the AI assistant prompt (override in .env)
    ORG_NAME = os.getenv('ORG_NAME', 'سازمان نمونه')
    APP_TITLE = os.getenv('APP_TITLE', 'سامانه داشبورد مدیریتی')

    @staticmethod
    def get_db_uri(base_dir):
        url = os.getenv('DATABASE_URL')
        default_db = 'sqlite:///' + os.path.join(base_dir, 'instance', 'seamaster.db').replace('\\', '/')
        if not url:
            return default_db
        if url.startswith('sqlite:///'):
            path_part = url[10:]
            # Check if already absolute path (e.g. C:/... or D:/... or /...)
            if (len(path_part) > 1 and path_part[1] == ':') or path_part.startswith('/') or path_part.startswith('\\'):
                return url
            if path_part.startswith('instance/') or path_part.startswith('instance\\'):
                path_part = path_part[9:]
            return 'sqlite:///' + os.path.join(base_dir, 'instance', path_part).replace('\\', '/')
        return url

    @staticmethod
    def init_app(app):
        pass

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': ProductionConfig
}
