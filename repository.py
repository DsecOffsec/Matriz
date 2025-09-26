
import streamlit as st
import gspread
import re
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
import google.generativeai as genai

# ==============================
# Config básica
# ==============================
st.title("MATRIZ DSEC — Mínimo (Sheets + CODIGO + IA)")
TZ = ZoneInfo("America/La_Paz")

# ---- Google Sheets (usa exactamente tu secrets e ID) ----
gc = gspread.service_account_from_dict(st.secrets["connections"]["gsheets"])
SHEET_ID = "1UP_fwvXam8-1IXI-oUbkNqGzb0_T0XNrYsU7ziJVAqE"  # tu ID
sh = gc.open_by_key(SHEET_ID)
ws = sh.worksheet("Reportes")
st.success("✅ Conectado a Google Sheets")

# ---- Gemini (IA) ----
genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
model = genai.GenerativeModel("gemini-1.5-flash")

# ---- Columnas canónicas ----
COLUMNAS = [
    "CODIGO","Fecha y Hora de Apertura","Modo Reporte","Evento/ Incidente",
    "Descripción Evento/ Incidente","Sistema","Area","Ubicación","Impacto",
    "Clasificación","Acción Inmediata","Solución","Area de GTIC - Coordinando",
    "Encargado SI","Fecha y Hora de Cierre","Tiempo Solución","Estado",
    "Vulnerabilidad","Causa","ID Amenaza","Amenaza"
]

# ==============================
# Utilidades mínimas
# ==============================
def assert_20_pipes(s: str):
    cnt = s.count("|")
    if cnt != 20:
        raise ValueError(f"Se esperaban 21 campos (20 pipes) y llegaron {cnt+1}.")

def sanitize_text(s: str) -> str:
    s = s.strip().replace("\n", " ").replace("\r", " ")
    s = s.strip("`")
    return s

def normalize_21_fields(raw: str):
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) < 21:
        parts += [""] * (21 - len(parts))
    elif len(parts) > 21:
        parts = parts[:21]
    return parts

def generar_codigo_inc(ws) -> str:
    #\"\"\"Formato: INC-[DD]-[MM]-[NNN] (correlativo por día).\"\"\"
    now = datetime.now(TZ)
    dd = now.day
    mm = now.month
    pref = f\"INC-{dd}-{mm}-\"
    existentes = ws.col_values(1)  # Primera columna (CODIGO)
    max_n = 0
    rx = re.compile(rf\"^{re.escape(pref)}(\\d{{3}})$\")
    for c in existentes:
        m = rx.match((c or \"\").strip())
        if m:
            n = int(m.group(1))
            if n > max_n:
                max_n = n
    return f\"{pref}{max_n+1:03d}\"

# ==============================
# Prompt mínimo a IA (sin extra lógica)
# ==============================
persona = f\"\"\"
Devuelve UNA SOLA LÍNEA con **exactamente 21** campos separados por | en este orden:
{COLUMNAS}

Reglas:
- Campo 1 (CODIGO) déjalo vacío (lo genera el sistema).
- Campos 18 a 21 (Vulnerabilidad, Causa, ID Amenaza, Amenaza) déjalos vacíos.
- No agregues comentarios ni texto extra. Solo la línea con 21 campos.

[REPORTE]:
\"\"\"

# ==============================
# UI mínima
# ==============================
texto = st.text_area(\"Pega el reporte en texto libre:\", height=180)

if st.button(\"Enviar a IA y guardar\", use_container_width=True):
    if not texto.strip():
        st.warning(\"Escribe algo primero.\")
        st.stop()

    try:
        resp = model.generate_content([persona + texto.strip()], generation_config={\"temperature\": 0.2})
        raw = resp.text if hasattr(resp, \"text\") else str(resp)
        raw = sanitize_text(raw)
        assert_20_pipes(raw)
        fila = normalize_21_fields(raw)
        # Forzar vacíos 18–21 por política
        fila[17] = \"\"; fila[18] = \"\"; fila[19] = \"\"; fila[20] = \"\"
    except Exception as e:
        st.error(f\"IA no devolvió un formato válido: {e}\")
        st.stop()

    # Insertar CODIGO en la primera columna
    try:
        fila[0] = generar_codigo_inc(ws)
    except Exception as e:
        st.error(f\"No pude generar el CODIGO: {e}\")
        st.stop()

    # Agregar timestamp (col extra al final)
    fila_out = fila + [datetime.now(TZ).strftime(\"%Y-%m-%d %H:%M:%S\")]

    # Vista previa y guardado
    st.dataframe(pd.DataFrame([fila_out], columns=COLUMNAS + [\"Hora de reporte\"]), use_container_width=True)
    try:
        ws.append_row(fila_out, value_input_option=\"USER_ENTERED\")
        st.success(f\"✅ Guardado con CODIGO: {fila[0]}\")
    except Exception as e:
        st.error(f\"No se pudo guardar en la hoja: {e}\")

