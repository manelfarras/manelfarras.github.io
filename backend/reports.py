"""Private, offline reports from an already loaded local dashboard snapshot."""
import argparse
import csv
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

REPOSITORY = Path(__file__).resolve().parent.parent


def folded(text):
    text = unicodedata.normalize('NFKD', str(text))
    return ' '.join(''.join(char for char in text if not unicodedata.combining(char)).upper().split())


def concept(row):
    description = ' '.join(str(row['description']).split())
    normalized = folded(description)
    contract = re.search(r'\(([^()]*)\)\s*$', description)
    if normalized.startswith('CUOTA PRESTAMO:') and contract:
        title = 'Préstamo hipotecario' if 'HIPOTECARIO' in normalized else 'Préstamo personal'
        # Contract identifies the group internally; report titles never expose it.
        return ('loan', contract.group(1)), title
    return ('description', normalized), description


def find_recurring(transactions):
    """Describe historical patterns; never infer a guaranteed future obligation."""
    groups = defaultdict(list)
    for row in transactions:
        if not row['amount_cents'] or row.get('excluded'):
            continue
        identity, title = concept(row)
        key = (row.get('account', 'Cuenta'), row['currency'], row['amount_cents'] < 0, identity)
        groups[key].append((row, title))
    result = []
    for (account, currency, debit, _), entries in groups.items():
        rows = [row for row, _ in entries]
        months = sorted({row['date'][:7] for row in rows})
        if len(months) < 3:
            continue
        counts = Counter(row['date'][:7] for row in rows)
        month_numbers = [int(month[:4]) * 12 + int(month[5:]) for month in months]
        gaps = [later - earlier for earlier, later in zip(month_numbers, month_numbers[1:])]
        days = sorted({date.fromisoformat(row['date']).day for row in rows})
        circular_gaps = [b - a for a, b in zip(days, days[1:])] + [days[0] + 31 - days[-1]]
        day_spread = 31 - max(circular_gaps)
        categories = folded(' '.join(str(row.get('category', '')) for row in rows))
        title = entries[0][1]
        text = folded(title) + ' ' + categories
        if any(word in text for word in ('END OF MONTH CREDIT CARD', 'LIQUIDACION TARJETA')):
            pattern = 'Liquidación de tarjeta'
            note = 'Pago de tarjeta repetido; su importe no representa una cuota fija.'
        elif any(word in text for word in ('TRASPAS', 'RECARGA', 'RECARREGA', 'CANAL DIGITAL', 'TRANSFERENCIA', 'TRANSFER ')):
            pattern = 'Movimiento de fondos repetido'
            note = 'Confirmar origen y destino; no se considera gasto fijo ni ingreso recurrente.'
        elif max(counts.values()) >= 3 or len(rows) > len(months) * 1.5:
            direct_debit = any(word in text for word in ('DOMICILI', 'PAIN008', 'CUOTA PRESTAMO'))
            pattern = 'Recibos repetidos' if direct_debit else 'Compras habituales'
            note = 'Varios apuntes al mes; la repetición no confirma una obligación periódica.'
        elif all(gap == 3 for gap in gaps) and day_spread <= 10:
            pattern = 'Trimestral probable'
            note = 'Al menos tres meses observados separados por tres meses; importe potencialmente variable.'
        elif any(a == b == 1 for a, b in zip(gaps, gaps[1:])) and day_spread <= 10:
            pattern = 'Mensual probable'
            note = 'Al menos tres meses consecutivos y fechas próximas; revisar meses sin apuntes.'
        else:
            pattern = 'Repetición irregular'
            note = 'Se repite en varios meses, sin periodicidad mensual o trimestral suficientemente clara.'
        monthly = {month: sum(abs(row['amount_cents']) for row in rows if row['date'].startswith(month)) for month in months}
        amounts = [abs(row['amount_cents']) for row in rows]
        result.append({'title': title, 'account': account, 'currency': currency,
                       'side': 'Cargo' if debit else 'Abono', 'pattern': pattern, 'note': note,
                       'count': len(rows), 'months_count': len(months), 'monthly_cents': monthly,
                       'total_cents': sum(amounts), 'min_cents': min(amounts), 'max_cents': max(amounts)})
    return sorted(result, key=lambda row: (-row['months_count'], row['title'], row['account'], row['currency'], row['side']))


