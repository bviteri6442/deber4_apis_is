# Integración de la API con Power BI: dashboard con filtros globales

> Written for: el equipo del taller que conecta la API con Power BI.

## 0. Procedimientos almacenados (requisito del taller)

La API **no ejecuta SQL directo** sobre `dbo.PrediccionesTrafico`. Cada endpoint
llama a un procedimiento almacenado de `sql/03_procedimientos.sql` y le pasa los
filtros como parámetros. Flujo:

```
Power BI  --HTTP-->  API Flask  --EXEC dbo.sp_...-->  SQL Server  -->  dbo.PrediccionesTrafico
```

| Endpoint / uso | Procedimiento almacenado |
|---|---|
| `POST /api/trafico/predecir`, `POST /api/trafico/lote` (guardar) | `dbo.sp_InsertarPrediccion` |
| `GET /api/dashboard/registros` | `dbo.sp_Dashboard_Registros` |
| `GET /api/dashboard/resumen` | `dbo.sp_Dashboard_Resumen` |
| `GET /api/dashboard/por-clasificacion` | `dbo.sp_Dashboard_PorClasificacion` |
| `GET /api/dashboard/por-protocolo` | `dbo.sp_Dashboard_PorProtocolo` |
| `GET /api/dashboard/por-puerto` | `dbo.sp_Dashboard_PorPuerto` |
| `GET /api/dashboard/distribucion-probabilidad` | `dbo.sp_Dashboard_DistribucionProbabilidad` |
| `GET /api/dashboard/intentos-fallidos` | `dbo.sp_Dashboard_IntentosFallidos` |
| (validación interna) | `dbo.sp_ValidarFiltros` |

Parámetros comunes de los SP del dashboard (todos opcionales, `NULL` = sin filtro):

| Parámetro SP | Tipo | Parámetro URL |
|---|---|---|
| `@FechaDesde` | `DATE` | `fecha_desde` |
| `@FechaHasta` | `DATE` (incluye el día completo) | `fecha_hasta` |
| `@Protocolo` | `VARCHAR(10)` | `protocolo` |
| `@Puerto` | `INT` | `puerto` |
| `@Clasificacion` | `VARCHAR(15)` | `clasificacion` |

Extras: `@Limite` en `sp_Dashboard_Registros` y `@Top` en `sp_Dashboard_PorPuerto`.

La sentencia que envía la API tiene siempre esta forma (los valores van en `?`):

```sql
EXEC dbo.sp_Dashboard_Resumen @FechaDesde = ?, @FechaHasta = ?, @Protocolo = ?, @Puerto = ?, @Clasificacion = ?
```

Instalación: en SSMS ejecutar `sql/01_crear_bd.sql` y luego
`sql/03_procedimientos.sql`. Los SP aparecen en
**TraficoIA > Programación > Procedimientos almacenados**.

## 1. Resumen de la decisión

**Arquitectura elegida: Alternativa A (tabla de registros común).**

Power BI importa una sola vez `GET /api/dashboard/registros` y las segmentaciones
(fecha, protocolo, puerto) filtran esa tabla de forma nativa. Las tarjetas, los
gráficos y la tabla de detalle comparten el mismo contexto de filtros porque
todos leen de la misma tabla importada.

Motivos:

- Power BI **no** envía los valores de una segmentación a una consulta web
  independiente. Con la Alternativa B, cada cambio de filtro exigiría parámetros
  de Power Query y una actualización manual, y cada visual podría quedar con
  un conjunto distinto si una URL se olvida de un parámetro.
- El volumen del proyecto es moderado (tabla de predicciones de un taller).
- Un único endpoint de detalle evita mantener seis consultas de agregación
  sincronizadas solo para el dashboard.

La Alternativa B **sigue disponible**: los endpoints agregados (`resumen`,
`por-clasificacion`, etc.) aceptan los mismos filtros y usan la misma función
`construir_filtros`. No hay una segunda implementación de los filtros.

## 2. Qué cambió

Archivos modificados:

