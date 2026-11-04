"""Read-only snapshots, always fetched in monthly intervals."""
import calendar
import json
import os
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlencode


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def normalize(data, *, account_labels=None, seen=None):
    if account_labels is None:
        account_labels = {}
    accounts = data['accountList']
    if not isinstance(accounts, list):
        raise ValueError('Formato de cuentas inesperado')
    items = []
    for index, account in enumerate(accounts, 1):
        account_id = str(account.get('accountId') or '')
        if seen is not None and not account_id:
            raise ValueError('Identificador de cuenta ausente')
        label = account_labels.setdefault(account_id or f'row-{index}', f'Cuenta {len(account_labels) + 1}')
        for row in account.get('transactionList', []):
            amount = Decimal(str(row['amount']))
            if not amount.is_finite():
                raise ValueError('Importe no válido')
            when = str(row['tradeDate'])[:10]
            datetime.strptime(when, '%Y-%m-%d')
            currency = row['curry']
            if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha():
                raise ValueError('Divisa no válida')
            category = row.get('category') or row.get('transactionType') or 'Sin clasificar'
            if isinstance(category, dict):
                category = category.get('transactionNameType') or category.get('name') or 'Sin clasificar'
            value_date = str(row.get('valueDate') or '')[:10]
            if value_date:
                datetime.strptime(value_date, '%Y-%m-%d')
            reversal = str(row.get('isRevs', ''))
            item = {'date': when, 'value_date': value_date, 'reversal': reversal,
                          'description': str(row.get('description') or 'Sin concepto'),
                          'category': str(category),
                          'account': label, 'currency': currency.upper(),
                          'amount_cents': int((amount * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))}
            if seen is not None:
                transaction_id = str(row.get('transactionId') or '')
                if not transaction_id:
                    raise ValueError('Identificador de movimiento ausente')
                # The bank reuses transactionId for the original and its reversal.
                # Some paired debit/credit entries also share the reversal flag.
                key = (account_id, transaction_id, reversal, amount < 0)
                if key in seen:
                    if seen[key] != item:
                        raise ValueError('Movimiento duplicado con datos incompatibles')
                    continue
                seen[key] = item
            items.append(item)
    return sorted(items, key=lambda item: item['date'], reverse=True), len(accounts)


def month_ranges(year, today):
    if year < 1900 or year > today.year:
        raise ValueError('Año fuera del periodo disponible')
    result = []
    for month in range(1, 13):
        start = date(year, month, 1)
        if start > today:
            break
        end = min(date(year, month, calendar.monthrange(year, month)[1]), today)
        result.append((start, end))
    return result


def snapshot(period='month', year=None, today=None, progress=None):
    if period not in ('month', 'year'):
        raise ValueError('Periodo no válido')
    now = datetime.now(ZoneInfo('Europe/Madrid'))
    today = today or now.date()
    year = today.year if year is None else year
    ranges = month_ranges(year, today)
    if period == 'month':
        ranges = [(today.replace(day=1), today)]
    opener = build_opener(NoRedirect())
    base = 'https://apis.creditandorragroup.com/credit-andorra/ehbp'

    def post(path, body, headers):
        with opener.open(Request(base + path, data=body, headers=headers, method='POST'), timeout=45) as response:
            return json.load(response, parse_float=Decimal)

    token = post('/v1/oauth2/token', urlencode({
        'grant_type': 'password', 'client_id': os.environ['BANK_CLIENT_ID'],
        'username': os.environ['BANK_USERNAME'], 'password': os.environ['BANK_PASSWORD'], 'scope': 'full',
    }).encode(), {'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'})
    headers = {
        'Content-Type': 'application/json', 'Accept': 'application/json', 'Accept-Language': 'es',
        'X-IBM-Client-Id': os.environ['BANK_CLIENT_ID'], 'X-IBM-Client-Secret': os.environ['BANK_CLIENT_SECRET'],
        'Authorization': 'Bearer ' + token['access_token'],
    }
    labels, seen, items, requests = {}, {}, [], []
    received = 0
    for month_start, month_end in ranges:
        start, end = month_start.isoformat(), month_end.isoformat()
        data = post('/v3/transactions', json.dumps({'dateFrom': start, 'dateTo': end, 'accounts': []}).encode(), headers)
        month_received = sum(len(account.get('transactionList', [])) for account in data['accountList'])
        batch, _ = normalize(data, account_labels=labels, seen=seen)
        received += month_received
        items.extend(batch)
        requests.append({'start': start, 'end': end, 'received': month_received, 'duplicates': month_received - len(batch)})
        if progress:
            progress(requests[-1])
    start, end = ranges[0][0].isoformat(), ranges[-1][1].isoformat()
    outside = sum(not start <= item['date'] <= end for item in items)
    items = [item for item in items if start <= item['date'] <= end]
    items.sort(key=lambda item: item['date'], reverse=True)
    from backend.finance import summary
    monthly = [{'month': a.strftime('%Y-%m'), 'start': a.isoformat(), 'end': b.isoformat(),
                'totals': summary(items, a.isoformat(), b.isoformat())} for a, b in ranges]
    return {'mode': 'live', 'today': end, 'start': start, 'updated_at': now.isoformat(timespec='seconds'),
            'period': period, 'requests': requests, 'received': received,
            'duplicates': received - len(seen), 'outside_period': outside,
            'accounts': len(labels), 'transactions': items, 'forecast': {}, 'monthly': monthly,
            'annual': summary(items, start, end),
            'notifications': {'channel': 'email', 'enabled': False}}


def monthly_snapshot():
    return snapshot('month')
