import csv
from datetime import datetime

def load_events_from_csv(csv_path):
    events = []
    def parse_dt(s):
        if not s:
            return None
        s = s.strip().replace('Z', '+00:00')
        try:
            return datetime.fromisoformat(s)
        except Exception:
            pass
        fmts = [
            '%Y-%m-%dT%H:%M%z', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%d %H:%M%z', '%Y-%m-%d %H:%M:%S%z',
            '%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S',
            '%Y/%m/%d %H:%M', '%Y/%m/%d %H:%M:%S', '%Y/%m/%dT%H:%M', '%Y/%m/%dT%H:%M:%S',
            '%Y-%m-%d'
        ]
        for fmt in fmts:
            try:
                return datetime.strptime(s, fmt)
            except Exception:
                continue
        return None
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                start = parse_dt((row.get('Start') or ''))
                end = parse_dt((row.get('End') or ''))
                if not start or not end:
                    continue
                events.append({
                    'title': (row.get('Title') or '').strip(),
                    'start': start,
                    'end': end,
                    'location': (row.get('Location') or '').strip(),
                    'meet_link': (row.get('MeetLink') or '').strip(),
                    'attendees': (row.get('Attendees') or '').strip(),
                    'responsible': (row.get('Responsible') or row.get('Owner') or row.get('Manager') or row.get('Host') or '').strip(),
                    'status': (row.get('Status') or row.get('MeetingStatus') or '').strip(),
                    'catering': (row.get('Catering') or row.get('Hospitality') or '').strip(),
                    'calendar_link': (row.get('CalendarLink') or '').strip(),
                    'day': start.date()
                })
    except FileNotFoundError:
        pass
    return events

