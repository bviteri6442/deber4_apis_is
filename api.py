
# -*- coding: utf-8 -*-
"""API REST + predicciones + almacenamiento opcional."""

import csv
import io
import os
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, Response
from dotenv import load_dotenv
from app.predictor import Predictor
from app.database import guardar, habilitada, conexion

load_dotenv()

app = Flask(__name__)

# Cargar el modelo UNA sola vez
predictor = Predictor()


# -----------------------------------------
# 1. Verificar estado del sistema
# -----------------------------------------
@app.get("/api/health")
def health():
    return jsonify(
        estado="activo",
        modelo="cargado",
        sql_server=habilitada()
    )


# -----------------------------------------
# 2. Predecir una conexion y guardar en SQL
# -----------------------------------------
@app.post("/api/trafico/predecir")
def predecir():
    contenido = request.get_json(silent=True)

    if not isinstance(contenido, dict):
        return jsonify(
            error="Enviar objeto JSON con las caracteristicas"
        ), 400

    try:
        resultados = predictor.predecir([contenido])

        # Guardar en SQL Server si esta habilitado
        guardados = guardar(resultados)

        fila = resultados.iloc[0]

        return jsonify(
            clasificacion=str(fila["clasificacion"]),
            probabilidad=float(fila["probabilidad"]),
            guardados_sql=guardados
        )

    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    except Exception:
        app.logger.exception("Error interno")
        return jsonify(
            error="No se pudo procesar la solicitud"
        ), 500


# -----------------------------------------
# 3. Predecir varias conexiones y guardar
# -----------------------------------------
@app.post("/api/trafico/lote")
def lote():
    contenido = request.get_json(silent=True)

    if not isinstance(contenido, list) or not 1 <= len(contenido) <= 500:
        return jsonify(
            error="Enviar lista JSON de 1 a 500 conexiones"
        ), 400

    if not all(isinstance(item, dict) for item in contenido):
        return jsonify(
            error="Cada conexion debe ser un objeto JSON"
        ), 400

    try:
        resultados = predictor.predecir(contenido)

        guardados = guardar(resultados)

        return jsonify(
            total=len(resultados),
            guardados_sql=guardados,
            resultados=resultados.to_dict(orient="records")
        )

    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    except Exception:
        app.logger.exception("Error interno")
        return jsonify(
            error="No se pudo procesar el lote"
        ), 500


# -----------------------------------------
# 4. NUEVA API GET: probar desde navegador
#    NO GUARDA EN SQL SERVER
# -----------------------------------------
@app.get("/api/trafico/probar")
def probar():
    try:
        datos = {
            "duracion": request.args.get("duracion"),
            "paquetes": request.args.get("paquetes"),
            "bytes": request.args.get("bytes"),
            "puerto": request.args.get("puerto"),
            "protocolo": request.args.get("protocolo"),
            "intentos_fallidos": request.args.get("intentos_fallidos")
        }

        # Utilizar modelo ya entrenado
        resultados = predictor.predecir([datos])

        fila = resultados.iloc[0]

        # NO llamar a guardar()
        return jsonify(
            clasificacion=str(fila["clasificacion"]),
            probabilidad=float(fila["probabilidad"]),
            guardados_sql=0,
            mensaje="Prediccion de prueba, no almacenada"
        )

    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    except Exception:
        app.logger.exception("Error al probar conexion")
        return jsonify(
            error="No se pudo realizar la prediccion"
        ), 500


# =========================================
# APIs PARA DASHBOARD DE POWER BI
# Leen dbo.PrediccionesTrafico (SQL Server).
# Power BI: Obtener datos > Web > URL del endpoint.
# Todas devuelven una lista JSON de registros (tabla plana).
#
# Filtros comunes, todos opcionales (un valor vacio no aplica condicion):
#   fecha_desde, fecha_hasta (YYYY-MM-DD, fecha UTC), protocolo, puerto,
#   clasificacion. Se aplican con AND dentro de la misma consulta.
# =========================================
class FiltroInvalido(ValueError):
    """Parametro de filtro no valido: se responde con HTTP 400."""


def consultar(sql, params=()):
    """Ejecuta un SELECT parametrizado y devuelve lista de dicts."""
    if not habilitada():
        raise RuntimeError("SQL Server deshabilitado (DB_ENABLED=false)")
    cn = conexion()
    try:
        cursor = cn.cursor()
        cursor.execute(sql, params)
        columnas = [c[0] for c in cursor.description]
        filas = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
        cursor.close()
        # Fechas en ISO 8601 (jsonify las enviaria en formato HTTP-date)
        return [
            {c: v.isoformat() if isinstance(v, datetime) else v
             for c, v in fila.items()}
            for fila in filas
        ]
    finally:
        cn.close()


