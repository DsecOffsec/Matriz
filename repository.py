
import streamlit as st
import gspread
import pandas as pd
import re
from datetime import datetime, timedelta, date, time
from zoneinfo import ZoneInfo
from typing import Optional, List, Tuple

# =====================================================
# CONFIG (puedes editar estos valores o usar st.secrets)
# =====================================================
TZ = ZoneInfo("America/La_Paz")
SHEET_ID = "1UP_fwvXam8-1IXI-oUbNkqGzb0_IQXh7YsU7ziJVAqE"  # tu ID real
WORKSHEET_NAME = "Reportes"
try:
    gc = gspread.service_account_from_dict(st.secrets["connections"]["gsheets"])
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(WORKSHEET_NAME)
    st.success("✅ Conectado a Google Sheets correctamente")
except Exception as e:
    ws = None
    st.error(f"No se pudo conectar a Google Sheets: {e}")

# =====================================================
# UI: Título
# =====================================================
st.title("MATRIZ DSEC — Reinicio desde cero (Análisis previo + 1 párrafo)")

# =====================================================
# 1) Conector seguro a Google Sheets (opcional)
# =====================================================
def connect_sheets() -> Optional[gspread.Worksheet]:
    try:
        gc = gspread.service_account_from_dict(st.secrets["connections"]["gsheets"])
    except Exception as e:
        st.info("ℹ️ No hay credenciales válidas en st.secrets['connections']['gsheets']. Seguiremos sin guardar.")
        return None

    sid = SHEET_ID or st.text_input("SHEET_ID no encontrado en secrets. Pégalo aquí:", "", key="sheet_id_input")
    if not sid:
        return None

    try:
        sh = gc.open_by_key(sid)
        try:
            ws = sh.worksheet(WORKSHEET_NAME)
            return ws
        except Exception:
            # Crear worksheet si no existe
            ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=30)
            return ws
    except Exception as e:
        st.error(f"No pude abrir la hoja por ID. Detalle: {e}")
        return None

ws = connect_sheets()

# =====================================================
# 2) Definición de las 21 columnas
# =====================================================
COLUMNAS = [
    "CODIGO","Fecha y Hora de Apertura","Modo Reporte","Evento/ Incidente",
    "Descripción Evento/ Incidente","Sistema","Area","Ubicación","Impacto",
    "Clasificación","Acción Inmediata","Solución","Area de GTIC - Coordinando",
    "Encargado SI","Fecha y Hora de Cierre","Tiempo Solución","Estado",
    "Vulnerabilidad","Causa","ID Amenaza","Amenaza"
]

# Si el worksheet está vacío, escribir encabezados (una sola vez)
if ws:
    try:
        existing_headers = ws.row_values(1)
        if existing_headers != COLUMNAS + ["Hora de reporte"]:
            ws.resize(rows=1, cols=len(COLUMNAS)+1)
            ws.update("A1", [COLUMNAS + ["Hora de reporte"]])
    except Exception:
        pass

# =====================================================
# 3) Utilidades de fechas/horas y parsing
# =====================================================
HORA_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
DATE_RES = [
    re.compile(r"\b(20\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b"),
    re.compile(r"\b(0?[1-9]|[12]\d|3[01])/(0?[1-9]|1[0-2])/(20\d{2})\b"),
    re.compile(r"\b(0?[1-9]|[12]\d|3[01])-(0?[1-9]|1[0-2])-(20\d{2})\b"),
    re.compile(r"\b(0?[1-9]|[12]\d|3[01])/(0?[1-9]|1[0-2])\b"),
    re.compile(r"\b(0?[1-9]|[12]\d|3[01])-(0?[1-9]|1[0-2])\b"),
]

def _first_date_in_text(texto: str) -> Optional[date]:
    for rx in DATE_RES:
        m = rx.search(texto)
        if m:
            try:
                if len(m.groups()) == 3 and len(m.group(1)) == 4:  # YYYY-MM-DD
                    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    return date(y, mo, d)
                elif len(m.groups()) == 3:  # DD/MM/YYYY o DD-MM-YYYY
                    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    return date(y, mo, d)
                elif len(m.groups()) == 2:  # DD/MM o DD-MM (año actual)
                    d, mo = int(m.group(1)), int(m.group(2))
                    return date(datetime.now(TZ).year, mo, d)
            except Exception:
                continue
    return None

def extraer_horas(texto: str) -> List[str]:
    return [f"{h}:{m}" for h, m in HORA_RE.findall(texto)]

def fechas_desde_texto(texto: str) -> Tuple[str, str]:
    horas = extraer_horas(texto)
    if not horas:
        return "", ""
    base_date = _first_date_in_text(texto) or datetime.now(TZ).date()
    apertura = datetime.combine(base_date, datetime.strptime(horas[0], "%H:%M").time())
    cierre = None
    if len(horas) > 1:
        h_last = datetime.combine(base_date, datetime.strptime(horas[-1], "%H:%M").time())
        if h_last < apertura:
            h_last += timedelta(days=1)
        cierre = h_last
    return apertura.strftime("%Y-%m-%d %H:%M"), cierre.strftime("%Y-%m-%d %H:%M") if cierre else ""

