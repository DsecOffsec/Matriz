# --- IMPORTS ---
import streamlit as st
import gspread
import pandas as pd
import re
import json
from typing import Optional, Iterable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Vertex AI
from vertexai import init as vertex_init
from vertexai.generative_models import GenerativeModel
from google.oauth2.service_account import Credentials

# --- CONFIG GOOGLE SHEETS (lo que ya tenías) ---
# gc = gspread.service_account_from_dict(st.secrets["connections"]["gsheets"])
# SHEET_ID = "..." ; sh = gc.open_by_key(SHEET_ID) ; ws = sh.worksheet("Reportes")

st.title("MATRIZ DE REPORTES DSEC")

# --- CONFIG VERTEX AI (usa tu Service Account en secrets) ---
PROJECT_ID = st.secrets["GCP_PROJECT_ID"]          # p.ej. "mi-proyecto-gcp"
REGION     = st.secrets.get("VERTEX_REGION", "us-central1")
SA_INFO    = st.secrets["GCP_SERVICE_ACCOUNT_JSON"]  # JSON completo de la SA

creds = Credentials.from_service_account_info(SA_INFO)
vertex_init(project=PROJECT_ID, location=REGION, credentials=creds)

# Usa el alias de modelo SIN sufijo de versión para evitar 404 por región/permisos
model = GenerativeModel("gemini-1.5-flash")

TZ = ZoneInfo("America/La_Paz")


st.markdown("""
### 📝 Instrucciones para registrar un incidente

Por favor, describe el incidente en **un solo párrafo** incluyendo estos campos **obligatorios**:

1. **Fecha y hora de apertura** — La hora de inicio del incidente/alerta con hora y AM/PM.
2. **Modo de reporte** - Si lo reportaron por correo, JIRA, monitoreo, llamada, otros, etc.
3. **Sistema afectado** — Por ejemplo: Correo, VPN, Antivirus, Firewall, etc.  
4. **Área afectada** — El departamento o unidad donde se detectó el problema.  
5. **Acción inmediata tomada** — Lo que hizo el usuario para mitigar el problema.  
6. **Solución aplicada** — Acción final que resolvió el incidente.  
7. **Área de GTIC que coordinó** — DSEC - Seguridad, DITC - Infraestructura, DSTC - Soporte Técnico, DISC - Sistemas.  
8. **Encargado** - El responsable del incidente/alerta.
""")

COLUMNAS = [
    "CODIGO","Fecha y Hora de Apertura","Modo Reporte","Evento/ Incidente",
    "Descripción Evento/ Incidente","Sistema","Area","Ubicación","Impacto",
    "Clasificación","Acción Inmediata","Solución","Area de GTIC - Coordinando",
    "Encargado SI","Fecha y Hora de Cierre","Tiempo Solución","Estado",
    "Vulnerabilidad","Causa","ID Amenaza","Amenaza"
]

# Valores válidos / normalizadores rápidos
MODO_VALIDOS = {"correo","jira","teléfono","telefono","monitoreo","webex","whatsapp","otro"}
IMPACTO_VALIDOS = {"alto","medio","bajo"}
ESTADO_VALIDOS = {"cerrado","en investigación"}

# ---------------------------
# Guías (texto de referencia)
# ---------------------------

CODE_RE = re.compile(r'^\d+\.\d+$')

# ---------------------------
# Clasificaciones válidas (lista cerrada)
# ---------------------------
CLASIF_CANON = {
    "acceso no autorizado": "Acceso no autorizado",
    "modificación de recursos no autorizado": "Modificación de recursos no autorizado",
    "uso inapropiado de recursos": "Uso inapropiado de recursos",
    "no disponibilidad de recursos": "No disponibilidad de recursos",
    "multicomponente": "Multicomponente",
    "exploración de vulnerabilidades": "Exploración de Vulnerabilidades",
    "otros": "Otros",
}
CLASIF_TEXTO = "\n".join([f"- {v}" for v in CLASIF_CANON.values()])

