"""HTTP receipt-age diagnostics for future US protocols; never a fill guarantee.

RFC 9111 section 4.2.3: https://www.rfc-editor.org/rfc/rfc9111.html#section-4.2.3
This does not change the frozen paper experiment or previous probe results.
"""
import math
import re
from email.utils import parsedate_to_datetime


def response_age(receipt, asof):
    received = float(receipt['received_at'])
    asof = float(asof)
    delay = float(receipt['round_trip_seconds'])
    if not all(math.isfinite(x) for x in [received,asof,delay]) or delay<0 or asof<received:
        raise ValueError('Invalid receipt clock or transport duration')
    headers = {k.lower():v for k,v in receipt.get('public_cache_headers',{}).items()}
    try:
        date = parsedate_to_datetime(headers['date'])
        if date.tzinfo is None:
            raise ValueError('HTTP Date has no timezone')
        date_value = date.timestamp()
    except (KeyError,TypeError,OverflowError,ValueError) as exc:
        raise ValueError('Missing or invalid HTTP Date') from exc
    if date_value > received+5:
        raise ValueError('HTTP Date exceeds allowed future clock skew')
    explicit = 'age' in headers
    value = str(headers.get('age','0')).split(',')[0].strip()
    if not re.fullmatch(r'[0-9]+',value):
        raise ValueError('Invalid explicit Age; future research policy fails closed')
    age = min(int(value),2147483648)
    apparent = max(0.,received-date_value)
    corrected = max(apparent,age+delay)
    resident = asof-received
    return dict(current_age_seconds=corrected+resident, apparent_age_seconds=apparent,
                corrected_initial_age_seconds=corrected, resident_seconds=resident,
                transport_seconds=delay, explicit_age=explicit, age_header_seconds=age,
                note='Estimated HTTP response age. Missing Age uses RFC zero fallback and remains explicitly marked; this does not establish exchange book generation time, availability or a fill.')