def validate_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme not in ('http', 'https') or parsed.hostname not in ('127.0.0.1', 'localhost', '::1')
            or parsed.username is not None or parsed.password is not None or parsed.fragment or parsed.query
            or parsed.path != '/api/dashboard'):
        raise ValueError('Solo se admite el endpoint /api/dashboard de un servidor local loopback.')
    try:
        parsed.port
    except ValueError:
        raise ValueError('Puerto local no válido.') from None
    return url


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_snapshot(url):
    validate_url(url)
    # Local loopback traffic needs no outbound proxy or authentication.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(url, timeout=20) as response:
        return json.load(response)


def validate_output(output):
    directory = Path(output).expanduser().resolve()
    if directory == REPOSITORY or REPOSITORY in directory.parents:
        raise ValueError('Guarda los informes privados fuera del checkout del repositorio.')
    return directory


def render_html(snapshot, recurring):
    safe_rows = [{key: row.get(key, '') for key in ('date', 'account', 'description', 'category', 'currency', 'amount_cents')}
                 for row in snapshot['transactions']]
    payload = json.dumps({'start': snapshot.get('start', ''), 'end': snapshot.get('today', ''),
                          'monthly': snapshot['monthly'], 'transactions': safe_rows, 'recurring': recurring}, ensure_ascii=True)
    payload = payload.replace('<', '\\u003c')
    return '''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Detalle financiero privado</title><style>body{font:15px system-ui;margin:0;background:#f4f6f8;color:#17313f}main{max-width:1250px;margin:auto;padding:24px}section{background:white;border:1px solid #dce3e8;border-radius:12px;padding:20px;margin:20px 0}h1{font-size:30px}h2{font-size:21px}p{line-height:1.6}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:right;border-bottom:1px solid #e5e9ed;white-space:nowrap}td:first-child,th:first-child{text-align:left}#records td:nth-child(3){white-space:normal;text-align:left;min-width:230px}select{padding:9px;font:inherit}</style>
<main><h1>Detalle mensual y patrones recurrentes</h1><p id="period"></p><p>Informe privado generado desde el historial ya cargado. Importes brutos por fecha de operación: incluyen traspasos, financiación y anulaciones. No equivalen a consumo ni ahorro. El último mes puede estar incompleto.</p>
<section><h2>Resumen mensual</h2><div class="scroll"><table><thead><tr><th>Mes</th><th>Divisa</th><th>Abonos</th><th>Cargos</th><th>Flujo neto</th><th>Movimientos</th></tr></thead><tbody id="totals"></tbody></table></div></section>
<section><h2>Patrones históricos</h2><p>Son candidatos, no pagos futuros confirmados. Cada fila separa cuenta, divisa y cargos/abonos. Los importes son magnitudes positivas; un guion significa que no consta apunte, no que haya terminado un contrato.</p><div class="scroll"><table><thead><tr id="recurring-head"></tr></thead><tbody id="recurring"></tbody></table></div><div id="notes"></div></section>
<section><h2>Movimientos del mes</h2><label>Mes: <select id="month"></select></label><p id="count"></p><div class="scroll"><table><thead><tr><th>Fecha</th><th>Cuenta</th><th>Concepto</th><th>Tipo</th><th>Importe</th></tr></thead><tbody id="records"></tbody></table></div></section></main>
<script type="application/json" id="data">PAYLOAD</script><script>
const data=JSON.parse(document.querySelector('#data').textContent),money=(v,c)=>new Intl.NumberFormat('es-ES',{style:'currency',currency:c}).format(v/100);
function addRow(target,values){const tr=document.createElement('tr');for(const value of values){const td=document.createElement('td');td.textContent=value;tr.append(td)}target.append(tr)}
document.querySelector('#period').textContent='Periodo: '+data.start+' a '+data.end;
for(const m of data.monthly){for(const [c,r] of Object.entries(m.totals)){addRow(document.querySelector('#totals'),[m.month,c,money(r.income,c),money(r.expenses,c),money(r.net,c),r.count])}const option=document.createElement('option');option.value=m.month;option.textContent=m.month;document.querySelector('#month').append(option)}
for(const title of ['Concepto','Cuenta','Sentido','Patrón',...data.monthly.map(m=>m.month),'Total']){const th=document.createElement('th');th.textContent=title;document.querySelector('#recurring-head').append(th)}
for(const r of data.recurring){addRow(document.querySelector('#recurring'),[r.title,r.account,r.side,r.pattern,...data.monthly.map(m=>r.monthly_cents[m.month]?money(r.monthly_cents[m.month],r.currency):'—'),money(r.total_cents,r.currency)]);const p=document.createElement('p');p.textContent=r.title+' · '+r.account+' · '+r.side+': '+r.note+' '+r.count+' apuntes en '+r.months_count+' meses.';document.querySelector('#notes').append(p)}
function filter(){const body=document.querySelector('#records');body.replaceChildren();const rows=data.transactions.filter(r=>r.date.startsWith(document.querySelector('#month').value));for(const r of rows){addRow(body,[r.date,r.account,r.description,r.category,money(r.amount_cents,r.currency)])}document.querySelector('#count').textContent=rows.length+' movimientos en el mes.'}document.querySelector('#month').addEventListener('change',filter);filter();
</script></html>'''.replace('PAYLOAD', payload)


