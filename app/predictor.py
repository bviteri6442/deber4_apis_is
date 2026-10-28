"""Carga el modelo ya entrenado y procesa dataframes nuevos."""
from threading import Lock
import joblib
import pandas as pd
from tensorflow.keras.models import load_model
from app.comun import MODELO, PREPRO, transformar, validar_dataframe

class Predictor:
    def __init__(self):
        if not MODELO.exists() or not PREPRO.exists():
            raise FileNotFoundError("Ejecuta primero: python entrenar.py")
        self.modelo = load_model(MODELO)
        # No cargar modelos joblib de fuentes externas/no confiables.
        self.config = joblib.load(PREPRO)
        self.lock = Lock()

    def predecir(self, datos):
        limpio = validar_dataframe(pd.DataFrame(datos))
        x = transformar(limpio, self.config)
        with self.lock:
            probs = self.modelo.predict(x, verbose=0).ravel()
        resultados = limpio.copy()
        resultados["probabilidad"] = [round(float(p), 5) for p in probs]
        resultados["clasificacion"] = ["Sospechoso" if p > 0.5 else "Normal" for p in probs]
        return resultados