| Archivo | Cambio |
|---|---|
| `api.py` | Bloque del dashboard: sin SQL directo. `ejecutar_sp` llama a `EXEC dbo.sp_...` con parámetros nombrados; `construir_filtros` valida y devuelve los parámetros (vacío → `NULL`). |
| `app/database.py` | `guardar` inserta con `EXEC dbo.sp_InsertarPrediccion` en lugar de `INSERT`. |
| `sql/03_procedimientos.sql` | Nuevo: los procedimientos almacenados. |
| `sql/02_consultas_powerbi.sql` | Ejemplos con `EXEC` de los SP. |
| `tests/test_api_dashboard.py` | 31 pruebas unitarias con mocks (comprueban que no hay `SELECT` en la API). |
| `docs/auditoria/integracion_powerbi.md` | Nuevo: este documento. |

Sin cambios: contrato de los endpoints (mismas URL, filtros y respuestas),
`/api/trafico/probar`, `/api/health`, esquema de la tabla y datos.

## 3. Verificación de la base de datos

Comprobado en `sql/01_crear_bd.sql` y en la captura del diseñador de SQL Server:

| Columna | Tipo | Uso en la API |
|---|---|---|
| `id_prediccion` | BIGINT IDENTITY, PK | Orden estable y clave de la fila |
| `fecha_prediccion` | DATETIME2(0), DEFAULT `SYSUTCDATETIME()` | Filtro de fechas (en **UTC**) |
| `duracion` | FLOAT | Métrica |
| `paquetes` | BIGINT | Métrica |
| `bytes` | BIGINT | Métrica |
| `puerto` | INT | Filtro |
| `protocolo` | VARCHAR(10) | Filtro |
| `intentos_fallidos` | INT | Métrica |
| `probabilidad` | FLOAT, `BETWEEN 0 AND 1` | Métrica |
| `clasificacion` | VARCHAR(15), `IN ('Normal','Sospechoso')` | Filtro |

Valores válidos según `app/comun.py`: protocolos `TCP`, `UDP`, `ICMP`; puertos
0–65535. La API **no** rechaza un protocolo distinto: si no existe en la tabla,
la respuesta es una lista vacía.

Existe el índice `IX_Predicciones_Fecha`. Los filtros de fecha usan
comparaciones por rango sobre la columna sin funciones y los SP llevan
`OPTION (RECOMPILE)`, para que el índice pueda usarse cuando llega una fecha.

## 4. Filtros comunes

Todos son opcionales. Un valor vacío no aplica condición.

| Parámetro | Formato | Validación |
|---|---|---|
| `fecha_desde` | `YYYY-MM-DD` | Formato, o 400 |
| `fecha_hasta` | `YYYY-MM-DD` | Formato, o 400. Incluye el día completo |
| `protocolo` | texto | Se pasa a mayúsculas. Valor inexistente → lista vacía |
| `puerto` | entero 0–65535 | No numérico o fuera de rango → 400 |
| `clasificacion` | `Normal` o `Sospechoso` | Texto libre; inexistente → lista vacía |

Reglas:

- `fecha_desde` posterior a `fecha_hasta` → 400.
- Los valores se envían como parámetros `?` de pyodbc al `EXEC` del SP. Nunca se concatenan al SQL.
- La API valida antes de llamar al SP (responde 400 sin tocar la base); el SP
  vuelve a validar con `dbo.sp_ValidarFiltros` por si se ejecuta desde SSMS.
- Fecha final inclusiva: la condición es `fecha_prediccion < (fecha_hasta + 1 día)`.

## 5. Endpoints

Todos devuelven JSON (lista de registros) y aceptan los filtros de la sección 4.

| Endpoint | Parámetros extra | Uso |
|---|---|---|
| `GET /api/dashboard/registros` | `limite` (entero > 0, opcional), `formato=csv` (opcional) | **Tabla fuente para Power BI** |
| `GET /api/dashboard/resumen` | — | KPIs (una fila) |
| `GET /api/dashboard/por-clasificacion` | — | Conteo por clasificación |
| `GET /api/dashboard/por-protocolo` | — | Protocolo × clasificación |
| `GET /api/dashboard/por-puerto` | `top` (1–100, por defecto 10) | Puerto × clasificación |
| `GET /api/dashboard/distribucion-probabilidad` | — | Histograma en tramos de 10 % |
| `GET /api/dashboard/intentos-fallidos` | — | Intentos × clasificación |
| `GET /api/health` | — | Estado (sin cambios) |

### Campos de `registros`

```
id_prediccion, fecha_prediccion, duracion, paquetes, bytes, puerto,
protocolo, intentos_fallidos, probabilidad, clasificacion
```

