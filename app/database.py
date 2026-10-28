"""Persistencia opcional en SQL Server (usar parametros siempre)."""
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()


def habilitada():
    return os.getenv("DB_ENABLED", "false").strip().lower() == "true"


def conexion():
    import pyodbc
    if not habilitada():
        return None
    driver = os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")
    server = os.getenv("DB_SERVER", "localhost")
    port = os.getenv("DB_PORT", "1433")
    db = os.getenv("DB_DATABASE", "TraficoIA")
    user = os.getenv("DB_USER", "sa")
    password = os.getenv("DB_PASSWORD", "")
    encrypt = os.getenv("DB_ENCRYPT", "yes")
    trust = os.getenv("DB_TRUST_SERVER_CERTIFICATE", "yes")
    cs = (f"DRIVER={{{driver}}};SERVER={server},{port};DATABASE={db};"
          f"UID={user};PWD={password};Encrypt={encrypt};TrustServerCertificate={trust};")
    return pyodbc.connect(cs, timeout=8)


def guardar(resultados):
    if not habilitada():
        return 0
    cn = conexion()
    try:
        cursor = cn.cursor()
        query = """INSERT INTO dbo.PrediccionesTrafico
        (duracion, paquetes, bytes, puerto, protocolo, intentos_fallidos, probabilidad, clasificacion)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
        filas = [(
            float(r.duracion), int(r.paquetes), int(r.bytes), int(r.puerto),
            str(r.protocolo), int(r.intentos_fallidos), float(r.probabilidad),
            str(r.clasificacion)) for r in resultados.itertuples(index=False)] # función de Pandas que permite recorrer un DataFrame fila por fila, convirtiendo cada fila en una tupla con campos accesibles por su nombre.
        cursor.executemany(query, filas)
        cn.commit()
        cursor.close()
        return len(filas)
    except Exception:
        cn.rollback()
        raise
    finally:
        cn.close()
