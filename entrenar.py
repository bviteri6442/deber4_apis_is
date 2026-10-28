# -*- coding: utf-8 -*-
"""Fase 1: entrenar, evaluar con holdout independiente y guardar artefactos."""
import json
import random
import joblib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from tensorflow.keras import Sequential
from tensorflow.keras.layers import Input, Dense
from tensorflow.keras.utils import set_random_seed
from app.comun import ROOT, MODELO, PREPRO, validar_dataframe

set_random_seed(42)
random.seed(42)
np.random.seed(42)

archivo = ROOT / "datos" / "trafico_red.csv"
df = pd.read_csv(archivo).dropna().drop_duplicates()
X = validar_dataframe(df)
y = df["estado"].astype(str).str.strip().str.lower().map({"normal": 0, "sospechoso": 1})
if y.isna().any():
    raise ValueError("La columna estado debe contener solo normal/sospechoso")
y = y.astype(int)
X = pd.get_dummies(X, columns=["protocolo"], dtype=int)
columnas = X.columns.tolist()

X_train, X_temp, y_train, y_temp = train_test_split(X, y, test_size=0.30, random_state=42, stratify=y)
X_val, X_test, y_val, y_test = train_test_split(X_temp, y_temp, test_size=0.5, random_state=42, stratify=y_temp)
scaler = StandardScaler()
X_train = scaler.fit_transform(X_train)
X_val = scaler.transform(X_val)
X_test = scaler.transform(X_test)

modelo = Sequential([Input(shape=(X_train.shape[1],)), Dense(16, activation="relu"),
                     Dense(8, activation="relu"), Dense(1, activation="sigmoid")])
modelo.compile(optimizer="adam", loss="binary_crossentropy", metrics=["accuracy"])
print(f"Dataset: {len(df)} filas. Entrenamiento: {len(y_train)}, validacion: {len(y_val)}, prueba: {len(y_test)}")
hist = modelo.fit(X_train, y_train, epochs=30, batch_size=8,
                  validation_data=(X_val, y_val), verbose=1)
prob = modelo.predict(X_test, verbose=0).ravel()
pred = (prob > 0.5).astype(int)
print("\nAccuracy de prueba:", round(accuracy_score(y_test, pred), 4))
print("\nMatriz de confusion (filas reales, columnas predichas; 0 normal, 1 sospechoso):")
print(confusion_matrix(y_test, pred, labels=[0, 1]))
print(classification_report(y_test, pred, labels=[0, 1], target_names=["normal", "sospechoso"], zero_division=0))

MODELO.parent.mkdir(parents=True, exist_ok=True)
modelo.save(MODELO)
# ATENCION: cargar archivos joblib unicamente de origen confiable.
joblib.dump({"scaler": scaler, "columnas": columnas}, PREPRO)
print("\nArchivos guardados:", MODELO, PREPRO, sep="\n")

plt.figure(figsize=(8, 4))
plt.plot(hist.history["accuracy"], label="Entrenamiento")
plt.plot(hist.history["val_accuracy"], label="Validacion")
plt.xlabel("Epoca")
plt.ylabel("Accuracy")
plt.title("Aprendizaje de la red neuronal")
plt.legend()
plt.tight_layout()
ruta = ROOT / "datos" / "grafica_entrenamiento.png"
plt.savefig(ruta, dpi=150)
plt.close()
print("Grafica:", ruta)
