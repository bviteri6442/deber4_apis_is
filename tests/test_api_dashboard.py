# -*- coding: utf-8 -*-
"""Pruebas unitarias de la API del dashboard (sin SQL Server ni TensorFlow).

Ejecutar desde la carpeta practica002:
    python -m unittest discover -s tests -v
"""
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class PredictorFalso:
    """Sustituye app.predictor.Predictor para no cargar el modelo Keras."""

    def predecir(self, datos):
        return ResultadosFalsos()


class ResultadosFalsos:
    def __init__(self):
        self.iloc = [{"clasificacion": "Sospechoso", "probabilidad": 0.91}]

    def to_dict(self, orient="records"):
        return list(self.iloc)

    def __len__(self):
        return len(self.iloc)


modulo_predictor = types.ModuleType("app.predictor")
modulo_predictor.Predictor = PredictorFalso
sys.modules["app.predictor"] = modulo_predictor

import api  # noqa: E402  (debe importarse despues de la simulacion)


class CursorFalso:
    def __init__(self, columnas, filas, error=None):
        self.description = [(c,) for c in columnas]
        self._filas = filas
        self._error = error
        self.ejecutado = []

    def execute(self, sql, params=()):
        if self._error:
            raise self._error
        self.ejecutado.append((sql, params))

    def fetchall(self):
        return self._filas

    def close(self):
        pass


class ConexionFalsa:
    def __init__(self, cursor):
        self._cursor = cursor
        self.cerrada = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.cerrada = True


COLUMNAS_REGISTROS = [
    "id_prediccion", "fecha_prediccion", "duracion", "paquetes", "bytes",
    "puerto", "protocolo", "intentos_fallidos", "probabilidad", "clasificacion",
]


class FiltrosTest(unittest.TestCase):
    def test_sin_filtros_no_agrega_where(self):
        self.assertEqual(api.construir_filtros({}), ("", ()))

    def test_valores_vacios_no_aplican_condicion(self):
        args = {"fecha_desde": "", "fecha_hasta": " ", "protocolo": "",
                "puerto": "", "clasificacion": ""}
        self.assertEqual(api.construir_filtros(args), ("", ()))

    def test_fecha_final_incluye_el_dia_completo(self):
        where, params = api.construir_filtros(
            {"fecha_desde": "2026-10-01", "fecha_hasta": "2026-10-26"})
        self.assertEqual(
            where,
            " WHERE fecha_prediccion >= ? AND fecha_prediccion < ?")
        self.assertEqual(params, (datetime(2026, 10, 1), datetime(2026, 10, 27)))

    def test_combinacion_de_todos_los_filtros(self):
        where, params = api.construir_filtros({
            "fecha_desde": "2026-10-01", "fecha_hasta": "2026-10-26",
            "protocolo": "tcp", "puerto": "443", "clasificacion": "Sospechoso",
        })
        self.assertEqual(
            where,
            " WHERE fecha_prediccion >= ? AND fecha_prediccion < ?"
            " AND protocolo = ? AND puerto = ? AND clasificacion = ?")
        self.assertEqual(params[2:], ("TCP", 443, "Sospechoso"))

    def test_protocolo_inexistente_no_es_error(self):
        where, params = api.construir_filtros({"protocolo": "XYZ"})
        self.assertEqual(params, ("XYZ",))

    def test_valor_malicioso_viaja_como_parametro(self):
        where, params = api.construir_filtros(
            {"protocolo": "TCP' OR '1'='1"})
        self.assertNotIn("OR", where)
        self.assertEqual(params, ("TCP' OR '1'='1",))

    def test_fecha_con_formato_invalido(self):
        with self.assertRaisesRegex(api.FiltroInvalido, "fecha_desde"):
            api.construir_filtros({"fecha_desde": "26/10/2026"})
        with self.assertRaisesRegex(api.FiltroInvalido, "fecha_hasta"):
            api.construir_filtros({"fecha_hasta": "2026-13-01"})

    def test_fecha_inicial_posterior_a_final(self):
        with self.assertRaisesRegex(api.FiltroInvalido, "posterior"):
            api.construir_filtros(
                {"fecha_desde": "2026-10-26", "fecha_hasta": "2026-10-01"})

    def test_mismo_dia_es_valido(self):
        where, params = api.construir_filtros(
            {"fecha_desde": "2026-10-26", "fecha_hasta": "2026-10-26"})
        self.assertEqual(len(params), 2)

    def test_puerto_fuera_de_rango(self):
        with self.assertRaisesRegex(api.FiltroInvalido, "rango"):
            api.construir_filtros({"puerto": "70000"})

    def test_puerto_no_numerico(self):
        with self.assertRaisesRegex(api.FiltroInvalido, "rango"):
            api.construir_filtros({"puerto": "abc"})
        with self.assertRaisesRegex(api.FiltroInvalido, "rango"):
            api.construir_filtros({"puerto": "-1"})