# ---------------------------
# Prompt (CODIGO lo genera backend y no se inventan fechas)
# ---------------------------
persona = f"""
Eres un asistente experto en seguridad informática. Convierte el reporte en UNA SOLA LÍNEA con exactamente 21 valores separados por | (pipe). Sin encabezados, sin markdown, sin explicaciones, sin saltos de línea. Exactamente 20 pipes.
{COLUMNAS}

Reglas:
- Las claves 18-21 ("Vulnerabilidad","Causa","ID Amenaza","Amenaza") siempre vacías.
- No inventes fechas. Usa "YYYY-MM-DD HH:MM" solo si el texto menciona día/mes/año; si no, deja vacío.
- Zona horaria: America/La_Paz. En el año 2025
- NO inventes ni completes los campos 18 (Vulnerabilidad), 19 (Causa), 20 (ID Amenaza) y 21 (Amenaza).
  Déjalos vacíos siempre.
- NO inventes fechas: si el reporte no incluye una fecha explícita con día/mes/año (p. ej., "2025-08-10", "10/08/2025" o "10 de agosto de 2025"), deja vacíos los campos de fecha. Si solo hay horas, no pongas fecha.
- Importante: NO uses el carácter | dentro de ningún campo. Si necesitas separar ideas usa ; (punto y coma).
- Responde únicamente la línea con 21 campos separados por | (exactamente 20 pipes), sin comentarios ni texto adicional.

Columnas y formato:
1. CODIGO → (dejar vacío; lo genera el sistema).
2. Fecha y Hora de Apertura → YYYY-MM-DD HH:MM, solo si se menciona (con día/mes/año explícitos).
3. Modo Reporte → valores válidos (Correo, Jira, Teléfono, Monitoreo, …).
4. Evento/ Incidente → Evento | Incidente.
5. Descripción Evento/ Incidente → resumen claro y profesional.
6. Sistema → (VPN, Correo, Active Directory, …).
7. Area
8. Ubicación
9. Impacto → Alto | Medio | Bajo.
10. Clasificación → elige exactamente UNO de: 
{CLASIF_TEXTO}
11. Acción Inmediata
12. Solución
13. Area de GTIC - Coordinando → (DSEC - Seguridad, DITC - Infraestructura, DSTC - Soporte Técnico, DISC - Sistemas, …).
14. Encargado SI → solo si se menciona; no inventes nombres.
15. Fecha y Hora de Cierre → YYYY-MM-DD HH:MM, solo si se menciona (con día/mes/año explícitos).
16. Tiempo Solución → “X horas Y minutos” si puedes calcular (Cierre − Apertura); si no, vacío.
17. Estado → Cerrado | En investigación.
18. Vulnerabilidad → Vacio
19. Causa → vacío.
20. ID Amenaza → Vacio
21. Amenaza → vacío.

[REPORTE DE ENTRADA]:
"""

# ---------------------------
# Utilidades de saneamiento / validación
# ---------------------------
def parse_model_output_to_dict(raw: str) -> dict | None:
    # Intenta JSON directo
    s = raw.strip()
    # Quitar cercos accidentales
    s = s.strip('`').strip()
    try:
        obj = json.loads(s)
        if isinstance(obj, dict) and all(k in obj for k in COLUMNAS):
            return obj
    except Exception:
        pass
    return None

def build_row_from_record(rec: dict) -> list[str]:
    # Mapea por nombre → orden canónico
    fila = [ (rec.get(col) or "").strip() for col in COLUMNAS ]
    return fila

def fallback_parse_pipes(raw: str) -> list[str]:
    cleaned = sanitize_text(raw)
    parts, _ = normalize_21_fields(cleaned)
    # “Evento/ Incidente” a valor canónico
    parts[3] = norm_evento_incidente(parts[3])
    # Forzar vacíos 18–21
    parts[17] = ""; parts[18] = ""; parts[19] = ""; parts[20] = ""
    return parts
    
