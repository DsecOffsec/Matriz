
import streamlit as st
import gspread
import pandas as pd
import re
import json
from typing import Optional, List, Tuple
from datetime import datetime, timedelta, date, time
from zoneinfo import ZoneInfo
import google.generativeai as genai

# =========================================
# Título
# =========================================
st.title("MATRIZ DE REPORTES DSEC — versión con Análisis Previo (1 párrafo)")

# =========================================
# Conexiones y configuración
# =========================================
# Nota: Mantén tus secretos en st.secrets
# st.secrets["connections"]["gsheets"] debe contener credenciales de servicio de Google
# st.secrets["GOOGLE_API_KEY"] para Gemini si deseas usar la fase LLM (opcional)

try:
    gc = gspread.service_account_from_dict(st.secrets["connections"]["gsheets"])
    SHEET_ID = st.secrets.get("SHEET_ID", None) or st.secrets["connections"].get("SHEET_ID", None)
except Exception as _e:
    gc = None
    SHEET_ID = None
    st.info("ℹ️ Aún no configuraste las credenciales o el SHEET_ID en st.secrets. Puedes seguir probando sin guardar en Sheets.")

if SHEET_ID and gc:
    try:
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet("Reportes")
    except Exception as _e:
        ws = None
        st.warning("No pude abrir la hoja 'Reportes'. Verifica el SHEET_ID y el nombre de la hoja.")
else:
    ws = None

# Gemini (opcional)
TZ = ZoneInfo("America/La_Paz")
GEMINI_READY = False
if "GOOGLE_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
        model = genai.GenerativeModel("gemini-1.5-flash")
        GEMINI_READY = True
    except Exception as _e:
        GEMINI_READY = False

# =========================================
# Columnas canónicas (21)
# =========================================
COLUMNAS = [
    "CODIGO","Fecha y Hora de Apertura","Modo Reporte","Evento/ Incidente",
    "Descripción Evento/ Incidente","Sistema","Area","Ubicación","Impacto",
    "Clasificación","Acción Inmediata","Solución","Area de GTIC - Coordinando",
    "Encargado SI","Fecha y Hora de Cierre","Tiempo Solución","Estado",
    "Vulnerabilidad","Causa","ID Amenaza","Amenaza"
]