def dashboard(sql, params=()):
    """Envuelve una consulta del dashboard con manejo de errores comun."""
    try:
        return jsonify(consultar(sql, params))
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 503
    except Exception:
        app.logger.exception("Error en API de dashboard")
        return jsonify(error="No se pudo consultar la base de datos"), 500


def leer_fecha(texto, nombre):
    """Convierte YYYY-MM-DD a datetime a medianoche; None si viene vacia."""
    if not texto:
        return None
    try:
        return datetime.strptime(texto, "%Y-%m-%d")
    except ValueError:
        raise FiltroInvalido(f"{nombre} debe tener formato YYYY-MM-DD")


def construir_filtros(args):
    """Devuelve (clausula WHERE, parametros) a partir de los filtros de la URL.

    Los valores siempre viajan como parametros ?, nunca dentro del SQL.
    """
    desde = leer_fecha(args.get("fecha_desde", "").strip(), "fecha_desde")
    hasta = leer_fecha(args.get("fecha_hasta", "").strip(), "fecha_hasta")
    if desde and hasta and desde > hasta:
        raise FiltroInvalido("fecha_desde no puede ser posterior a fecha_hasta")

    condiciones = []
    params = []

    if desde:
        condiciones.append("fecha_prediccion >= ?")
        params.append(desde)

    # Rango abierto al final: incluye todo el dia de fecha_hasta
    if hasta:
        condiciones.append("fecha_prediccion < ?")
        params.append(hasta + timedelta(days=1))

    protocolo = args.get("protocolo", "").strip().upper()
    if protocolo:
        condiciones.append("protocolo = ?")
        params.append(protocolo)

    puerto = args.get("puerto", "").strip()
    if puerto:
        if not puerto.isdigit() or int(puerto) > 65535:
            raise FiltroInvalido("Puerto fuera de rango (0-65535)")
        condiciones.append("puerto = ?")
        params.append(int(puerto))

    clasificacion = args.get("clasificacion", "").strip()
    if clasificacion:
        condiciones.append("clasificacion = ?")
        params.append(clasificacion)

    if not condiciones:
        return "", ()
    return " WHERE " + " AND ".join(condiciones), tuple(params)


def dashboard_filtrado(plantilla):
    """Ejecuta una consulta del dashboard con los filtros de la URL.

    La plantilla debe contener {where} donde va la clausula de filtros.
    """
    try:
        where, params = construir_filtros(request.args)
    except FiltroInvalido as exc:
        return jsonify(error=str(exc)), 400
    return dashboard(plantilla.replace("{where}", where), params)


# 5. KPIs generales (una sola fila: tarjetas del dashboard)
@app.get("/api/dashboard/resumen")
def dash_resumen():
    return dashboard_filtrado("""
        SELECT COUNT(*) AS total_conexiones,
               SUM(CASE WHEN clasificacion <> 'Normal' THEN 1 ELSE 0 END) AS total_sospechosas,
               AVG(CAST(probabilidad AS FLOAT)) AS probabilidad_promedio,
               AVG(CAST(duracion AS FLOAT)) AS duracion_promedio,
               AVG(CAST(paquetes AS FLOAT)) AS paquetes_promedio,
               SUM(CAST(bytes AS BIGINT)) AS bytes_totales,
               SUM(intentos_fallidos) AS intentos_fallidos_totales
        FROM dbo.PrediccionesTrafico{where}""")


# 6. Conteo por clasificacion (grafico circular / barras)
@app.get("/api/dashboard/por-clasificacion")
def dash_clasificacion():
    return dashboard_filtrado("""
        SELECT clasificacion, COUNT(*) AS total,
               AVG(CAST(probabilidad AS FLOAT)) AS probabilidad_promedio
        FROM dbo.PrediccionesTrafico{where}
        GROUP BY clasificacion ORDER BY total DESC""")


# 7. Conteo por protocolo y clasificacion (barras apiladas)
@app.get("/api/dashboard/por-protocolo")
def dash_protocolo():
    return dashboard_filtrado("""
        SELECT protocolo, clasificacion, COUNT(*) AS total,
               AVG(CAST(bytes AS FLOAT)) AS bytes_promedio
        FROM dbo.PrediccionesTrafico{where}
        GROUP BY protocolo, clasificacion ORDER BY protocolo, total DESC""")