Orden: `fecha_prediccion DESC, id_prediccion DESC`.

`fecha_prediccion` se devuelve como ISO 8601 sin zona horaria (por ejemplo
`2026-10-26T10:30:00`) y corresponde a **UTC**.

### Ejemplos de solicitud

```
GET http://127.0.0.1:5000/api/dashboard/registros
GET http://127.0.0.1:5000/api/dashboard/registros?fecha_desde=2026-10-01&fecha_hasta=2026-10-26&protocolo=TCP&puerto=443
GET http://127.0.0.1:5000/api/dashboard/resumen?fecha_desde=2026-10-01&fecha_hasta=2026-10-26&protocolo=TCP&puerto=443
GET http://127.0.0.1:5000/api/dashboard/registros?formato=csv
```

### Forma de las respuestas

Éxito: lista JSON. `resumen` devuelve una lista de una fila. Ejemplo de forma
(los valores son ilustrativos, no resultados reales):

```json
[{"id_prediccion": 12, "fecha_prediccion": "2026-10-26T10:30:00",
  "duracion": 1.5, "paquetes": 10, "bytes": 500, "puerto": 443,
  "protocolo": "TCP", "intentos_fallidos": 0, "probabilidad": 0.2,
  "clasificacion": "Normal"}]
```

Errores:

| Código | Cuándo | Cuerpo |
|---|---|---|
| 400 | Fecha, puerto o `limite` inválidos | `{"error": "..."}` |
| 503 | `DB_ENABLED=false` | `{"error": "SQL Server deshabilitado..."}` |
| 500 | Error de SQL o de conexión | `{"error": "No se pudo consultar la base de datos"}` (sin detalles internos) |

Un conjunto vacío devuelve `[]`. Los agregados de `resumen` sobre un conjunto
vacío pueden devolver `null` en las sumas y promedios; el conteo devuelve `0`.

## 6. Conexión desde Power BI Desktop

1. Arrancar la API: `python api.py` (con `DB_ENABLED=true` en `.env`).
2. **Inicio > Obtener datos > Web**, URL:
   `http://127.0.0.1:5000/api/dashboard/registros`
   (sin parámetros: se importan todos los registros).
3. En Power Query, convertir la lista en tabla y ajustar tipos:

```
let
    Origen = Json.Document(Web.Contents("http://127.0.0.1:5000/api/dashboard/registros")),
    ComoTabla = Table.FromRecords(Origen),
    Tipos = Table.TransformColumnTypes(ComoTabla, {
        {"id_prediccion", Int64.Type},
        {"fecha_prediccion", type datetime},
        {"duracion", type number},
        {"paquetes", Int64.Type},
        {"bytes", Int64.Type},
        {"puerto", Int64.Type},
        {"protocolo", type text},
        {"intentos_fallidos", Int64.Type},
        {"probabilidad", type number},
        {"clasificacion", type text}
    }),
    ConFecha = Table.AddColumn(Tipos, "fecha", each DateTime.Date([fecha_prediccion]), type date)
in
    ConFecha
```

4. Renombrar la consulta a `Registros`. Si se usa el CSV (`?formato=csv`), la
   importación es **Obtener datos > Texto/CSV** con la misma URL, y hay que
   revisar los tipos igual que arriba.
5. Cerrar y aplicar.

### Opcional: parámetros de Power Query en la URL

Si el docente pide que el dashboard **reciba parámetros** (y no solo filtrar con
segmentaciones), crear en **Transformar datos > Administrar parámetros > Nuevo
parámetro** estos parámetros de tipo Texto (valor vacío = sin filtro):
`pFechaDesde`, `pFechaHasta`, `pProtocolo`, `pPuerto`.

Consulta `Registros` usando los parámetros (Power BI los envía a la API y la API
al SP):

```
let
    Filtros = [
        fecha_desde = pFechaDesde,
        fecha_hasta = pFechaHasta,
        protocolo   = pProtocolo,
        puerto      = pPuerto
    ],
    Origen = Json.Document(Web.Contents(
        "http://127.0.0.1:5000",
        [RelativePath = "api/dashboard/registros", Query = Filtros])),
    ComoTabla = Table.FromRecords(Origen),
    Tipos = Table.TransformColumnTypes(ComoTabla, {
        {"id_prediccion", Int64.Type}, {"fecha_prediccion", type datetime},
        {"duracion", type number}, {"paquetes", Int64.Type}, {"bytes", Int64.Type},
        {"puerto", Int64.Type}, {"protocolo", type text},
        {"intentos_fallidos", Int64.Type}, {"probabilidad", type number},
        {"clasificacion", type text}}),
    ConFecha = Table.AddColumn(Tipos, "fecha", each DateTime.Date([fecha_prediccion]), type date)
in
    ConFecha
```