def calcula_tiempo_desde_texto(texto: str) -> str:
    horas = 0; minutos = 0
    for m in re.finditer(r"(\d+)\s*(horas|hora|h)\b", texto, flags=re.IGNORECASE):
        horas += int(m.group(1))
    for m in re.finditer(r"(\d+)\s*(minutos|min|m)\b", texto, flags=re.IGNORECASE):
        minutos += int(m.group(1))
    total = horas*60 + minutos
    return f"{total//60:02d}:{total%60:02d}" if total>0 else ""

def calcula_tiempo_solucion(a_str: str, c_str: str) -> str:
    if not a_str or not c_str:
        return ""
    try:
        a = datetime.strptime(a_str, "%Y-%m-%d %H:%M")
        c = datetime.strptime(c_str, "%Y-%m-%d %H:%M")
        if c < a: return ""
        delta = c - a
        total_min = int(delta.total_seconds() // 60)
        return f"{total_min//60:02d}:{total_min%60:02d}"
    except Exception:
        return ""

# =====================================================
# 4) Inferencias simples
# =====================================================
MODO_KEYWORDS = {
    "Correo": ["correo", "email", "outlook", "mail"],
    "Jira": ["jira", "ticket"],
    "Teléfono": ["llamada", "telefono", "teléfono"],
    "Monitoreo": ["zabbix", "monitor", "monitoreo", "alerta"],
    "WhatsApp": ["whatsapp", "wa"]
}
SISTEMAS = ["Firewall","VPN","Correo","Active Directory","Antivirus","Proxy","SIEM","Cortex XDR","Zabbix","Check Point","Cisco ISE","Umbrella","Tenable","Windows","Linux","Red"]
AREAS = ["DSEC - Seguridad","DITC - Infraestructura","DSTC - Soporte Técnico","DISC - Sistemas","GTIC","RRHH","Finanzas","Operaciones","Comercial","Gerencia"]
UBIC_CIUDADES = ["La Paz","El Alto","Cochabamba","Santa Cruz","Tarija","Potosí","Oruro","Sucre","Beni","Pando"]
CLASIF = ["Malware","Phishing","Credenciales","Política","Red","VPN","Correo","Firewall","Sistema","Usuarios","Otros"]

def detectar_modo_reporte(texto: str) -> Optional[str]:
    t = texto.lower()
    for modo, kws in MODO_KEYWORDS.items():
        if any(k in t for k in kws):
            return modo
    return None

def infer_sistema(texto: str) -> str:
    t = texto.lower()
    for s in SISTEMAS:
        if s.lower() in t:
            return s
    if "vpn" in t: return "VPN"
    if "correo" in t or "outlook" in t: return "Correo"
    if "firewall" in t or "checkpoint" in t: return "Firewall"
    if "zabbix" in t: return "Zabbix"
    if "cortex" in t: return "Cortex XDR"
    return ""

def infer_area(texto: str) -> str:
    t = texto.lower()
    for a in AREAS:
        if a.lower() in t:
            return a
    if "soporte" in t: return "DSTC - Soporte Técnico"
    if "seguridad" in t: return "DSEC - Seguridad"
    if "infraestructura" in t: return "DITC - Infraestructura"
    if "sistemas" in t: return "DISC - Sistemas"
    return ""

def detectar_ubicacion(texto: str) -> str:
    for u in UBIC_CIUDADES:
        if re.search(rf"\b{re.escape(u)}\b", texto, flags=re.IGNORECASE):
            return f"{u}, Bolivia"
    return ""

def infer_accion_inmediata(texto: str) -> str:
    t = texto.lower()
    if "bloque" in t:
        return "Se aplicó bloqueo inicial"
    if "reinicio" in t or "reinició" in t:
        return "Reinicio del servicio/equipo"
    if "notific" in t or "comunic" in t:
        return "Notificación a responsable/usuario"
    return ""

def infer_solucion(texto: str) -> str:
    t = texto.lower()
    if "solucionado" in t or "resuelto" in t or "normalizado" in t:
        return "Incidente solucionado y normalizado"
    if "instaló" in t or "actualizó" in t:
        return "Actualización/instalación aplicada"
    return ""

def infer_clasificacion(texto: str) -> str:
    t = texto.lower()
    if "phishing" in t: return "Phishing"
    if "malware" in t or "virus" in t: return "Malware"
    if "vpn" in t: return "VPN"
    if "correo" in t: return "Correo"
    if "firewall" in t or "checkpoint" in t: return "Firewall"
    if "red" in t or "switch" in t or "router" in t: return "Red"
    if "credencial" in t or "password" in t: return "Credenciales"
    return "Otros"

# =====================================================
# 5) Fase 0: extracción estructurada y 1 párrafo
# =====================================================
def extract_structured_fields(texto: str) -> dict:
    ap_auto, ci_auto = fechas_desde_texto(texto)
    tiempo_auto = calcula_tiempo_desde_texto(texto) or calcula_tiempo_solucion(ap_auto, ci_auto)

    rec = {
        "CODIGO": "",
        "Fecha y Hora de Apertura": ap_auto,
        "Modo Reporte": detectar_modo_reporte(texto) or "Otro",
        "Evento/ Incidente": "Incidente",
        "Descripción Evento/ Incidente": texto.strip(),
        "Sistema": infer_sistema(texto) or "Firewall",
        "Area": infer_area(texto),
        "Ubicación": detectar_ubicacion(texto) or "La Paz, Bolivia",
        "Impacto": "",
        "Clasificación": infer_clasificacion(texto),
        "Acción Inmediata": infer_accion_inmediata(texto),
        "Solución": infer_solucion(texto),
        "Area de GTIC - Coordinando": infer_area(texto),
        "Encargado SI": "",
        "Fecha y Hora de Cierre": ci_auto,
        "Tiempo Solución": tiempo_auto,
        "Estado": "Cerrado" if ci_auto else "En investigación",
        "Vulnerabilidad": "",
        "Causa": "",
        "ID Amenaza": "",
        "Amenaza": "",
    }
    return rec

def one_paragraph_summary(rec: dict) -> str:
    partes = []
    if rec.get("Fecha y Hora de Apertura"): partes.append(f"Apertura: {rec['Fecha y Hora de Apertura']}.")
    if rec.get("Modo Reporte"): partes.append(f"Modo: {rec['Modo Reporte']}.")
    if rec.get("Sistema"): partes.append(f"Sistema: {rec['Sistema']}.")
    if rec.get("Area"): partes.append(f"Área: {rec['Area']}.")
    if rec.get("Ubicación"): partes.append(f"Ubicación: {rec['Ubicación']}.")
    if rec.get("Clasificación"): partes.append(f"Clasificación: {rec['Clasificación']}.")
    if rec.get("Descripción Evento/ Incidente"): partes.append(f"Descripción: {rec['Descripción Evento/ Incidente']}")
    if rec.get("Acción Inmediata"): partes.append(f"Acción inmediata: {rec['Acción Inmediata']}.")
    if rec.get("Solución"): partes.append(f"Solución: {rec['Solución']}.")
    if rec.get("Fecha y Hora de Cierre"): partes.append(f"Cierre: {rec['Fecha y Hora de Cierre']}.")
    if rec.get("Tiempo Solución"): partes.append(f"Tiempo de solución: {rec['Tiempo Solución']}.")
    if rec.get("Estado"): partes.append(f"Estado: {rec['Estado']}.")
    return " ".join(partes).strip()

# =====================================================
# 6) Generación de CÓDIGO: "INC-[DD]-[MM]-[NNN]"
#     NNN = correlativo del día (por sede) según filas existentes
# =====================================================
def generar_codigo_inc_formato(ws_obj: Optional[gspread.Worksheet]) -> str:
    hoy = datetime.now(TZ)
    dd = hoy.strftime("%d")
    mm = hoy.strftime("%m")
    pref = f"INC-{dd}-{mm}-"
    correl = 1
    if ws_obj:
        try:
            col1 = ws_obj.col_values(1)  # columna CODIGO
            existentes = [x for x in col1 if x.startswith(pref)]
            if existentes:
                nums = []
                for e in existentes:
                    m = re.search(r"INC-\d{2}-\d{2}-(\d{3})$", e.strip())
                    if m:
                        nums.append(int(m.group(1)))
                if nums:
                    correl = max(nums) + 1
        except Exception:
            pass
    return f"{pref}{correl:03d}"

# =====================================================
# 7) UI principal
# =====================================================
st.markdown("Escribe el incidente en **un solo párrafo**. Primero verás **qué entendimos** y luego la fila de **21 columnas**.")
texto = st.text_area("Descripción del incidente", height=180)

enable_save = st.toggle("Guardar en Google Sheets", value=bool(ws), disabled=not bool(ws))

if st.button("Reportar", use_container_width=True):
    if not texto.strip():
        st.warning("Por favor, describe el incidente antes de continuar.")
        st.stop()

    rec = extract_structured_fields(texto)
    st.subheader("🧩 Resumen en un párrafo (interpretación previa)")
    st.write(one_paragraph_summary(rec))

    # Construcción de fila y código
    fila = [ (rec.get(col) or "").strip() for col in COLUMNAS ]
    fila[0] = generar_codigo_inc_formato(ws)
    ts = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    fila_out = fila + [ts]

    st.subheader("✅ Vista previa de la fila (21 columnas + Hora de reporte)")
    st.dataframe(pd.DataFrame([fila_out], columns=COLUMNAS + ["Hora de reporte"]), use_container_width=True)

if ws:
    try:
        ws.append_row(fila_out, value_input_option="USER_ENTERED")
        st.success("✅ Incidente guardado en Google Sheets")
    except Exception as e:
        st.error(f"No se pudo guardar en la hoja: {e}")

