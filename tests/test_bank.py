import unittest
from decimal import Decimal
from backend.bank import normalize


class BankTests(unittest.TestCase):
    def test_signed_amount_and_masked_account(self):
        rows, count = normalize({'accountList': [{'accountId': 'private-iban', 'transactionList': [
            {'tradeDate': '2026-11-03', 'amount': Decimal('-12.34'), 'curry': 'EUR', 'description': '<script>example</script>'}
        ]}]})
        self.assertEqual(count, 1)
        self.assertEqual(rows[0]['amount_cents'], -1234)
        self.assertEqual(rows[0]['account'], 'Cuenta 1')
        self.assertNotIn('private-iban', str(rows))

    def test_invalid_amount_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize({'accountList': [{'transactionList': [{'amount': 'NaN'}]}]})
