import streamlit as st
import gspread
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/La_Paz")

# 1) CONFIG: Usa tu ID real y la pestaña exacta
SHEET_ID = "1UP_fwvXam8-1IXI-oUbNkqGzb0_IQXh7YsU7ziJVAqE"  # <-- tu ID
WORKSHEET_NAME = "Reportes"                                 # <-- tu pestaña

st.subheader("🔧 Diagnóstico de conexión a Google Sheets")

# 2) Validar que exista el bloque de credenciales
if "connections" not in st.secrets or "gsheets" not in st.secrets["connections"]:
    st.error("No encontré st.secrets['connections']['gsheets']. Revisa tus Secrets.")
    st.stop()

svc = st.secrets["connections"]["gsheets"]
required_keys = ["type","project_id","private_key_id","private_key","client_email","client_id","token_uri"]
missing = [k for k in required_keys if k not in svc or not svc[k]]
if missing:
    st.error(f"Faltan claves en las credenciales: {missing}")
    st.stop()

# 3) Mostrar (solo) el email del service account para que compartas la hoja
st.info(f"Comparte la hoja (Editor) con: **{svc['client_email']}**")

# 4) Intentar construir el cliente
try:
    # FIX opcional: a veces el private_key viene sin saltos reales:
    if "\\n" in svc["private_key"]:
        svc = dict(svc)  # copiar
        svc["private_key"] = svc["private_key"].replace("\\n", "\n")

    gc = gspread.service_account_from_dict(svc)
    st.success("Paso 1/3 OK: credenciales válidas.")
except Exception as e:
    st.exception(e)
    st.stop()

# 5) Abrir hoja por ID
try:
    sh = gc.open_by_key(SHEET_ID)
    st.success("Paso 2/3 OK: hoja abierta por ID.")
except Exception as e:
    st.error("No pude abrir la hoja por ID. ¿Es el ID correcto?")
    st.exception(e)
    st.stop()

# 6) Listar pestañas para confirmar nombre
try:
    tabs = [w.title for w in sh.worksheets()]
    st.write("Pestañas disponibles:", tabs)
    if WORKSHEET_NAME not in tabs:
        st.warning(f"No existe la pestaña '{WORKSHEET_NAME}'. Se intentará crearla.")
        try:
            ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=30)
            st.success(f"Pestaña '{WORKSHEET_NAME}' creada.")
        except Exception as e:
            st.error("No pude crear la pestaña. Créala manualmente y vuelve a ejecutar.")
            st.exception(e)
            st.stop()
    else:
        ws = sh.worksheet(WORKSHEET_NAME)
        st.success(f"Paso 3/3 OK: pestaña '{WORKSHEET_NAME}' abierta.")
except Exception as e:
    st.exception(e)
    st.stop()

# 7) Probar un append
if st.button("Hacer prueba de escritura (append_row)"):
    try:
        now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
        ws.append_row(["PING", now], value_input_option="USER_ENTERED")
        st.success("✅ Escribí una fila de prueba: ['PING', ahora]. Revisa la hoja.")
    except Exception as e:
        st.error("Fallo el append_row. Revisa permisos de edición de la hoja.")
        st.exception(e)
