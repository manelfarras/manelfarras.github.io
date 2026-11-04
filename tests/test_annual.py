import unittest
from datetime import date, timedelta
from decimal import Decimal

from backend.bank import month_ranges, normalize


def transaction(identifier, *, when="2026-01-31", amount="-12.34"):
    return {
        "transactionId": identifier,
        "tradeDate": when,
        "valueDate": "2026-02-02",
        "amount": Decimal(amount),
        "curry": "EUR",
        "description": "Compra de ejemplo",
        "category": "Compras",
    }


def account(identifier, rows):
    return {"accountId": identifier, "transactionList": rows}


class AnnualPeriodTests(unittest.TestCase):
    def test_completed_leap_year_has_twelve_calendar_requests(self):
        ranges = month_ranges(2024, date(2026, 11, 5))
        self.assertEqual(len(ranges), 12)
        self.assertEqual(ranges[0], (date(2024, 1, 1), date(2024, 1, 31)))
        self.assertEqual(ranges[1], (date(2024, 2, 1), date(2024, 2, 29)))
        self.assertEqual(ranges[-1], (date(2024, 12, 1), date(2024, 12, 31)))
        for previous, current in zip(ranges, ranges[1:]):
            self.assertEqual(previous[1] + timedelta(days=1), current[0])

    def test_current_year_stops_at_today_and_never_queries_future_days(self):
        today = date(2026, 11, 5)
        ranges = month_ranges(today.year, today)
        self.assertEqual(len(ranges), 11)
        self.assertEqual(ranges[-1], (date(2026, 11, 1), today))
        self.assertTrue(all(start <= end <= today for start, end in ranges))
        self.assertTrue(all(start.month == end.month for start, end in ranges))

    def test_first_day_of_year_has_only_one_day_to_query(self):
        self.assertEqual(month_ranges(2026, date(2026, 1, 1)), [(date(2026, 1, 1), date(2026, 1, 1))])


class AnnualDeduplicationTests(unittest.TestCase):
    def test_month_overlap_is_deduplicated_with_stable_account_labels(self):
        labels, seen = {}, {}
        first, _ = normalize({"accountList": [
            account("iban-a", [transaction("a-1")]),
            account("iban-b", [transaction("b-1")]),
        ]}, account_labels=labels, seen=seen)
        second, _ = normalize({"accountList": [
            account("iban-b", [transaction("b-2", when="2026-02-03")]),
            account("iban-a", [transaction("a-1"), transaction("a-2", when="2026-02-04")]),
        ]}, account_labels=labels, seen=seen)
        self.assertEqual(len(first), 2)
        self.assertEqual(len(second), 2)
        self.assertEqual(len(seen), 4)
        by_date = {row["date"]: row["account"] for row in second}
        self.assertEqual(by_date["2026-02-03"], "Cuenta 2")
        self.assertEqual(by_date["2026-02-04"], "Cuenta 1")
        self.assertNotIn("iban-", str(first + second))

    def test_same_transaction_id_on_different_accounts_is_not_a_duplicate(self):
        rows, _ = normalize({"accountList": [
            account("iban-a", [transaction("shared-id")]),
            account("iban-b", [transaction("shared-id")]),
        ]}, account_labels={}, seen={})
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["account"] for row in rows}, {"Cuenta 1", "Cuenta 2"})

    def test_identical_legitimate_payments_with_different_ids_are_retained(self):
        rows, _ = normalize({"accountList": [account("iban-a", [transaction("one"), transaction("two")])]},
                            account_labels={}, seen={})
        self.assertEqual(len(rows), 2)

    def test_original_and_reversal_are_retained_and_repeated_response_is_deduplicated(self):
        original = transaction("reversed-entry", amount="-5.52")
        original["isRevs"] = False
        reversal = transaction("reversed-entry", amount="5.52")
        reversal["isRevs"] = True
        response = {"accountList": [account("iban-a", [original, reversal])]}
        labels, seen = {}, {}
        rows, _ = normalize(response, account_labels=labels, seen=seen)
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["amount_cents"] for row in rows}, {-552, 552})
        self.assertEqual(sum(row["amount_cents"] for row in rows), 0)
        self.assertEqual(len({row["reversal"] for row in rows}), 2)
        repeated, _ = normalize(response, account_labels=labels, seen=seen)
        self.assertEqual(repeated, [])
        self.assertEqual(len(seen), 2)

    def test_debit_credit_pair_with_same_id_and_flag_is_retained_and_deduplicated(self):
        debit = transaction("paired-entry", amount="-362.51")
        credit = transaction("paired-entry", amount="362.51")
        debit["isRevs"] = credit["isRevs"] = False
        response = {"accountList": [account("iban-a", [debit, credit])]}
        labels, seen = {}, {}
        rows, _ = normalize(response, account_labels=labels, seen=seen)
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["amount_cents"] for row in rows}, {-36251, 36251})
        self.assertEqual(sum(row["amount_cents"] for row in rows), 0)
        self.assertEqual(len({row["reversal"] for row in rows}), 1)
        repeated, _ = normalize(response, account_labels=labels, seen=seen)
        self.assertEqual(repeated, [])
        self.assertEqual(len(seen), 2)

    def test_trade_date_is_preserved_even_when_value_date_is_next_month(self):
        rows, _ = normalize({"accountList": [account("iban-a", [transaction("one")])]},
                            account_labels={}, seen={})
        self.assertEqual(rows[0]["date"], "2026-01-31")

    def test_conflicting_duplicate_is_rejected_instead_of_silently_counted(self):
        labels, seen = {}, {}
        normalize({"accountList": [account("iban-a", [transaction("one")])]}, account_labels=labels, seen=seen)
        with self.assertRaises(ValueError):
            normalize({"accountList": [account("iban-a", [transaction("one", amount="-99.99")])]},
                      account_labels=labels, seen=seen)

    def test_missing_identity_is_rejected_when_deduplication_is_enabled(self):
        row = transaction("one")
        del row["transactionId"]
        with self.assertRaises(ValueError):
            normalize({"accountList": [account("iban-a", [row])]}, account_labels={}, seen={})
        with self.assertRaises(ValueError):
            normalize({"accountList": [{"transactionList": [transaction("one")]}]}, account_labels={}, seen={})
