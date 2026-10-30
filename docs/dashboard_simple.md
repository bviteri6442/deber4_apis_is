# Dashboard sencillo en Power BI

Una sola página, una sola consulta a la API. Los datos vienen de
`dbo.PrediccionesTrafico` a través de `dbo.sp_Dashboard_Registros`.

## 0. Antes de empezar

1. En SSMS ejecutar `sql/03_procedimientos.sql` sobre `TraficoIA`.
   Comprobar con `EXEC dbo.sp_Dashboard_Registros;` (debe salir la tabla).
2. Arrancar la API: `python api.py`.
3. Abrir en el navegador `http://127.0.0.1:5000/api/dashboard/registros`:
   debe verse una lista JSON con los registros.

## 1. Cargar los datos

1. Power BI > **Obtener datos > Web** > URL:
   `http://127.0.0.1:5000/api/dashboard/registros` > Aceptar.
2. En Power Query: **A la tabla** > Aceptar > expandir la columna (botón de las
   flechas, desmarcar "Usar el nombre de la columna original como prefijo").
3. Tipos: `fecha_prediccion` = Fecha y hora, `probabilidad` y `duracion` =
   Número decimal, el resto de números = Número entero.
4. Renombrar la consulta a `Registros` > **Cerrar y aplicar**.

## 2. Medidas (3)

Inicio > Nueva medida:

```dax
Total conexiones = COUNTROWS(Registros)
Total sospechosas = CALCULATE(COUNTROWS(Registros), Registros[clasificacion] = "Sospechoso")
% sospechosas = DIVIDE([Total sospechosas], [Total conexiones])
```

Poner `% sospechosas` en formato Porcentaje.

## 3. Visuales (una página)

| # | Visual | Campos |
|---|---|---|
| 1 | Tarjeta | `Total conexiones` |
| 2 | Tarjeta | `Total sospechosas` |
| 3 | Tarjeta | `% sospechosas` |
| 4 | Gráfico de anillo | Leyenda: `clasificacion` · Valores: `Total conexiones` |
| 5 | Barras agrupadas | Eje: `protocolo` · Leyenda: `clasificacion` · Valores: `Total conexiones` |
| 6 | Columnas agrupadas | Eje: `puerto` · Leyenda: `clasificacion` · Valores: `Total conexiones` |
| 7 | Tabla | `fecha_prediccion`, `puerto`, `protocolo`, `intentos_fallidos`, `probabilidad`, `clasificacion` |

Segmentaciones (filtran todo):

- `protocolo` (lista)
- `clasificacion` (lista)

Distribución sugerida: arriba las 3 tarjetas y las 2 segmentaciones; en el
medio el anillo y las barras de protocolo; abajo puertos y la tabla.

## 4. Actualizar

Cuando la API guarde predicciones nuevas: **Inicio > Actualizar**.

## 5. Usar parámetros (Power BI → API → SP)

Sin parámetros la URL llama a `sp_Dashboard_Registros` con todo en `NULL`
(trae todo) y el filtrado lo hacen las segmentaciones dentro de Power BI.
Para que el filtro llegue al procedimiento almacenado:

1. **Transformar datos > Administrar parámetros > Nuevo**. Crear 4 parámetros
   de tipo **Texto**, con **Requerido desmarcado** (vacío = sin filtro):

   | Nombre | Valores sugeridos | Valor actual de ejemplo |
   |---|---|---|
   | `pProtocolo` | Lista: `TCP`, `UDP`, `ICMP` | `TCP` |
   | `pClasificacion` | Lista: `Normal`, `Sospechoso` | (vacío) |
   | `pFechaDesde` | Cualquier valor (`YYYY-MM-DD`) | (vacío) |
   | `pFechaHasta` | Cualquier valor (`YYYY-MM-DD`) | (vacío) |

2. Seleccionar la consulta `Registros` > **Editor avanzado** y cambiar **solo**
   la línea `Origen` por:

   ```
   Origen = Json.Document(Web.Contents("http://127.0.0.1:5000",
       [RelativePath = "api/dashboard/registros",
        Query = [protocolo = pProtocolo, clasificacion = pClasificacion,
                 fecha_desde = pFechaDesde, fecha_hasta = pFechaHasta]])),
   ```

3. **Cerrar y aplicar**. Para cambiar el filtro: **Inicio > Transformar datos >
   Editar parámetros** > Aceptar > **Aplicar cambios**.

Recorrido del valor: parámetro `pProtocolo = TCP` → URL `?protocolo=TCP` →
API → `EXEC dbo.sp_Dashboard_Registros @Protocolo = 'TCP'`.

Si un filtro no tiene datos, la API devuelve `[]` y el paso de expandir
columnas da error: dejar el parámetro vacío o elegir otro valor.

## 6. Comprobar que se usan los SP

En SSMS, después de actualizar Power BI:

```sql
USE TraficoIA;
SELECT OBJECT_NAME(object_id) AS procedimiento, execution_count, last_execution_time
FROM sys.dm_exec_procedure_stats
WHERE database_id = DB_ID();
```

Debe aparecer `sp_Dashboard_Registros` con `last_execution_time` de ese momento.
