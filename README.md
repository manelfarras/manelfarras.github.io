# Mi balance

Prototipo local de panel financiero para las APIs de Crèdit Andorrà. Por defecto utiliza datos ficticios. El modo de lectura bancaria permite consultar el mes actual o el acumulado anual mediante peticiones mensuales; no envía correos.

## Ejecutar

Python 3.12 o posterior, sin dependencias adicionales:

```sh
cd /workspace/manelfarras.github.io
python3 -m backend.app
```

El servidor escucha únicamente en la interfaz local, puerto 8001. Comprobaciones:

```sh
python3 -m unittest discover -s tests -v
```

El panel incluye balance anual, movimientos y una previsión orientativa basada en tres meses completos. Los importes se calculan en céntimos y las monedas se muestran separadas. La exclusión de transferencias propias requiere clasificación; no se infiere automáticamente.

## Integración pendiente

- OAuth y Transactions v3 de producción se han validado con una consulta de lectura. Queda confirmar límites, historial y política de consultas.
- Configurar las credenciales bancarias exclusivamente en un almacén de secretos del backend. Nunca incluirlas en HTML, Git, correos o registros. No introducir valores en el chat.
- Configurar Gmail como remitente y destinatario de forma privada. Los secretos HTTPS de Codex no autentican SMTP directamente; requiere Gmail API o un alojamiento compatible con SMTP.
- Implementar sincronización persistente con identificadores de cuenta/movimiento, primera carga sin avisos históricos, reintentos y cola de correo sin duplicados.
- Implementar resúmenes del día, mes y año anteriores y su planificación con zona horaria Europe/Madrid a las 08:00.
- Confirmar cobertura histórica antes de generar previsiones; distinguir meses sin datos de meses sin gastos.
- Antes de alojarlo fuera del entorno local: autenticación, HTTPS y almacenamiento protegido. GitHub Pages solo sirve archivos estáticos; el backend necesita alojamiento independiente y ejecución programada.

Los avisos inmediatos dependen de eventos del banco, que no se describen en los PDF. La alternativa es consultar periódicamente con la frecuencia autorizada por el banco.

## Consulta real del mes

Con los secretos BANK_CLIENT_ID, BANK_CLIENT_SECRET, BANK_USERNAME y BANK_PASSWORD configurados mediante el proxy HTTPS de Codex:

```sh
BANK_MODE=live PORT=8002 python3 -m backend.app
```

Realiza una única consulta al iniciar y mantiene el resultado en memoria. Para actualizar, reinicia el proceso. No almacena tokens ni movimientos en disco. No muestra IBAN completos. Un fallo bancario impide arrancar el modo real, sin sustituirlo por datos ficticios. El servicio escucha solo en la interfaz local y no tiene autenticación para acceso externo: no exponerlo públicamente. La captura del panel puede contener datos financieros; no incluirla en Git. Las previsiones quedan desactivadas con historial limitado al mes actual.


## Acumulado anual mediante consultas mensuales

```sh
BANK_MODE=live BANK_PERIOD=year PORT=8004 python3 -m backend.app
```

Consulta secuencialmente cada mes del año actual, desde el 1 de enero hasta hoy (Europe/Madrid). Nunca solicita todo el año en una sola petición: cada intervalo está dentro de un mes natural. El mes actual se limita al día de ejecución. Utiliza una única autenticación mientras se realiza la carga. Si falla cualquier mes, el panel real no arranca con un acumulado parcial.

El desglose se calcula por `tradeDate` después de unir las respuestas, porque el banco puede devolver en un mes apuntes con fecha de operación del mes anterior. Se conservan por separado la fecha de operación y la fecha valor. La cobertura exacta de los límites del año depende del criterio de fechas y del historial que entregue el banco.

Las etiquetas de cuentas se mantienen estables entre respuestas sin exponer IBAN. La deduplicación usa internamente cuenta, identificador, indicador de reverso y signo: el banco puede reutilizar el identificador para un cargo y su abono/anulación. No se deduplican pagos por coincidencia de concepto o importe. Un conflicto entre apuntes de la misma identidad detiene el cálculo para evitar un resultado ambiguo.

Los totales son **abonos y cargos brutos**, separados por divisa. Incluyen financiación, transferencias propias e inversiones sin clasificar; el flujo neto no equivale a ahorro ni rentabilidad. El acumulado del año en curso es parcial, no una proyección de cierre. No se publican resultados privados en GitHub.

## Informes privados y movimientos recurrentes

Con el servidor anual anterior en ejecución, genera un informe a partir de los datos que ya mantiene en memoria, sin nuevas peticiones al banco:

```sh
python3 -m backend.reports \
  --url http://127.0.0.1:8004/api/dashboard \
  --output /workspace/artifacts
```

Se genera un HTML descargable con detalle mensual y un CSV con patrones recurrentes. Los archivos contienen información financiera privada: se escriben fuera del checkout y no se incluyen en este repositorio. Solo el código que permite regenerarlos se guarda en GitHub. Las credenciales deben seguir en el almacén de secretos del backend.

La detección agrupa movimientos por cuenta, divisa, sentido y concepto; las cuotas de préstamos mantienen una identidad interna estable cuando cambia el interés. Distingue patrones mensuales, trimestrales, compras habituales y movimientos de fondos. Las recurrencias son indicios históricos, no confirmaciones de contratos activos ni garantías de pagos futuros. El mes actual es parcial y la ausencia de un cargo no acredita su cancelación.
