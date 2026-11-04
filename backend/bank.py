"""Read-only monthly snapshot; secrets and tokens never leave this process."""
import json
import os
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlencode


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def normalize(data):
    accounts = data['accountList']
    if not isinstance(accounts, list):
        raise ValueError('Formato de cuentas inesperado')
    items = []
    for index, account in enumerate(accounts, 1):
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
            items.append({'date': when, 'description': str(row.get('description') or 'Sin concepto'),
                          'category': str(category),
                          'account': f'Cuenta {index}', 'currency': currency.upper(),
                          'amount_cents': int((amount * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))})
    return sorted(items, key=lambda item: item['date'], reverse=True), len(accounts)


def monthly_snapshot():
    opener = build_opener(NoRedirect())
    base = 'https://apis.creditandorragroup.com/credit-andorra/ehbp'

    def post(path, body, headers):
        with opener.open(Request(base + path, data=body, headers=headers, method='POST'), timeout=45) as response:
            return json.load(response, parse_float=Decimal)

    token = post('/v1/oauth2/token', urlencode({
        'grant_type': 'password', 'client_id': os.environ['BANK_CLIENT_ID'],
        'username': os.environ['BANK_USERNAME'], 'password': os.environ['BANK_PASSWORD'], 'scope': 'full',
    }).encode(), {'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'})
    now = datetime.now(ZoneInfo('Europe/Madrid'))
    end, start = now.date().isoformat(), now.date().replace(day=1).isoformat()
    data = post('/v3/transactions', json.dumps({'dateFrom': start, 'dateTo': end, 'accounts': []}).encode(), {
        'Content-Type': 'application/json', 'Accept': 'application/json', 'Accept-Language': 'es',
        'X-IBM-Client-Id': os.environ['BANK_CLIENT_ID'], 'X-IBM-Client-Secret': os.environ['BANK_CLIENT_SECRET'],
        'Authorization': 'Bearer ' + token['access_token'],
    })
    items, count = normalize(data)
    received = len(items)
    items = [item for item in items if start <= item['date'] <= end]
    return {'mode': 'live', 'today': end, 'start': start, 'updated_at': now.isoformat(timespec='seconds'),
            'outside_period': received - len(items),
            'accounts': count, 'transactions': items, 'forecast': {},
            'notifications': {'channel': 'email', 'enabled': False}}