def sanitize_text(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^```.*?\n", "", s, flags=re.DOTALL)
    s = re.sub(r"```$", "", s)
    s = s.replace("```", "")
    s = s.replace("\n", " ").replace("\r", " ")
    s = s.replace("“", '"').replace("”", '"').replace("’", "'")
    m = re.search(r"[^|\n]*\|[^|\n]*\|", s)
    if m:
        s = s[m.start():]
    return s.strip().strip('"').strip()

def assert_20_pipes(s: str):
    """Muestra un aviso si la línea no tiene exactamente 20 pipes (21 campos)."""
    cnt = s.count("|")
    if cnt != 20:
        st.info(f"Se detectaron {cnt+1} campos; se fusionará el excedente en 'Descripción'.")

def normalize_21_fields(raw: str) -> Tuple[List[str], List[str]]:
    avisos = []
    parts = [p.strip() for p in raw.split("|")]
    original_count = len(parts)
    if original_count > 21:
        # Fusiona el excedente en 'Descripción' (columna 5)
        keep_tail = 16  # columnas 6..21
        left_end = max(4, original_count - keep_tail)
        desc = " | ".join(parts[4:left_end])
        parts = parts[:4] + [desc] + parts[left_end:]
        avisos.append(f"Se detectaron {original_count} campos; se fusionó el excedente en 'Descripción'.")
    if len(parts) < 21:
        faltan = 21 - len(parts)
        avisos.append(f"Se detectaron {len(parts)} campos; se completaron {faltan} vacíos.")
        parts += [""] * faltan
    parts = [p.strip() for p in parts]
    return parts, avisos

def is_empty_token(x: str) -> bool:
    # Por ahora, solo vacío literal (""), como pediste
    return x.strip().lower() in {""}

def clean_empty_tokens(parts: list[str]) -> list[str]:
    """Quita espacios extra en cada token sin alterar posiciones."""
    return [(p or "").strip() for p in parts]

def norm_opcion(valor: str, opciones: list[str]) -> str:
    """Normaliza por similitud básica contra un set de opciones."""
    v = (valor or "").strip().lower()
    for op in opciones:
        if v == op.lower():
            return op
    # sinonimos rápidos
    if v in ("telefono","teléfono","tel"): return "Teléfono"
    if v in ("email","correo"): return "Correo"
    return valor or ""


def parse_dt(s: str):
    s = s.strip()
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
    except Exception:
        return None

def calcula_tiempo_solucion(apertura: str, cierre: str) -> str:
    dt_a = parse_dt(apertura) if apertura else None
    dt_c = parse_dt(cierre) if cierre else None
    if dt_a and dt_c and dt_c >= dt_a:
        delta = dt_c - dt_a
        horas = delta.seconds // 3600 + delta.days * 24
        minutos = (delta.seconds % 3600) // 60
        return f"{horas} horas {minutos} minutos"
    return ""

# ---------------------------
# Fechas/horas del texto (am/pm y 24h)
# ---------------------------
MESES_ES = r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre"
MESES_MAP = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}
ISO_FECHA_RE = re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b")              # 2025-09-05
DMY_SLASH_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b")   # 5/9[/2025] o 05-09-2025
DM_DE_MES_RE = re.compile(
    rf"\b(\d{{1,2}})\s+de\s+(?:{MESES_ES})(?:\s+de\s+(\d{{4}}))?\b", re.IGNORECASE
)

def _safe_int(x: str) -> int | None:
    try:
        return int(x)
    except Exception:
        return None

def _year_or_current(y: str | None) -> int:
    if not y:
        return datetime.now(TZ).year
    yi = _safe_int(y)
    if yi is None:
        return datetime.now(TZ).year
    if 0 <= yi < 100:
        return 2000 + yi
    return yi

def _first_date_in_text(texto: str) -> Optional[datetime.date]:
    t = texto.lower()

    m = ISO_FECHA_RE.search(t)
    if m:
        y, mo, d = map(int, m.groups())
        return datetime(y, mo, d, tzinfo=TZ).date()

    m = DM_DE_MES_RE.search(t)
    if m:
        d = int(m.group(1))
        mes_txt = m.group(0).lower()
        mes_name = re.search(rf"{MESES_ES}", mes_txt).group(0)
        mo = MESES_MAP.get(mes_name, None)
        y = _year_or_current(m.group(2))
        if mo:
            return datetime(y, mo, d, tzinfo=TZ).date()

    m = DMY_SLASH_RE.search(t)
    if m:
        d = int(m.group(1)); mo = int(m.group(2)); y = _year_or_current(m.group(3))
        if 1 <= d <= 31 and 1 <= mo <= 12:
            return datetime(y, mo, d, tzinfo=TZ).date()

    return None

AMPM_RE = re.compile(
    r"\b(?P<hour>1[0-2]|0?[1-9])(?::(?P<minute>[0-5]\d))?\s*(?P<ampm>a\.?m\.?|am|p\.?m\.?|pm)\b",
    re.IGNORECASE
)
H24_RE = re.compile(r"\b(?P<hour>[01]?\d|2[0-3]):(?P<minute>[0-5]\d)\b")

def _to_24h(hour: int, minute: int, ampm: str) -> tuple[int, int]:
    ampm = ampm.lower().replace(".", "")
    if ampm.startswith("p") and hour != 12:
        hour += 12
    if ampm.startswith("a") and hour == 12:
        hour = 0
    return hour, minute

