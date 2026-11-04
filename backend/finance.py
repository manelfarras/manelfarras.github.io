"""Read-only financial summaries. Amounts are integer cents, grouped by currency."""
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP


def summary(transactions, start, end):
    totals = defaultdict(lambda: {"income": 0, "expenses": 0, "net": 0, "count": 0})
    for item in transactions:
        if not start <= item["date"] <= end or item.get("excluded", False):
            continue
        row = totals[item["currency"]]
        amount = item["amount_cents"]
        row["income"] += max(amount, 0)
        row["expenses"] += max(-amount, 0)
        row["net"] += amount
        row["count"] += 1
    return dict(totals)


def forecast(transactions, today):
    """Average spending over the last three complete calendar months."""
    first = today.replace(day=1)
    index = first.year * 12 + first.month - 1 - 3
    start = date(index // 12, index % 12 + 1, 1)
    from datetime import timedelta
    totals = summary(transactions, start.isoformat(), (first - timedelta(days=1)).isoformat())
    return {currency: int((Decimal(row["expenses"]) / 3).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            for currency, row in totals.items()}
