# -*- coding: utf-8 -*-
"""Fase 2: predicciones desde CSV sin entrenamiento."""
import argparse
import pandas as pd
from app.comun import ROOT
from app.predictor import Predictor

parser = argparse.ArgumentParser()
parser.add_argument("--archivo", default=str(ROOT / "datos" / "nuevo_trafico.csv"))
args = parser.parse_args()

entradas = pd.read_csv(args.archivo)
resultados = Predictor().predecir(entradas.to_dict(orient="records"))
salida = ROOT / "datos" / "resultados_prediccion.csv"
resultados.to_csv(salida, index=False)
print(resultados.to_string(index=False))
print("\nGuardado:", salida)