class EndpointsTest(unittest.TestCase):
    def setUp(self):
        api.app.config["TESTING"] = True
        self.cliente = api.app.test_client()
        self.habilitada = mock.patch.object(api, "habilitada", return_value=True)
        self.habilitada.start()
        self.addCleanup(self.habilitada.stop)

    def conectar(self, columnas=("total",), filas=((0,),), error=None):
        cursor = CursorFalso(list(columnas), list(filas), error)
        cn = ConexionFalsa(cursor)
        patcher = mock.patch.object(api, "conexion", return_value=cn)
        patcher.start()
        self.addCleanup(patcher.stop)
        return cursor, cn

    def test_resumen_sin_filtros_no_usa_where(self):
        cursor, cn = self.conectar()
        respuesta = self.cliente.get("/api/dashboard/resumen")
        self.assertEqual(respuesta.status_code, 200)
        sql, params = cursor.ejecutado[0]
        self.assertNotIn("WHERE", sql)
        self.assertEqual(params, ())
        self.assertTrue(cn.cerrada)

    def test_resumen_aplica_los_filtros_con_parametros(self):
        cursor, _ = self.conectar()
        self.cliente.get("/api/dashboard/resumen?protocolo=TCP&puerto=443")
        sql, params = cursor.ejecutado[0]
        self.assertIn("WHERE protocolo = ? AND puerto = ?", sql)
        self.assertEqual(params, ("TCP", 443))

    def test_todos_los_endpoints_agregados_aplican_el_mismo_filtro(self):
        rutas = [
            "/api/dashboard/resumen",
            "/api/dashboard/por-clasificacion",
            "/api/dashboard/por-protocolo",
            "/api/dashboard/por-puerto",
            "/api/dashboard/distribucion-probabilidad",
            "/api/dashboard/intentos-fallidos",
            "/api/dashboard/registros",
        ]
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                cursor, _ = self.conectar()
                self.cliente.get(ruta + "?protocolo=UDP&puerto=53")
                sql, params = cursor.ejecutado[0]
                self.assertIn("protocolo = ?", sql, ruta)
                self.assertIn("puerto = ?", sql, ruta)
                self.assertEqual(params, ("UDP", 53), ruta)

    def test_filtro_invalido_responde_400_sin_consultar(self):
        with mock.patch.object(api, "conexion") as conexion:
            respuesta = self.cliente.get(
                "/api/dashboard/resumen?fecha_desde=2026-10-26&fecha_hasta=2026-10-01")
            self.assertEqual(respuesta.status_code, 400)
            conexion.assert_not_called()

    def test_registros_sin_limite_no_usa_top(self):
        cursor, _ = self.conectar(COLUMNAS_REGISTROS, [])
        respuesta = self.cliente.get("/api/dashboard/registros")
        self.assertEqual(respuesta.status_code, 200)
        sql, _ = cursor.ejecutado[0]
        self.assertNotIn("TOP", sql)
        self.assertIn("ORDER BY fecha_prediccion DESC, id_prediccion DESC", sql)

    def test_registros_con_limite_usa_top(self):
        cursor, _ = self.conectar(COLUMNAS_REGISTROS, [])
        self.cliente.get("/api/dashboard/registros?limite=50")
        sql, _ = cursor.ejecutado[0]
        self.assertIn("TOP (50)", sql)

    def test_registros_limite_invalido(self):
        for valor in ("0", "-5", "abc"):
            with self.subTest(limite=valor):
                respuesta = self.cliente.get(
                    f"/api/dashboard/registros?limite={valor}")
                self.assertEqual(respuesta.status_code, 400)

    def test_registros_devuelve_fecha_iso_e_id(self):
        fila = (7, datetime(2026, 10, 26, 10, 30, 0)) + (0,) * 8
        self.conectar(COLUMNAS_REGISTROS, [fila])
        datos = self.cliente.get("/api/dashboard/registros").get_json()
        self.assertEqual(datos[0]["id_prediccion"], 7)
        self.assertEqual(datos[0]["fecha_prediccion"], "2026-10-26T10:30:00")

    def test_registros_csv(self):
        fila = (7, datetime(2026, 10, 26, 10, 30, 0), 1.5, 10, 500, 443,
                "TCP", 0, 0.2, "Normal")
        self.conectar(COLUMNAS_REGISTROS, [fila])
        respuesta = self.cliente.get("/api/dashboard/registros?formato=csv")
        self.assertEqual(respuesta.mimetype, "text/csv")
        lineas = respuesta.get_data(as_text=True).strip().splitlines()
        self.assertEqual(lineas[0], ",".join(COLUMNAS_REGISTROS))
        self.assertTrue(lineas[1].startswith("7,2026-10-26T10:30:00,1.5"))

    def test_base_de_datos_deshabilitada_responde_503(self):
        with mock.patch.object(api, "habilitada", return_value=False):
            respuesta = self.cliente.get("/api/dashboard/resumen")
        self.assertEqual(respuesta.status_code, 503)

    def test_error_de_sql_no_expone_detalles(self):
        self.conectar(error=Exception("Login failed for user 'sa' password=secreto"))
        respuesta = self.cliente.get("/api/dashboard/resumen")
        self.assertEqual(respuesta.status_code, 500)
        self.assertNotIn("secreto", respuesta.get_data(as_text=True))

    def test_error_de_conexion_en_csv_responde_500(self):
        with mock.patch.object(api, "conexion", side_effect=OSError("sin red")):
            respuesta = self.cliente.get("/api/dashboard/registros?formato=csv")
        self.assertEqual(respuesta.status_code, 500)
        self.assertNotIn("sin red", respuesta.get_data(as_text=True))

    def test_resultado_vacio_devuelve_lista_vacia(self):
        self.conectar(COLUMNAS_REGISTROS, [])
        datos = self.cliente.get(
            "/api/dashboard/registros?protocolo=ICMP&puerto=22").get_json()
        self.assertEqual(datos, [])

    def test_totales_coinciden_con_los_registros_filtrados(self):
        """El resumen y el detalle deben usar la misma clausula WHERE."""
        cursor, _ = self.conectar()
        self.cliente.get("/api/dashboard/resumen?clasificacion=Sospechoso")
        self.cliente.get("/api/dashboard/registros?clasificacion=Sospechoso")
        sql_resumen, params_resumen = cursor.ejecutado[0]
        sql_registros, params_registros = cursor.ejecutado[1]
        self.assertIn("FROM dbo.PrediccionesTrafico WHERE clasificacion = ?", sql_resumen)
        self.assertIn("FROM dbo.PrediccionesTrafico WHERE clasificacion = ?", sql_registros)
        self.assertEqual(params_resumen, params_registros)


class PrediccionesNoAfectadasTest(unittest.TestCase):
    def setUp(self):
        api.app.config["TESTING"] = True
        self.cliente = api.app.test_client()

    def test_predecir_sigue_guardando_y_responde(self):
        with mock.patch.object(api, "guardar", return_value=1) as guardar:
            respuesta = self.cliente.post(
                "/api/trafico/predecir",
                json={"duracion": 1, "paquetes": 2, "bytes": 3,
                      "puerto": 443, "protocolo": "TCP",
                      "intentos_fallidos": 0})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.get_json()["guardados_sql"], 1)
        guardar.assert_called_once()

    def test_probar_no_guarda(self):
        with mock.patch.object(api, "guardar") as guardar:
            respuesta = self.cliente.get(
                "/api/trafico/probar?duracion=10&paquetes=120&bytes=5000"
                "&puerto=80&protocolo=TCP&intentos_fallidos=0")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.get_json()["guardados_sql"], 0)
        guardar.assert_not_called()

    def test_health(self):
        with mock.patch.object(api, "habilitada", return_value=False):
            respuesta = self.cliente.get("/api/health")
        self.assertEqual(respuesta.get_json()["sql_server"], False)


if __name__ == "__main__":
    unittest.main()
