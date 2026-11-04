import io
import json
import unittest
from datetime import date
from unittest.mock import patch

from backend.bank import snapshot


class MonthlyRequestsTests(unittest.TestCase):
    def test_year_is_requested_month_by_month_and_overlap_is_counted_once(self):
        calls = []
        row = {'transactionId': 'example', 'tradeDate': '2026-01-31', 'valueDate': '2026-02-02',
               'amount': '-10.50', 'curry': 'EUR'}

        class Opener:
            def open(self, request, timeout):
                if request.full_url.endswith('/oauth2/token'):
                    return io.StringIO(json.dumps({'access_token': 'test-token'}))
                body = json.loads(request.data)
                calls.append(body)
                # Same bank posting appears in two adjacent query results.
                rows = [row] if body['dateFrom'] in ('2026-01-01', '2026-02-01') else []
                return io.StringIO(json.dumps({'accountList': [{'accountId': 'test-account', 'transactionList': rows}]}))

        variables = dict.fromkeys(['BANK_CLIENT_ID', 'BANK_CLIENT_SECRET', 'BANK_USERNAME', 'BANK_PASSWORD'], 'test')
        with patch('backend.bank.build_opener', return_value=Opener()), patch.dict('os.environ', variables):
            data = snapshot('year', today=date(2026, 11, 5))
        self.assertEqual(len(calls), 11)
        self.assertEqual(calls[0], {'dateFrom': '2026-01-01', 'dateTo': '2026-01-31', 'accounts': []})
        self.assertEqual(calls[-1]['dateTo'], '2026-11-05')
        self.assertTrue(all(c['dateFrom'][:7] == c['dateTo'][:7] for c in calls))
        self.assertEqual(data['duplicates'], 1)
        self.assertEqual(data['annual']['EUR']['expenses'], 1050)
        self.assertEqual(data['monthly'][0]['totals']['EUR']['count'], 1)
        self.assertEqual(data['monthly'][1]['totals'], {})
