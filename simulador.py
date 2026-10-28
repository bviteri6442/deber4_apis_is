# python3 simulador.py --cantidad 3000 --lote 500
import argparse
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
CSV = ROOT / "datos" / "trafico_red.csv"

URL = "http://127.0.0.1:5000/api/trafico/lote"

parser = argparse.ArgumentParser()
parser.add_argument("--cantidad", type=int, default=3000)
parser.add_argument("--lote", type=int, default=500)
args = parser.parse_args()

if args.cantidad <= 0:
    parser.error("La cantidad debe ser mayor que cero")

if not 1 <= args.lote <= 500:
    parser.error("El lote debe estar entre 1 y 500")

# Leer los registros
df = pd.read_csv(CSV)

# Seleccionar la cantidad solicitada
df = df.head(args.cantidad)

# El estado no debe enviarse al modelo
df = df.drop(columns=["estado"], errors="ignore")

total_enviados = 0
total_guardados = 0

# Dividir en lotes
for inicio in range(0, len(df), args.lote):

    lote = df.iloc[inicio:inicio + args.lote]

    datos = lote.to_dict(orient="records")

    respuesta = requests.post(
        URL,
        json=datos,
        timeout=120
    )

    if not respuesta.ok:
        print("Error HTTP:", respuesta.status_code)
        print("Respuesta:", respuesta.text)
        respuesta.raise_for_status()

    resultado = respuesta.json()

    enviados = len(datos)
    guardados = resultado.get("guardados_sql", 0)

    total_enviados += enviados
    total_guardados += guardados

    print("Lote procesado:", enviados)
    print("Total enviados:", total_enviados)
    print("Total guardados:", total_guardados)
    print("------------------------")

print("PROCESAMIENTO FINALIZADO")
print("Conexiones enviadas:", total_enviados)
print("Registros guardados:", total_guardados)
