
# -*- coding: utf-8 -*-
"""API REST + predicciones + almacenamiento opcional."""

import csv
import io
import os
from datetime import date, datetime
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
# Cada endpoint llama a un PROCEDIMIENTO ALMACENADO (sql/03_procedimientos.sql).
# La API no contiene SELECT sobre la tabla: solo EXEC dbo.sp_... con parametros.
# Power BI: Obtener datos > Web > URL del endpoint.
# Todas devuelven una lista JSON de registros (tabla plana).
#
# Filtros comunes, todos opcionales (un valor vacio se envia como NULL):
#   fecha_desde, fecha_hasta (YYYY-MM-DD, fecha UTC), protocolo, puerto,
#   clasificacion. El SP los aplica con AND.
# =========================================
class FiltroInvalido(ValueError):
    """Parametro de filtro no valido: se responde con HTTP 400."""


# Parametros de filtro que reciben todos los SP del dashboard (en este orden)
PARAMETROS_FILTRO = ("FechaDesde", "FechaHasta", "Protocolo", "Puerto", "Clasificacion")


def ejecutar_sp(nombre, params=None):
    """Ejecuta EXEC dbo.<nombre> con parametros nombrados y devuelve lista de dicts.

    params: dict {NombreParametro: valor}. Los valores viajan como ?, nunca
    dentro del texto SQL. El nombre del SP es fijo en el codigo, no viene del usuario.
    """
    if not habilitada():
        raise RuntimeError("SQL Server deshabilitado (DB_ENABLED=false)")
    params = params or {}
    asignaciones = ", ".join(f"@{p} = ?" for p in params)
    sql = f"EXEC dbo.{nombre} {asignaciones}".strip()
    cn = conexion()
    try:
        cursor = cn.cursor()
        cursor.execute(sql, tuple(params.values()))
        columnas = [c[0] for c in cursor.description]
        filas = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
        cursor.close()
        # Fechas en ISO 8601 (jsonify las enviaria en formato HTTP-date)
        return [
            {c: v.isoformat() if isinstance(v, (datetime, date)) else v
             for c, v in fila.items()}
            for fila in filas
        ]
    finally:
        cn.close()


def dashboard(nombre, params=None):
    """Ejecuta un SP del dashboard con manejo de errores comun."""
    try:
        return jsonify(ejecutar_sp(nombre, params))
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 503
    except Exception:
        app.logger.exception("Error en API de dashboard")
        return jsonify(error="No se pudo consultar la base de datos"), 500


def leer_fecha(texto, nombre):
    """Convierte YYYY-MM-DD a date; None si viene vacia."""
    if not texto:
        return None
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        raise FiltroInvalido(f"{nombre} debe tener formato YYYY-MM-DD")


def construir_filtros(args):
    """Devuelve el dict de parametros de filtro para los SP.

    Un filtro vacio se envia como None (NULL en SQL Server = sin filtro).
    Se valida aqui para responder 400 sin llegar a la base de datos; el SP
    vuelve a validar (dbo.sp_ValidarFiltros).
    """
    desde = leer_fecha(args.get("fecha_desde", "").strip(), "fecha_desde")
    hasta = leer_fecha(args.get("fecha_hasta", "").strip(), "fecha_hasta")
    if desde and hasta and desde > hasta:
        raise FiltroInvalido("fecha_desde no puede ser posterior a fecha_hasta")

    puerto = args.get("puerto", "").strip()
    if puerto:
        if not puerto.isdigit() or int(puerto) > 65535:
            raise FiltroInvalido("Puerto fuera de rango (0-65535)")
        puerto = int(puerto)

    return {
        "FechaDesde": desde,
        "FechaHasta": hasta,
        "Protocolo": args.get("protocolo", "").strip().upper() or None,
        "Puerto": puerto if puerto != "" else None,
        "Clasificacion": args.get("clasificacion", "").strip() or None,
    }


def dashboard_filtrado(nombre, extra=None):
    """Ejecuta un SP del dashboard con los filtros de la URL (+ parametros extra)."""
    try:
        params = construir_filtros(request.args)
    except FiltroInvalido as exc:
        return jsonify(error=str(exc)), 400
    params.update(extra or {})
    return dashboard(nombre, params)


# 5. KPIs generales (una sola fila: tarjetas del dashboard)
@app.get("/api/dashboard/resumen")
def dash_resumen():
    return dashboard_filtrado("sp_Dashboard_Resumen")


# 6. Conteo por clasificacion (grafico circular / barras)
@app.get("/api/dashboard/por-clasificacion")
def dash_clasificacion():
    return dashboard_filtrado("sp_Dashboard_PorClasificacion")


# 7. Conteo por protocolo y clasificacion (barras apiladas)
@app.get("/api/dashboard/por-protocolo")
def dash_protocolo():
    return dashboard_filtrado("sp_Dashboard_PorProtocolo")


# 8. Puertos mas usados (?top=10)
@app.get("/api/dashboard/por-puerto")
def dash_puerto():
    top = request.args.get("top", default=10, type=int)
    top = max(1, min(top, 100))
    return dashboard_filtrado("sp_Dashboard_PorPuerto", {"Top": top})


# 9. Distribucion de probabilidad en rangos de 10% (histograma)
@app.get("/api/dashboard/distribucion-probabilidad")
def dash_probabilidad():
    return dashboard_filtrado("sp_Dashboard_DistribucionProbabilidad")


# 10. Intentos fallidos agrupados (dispersion / barras)
@app.get("/api/dashboard/intentos-fallidos")
def dash_intentos():
    return dashboard_filtrado("sp_Dashboard_IntentosFallidos")


# 11. Tabla detalle: fuente recomendada para Power BI (ver docs/auditoria)
#     ?limite=N opcional. Sin el devuelve TODOS los registros que cumplen
#     los filtros, para que los totales de Power BI no queden truncados.
#     ?formato=csv para importar como CSV en Power BI
@app.get("/api/dashboard/registros")
def dash_registros():
    limite = request.args.get("limite", "").strip()
    if limite and (not limite.isdigit() or int(limite) < 1):
        return jsonify(error="limite debe ser un entero positivo"), 400

    try:
        params = construir_filtros(request.args)
    except FiltroInvalido as exc:
        return jsonify(error=str(exc)), 400
    params["Limite"] = int(limite) if limite else None

    if request.args.get("formato", "").lower() != "csv":
        return dashboard("sp_Dashboard_Registros", params)

    try:
        filas = ejecutar_sp("sp_Dashboard_Registros", params)
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