Para cambiar los filtros: **Inicio > Transformar datos > Editar parámetros** y
**Actualizar**. El mismo patrón sirve para `resumen`, `por-protocolo`, etc.
(cambiando `RelativePath`). Si una consulta devuelve `[]`, `Table.FromRecords`
produce una tabla sin columnas: es normal cuando el filtro no tiene datos.

### Segmentaciones (en la tabla `Registros`)

| Segmentación | Campo | Tipo de segmentación |
|---|---|---|
| Rango de fechas | `Registros[fecha]` | Entre (dos fechas) |
| Protocolo | `Registros[protocolo]` | Lista desplegable |
| Puerto | `Registros[puerto]` | Lista desplegable (o cuadro de búsqueda) |

Todas las visuales se crean sobre `Registros`, así que las tres segmentaciones
afectan a todas por la relación de contexto de filtro, sin llamadas adicionales
a la API.

### Medidas DAX

```dax
Total conexiones = COUNTROWS(Registros)

Total sospechosas = CALCULATE(COUNTROWS(Registros), Registros[clasificacion] = "Sospechoso")

% sospechosas = DIVIDE([Total sospechosas], [Total conexiones])

Probabilidad promedio = AVERAGE(Registros[probabilidad])

Duración promedio = AVERAGE(Registros[duracion])

Paquetes promedio = AVERAGE(Registros[paquetes])

Total bytes = SUM(Registros[bytes])

Total intentos fallidos = SUM(Registros[intentos_fallidos])
```

Las tarjetas KPI usan estas medidas. `Total sospechosas` cuenta
`Sospechoso`, igual que la restricción de la tabla.

### Configuración de visuales

| Visual | Eje / Categoría | Leyenda | Valores |
|---|---|---|---|
| Tarjetas KPI | — | — | `[Total conexiones]`, `[Total sospechosas]`, `[Probabilidad promedio]`, `[Total bytes]`, `[Total intentos fallidos]` |
| Distribución por clasificación (circular) | `clasificacion` | — | `[Total conexiones]` |
| Conexiones por protocolo y clasificación (barras apiladas) | `protocolo` | `clasificacion` | `[Total conexiones]` |
| Conexiones por puerto | `puerto` | `clasificacion` | `[Total conexiones]` |
| Distribución de probabilidades (histograma) | Columna `probabilidad` agrupada en intervalos de 0,1 | `clasificacion` | `[Total conexiones]` |
| Intentos fallidos vs. clasificación | `intentos_fallidos` | `clasificacion` | `[Total conexiones]` |
| Tabla de detalle | — | — | `fecha_prediccion`, `puerto`, `protocolo`, `intentos_fallidos`, `probabilidad`, `clasificacion` |

Para el histograma, crear en Power Query una columna `tramo` con
`Number.Floor([probabilidad] * 10) / 10` (y tratar 1,0 como tramo 0,9–1,0).

## 7. Procedimiento para mantener los endpoints agregados (Alternativa B)

No es necesario para el dashboard. Si algún día se usan los endpoints agregados
desde Power BI:

- Power BI no envía las segmentaciones a una URL web. Hay que crear **Parámetros
  de Power Query** (`fecha_desde`, `fecha_hasta`, `protocolo`, `puerto`) y
  construir la URL con ellos en la consulta.
- Cada cambio de parámetro requiere **actualizar** la consulta; no es automático.
- Cada visual necesita su propia consulta, y todas deben usar los mismos
  parámetros. Eso es fácil de romper sin darse cuenta.

Por eso no se recomienda para este dashboard.

## 8. Limitaciones

- **Actualización manual o programada.** La tabla es una importación: al entrar
  predicciones nuevas hay que actualizar el conjunto de datos. Power BI no
  refresca solo.
