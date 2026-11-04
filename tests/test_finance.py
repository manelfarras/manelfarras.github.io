import unittest
from datetime import date
from backend.finance import summary, forecast


class FinanceTests(unittest.TestCase):
    def test_currency_period_and_internal_transfers(self):
        rows = [{"date": "2026-01-01", "currency": "EUR", "amount_cents": 10000},
                {"date": "2026-02-01", "currency": "EUR", "amount_cents": -3000},
                {"date": "2026-02-01", "currency": "USD", "amount_cents": -500},
                {"date": "2026-02-01", "currency": "EUR", "amount_cents": -9000, "excluded": True},
                {"date": "2025-12-31", "currency": "EUR", "amount_cents": -1000}]
        result = summary(rows, "2026-01-01", "2026-12-31")
        self.assertEqual(result["EUR"], {"income": 10000, "expenses": 3000, "net": 7000, "count": 2})
        self.assertEqual(result["USD"]["expenses"], 500)

    def test_forecast_crosses_year_and_excludes_current_month(self):
        rows = [{"date": day, "currency": "EUR", "amount_cents": amount} for day, amount in
                [("2025-10-01", -90000), ("2025-11-01", -30000), ("2025-12-01", -60000), ("2026-01-01", -999999)]]
        self.assertEqual(forecast(rows, date(2026, 1, 5)), {"EUR": 60000})


if __name__ == "__main__":
    unittest.main()