# =========================================
# Utilidades de tiempo/fechas
# =========================================
HORA_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")  # HH:MM
# 2025-09-26, 26/09/2025, 26-09-2025, 26/9 etc.
DATE_RES = [
    re.compile(r"\b(20\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b"),              # YYYY-MM-DD
    re.compile(r"\b(0?[1-9]|[12]\d|3[01])/(0?[1-9]|1[0-2])/(20\d{2})\b"),           # DD/MM/YYYY
    re.compile(r"\b(0?[1-9]|[12]\d|3[01])-(0?[1-9]|1[0-2])-(20\d{2})\b"),           # DD-MM-YYYY
    re.compile(r"\b(0?[1-9]|[12]\d|3[01])/(0?[1-9]|1[0-2])\b"),                     # DD/MM (asume año actual)
    re.compile(r"\b(0?[1-9]|[12]\d|3[01])-(0?[1-9]|1[0-2])\b"),                     # DD-MM (asume año actual)
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
                elif len(m.groups()) == 2:  # DD/MM o DD-MM (asumimos año actual)
                    d, mo = int(m.group(1)), int(m.group(2))
                    return date(datetime.now(TZ).year, mo, d)
            except Exception:
                continue
    return None

def extraer_horas_any(texto: str) -> List[str]:
    return [f"{h}:{m}" for h, m in HORA_RE.findall(texto)]

def fechas_desde_texto(texto: str) -> Tuple[str, str]:
    """
    Heurística:
    - Apertura/Cierre en formato "YYYY-MM-DD HH:MM" si hay horas.
    - Si hay fecha (DD/MM[/YYYY] o YYYY-MM-DD), úsala; si no, usa hoy.
    - Si hay >=2 horas, cierre = última; si la última < primera, suma 1 día.
    - Si no hay horas, retorna ("","").
    """
    horas = extraer_horas_any(texto)
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
    a_str = apertura.strftime("%Y-%m-%d %H:%M")
    c_str = cierre.strftime("%Y-%m-%d %H:%M") if cierre else ""
    return a_str, c_str

def calcula_tiempo_desde_texto(texto: str) -> str:
    """
    Busca patrones como 'X horas', 'X h', 'Y minutos', 'Y min'.
    Retorna 'HH:MM' si encuentra algo, de lo contrario ''.
    """
    horas = 0
    minutos = 0
    for m in re.finditer(r"(\d+)\s*(horas|hora|h)\b", texto, flags=re.IGNORECASE):
        horas += int(m.group(1))
    for m in re.finditer(r"(\d+)\s*(minutos|min|m)\b", texto, flags=re.IGNORECASE):
        minutos += int(m.group(1))
    total = horas * 60 + minutos
    if total <= 0:
        return ""
    return f"{total//60:02d}:{total%60:02d}"

def calcula_tiempo_solucion(a_str: str, c_str: str) -> str:
    if not a_str or not c_str:
        return ""
    try:
        a = datetime.strptime(a_str, "%Y-%m-%d %H:%M")
        c = datetime.strptime(c_str, "%Y-%m-%d %H:%M")
        if c < a:
            return ""
        delta = c - a
        total_min = int(delta.total_seconds() // 60)
        return f"{total_min//60:02d}:{total_min%60:02d}"
    except Exception:
        return ""

# =========================================
# Inferencias / Normalizaciones sencillas
# =========================================
MODO_KEYWORDS = {
    "Correo": ["correo", "email", "outlook", "mail"],
    "Jira": ["jira", "ticket"],
    "Teléfono": ["llamada", "telefono", "teléfono"],
    "Monitoreo": ["zabbix", "monitor", "monitoreo", "alerta"],
    "WhatsApp": ["whatsapp", "wa"]
}

SISTEMAS = [
    "Firewall","VPN","Correo","Active Directory","Antivirus","Proxy","SIEM","Cortex XDR",
    "Zabbix","Check Point","Cisco ISE","Umbrella","Tenable","Windows","Linux","Red",
]

AREAS = [
    "DSEC - Seguridad","DITC - Infraestructura","DSTC - Soporte Técnico","DISC - Sistemas",
    "GTIC","RRHH","Finanzas","Operaciones","Comercial","Gerencia"
]

UBIC_CIUDADES = ["La Paz","El Alto","Cochabamba","Santa Cruz","Tarija","Potosí","Oruro","Sucre","Beni","Pando"]

CLASIF = [
    "Malware","Phishing","Credenciales","Política","Red","VPN","Correo","Firewall","Sistema","Usuarios","Otros"
]

def norm_opcion(valor: Optional[str], opciones: List[str]) -> Optional[str]:
    if not valor:
        return None
    v = valor.strip().lower()
    for op in opciones:
        if v == op.lower():
            return op
    # aproximación
    for op in opciones:
        if v in op.lower() or op.lower() in v:
            return op
    return None

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
    # heurística por palabras
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

def detectar_ubicacion_ext(texto: str) -> str:
    for u in UBIC_CIUDADES:
        if re.search(rf"\b{re.escape(u)}\b", texto, flags=re.IGNORECASE):
            return f"{u}, Bolivia"
    return ""

def infer_accion_inmediata(texto: str) -> str:
    t = texto.lower()
    if "se bloqueó" in t or "bloqueo" in t or "bloqueado" in t:
        return "Se aplicó bloqueo inicial"
    if "se reinició" in t or "reinicio" in t:
        return "Reinicio del servicio/equipo"
    if "se comunicó" in t or "se notificó" in t:
        return "Notificación a responsable/usuario"
    return ""

def infer_solucion(texto: str) -> str:
    t = texto.lower()
    if "solucionado" in t or "resuelto" in t or "normalizado" in t:
        return "Incidente solucionado y normalizado"
    if "se instaló" in t or "se actualizó" in t:
        return "Actualización/instalación aplicada"
    return ""

def infer_area_coordinando(texto: str) -> str:
    t = texto.lower()
    for a in AREAS:
        if a.lower() in t:
            return a
    if "gtic" in t:
        return "GTIC"
    if "dsec" in t:
        return "DSEC - Seguridad"
    return ""

def extraer_encargado(texto: str) -> str:
    # Busca patrones tipo: Encargado: Nombre Apellido / Responsable: ...
    m = re.search(r"(encargado|responsable)\s*:\s*([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+)", texto, flags=re.IGNORECASE)
    if m:
        return m.group(2).strip()
    return ""

def normaliza_clasificacion_final(valor: str) -> str:
    if not valor:
        return ""
    v = valor.strip().lower()
    for c in CLASIF:
        if v == c.lower():
            return c
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

# =========================================
# Sanitizado/normalización para LLM (opcional)
# =========================================
def sanitize_text(s: str) -> str:
    s = re.sub(r"[|]{2,}", "|", s)
    s = s.replace("\t", " ").replace("\n", " ").strip()
    return s

def assert_20_pipes(s: str) -> None:
    # 21 columnas => 20 pipes
    if s.count("|") < 20:
        raise ValueError("El modelo no devolvió 21 campos separados por '|'")

def normalize_21_fields(s: str) -> Tuple[List[str], List[str]]:
    tokens = [t.strip() for t in s.split("|")]
    avisos = []
    if len(tokens) < 21:
        tokens += [""] * (21 - len(tokens))
        avisos.append("Se completaron campos vacíos para alcanzar 21 columnas.")
    elif len(tokens) > 21:
        tokens = tokens[:21]
        avisos.append("Se truncaron campos para ajustarse a 21 columnas.")
    return tokens, avisos

def clean_empty_tokens(tokens: List[str]) -> List[str]:
    return [t if t is not None else "" for t in tokens]

# =========================================
# Núcleo pedido: análisis previo y resumen 1 párrafo
# =========================================
def extract_structured_fields(texto: str) -> dict:
    ap_auto, ci_auto = fechas_desde_texto(texto)
    tiempo_auto = calcula_tiempo_desde_texto(texto) or calcula_tiempo_solucion(ap_auto, ci_auto)

    modo = norm_opcion(detectar_modo_reporte(texto), ["Correo","Jira","Teléfono","Monitoreo","WhatsApp","Otro"]) or "Otro"
    sistema = infer_sistema(texto)
    area   = infer_area(texto)
    ubic   = detectar_ubicacion_ext(texto)
    accion = infer_accion_inmediata(texto)
    sol    = infer_solucion(texto)
    gtic   = infer_area_coordinando(texto)
    enc    = extraer_encargado(texto)
    clas   = normaliza_clasificacion_final("") or infer_clasificacion(texto) or "Otros"

    estado = "Cerrado" if ci_auto else "En investigación"

    rec = {
        "CODIGO": "",
        "Fecha y Hora de Apertura": ap_auto,
        "Modo Reporte": modo,
        "Evento/ Incidente": "Incidente",
        "Descripción Evento/ Incidente": texto.strip(),
        "Sistema": sistema or "Firewall",
        "Area": area,
        "Ubicación": ubic or "La Paz, Bolivia",
        "Impacto": "",
        "Clasificación": clas,
        "Acción Inmediata": accion,
        "Solución": sol,
        "Area de GTIC - Coordinando": gtic,
        "Encargado SI": enc,
        "Fecha y Hora de Cierre": ci_auto,
        "Tiempo Solución": tiempo_auto,
        "Estado": estado,
        "Vulnerabilidad": "",
        "Causa": "",
        "ID Amenaza": "",
        "Amenaza": "",
    }
    return rec

def one_paragraph_summary(rec: dict) -> str:
    partes = []
    if rec.get("Fecha y Hora de Apertura"):
        partes.append(f"Apertura: {rec['Fecha y Hora de Apertura']}.")
    if rec.get("Modo Reporte"):
        partes.append(f"Modo de reporte: {rec['Modo Reporte']}.")
    if rec.get("Sistema"):
        partes.append(f"Sistema afectado: {rec['Sistema']}.")
    if rec.get("Area"):
        partes.append(f"Área: {rec['Area']}.")
    if rec.get("Ubicación"):
        partes.append(f"Ubicación: {rec['Ubicación']}.")
    if rec.get("Clasificación"):
        partes.append(f"Clasificación: {rec['Clasificación']}.")
    if rec.get("Descripción Evento/ Incidente"):
        partes.append(f"Descripción: {rec['Descripción Evento/ Incidente']}")
    if rec.get("Acción Inmediata"):
        partes.append(f"Acción inmediata: {rec['Acción Inmediata']}.")
    if rec.get("Solución"):
        partes.append(f"Solución: {rec['Solución']}.")
    if rec.get("Area de GTIC - Coordinando"):
        partes.append(f"Coordinó: {rec['Area de GTIC - Coordinando']}.")
    if rec.get("Fecha y Hora de Cierre"):
        partes.append(f"Cierre: {rec['Fecha y Hora de Cierre']}.")
    if rec.get("Tiempo Solución"):
        partes.append(f"Tiempo de solución: {rec['Tiempo Solución']}.")
    if rec.get("Estado"):
        partes.append(f"Estado: {rec['Estado']}.")
    if rec.get("Encargado SI"):
        partes.append(f"Encargado: {rec['Encargado SI']}.")
    return " ".join(partes).strip()

# =========================================
# Generación de CODIGO (no afectar tu lógica)
# =========================================
def _fallback_generar_codigo_inc(ws_obj, apertura_val: Optional[str]) -> str:
    """Genera un código YYYYMMDD-XXX incremental por día (fallback)."""
    hoy = datetime.now(TZ).strftime("%Y%m%d")
    base = f"{hoy}-"
    num = 1
    if ws_obj:
        try:
            data = ws_obj.col_values(1)  # CODIGO está en col 1
            existentes = [x for x in data if x.startswith(base)]
            if existentes:
                # extrae los numeritos finales
                nums = []
                for e in existentes:
                    m = re.search(r"-(\d{3})$", e.strip())
                    if m:
                        nums.append(int(m.group(1)))
                if nums:
                    num = max(nums) + 1
        except Exception:
            pass
    return f"{base}{num:03d}"

def safe_generar_codigo_inc(ws_obj, apertura_val: Optional[str]) -> str:
    """Si el usuario ya tiene su generar_codigo_inc(ws, apertura), úsalo. Si no, usa fallback."""
    # Intentar usar una función externa si existe en el entorno (no aplicable en script único)
    try:
        # Si está definida en este archivo porque el usuario pegó su propia función, úsala
        if "generar_codigo_inc" in globals() and callable(globals()["generar_codigo_inc"]):
            return globals()["generar_codigo_inc"](ws_obj, apertura_val)
    except Exception:
        pass
    return _fallback_generar_codigo_inc(ws_obj, apertura_val)

# =========================================
# UI
# =========================================
st.markdown("""
### 📝 Instrucciones
1. Escribe el incidente en **un solo párrafo** con la mayor cantidad de detalles (fechas/horas, sistema, área, acciones, cierre).
2. Al presionar **Reportar**, verás primero **qué entendió el sistema en un párrafo** (sin forzar columnas).
3. Luego se arma la **fila de 21 columnas** con **CODIGO** generado (sin alterar tu lógica si ya la tienes).
""")

user_question = st.text_area("Describe el incidente aquí…", height=180, placeholder="Ej: A las 09:15 se detectó alerta en Zabbix por caída de VPN en La Paz. DSEC coordinó, se notificó a Soporte; se aplicó reinicio a las 09:40 y normalizó. Encargado: Juan Pérez.")

use_llm = st.toggle("Usar Gemini para completar campos ambiguos (opcional)", value=False, disabled=not GEMINI_READY)
guardar = st.toggle("Guardar en Google Sheets", value=True if ws else False, disabled=ws is None)

if st.button("Reportar", use_container_width=True):
    if not user_question.strip():
        st.warning("Por favor, describe el incidente antes de continuar.")
        st.stop()

    with st.spinner("Analizando el reporte…"):
        # ---------- FASE 0: Análisis previo ----------
        rec = extract_structured_fields(user_question)

        st.subheader("🧩 Resumen en un párrafo (interpretación previa)")
        st.write(one_paragraph_summary(rec))

        # ---------- (Opcional) FASE LLM ----------
        if use_llm and GEMINI_READY:
            prompt = (
                "Devuelve exactamente 21 campos separados por '|' en el siguiente orden: "
                + "|".join(COLUMNAS) +
                ". Campos 18 a 21 déjalos vacíos. Texto:\n" + user_question.strip()
            )
            try:
                resp = model.generate_content([prompt], generation_config={"temperature": 0.2})
                response_text = resp.text if hasattr(resp, "text") else str(resp)
                cleaned = sanitize_text(response_text)
                cleaned = re.sub(r"\s\|\s", " ; ", cleaned)
                assert_20_pipes(cleaned)
                fila_llm, avisos = normalize_21_fields(cleaned)
                fila_llm = clean_empty_tokens(fila_llm)
                # Forzar vacíos 18–21 por política
                fila_llm[17] = ""; fila_llm[18] = ""; fila_llm[19] = ""; fila_llm[20] = ""
                # Suavemente completar rec solo si está vacío
                for i, col in enumerate(COLUMNAS):
                    if (rec.get(col) or "") == "" and (fila_llm[i] or "") != "":
                        rec[col] = fila_llm[i]
                if avisos:
                    st.caption("LLM avisos: " + "; ".join(avisos))
            except Exception as e:
                st.info(f"No se pudo usar el LLM: {e}")

        # ---------- FASE 1: Construcción de la fila ----------
        fila = [ (rec.get(col) or "").strip() for col in COLUMNAS ]

        # CODIGO (no romper tu lógica existente)
        codigo = safe_generar_codigo_inc(ws, fila[1] if fila[1] else None)
        fila[0] = codigo

        # Timestamp adicional para la hoja (columna auxiliar)
        registro_ts = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
        columnas_mas = COLUMNAS + ["Hora de reporte"]
        fila_con_ts = fila + [registro_ts]

        st.subheader("✅ Vista previa de la fila (21 columnas + Hora de reporte)")
        st.dataframe(pd.DataFrame([fila_con_ts], columns=columnas_mas), use_container_width=True)

        if guardar and ws:
            try:
                ws.append_row(fila_con_ts, value_input_option="USER_ENTERED")
                st.success(f"Incidente registrado correctamente: {codigo}")
            except Exception as e:
                st.error(f"No se pudo escribir en la hoja: {e}")
        elif guardar and not ws:
            st.warning("No se guardó porque no se pudo abrir la hoja. Revisa tus credenciales.")








