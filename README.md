# deber4_apis_is

API Flask que clasifica tráfico de red y expone datos para un dashboard de Power BI.
**Toda la base de datos se usa mediante procedimientos almacenados** (sin SQL directo en la API).

## Puesta en marcha

1. En SSMS ejecutar, en orden:
   - `sql/01_crear_bd.sql` (base `TraficoIA` y tabla)
   - `sql/03_procedimientos.sql` (procedimientos almacenados)
2. Copiar `.env.example` a `.env` y poner `DB_ENABLED=true` y los datos de conexión.
3. `pip install -r requirements.txt`, `python entrenar.py`, `python api.py`.
4. Power BI: **Obtener datos > Web** → `http://127.0.0.1:5000/api/dashboard/registros`.

Dashboard sencillo paso a paso: [docs/dashboard_simple.md](docs/dashboard_simple.md).

Detalle de endpoints, SP, parámetros y configuración de Power BI:
[docs/auditoria/integracion_powerbi.md](docs/auditoria/integracion_powerbi.md).

Pruebas: `python -m unittest discover -s tests -v`
