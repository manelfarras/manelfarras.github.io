# Mi balance

Prototipo local de panel financiero para las APIs de Crèdit Andorrà. Por defecto utiliza datos ficticios. El modo de lectura bancaria consulta el mes actual; no envía correos.

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