def extraer_horas_any(texto: str) -> list[str]:
    t = texto.lower()
    horas: list[str] = []
    for m in AMPM_RE.finditer(t):
        h = int(m.group("hour")); mi = int(m.group("minute") or 0)
        H, M = _to_24h(h, mi, m.group("ampm"))
        horas.append(f"{H:02d}:{M:02d}")
    for m in H24_RE.finditer(t):
        H = int(m.group("hour")); M = int(m.group("minute"))
        horas.append(f"{H:02d}:{M:02d}")
    seen, out = set(), []
    for x in horas:
        if x not in seen:
            seen.add(x); out.append(x)
    return out

def fechas_desde_texto(texto: str) -> tuple[str, str]:
    """
    Retorna (apertura, cierre) en "YYYY-MM-DD HH:MM".
    - Si hay día+mes (con o sin año) y horas, usa esa fecha (año actual si falta).
    - Si solo hay horas, usa fecha de hoy.
    - Si no hay horas, retorna ("","").
    - Si hay dos o más horas, cierre = última; si la última < primera, suma 1 día.
    """
    horas = extraer_horas_any(texto)
    if not horas:
        return "", ""

    base_date = _first_date_in_text(texto) or datetime.now(TZ).date()
    a_str = f"{base_date} {horas[0]}"
    if len(horas) > 1:
        c_date = base_date
        h0 = datetime.strptime(horas[0], "%H:%M").time()
        h1 = datetime.strptime(horas[-1], "%H:%M").time()
        if (h1.hour, h1.minute) < (h0.hour, h0.minute):
            c_date = base_date + timedelta(days=1)
        c_str = f"{c_date} {horas[-1]}"
    else:
        c_str = ""
    return a_str, c_str

