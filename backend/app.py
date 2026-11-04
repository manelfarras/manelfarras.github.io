"""Local dashboard server. Demo by default; opt-in read-only bank snapshot."""
import json
import os
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from backend.finance import summary, forecast

ROOT = Path(__file__).resolve().parent.parent
LIVE_DATA = None


def demo_transactions():
    today = date.today()
    result = []
    for offset in range(12):
        index = today.year * 12 + today.month - 1 - offset
        year, month = index // 12, index % 12 + 1
        for day, description, amount, category in [(1, "Nómina", 260000, "Ingresos"), (3, "Alquiler", -85000, "Vivienda"), (5, "Supermercado", -24500-offset*300, "Alimentación"), (8, "Suministros", -13500, "Hogar")]:
            when = date(year, month, day)
            if when <= today:
                result.append({"id": f"demo-{year}-{month}-{day}", "date": when.isoformat(), "description": description, "amount_cents": amount, "currency": "EUR", "category": category})
    return sorted(result, key=lambda item: item["date"], reverse=True)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/dashboard":
            today = date.today()
            items = demo_transactions()
            data = {"mode": "demo", "today": today.isoformat(), "year": today.year,
                    "annual": summary(items, f"{today.year}-01-01", today.isoformat()),
                    "forecast": forecast(items, today), "transactions": items,
                    "notifications": {"channel": "email", "enabled": False}}
            if LIVE_DATA is not None:
                data = LIVE_DATA
            body, mime = json.dumps(data).encode(), "application/json"
        elif self.path in ("/", "/index.html"):
            body, mime = (ROOT / "index.html").read_bytes(), "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    if os.environ.get('BANK_MODE') == 'live':
        from backend.bank import monthly_snapshot
        try:
            LIVE_DATA = monthly_snapshot()
            LIVE_DATA['annual'] = summary(LIVE_DATA['transactions'], LIVE_DATA['start'], LIVE_DATA['today'])
        except Exception:
            raise SystemExit('No se ha podido cargar el banco. No se mostrarán datos ficticios como reales.') from None
        print('Consulta bancaria cargada en memoria; correo desactivado.', flush=True)
    else:
        print('Modo demostración; correo desactivado.', flush=True)
    ThreadingHTTPServer(("127.0.0.1", int(os.environ.get('PORT', '8001'))), Handler).serve_forever()
