import re

def sanitize_input(text_input, max_length=500):
    if not text_input:
        return text_input
    sanitized = re.sub(r'<[^>]*>', '', str(text_input))
    sanitized = sanitized.strip()
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    return sanitized

def validate_email(email):
    if not email:
        return None
    email = email.strip().lower()
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return None
    return email