def csv_text(value):
    value = str(value)
    return "'" + value if value.startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else value


def write_reports(snapshot, output):
    directory = validate_output(output)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    recurring = find_recurring(snapshot['transactions'])
    html_path, csv_path = directory / 'detalle-mensual.html', directory / 'movimientos-recurrentes.csv'
    if html_path.exists() or csv_path.exists():
        raise FileExistsError('Los informes ya existen; elige otro directorio para conservarlos.')
    # Exclusive creation protects existing user files; private file permissions are explicit.
    with os.fdopen(os.open(html_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as file:
        file.write(render_html(snapshot, recurring))
    with os.fdopen(os.open(csv_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8', newline='') as file:
        writer = csv.writer(file)
        months = [month['month'] for month in snapshot['monthly']]
        writer.writerow(['Concepto', 'Cuenta', 'Divisa', 'Sentido', 'Patron', *months, 'Total', 'Apuntes', 'Observaciones'])
        for row in recurring:
            writer.writerow([*[csv_text(row[key]) for key in ('title', 'account', 'currency', 'side', 'pattern')],
                             *[f"{row['monthly_cents'].get(month, 0)/100:.2f}" for month in months],
                             f"{row['total_cents']/100:.2f}", row['count'], csv_text(row['note'])])
    return html_path, csv_path


def main():
    parser = argparse.ArgumentParser(description='Genera informes privados desde el panel local, sin consultar el banco.')
    parser.add_argument('--url', default='http://127.0.0.1:8004/api/dashboard')
    parser.add_argument('--output', required=True, help='Directorio nuevo de resultados fuera del repositorio')
    args = parser.parse_args()
    try:
        validate_output(args.output)
        paths = write_reports(read_snapshot(args.url), args.output)
    except Exception:
        raise SystemExit('No se pudieron generar los informes. Comprueba servidor local, formato y directorio de salida fuera del repositorio; no se sobrescriben informes existentes.') from None
    print('Informes privados generados: ' + ', '.join(str(path) for path in paths))


if __name__ == '__main__':
    main()
