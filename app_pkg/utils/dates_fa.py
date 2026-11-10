from datetime import datetime, date

def to_farsi_digits(value):
    s = str(value)
    map_digits = {
        '0': '۰', '1': '۱', '2': '۲', '3': '۳', '4': '۴',
        '5': '۵', '6': '۶', '7': '۷', '8': '۸', '9': '۹'
    }
    return ''.join(map_digits.get(ch, ch) for ch in s)

def from_farsi_digits(value: str) -> str:
    if not value:
        return ''
    mapping = {'۰':'0','۱':'1','۲':'2','۳':'3','۴':'4','۵':'5','۶':'6','۷':'7','۸':'8','۹':'9'}
    return ''.join(mapping.get(ch, ch) for ch in value)

def gregorian_to_jalali(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy - 1600
    gm2 = gm - 1
    gd2 = gd - 1
    g_day_no = 365 * gy2 + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
    g_day_no += g_d_m[gm2] + gd2
    if gm > 2 and ((gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0)):
        g_day_no += 1
    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no = j_day_no % 12053
    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += (j_day_no - 366) // 365 + 1
        j_day_no = (j_day_no - 366) % 365
    if j_day_no < 186:
        jm = 1 + j_day_no // 31
        jd = 1 + j_day_no % 31
    else:
        jm = 7 + (j_day_no - 186) // 30
        jd = 1 + (j_day_no - 186) % 30
    return jy, jm, jd

def jalali_to_gregorian(jy, jm, jd):
    jy -= 979
    j_day_no = 365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4
    j_day_no += (jd - 1)
    if jm <= 6:
        j_day_no += (jm - 1) * 31
    else:
        j_day_no += (jm - 7) * 30 + 186
    g_day_no = j_day_no + 79
    gy = 1600 + 400 * (g_day_no // 146097)
    g_day_no %= 146097
    leap = True
    if g_day_no >= 36525:
        g_day_no -= 1
        gy += 100 * (g_day_no // 36524)
        g_day_no %= 36524
        if g_day_no >= 365:
            g_day_no += 1
        else:
            leap = False
    gy += 4 * (g_day_no // 1461)
    g_day_no %= 1461
    if g_day_no >= 366:
        leap = False
        g_day_no -= 1
        gy += g_day_no // 365
        g_day_no %= 365
    gd = g_day_no + 1
    months = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 12 and gd > months[gm]:
        gd -= months[gm]
        gm += 1
    gm += 1
    return gy, gm, gd

def _parse_date_obj(obj):
    if isinstance(obj, (datetime, date)):
        return obj
    if isinstance(obj, str) and obj.strip():
        s = obj.strip()
        try:
            return datetime.fromisoformat(s.replace(' ', 'T'))
        except Exception:
            pass
        try:
            return datetime.strptime(s.split('.')[0], '%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
        try:
            return datetime.strptime(s.split('T')[0], '%Y-%m-%d')
        except Exception:
            pass
    return None

def weekday_name_fa(dt):
    dt = _parse_date_obj(dt)
    if not dt:
        return ''
    names = ['دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه', 'شنبه', 'یکشنبه']
    return names[dt.weekday()]

def format_jalali_datetime(dt):
    dt = _parse_date_obj(dt)
    if not dt:
        return '-'
    jy, jm, jd = gregorian_to_jalali(dt.year, dt.month, dt.day)
    jalali_months_fa = {
        1: 'فروردین', 2: 'اردیبهشت', 3: 'خرداد', 4: 'تیر', 5: 'مرداد', 6: 'شهریور',
        7: 'مهر', 8: 'آبان', 9: 'آذر', 10: 'دی', 11: 'بهمن', 12: 'اسفند'
    }
    wd = weekday_name_fa(dt)
    hm = dt.strftime('%H:%M') if isinstance(dt, datetime) else '۰۰:۰۰'
    return f"{to_farsi_digits(jy)} {jalali_months_fa.get(jm, jm)} {to_farsi_digits(jd)}, {wd} - {to_farsi_digits(hm)}"

def format_jalali_date_any(obj):
    obj = _parse_date_obj(obj)
    if not obj:
        return '-'
    gy, gm, gd = obj.year, obj.month, obj.day
    jy, jm, jd = gregorian_to_jalali(gy, gm, gd)
    jalali_months_fa = {
        1: 'فروردین', 2: 'اردیبهشت', 3: 'خرداد', 4: 'تیر', 5: 'مرداد', 6: 'شهریور',
        7: 'مهر', 8: 'آبان', 9: 'آذر', 10: 'دی', 11: 'بهمن', 12: 'اسفند'
    }
    return f"{to_farsi_digits(jd)} {jalali_months_fa.get(jm, jm)} {to_farsi_digits(jy)}"

def format_jalali_dmy(obj):
    obj = _parse_date_obj(obj)
    if not obj:
        return '-'
    gy, gm, gd = obj.year, obj.month, obj.day
    jy, jm, jd = gregorian_to_jalali(gy, gm, gd)
    jalali_months_fa = {
        1: 'فروردین', 2: 'اردیبهشت', 3: 'خرداد', 4: 'تیر', 5: 'مرداد', 6: 'شهریور',
        7: 'مهر', 8: 'آبان', 9: 'آذر', 10: 'دی', 11: 'بهمن', 12: 'اسفند'
    }
    return f"{to_farsi_digits(jd)} {jalali_months_fa.get(jm, jm)} {to_farsi_digits(jy)}"

def format_jalali_weekday_dm(obj):
    obj = _parse_date_obj(obj)
    if not obj:
        return '-'
    gy, gm, gd = obj.year, obj.month, obj.day
    wd = weekday_name_fa(datetime(gy, gm, gd))
    jy, jm, jd = gregorian_to_jalali(gy, gm, gd)
    jalali_months_fa = {
        1: 'فروردین', 2: 'اردیبهشت', 3: 'خرداد', 4: 'تیر', 5: 'مرداد', 6: 'شهریور',
        7: 'مهر', 8: 'آبان', 9: 'آذر', 10: 'دی', 11: 'بهمن', 12: 'اسفند'
    }
    return f"{wd} {to_farsi_digits(jd)} {jalali_months_fa.get(jm, jm)}"

def format_jalali_ymd(obj):
    obj = _parse_date_obj(obj)
    if not obj:
        return ''
    gy, gm, gd = obj.year, obj.month, obj.day
    jy, jm, jd = gregorian_to_jalali(gy, gm, gd)
    jm_str = to_farsi_digits(jm).rjust(2, '۰')
    jd_str = to_farsi_digits(jd).rjust(2, '۰')
    return f"{to_farsi_digits(jy)}-{jm_str}-{jd_str}"

