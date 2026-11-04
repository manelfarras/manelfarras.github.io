import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.reports import REPOSITORY, find_recurring, read_snapshot, render_html, validate_output, validate_url, write_reports


def row(month, description='Servicio de ejemplo', amount=-1250, **kwargs):
    return {'date': f'2026-{month:02d}-05', 'description': description, 'amount_cents': amount,
            'currency': 'EUR', 'account': 'Cuenta 1', 'category': 'Pago domiciliado', **kwargs}


class RecurrenceTests(unittest.TestCase):
    def test_variable_loan_descriptions_share_contract_without_disclosing_it(self):
        rows = [row(m, f'Cuota préstamo: Préstamo personal EUR, {m}.15%, 01.01.2020-01.01.2030 (fictional-contract)', -10000 - m)
                for m in (1, 2, 3)]
        result = find_recurring(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['pattern'], 'Mensual probable')
        self.assertEqual(result[0]['total_cents'], 30006)
        self.assertNotIn('fictional-contract', json.dumps(result))

    def test_frequent_purchases_are_not_labelled_monthly_obligations(self):
        rows = [row(m, 'Comercio de ejemplo', category='POS Payment', date=f'2026-{m:02d}-{day:02d}')
                for m in (1, 2, 3) for day in (2, 9, 25)]
        self.assertEqual(find_recurring(rows)[0]['pattern'], 'Compras habituales')

    def test_accounts_currencies_and_sides_remain_separate(self):
        rows = [row(m, amount=amount, currency=currency, account=account)
                for m in (1, 2, 3) for account, currency, amount in
                [('Cuenta 1', 'EUR', -100), ('Cuenta 1', 'USD', -100), ('Cuenta 1', 'EUR', 100), ('Cuenta 2', 'EUR', -100)]]
        self.assertEqual(len(find_recurring(rows)), 4)

    def test_transfer_is_not_a_recurring_income_or_expense(self):
        result = find_recurring([row(m, 'Canal digital', category='Traspaso') for m in (1, 2, 3)])
        self.assertEqual(result[0]['pattern'], 'Movimiento de fondos repetido')

    def test_quarterly_pattern_and_insufficient_history(self):
        self.assertEqual(find_recurring([row(m) for m in (1, 4, 7)])[0]['pattern'], 'Trimestral probable')
        self.assertEqual(find_recurring([row(m) for m in (1, 2)]), [])


class PrivateReportTests(unittest.TestCase):
    def test_local_endpoint_only_and_no_credentials_or_redirects(self):
        for host in ('127.0.0.1', 'localhost', '[::1]'):
            validate_url(f'http://{host}:8004/api/dashboard')
        for url in ('https://example.com/api/dashboard', 'http://127.0.0.2/api/dashboard',
                    'http://user:password@localhost/api/dashboard', 'file:///api/dashboard',
                    'http://127.0.0.1/api/dashboard?next=external'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url)
        with patch('backend.reports.build_opener') as opener:
            with self.assertRaises(ValueError):
                read_snapshot('https://example.com/api/dashboard')
            opener.assert_not_called()

    def test_output_rejects_checkout_and_symlink_into_it(self):
        with self.assertRaises(ValueError):
            validate_output(REPOSITORY / 'private-artifacts')
        with tempfile.TemporaryDirectory() as directory:
            link = Path(directory) / 'checkout'
            link.symlink_to(REPOSITORY, target_is_directory=True)
            with self.assertRaises(ValueError):
                validate_output(link / 'private-artifacts')

    def test_html_embeds_data_safely_and_omits_unexpected_fields(self):
        snapshot = {'monthly': [], 'transactions': [row(1, '</script><script>alert(1)</script>', access_token='test-sensitive-field')]}
        document = render_html(snapshot, [])
        self.assertNotIn('</script><script>alert', document)
        self.assertIn('\\u003c/script>', document)
        self.assertNotIn('test-sensitive-field', document)
        payload = re.search(r'id="data">(.*?)</script>', document).group(1)
        self.assertEqual(json.loads(payload)['transactions'][0]['description'], '</script><script>alert(1)</script>')
        self.assertNotIn('innerHTML', document)

    def test_reports_stay_private_and_preserve_existing_outputs(self):
        snapshot = {'monthly': [{'month': '2026-01', 'totals': {}}], 'transactions': [row(m, '=formula-example') for m in (1, 2, 3)]}
        with tempfile.TemporaryDirectory() as directory:
            html_path, csv_path = write_reports(snapshot, directory)
            self.assertEqual(html_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(csv_path.stat().st_mode & 0o777, 0o600)
            self.assertIn("'=formula-example", csv_path.read_text())
            with self.assertRaises(FileExistsError):
                write_reports(snapshot, directory)