# 8. Puertos mas usados (?top=10)
@app.get("/api/dashboard/por-puerto")
def dash_puerto():
    top = request.args.get("top", default=10, type=int)
    top = max(1, min(top, 100))
    return dashboard_filtrado(f"""
        SELECT TOP ({top}) puerto, clasificacion, COUNT(*) AS total
        FROM dbo.PrediccionesTrafico{{where}}
        GROUP BY puerto, clasificacion ORDER BY total DESC""")


# 9. Distribucion de probabilidad en rangos de 10% (histograma)
@app.get("/api/dashboard/distribucion-probabilidad")
def dash_probabilidad():
    return dashboard_filtrado("""
        SELECT rango, clasificacion, COUNT(*) AS total
        FROM (SELECT clasificacion,
                     CASE WHEN probabilidad >= 1 THEN 9
                          ELSE FLOOR(probabilidad * 10) END AS bucket,
                     CONCAT(CASE WHEN probabilidad >= 1 THEN 90
                                 ELSE FLOOR(probabilidad * 10) * 10 END,
                            '-',
                            CASE WHEN probabilidad >= 1 THEN 100
                                 ELSE FLOOR(probabilidad * 10) * 10 + 10 END, '%') AS rango
              FROM dbo.PrediccionesTrafico{where}) t
        GROUP BY bucket, rango, clasificacion ORDER BY bucket""")


# 10. Intentos fallidos agrupados (dispersion / barras)
@app.get("/api/dashboard/intentos-fallidos")
def dash_intentos():
    return dashboard_filtrado("""
        SELECT intentos_fallidos, clasificacion, COUNT(*) AS total,
               AVG(CAST(probabilidad AS FLOAT)) AS probabilidad_promedio
        FROM dbo.PrediccionesTrafico{where}
        GROUP BY intentos_fallidos, clasificacion ORDER BY intentos_fallidos""")


# 11. Tabla detalle: fuente recomendada para Power BI (ver docs/auditoria)
#     ?limite=N opcional. Sin el devuelve TODOS los registros que cumplen
#     los filtros, para que los totales de Power BI no queden truncados.
#     ?formato=csv para importar como CSV en Power BI
@app.get("/api/dashboard/registros")
def dash_registros():
    limite = request.args.get("limite", "").strip()
    top = ""
    if limite:
        if not limite.isdigit() or int(limite) < 1:
            return jsonify(error="limite debe ser un entero positivo"), 400
        top = f"TOP ({int(limite)}) "

    try:
        where, params = construir_filtros(request.args)
    except FiltroInvalido as exc:
        return jsonify(error=str(exc)), 400

    sql = f"""SELECT {top}id_prediccion, fecha_prediccion, duracion, paquetes,
                     bytes, puerto, protocolo, intentos_fallidos,
                     probabilidad, clasificacion
              FROM dbo.PrediccionesTrafico{where}
              ORDER BY fecha_prediccion DESC, id_prediccion DESC"""

    if request.args.get("formato", "").lower() != "csv":
        return dashboard(sql, params)

    try:
        filas = consultar(sql, params)
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 503
    except Exception:
        app.logger.exception("Error en API de dashboard")
        return jsonify(
            error="No se pudo consultar la base de datos"
        ), 500

    columnas = [
        "id_prediccion",
        "fecha_prediccion",
        "duracion",
        "paquetes",
        "bytes",
        "puerto",
        "protocolo",
        "intentos_fallidos",
        "probabilidad",
        "clasificacion"
    ]

    salida = io.StringIO()
    escritor = csv.DictWriter(salida, fieldnames=columnas)
    escritor.writeheader()
    escritor.writerows(filas)

    return Response(
        salida.getvalue(),
        mimetype="text/csv"
    )


# -----------------------------------------
# Iniciar servidor Flask
# -----------------------------------------
if __name__ == "__main__":
    app.run(
        host=os.getenv("API_HOST", "127.0.0.1"),
        port=int(os.getenv("API_PORT", "5000")),
        debug=False
    )


#http://127.0.0.1:5000/api/trafico/probar?duracion=10&paquetes=120&bytes=5000&puerto=80&protocolo=TCP&intentos_fallidos=0
#http://127.0.0.1:5000/api/trafico/probar?duracion=85&paquetes=2500&bytes=180000&puerto=22&protocolo=TCP&intentos_fallidos=12
#http://127.0.0.1:5000/api/trafico/probar?duracion=30&paquetes=180&bytes=12000&puerto=443&protocolo=TCP&intentos_fallidos=0