- **Volumen.** `registros` sin `limite` devuelve **todos** los registros. Para
  volúmenes pequeños y medianos esto funciona bien. Si la tabla crece hasta cifras
  de cientos de miles o más, se puede usar el conector nativo de SQL Server con
  una instrucción `EXEC dbo.sp_Dashboard_Registros ...` (opciones avanzadas), sin
  leer la tabla directamente. Esto es una recomendación: no se ha medido un umbral.
- **`limite`.** Si se usa, la tabla importada queda truncada y las medidas DAX
  serán incorrectas. Por eso no se usa en el dashboard.
- **Zona horaria.** `fecha_prediccion` se guarda en UTC. Los filtros de fecha y la
  columna `fecha` son UTC. Si el taller necesita fechas locales, hay que convertir
  en Power Query antes de la segmentación.
- **`por-puerto` con `top`.** Limita a las N combinaciones (`puerto`,
  `clasificacion`) con más registros, no a los N puertos más usados. Se
  mantiene como estaba; si se necesita el top de puertos, habría que añadir una
  subconsulta.
- **Índices.** Se usa el índice existente `IX_Predicciones_Fecha`. No se ha
  revisado el plan de ejecución en SQL Server, así que no se proponen índices
  nuevos.
- **Red.** `127.0.0.1` solo funciona si Power BI corre en el mismo equipo que la
  API. Para otro equipo hay que usar la IP de la red y configurar la seguridad
  correspondiente.
- **Sin autenticación.** La API no tiene autenticación. No debe exponerse fuera de
  la red local.

## 9. Pruebas

### Ejecutadas

```
python -m unittest discover -s tests -v
```

Resultado: **31 pruebas, 31 correctas, 0 fallos.** Las pruebas usan un cursor y
una conexión simulados, y sustituyen el `Predictor` para no cargar TensorFlow.

Cubren:

- Cada endpoint ejecuta `EXEC dbo.sp_...` correcto y la sentencia no contiene
  `SELECT`, `FROM` ni `WHERE` (sin SQL directo).
- La inserción usa `EXEC dbo.sp_InsertarPrediccion` (sin `INSERT`).
- Sin filtros se envían `NULL`; filtros vacíos también.
- Fechas como `date`, protocolo en mayúsculas, puerto entero, combinación de todos.
- Mismo conjunto de filtros en los siete endpoints de dashboard; `top` acotado a 100.
- Protocolo inexistente → no es error; valor malicioso → viaja como parámetro.
- Fechas con formato inválido, fecha inicial posterior a la final, mismo día válido.
- Puerto fuera de rango y no numérico.
- `limite` sin valor (`@Limite = NULL`), con valor e inválido (400).
- Fechas en ISO 8601 y exportación CSV.
- Base de datos deshabilitada (503), error de SQL y de conexión (500 sin detalles).
- Resultados vacíos (`[]`).
- `resumen` y `registros` con los mismos parámetros de filtro.
- `/api/trafico/predecir` sigue guardando, `/api/trafico/probar` no guarda,
  `/api/health` sin cambios.

### Pendientes (no ejecutadas)

- **Integración con SQL Server real.** No se ha podido conectar en este entorno,
  así que los SP no se han ejecutado aquí. Hay que ejecutar
  `sql/03_procedimientos.sql` en SSMS y comprobar: que `fecha_prediccion` se rellena al insertar, que los
  filtros devuelven los mismos totales que una consulta manual en SSMS, y que
  `probabilidad` y las sumas de `resumen` coinciden.
- **Power BI real.** No se ha probado la importación ni las medidas DAX en
  Power BI Desktop.
- **Coherencia cruzada.** Comparar `resumen` contra el recuento de `registros`
  con los mismos filtros sobre datos reales.

Comandos sugeridos para cerrar lo pendiente:

```
curl "http://127.0.0.1:5000/api/dashboard/resumen?fecha_desde=2026-10-01&fecha_hasta=2026-10-26&protocolo=TCP&puerto=443"
curl "http://127.0.0.1:5000/api/dashboard/registros?fecha_desde=2026-10-01&fecha_hasta=2026-10-26&protocolo=TCP&puerto=443"
```

El `total_conexiones` del primero debe coincidir con el número de elementos del
segundo.

## 10. Instalación de dependencias para las pruebas

Las pruebas necesitan `flask` y `python-dotenv` (ya declaradas en
`requirements.txt`). No necesitan `tensorflow`, `pandas` ni `pyodbc`.
