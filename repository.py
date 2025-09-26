import streamlit as st
import gspread
import pandas as pd
import re
from datetime import datetime
from zoneinfo import ZoneInfo

# ==============================
# Título / Zona horaria
# ==============================
st.title("MATRIZ DSEC — Mínimo (Sheets + CODIGO + IA con fallback)")
TZ = ZoneInfo("America/La_Paz")

# ==============================
# Conexión a Google Sheets
# ==============================
# Debes tener en st.secrets:
# [connections.gsheets]  -> JSON de service account
# SHEET_ID = "tu_id_de_hoja"
try:
    gc = gspread.service_account_from_dict(st.secrets["connections"]["gsheets"])
    SHEET_ID = st.secrets["SHEET_ID"]
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet("Reportes")
    st.success("✅ Conectado a Google Sheets (pestaña: Reportes)")
except Exception as e:
    ws = None
    st.error(f"❌ No se pudo conectar a Google Sheets: {e}")

# Columnas canónicas (21)
COLUMNAS = [
    "CODIGO", "Fecha y Hora de Apertura", "Modo Reporte", "Evento/ Incidente",
    "Descripción Evento/ Incidente", "Sistema", "Area", "Ubicación", "Impacto",
    "Clasificación", "Acción Inmediata", "Solución", "Area de GTIC - Coordinando",
    "Encargado SI", "Fecha y Hora de Cierre", "Tiempo Solución", "Estado",
    "Vulnerabilidad", "Causa", "ID Amenaza", "Amenaza"
]

# Si la hoja está vacía, escribe encabezados (21 + Hora de reporte)
if ws:
    try:
        headers = ws.row_values(1)
        if headers != COLUMNAS + ["Hora de reporte"]:
            ws.resize(rows=1, cols=len(COLUMNAS) + 1)
            ws.update("A1", [COLUMNAS + ["Hora de reporte"]])
    except Exception:
        pass

# ==============================
# IA (opcional) + bandera de disponibilidad
# ==============================
IA_READY = False
model = None
try:
    import google.generativeai as genai
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])  # API key de ai.google.dev (consumer)
    model = genai.GenerativeModel("gemini-1.5-flash")
    IA_READY = True
    st.caption("ℹ️ IA lista: gemini-1.5-flash (consumer API).")
except Exception:
    st.caption("ℹ️ IA no disponible: se usará fallback determinístico.")

PROMPT = f"""
Devuelve UNA SOLA LÍNEA con exactamente 21 campos separados por | en este orden:
{COLUMNAS}

Reglas:
- Campo 1 (CODIGO) déjalo vacío (lo genera el sistema).
- Campos 18 a 21 (Vulnerabilidad, Causa, ID Amenaza, Amenaza) déjalos vacíos.
- No agregues comentarios ni texto extra. Solo la línea con 21 campos.

[REPORTE]:
"""

# ==============================
# Utilidades mínimas
# ==============================
def sanitize_text(s: str) -> str:
    s = s.strip().replace("\n", " ").replace("\r", " ")
    return s.strip("`").strip()

def assert_20_pipes(s: str):
    # 21 campos => 20 pipes
    if s.count("|") != 20:
        raise ValueError("La IA no devolvió 21 campos separados por '|'.")

def normalize_21_fields(raw: str):
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) < 21:
        parts += [""] * (21 - len(parts))
    elif len(parts) > 21:
        parts = parts[:21]
    return parts

def generar_codigo_inc(ws_obj) -> str:
    """Formato: INC-[DD]-[MM]-[NNN] (correlativo por día)."""
    now = datetime.now(TZ)
    pref = f"INC-{now:%d}-{now:%m}-"      # INC-26-09-
    max_n = 0
    if ws_obj:
        try:
            col1 = ws_obj.col_values(1)   # primera columna (CODIGO)
            rx = re.compile(rf"^{re.escape(pref)}(\d{{3}})$")
            for c in col1:
                m = rx.match((c or "").strip())
                if m:
                    n = int(m.group(1))
                    if n > max_n:
                        max_n = n
        except Exception:
            pass
    return f"{pref}{max_n+1:03d}"

# ==============================
# UI
# ==============================
texto = st.text_area("Pega el reporte en texto libre:", height=160,
    placeholder="Ej: A las 7:00 se reportó phishing por correo...")

if st.button("Enviar a IA y guardar", use_container_width=True):
    if not texto.strip():
        st.warning("Escribe algo primero.")
        st.stop()

    fila = None

    # 1) Intentar IA
    if IA_READY:
        try:
            resp = model.generate_content([PROMPT + texto.strip()],
                                          generation_config={"temperature": 0.2})
            raw = resp.text if hasattr(resp, "text") else str(resp)
            raw = sanitize_text(raw)
            assert_20_pipes(raw)
            fila = normalize_21_fields(raw)
            # Forzar 18–21 vacíos
            fila[17] = ""; fila[18] = ""; fila[19] = ""; fila[20] = ""
        except Exception as e:
            st.warning(f"IA no devolvió formato válido ({e}). Se usará fallback.")
            fila = None

    # 2) Fallback determinístico (si IA falló o no está disponible)
    if fila is None:
        fila = [""] * 21
        fila[2]  = "Correo"                # Modo Reporte (default suave)
        fila[3]  = "Incidente"
        fila[4]  = texto.strip()           # Descripción
        fila[5]  = "Correo"                # Sistema (default suave)
        fila[7]  = "La Paz, Bolivia"       # Ubicación (default)
        fila[9]  = "Correo"                # Clasificación (default)
        fila[16] = "En investigación"

    # 3) Generar CODIGO en col 1
    if not ws:
        st.error("No hay conexión a Google Sheets. No se puede guardar.")
        st.stop()

    try:
        fila[0] = generar_codigo_inc(ws)
    except Exception as e:
        st.error(f"No pude generar el CODIGO: {e}")
        st.stop()

    # 4) Vista previa y guardado
    fila_out = fila + [datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")]
    st.dataframe(pd.DataFrame([fila_out], columns=COLUMNAS + ["Hora de reporte"]),
                 use_container_width=True)

    try:
        ws.append_row(fila_out, value_input_option="USER_ENTERED")
        st.success(f"✅ Guardado con CODIGO: {fila[0]}")
    except Exception as e:
        st.error(f"❌ No se pudo guardar en la hoja: {e}")