def calcula_tiempo_desde_texto(texto: str) -> str:
    # Si hay al menos dos horas en el texto, calcula diferencia usando la fecha de hoy
    hh = extraer_horas_any(texto)
    if len(hh) < 2:
        return ""
    h_ini, h_fin = hh[0], hh[-1]
    today = datetime.now(TZ).date()
    a = datetime.strptime(f"{today} {h_ini}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
    c = datetime.strptime(f"{today} {h_fin}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
    if c < a:
        c = c + timedelta(days=1)
    delta = c - a
    horas = delta.seconds // 3600 + delta.days * 24
    minutos = (delta.seconds % 3600) // 60
    return f"{horas} horas {minutos} minutos"

# ---------------------------
# Inferencia de Ubicación / Modo / Acción / Solución / Clasificación / Área GTIC / Sistema / Área
# ---------------------------
DEPTS_BO = {
    "la paz": ["la paz", "lpz", "senkata"],
    "santa cruz": ["santa cruz", "scz", "santa cruz de la sierra", "pau"],
    "cochabamba": ["cochabamba", "cbba", "cbb"],
    "chuquisaca": ["chuquisaca", "sucre"],
    "oruro": ["oruro"],
    "potosí": ["potosi", "potosí"],
    "beni": ["beni", "trinidad"],
    "pando": ["pando", "cobija"],
    "tarija": ["tarija", "yacuiba", "villa montes"],
}
def detectar_ubicacion_ext(texto: str) -> str:
    t = texto.lower()
    if "a nivel nacional" in t or "nivel nacional" in t:
        return "Bolivia (nivel nacional)"
    m = re.search(r"(sucursal|oficina|sede)\s+([a-záéíóúñ ]+)", t)
    if m:
        return f"{m.group(1).title()} {m.group(2).strip().title()}"
    for dept, keys in DEPTS_BO.items():
        for k in keys:
            if re.search(rf"\b{k}\b", t):
                return f"{dept.title()}, Bolivia"
    return ""

def detectar_modo_reporte(texto: str) -> str:
    t = texto.lower()
    if "jira" in t or "ticket" in t:
        return "Jira"
    if "monitoreo" in t or "alerta" in t:
        return "Monitoreo"
    if any(x in t for x in ["teléfono", "telefono", "llam", "llamada", "celular", "whatsapp"]):
        return "Teléfono"
    if any(x in t for x in ["correo", "e-mail", "email", "mail", "outlook"]):
        return "Correo"
    return "Teléfono"

def extraer_encargado(texto: str) -> str:
    """
    Busca frases como 'el encargado es <NOMBRE>' o 'responsable <NOMBRE>'.
    Devuelve el nombre si lo encuentra.
    """
    t = texto.lower()
    m = re.search(r"(encargad[oa]|responsable)\s+(es\s+)?([a-záéíóúñ\s]+)", texto, re.IGNORECASE)
    if m:
        nombre = m.group(3).strip()
        # Cortar si hay 'del área' o frases largas
        nombre = re.split(r"\s+(del|de la|de los|de las)\b", nombre, 1)[0].strip()
        return nombre.title()
    return ""

ACCION_RULES = [
    (r"reinici(ar|ó|o|amos|aron).*(equipo|pc|servicio|servidor)", "Reinicio de servicios/equipo"),
    (r"(verific(ar|ó|aron).*(conectividad|ping|traz))", "Verificación de conectividad"),
    (r"(bloque(o|ar|ó).*(cuenta)|forz[oó].*contraseñ|cambio de contraseñ)", "Bloqueo/cambio de contraseñas"),
    (r"aisl(ar|ado|amiento).*(equipo)|segmentaci[oó]n", "Aislamiento del equipo"),
]
SOLUCION_RULES = [
    (r"(desbloque(o|ar)|reset).*cuenta|restablecimi?ento.*contraseñ", "Desbloqueo / reseteo de cuenta"),
    (r"(limpieza|eliminaci[oó]n).*(malware|virus|troyano)", "Limpieza de malware"),
    (r"(regla|permit|bloque).*(firewall|fw|ips|waf)", "Ajuste de reglas en firewall/WAF"),
    (r"(whitelist|allowlist|excepci[oó]n)", "Creación de excepción/allowlist"),
    (r"(reconfiguraci[oó]n|ajuste).*(pol[ií]tica|configuraci[oó]n)", "Reconfiguración de políticas"),
]
def _collect(vals: set[str], rules: list[tuple[str,str]], texto: str):
    t = texto.lower()
    for pat, label in rules:
        if re.search(pat, t):
            vals.add(label)
def infer_accion_inmediata(texto: str) -> str:
    s: set[str] = set(); _collect(s, ACCION_RULES, texto)
    return "; ".join(sorted(s)) if s else ""
def infer_solucion(texto: str) -> str:
    s: set[str] = set(); _collect(s, SOLUCION_RULES, texto)
    return "; ".join(sorted(s)) if s else ""

CLASIF_PATTERNS = {
    "Acceso no autorizado": [
        r"acceso no autoriz", r"intrus", r"suplantaci[oó]n",
        r"credenciales? (compromet|filtrad|robadas)", r"elevaci[oó]n de privilegios",
        r"cuenta comprometida|login irregular",
    ],
    "Modificación de recursos no autorizado": [
        r"defacement|desfiguraci[oó]n", r"alteraci[oó]n|modificaci[oó]n.*no autoriz",
        r"borrad(o|a) (no autoriz|accidental)", r"integridad.*(afectad|compromet)",
    ],
    "Uso inapropiado de recursos": [
        r"uso inapropiad|uso indebido|violaci[oó]n.*pol[íi]tica.*uso", r"usb no autoriz",
    ],
    "No disponibilidad de recursos": [
        r"ca[ií]da|indisponibil|no disponible|servicio.*no responde|interrupci[oó]n|apag[oó]n|fuera de servicio|vpn.*ca[ií]da|ddos|denegaci[oó]n",
    ],
    "Exploración de Vulnerabilidades": [
        r"escane[oó]|scan|nmap|nessus|openvas|enumeraci[oó]n|port scan|sondeo de puertos",
    ],
}
def infer_clasificacion(texto: str, clasif_modelo: str = "") -> str:
    cm = clasif_modelo.strip().lower()
    if cm in CLASIF_CANON:
        return CLASIF_CANON[cm]
    hits = []
    t = texto.lower()
    for nombre, pats in CLASIF_PATTERNS.items():
        if any(re.search(p, t) for p in pats):
            hits.append(nombre)
    if len(hits) >= 2: return "Multicomponente"
    if len(hits) == 1: return hits[0]
    return ""

def normaliza_clasificacion_final(valor: str) -> str:
    v = valor.strip().lower()
    if not v: return ""
    for k, canon in CLASIF_CANON.items():
        if k in v:
            return canon
    return ""

def infer_area_coordinando(texto: str) -> str:
    t = texto.lower()
    if "seguridad" in t:
        return "DSEC - Seguridad"
    if "infraestructura" in t or "redes" in t or "vpn" in t or "cisco" in t:
        return "DITC - Infraestructura"
    if "soporte" in t or "mesa de ayuda" in t:
        return "DSTC - Soporte Técnico"
    if "sistemas" in t or "erp" in t or "base de datos" in t:
        return "DISC - Sistemas"
    return ""


def infer_sistema(texto: str) -> str:
    t = texto.lower()
    if re.search(r"\bvpn\b", t): return "VPN"
    if re.search(r"correo|email|outlook|exchange", t): return "Correo"
    if re.search(r"active directory|\bad\b", t): return "Active Directory"
    if re.search(r"\bfirewall\b", t): return "Firewall"
    if re.search(r"\berp\b", t): return "ERP"
    if re.search(r"whatsapp", t): return "WhatsApp"
    if re.search(r"portal web|sitio web|web p[úu]blica|p[aá]gina web", t): return "Portal Web"
    if re.search(r"base de datos|postgres|oracle|mysql|sql server|mssql", t): return "Base de Datos"
    return ""

def infer_area(texto: str) -> str:
    t = texto.lower()
    m = re.search(r"(área|area|departamento|unidad)\s+de\s+([a-záéíóúñ ]+)", t)
    if m:
        return m.group(2).strip().title()
    return ""

def norm_opcion(valor: str, validos: list[str]) -> str:
    v = (valor or "").strip().lower()
    for x in validos:
        if v == x.lower():
            return x
    return ""

# ---------------------------
# Generador de CODIGO: INC-<día>-<mes>-<NNN>
# ---------------------------
def generar_codigo_inc(ws, fecha_apertura: str | None) -> str:
    dia, mes = None, None
    if fecha_apertura:
        try:
            dt = datetime.strptime(fecha_apertura.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
            dia, mes = dt.day, dt.month
        except Exception:
            pass
    if dia is None:
        now = datetime.now(TZ)
        dia, mes = now.day, now.month

    codigos = ws.col_values(1)  # CODIGO
    patron = re.compile(rf"^INC-{dia}-{mes}-(\d{{3}})$")
    max_seq = 0
    for c in codigos:
        if not c: continue
        m = patron.match(c.strip())
        if m:
            n = int(m.group(1))
            if n > max_seq: max_seq = n

    seq = max_seq + 1
    candidato = f"INC-{dia}-{mes}-{seq:03d}"
    existentes = set(x.strip() for x in codigos if x)
    while candidato in existentes:
        seq += 1
        candidato = f"INC-{dia}-{mes}-{seq:03d}"
    return candidato

# ---------------------------
# UI
# ---------------------------
user_question = st.text_area(
    "Describe el incidente:",
    height=200,
    placeholder="Ej: A las 8:00am el área de Contabilidad reporta por Correo que no puede acceder al sistema de Correo corporativo. Como acción inmediata, el usuario reinició el equipo y Mesa de Ayuda validó conectividad sin resultados. Seguridad Informática coordinó la atención y reinició el servicio de Correo en el servidor, verificando autenticación y entrega de mensajes. A las 10:15am el servicio quedó restablecido y se cerró el incidente.",
    help="Incluye: Fecha/hora de apertura, Sistema, Área, Acción inmediata, Solución, Área GTIC que coordinó y Fecha/hora de cierre."
)

if st.button("Reportar", use_container_width=True):
    if not user_question.strip():
        st.warning("Por favor, describe el incidente antes de continuar.")
        st.stop()

    prompt = persona + user_question.strip()

    with st.spinner("Generando y validando la fila..."):
        # 1) LLM
        try:
            resp = model.generate_content([prompt], generation_config={"temperature": 0.2})
            response_text = resp.text if hasattr(resp, "text") else str(resp)
        except Exception as e:
            st.error(f"Error al generar contenido: {e}")
            st.stop()

        # 2) Saneo + normalización a 21 columnas
        cleaned = sanitize_text(response_text)
        cleaned = re.sub(r"\s\|\s", " ; ", cleaned)
        assert_20_pipes(cleaned)
        fila, avisos = normalize_21_fields(cleaned)
        fila = clean_empty_tokens(fila)
        fila[3] = "Evento" if "evento" in (fila[3] or "").lower() else "Incidente"

        # Forzar vacíos 18–21
        fila[17] = ""; fila[18] = ""; fila[19] = ""; fila[20] = ""

        # 3) Fechas: extraer del texto y defaults
        ap_auto, ci_auto = fechas_desde_texto(user_question)
        # Si el modelo no dio apertura, usa ahora
        if not fila[1].strip():
            fila[1] = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
        # Si no hay cierre y el extractor encontró, úsalo
        if not fila[14].strip() and ci_auto:
            fila[14] = ci_auto

        # 4) Realineo semántico mínimo (corrige campos corridos)
                # 4) Realineo semántico reforzado (corrige campos corridos)
        CIUDADES = {"la paz","el alto","santa cruz","cochabamba","tarija","potosí","potosi","sucre","beni","pando","oruro","bolivia"}
        IMPACTOS = {"alto","medio","bajo"}
        ESTADOS  = {"cerrado","en investigación","en investigacion"}
        MODO_OPC = ["Correo","Jira","Teléfono","Monitoreo","Webex","WhatsApp"]
        SISTEMAS_KEYWORDS = ["firewall","kubernetes","cortex","checkpoint","proxy","waf","antivirus","umbrella","ise","vpn","exchange","servidor","server","correo","email","outlook"]

        def _looks_ciudad(s: str) -> bool:
            return any(c in (s or "").lower() for c in CIUDADES)
        def _looks_impacto(s: str) -> bool:
            return (s or "").strip().lower() in IMPACTOS
        def _looks_estado(s: str) -> bool:
            return (s or "").strip().lower() in ESTADOS
        def _looks_evento_incidente(s: str) -> bool:
            return (s or "").strip().lower() in {"evento","incidente"}
        def _looks_sistema(s: str) -> bool:
            t = (s or "").strip().lower()
            return any(k in t for k in SISTEMAS_KEYWORDS)
        def _norm_modo(s: str) -> str:
            return norm_opcion(s, MODO_OPC)

        def _put(idx: int, val: str) -> bool:
            """Escribe en idx solo si está vacío."""
            if not (fila[idx] or "").strip() and (val or "").strip():
                fila[idx] = val
                return True
            return False

        # Limpieza básica
        fila = [(x or "").strip() for x in fila]

        # A) Impacto mal ubicado (a veces cae en Sistema/Área/Ubicación/Clasificación…)
        for i in range(21):
            if i == 8: 
                continue
            if _looks_impacto(fila[i]):
                _put(8, fila[i].title())
                if i != 8:
                    fila[i] = ""

        # B) Estado mal ubicado
        for i in range(21):
            if i == 16: 
                continue
            if _looks_estado(fila[i]):
                _put(16, fila[i].capitalize())
                if i != 16:
                    fila[i] = ""

        # C) Evento/Incidente mal ubicado
        for i in range(21):
            if i == 3: 
                continue
            if _looks_evento_incidente(fila[i]):
                _put(3, fila[i].title())
                if i != 3:
                    fila[i] = ""

        # D) Modo de reporte en otro campo
        for i in range(21):
            if i == 2: 
                continue
            mm = _norm_modo(fila[i])
            if mm:
                _put(2, mm)
                if i != 2:
                    fila[i] = ""

        # E) Área GTIC (DSEC/DITC/DSTC/DISC) detectada en otro lado
        for i in range(21):
            if i == 12: 
                continue
            t = (fila[i] or "").lower()
            if any(k in t for k in ["dsec","ditc","dstc","disc"]):
                _put(12, fila[i])
                if i != 12:
                    fila[i] = ""

        # F) Encargado: del texto libre o si cayó en otra columna
        if not fila[13].strip():
            enc = extraer_encargado(user_question)
            if enc:
                fila[13] = enc
        # Si nombres cortos quedaron en otras columnas, muévelos
        for i in (5,6,7,9,10,11,12):
            t = (fila[i] or "").strip()
            if re.fullmatch(r"[A-Za-zÁÉÍÓÚÜáéíóúñÑ]+(?:\s+[A-Za-zÁÉÍÓÚÜáéíóúñÑ]+)?", t) and len(t.split()) <= 2:
                if t and t[0].isalpha() and t[0].isupper():
                    if _put(13, t): 
                        fila[i] = ""

        # G) “AGETIC” → Área (si está en otra columna)
        for i in range(21):
            if "agetic" in (fila[i] or "").lower():
                _put(6, "AGETIC")
                if i != 6:
                    fila[i] = ""

        # H) Sistema mal ubicado / inferencia por texto
        if not fila[5].strip():
            sis = infer_sistema(user_question)
            if sis:
                fila[5] = sis
        for i in range(21):
            if i == 5: 
                continue
            if _looks_sistema(fila[i]):
                if _put(5, fila[i]):
                    fila[i] = ""

        # I) Ubicación: si hay ciudad en otras columnas, muévela; si vacía, infiere del texto
        if not fila[7].strip():
            for i in range(21):
                if i == 7: 
                    continue
                if _looks_ciudad(fila[i]):
                    fila[7] = fila[i]
                    if i != 7:
                        fila[i] = ""
                    break
        if not fila[7].strip():
            fila[7] = detectar_ubicacion_ext(user_question) or ""

        # J) Acción inmediata / Solución mal ubicadas (verbos típicos en otras columnas)
        if not fila[10].strip():
            fila[10] = infer_accion_inmediata(user_question)
        if not fila[11].strip():
            fila[11] = infer_solucion(user_question)

        for i in (5,6,7,9):
            t = (fila[i] or "").lower()
            if re.search(r"\b(reinici|bloque|verific|restablec|permit|desbloque|allow|whitelist)\b", t):
                # Si no hay solución → va a Solución; si hay → a Acción inmediata
                if not fila[11].strip():
                    fila[11] = fila[i]
                elif not fila[10].strip():
                    fila[10] = fila[i]
                fila[i] = ""

        # K) Clasificación final (catálogo + inferencia)
        fila[9] = normaliza_clasificacion_final(fila[9]) or infer_clasificacion(user_question) or "Otros"

        # L) Corrección de valores imposibles en Sistema/Área/Ubicación
        #    (p.ej. Impacto o Estado que se nos haya escapado)
        if _looks_impacto(fila[5]): 
            _put(8, fila[5].title()); fila[5] = infer_sistema(user_question) or fila[5]
        if _looks_estado(fila[5]): 
            _put(16, fila[5].capitalize()); fila[5] = infer_sistema(user_question) or ""
        if _looks_impacto(fila[6]): 
            _put(8, fila[6].title()); fila[6] = ""
        if _looks_estado(fila[6]): 
            _put(16, fila[6].capitalize()); fila[6] = ""
        if not _looks_ciudad(fila[7]) and _looks_sistema(fila[7]):
            _put(5, fila[7]); fila[7] = detectar_ubicacion_ext(user_question) or "La paz"

        # 5) Tiempo de solución
        if not fila[15].strip():
            fila[15] = calcula_tiempo_solucion(fila[1], fila[14])
        if not fila[15].strip():
            fila[15] = calcula_tiempo_desde_texto(user_question)

        # 6) Inferencias y normalizaciones
        # Modo Reporte
        fila[2] = norm_opcion(fila[2] or detectar_modo_reporte(user_question),
                              ["Correo","Jira","Teléfono","Monitoreo","Webex","WhatsApp"]) or "Otro"

        # Ubicación (si quedó vacía)
        if not fila[7].strip():
            fila[7] = detectar_ubicacion_ext(user_question) or "La Paz, Bolivia"

        # Acción inmediata y Solución
        if not fila[10].strip():
            fila[10] = infer_accion_inmediata(user_question)
        if not fila[11].strip():
            fila[11] = infer_solucion(user_question)

        # Clasificación
        fila[9] = normaliza_clasificacion_final(fila[9]) or infer_clasificacion(user_question) or "Otros"

        # Área de GTIC / Encargado
        if not fila[12].strip():
            fila[12] = infer_area_coordinando(user_question)
        if not fila[13].strip():
            fila[13] = extraer_encargado(user_question)

        # Sistema / Área
        if not fila[5].strip():
            fila[5] = infer_sistema(user_question) or "Firewall"
        if not fila[6].strip():
            fila[6] = infer_area(user_question)

        # Estado por defecto
        if not fila[16].strip():
            fila[16] = "Cerrado" if fila[14].strip() else "En investigación"

        # 7) Validaciones finales
        if len(fila) != 21:
            st.error(f"La salida quedó con {len(fila)} columnas (esperado: 21).")
            st.code(cleaned, language="text")
            st.stop()

        # 8) Código + timestamp
        codigo = generar_codigo_inc(ws, fila[1] if fila[1].strip() else None)
        fila[0] = codigo
        registro_ts = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
        fila_con_ts = fila + [registro_ts]

        # 9) Vista previa
        df_prev = pd.DataFrame([fila_con_ts], columns=COLUMNAS + ["Hora de reporte"])
        st.subheader("Vista previa")
        st.dataframe(df_prev, use_container_width=True)
        if avisos:
            st.info(" | ".join(avisos))

        # 10) Guardar
        try:
            ws.append_row(fila_con_ts, value_input_option="USER_ENTERED")
            st.success(f"Incidente registrado correctamente: {codigo}")
        except Exception as e:
            st.error(f"No se pudo escribir en la hoja: {e}")



