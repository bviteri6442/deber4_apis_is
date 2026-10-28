from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODELO = ROOT / "modelos" / "modelo_trafico.keras"
PREPRO = ROOT / "modelos" / "preprocesamiento.joblib"
CAMPOS = ("duracion", "paquetes", "bytes", "puerto", "protocolo", "intentos_fallidos")
NUMERICOS = tuple(x for x in CAMPOS if x != "protocolo")
PROTOCOLOS = ("TCP", "UDP", "ICMP")


def validar_dataframe(df):
    """Valida sin deducir etiquetas a partir de reglas arbitrarias."""
    faltantes = set(CAMPOS) - set(df.columns)
    if faltantes:
        raise ValueError(f"Faltan columnas: {', '.join(sorted(faltantes))}")
    if df.empty:
        raise ValueError("No se recibieron conexiones")
    resultado = df.loc[:, list(CAMPOS)].copy()
    for campo in NUMERICOS:
        resultado[campo] = pd.to_numeric(resultado[campo], errors="coerce")
        if resultado[campo].isna().any():
            raise ValueError(f"{campo}: hay valores no numericos o vacios")
        if (resultado[campo] < 0).any():
            raise ValueError(f"{campo}: no se permiten valores negativos")
    for campo in ("paquetes", "bytes", "puerto", "intentos_fallidos"):
        if (resultado[campo] % 1 != 0).any():
            raise ValueError(f"{campo}: debe ser entero")
        resultado[campo] = resultado[campo].astype("int64")
    if ((resultado["puerto"] > 65535)).any():
        raise ValueError("puerto debe estar entre 0 y 65535")
    resultado["protocolo"] = resultado["protocolo"].astype(str).str.strip().str.upper()
    if not resultado["protocolo"].isin(PROTOCOLOS).all():
        raise ValueError("protocolo debe ser TCP, UDP o ICMP")
    return resultado


def transformar(df, config):
    """Aplicar exactamente la codificacion y escala aprendidas en el entrenamiento."""
    valores = validar_dataframe(df)
    x = pd.get_dummies(valores, columns=["protocolo"], dtype=int)
    x = x.reindex(columns=config["columnas"], fill_value=0)
    return config["scaler"].transform(x)
