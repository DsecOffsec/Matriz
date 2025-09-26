import streamlit as st
import gspread
import pandas as pd
import re
import json
from typing import Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import google.generativeai as genai
from typing import List, Tuple

st.title("MATRIZ DE REPORTES DSEC")

# ---------------------------
# Conexiones y configuraciÃ³n
# ---------------------------
gc = gspread.service_account_from_dict(st.secrets["connections"]["gsheets"])
# Recomendado: mover a secrets -> st.secrets["connections"]["SHEET_ID"]
SHEET_ID = "1UP_fwvXam8-1IXI-oUbkNqGzb0_T0XNrYsU7ziJVAqE"
sh = gc.open_by_key(SHEET_ID)
ws = sh.worksheet("Reportes")

api_key = st.secrets["GOOGLE_API_KEY"]
genai.configure(api_key=api_key)
model = genai.GenerativeModel("gemini-1.5-flash")

TZ = ZoneInfo("America/La_Paz")

st.markdown("""
### ðŸ“ Instrucciones para registrar un incidente

Por favor, describe el incidente en **un solo pÃ¡rrafo** incluyendo estos campos **obligatorios**:

1. **Fecha y hora de apertura** â€” La hora de inicio del incidente/alerta con hora y AM/PM.
2. **Modo de reporte** - Si lo reportaron por correo, JIRA, monitoreo, llamada, otros, etc.
3. **Sistema afectado** â€” Por ejemplo: Correo, VPN, Antivirus, Firewall, etc.  
4. **Ãrea afectada** â€” El departamento o unidad donde se detectÃ³ el problema.  
5. **AcciÃ³n inmediata tomada** â€” Lo que hizo el usuario para mitigar el problema.  
6. **SoluciÃ³n aplicada** â€” AcciÃ³n final que resolviÃ³ el incidente.  
7. **Ãrea de GTIC que coordinÃ³** â€” DSEC - Seguridad, DITC - Infraestructura, DSTC - Soporte TÃ©cnico, DISC - Sistemas.  
8. **Encargado** - El responsable del incidente/alerta.
""")

COLUMNAS = [
    "CODIGO","Fecha y Hora de Apertura","Modo Reporte","Evento/ Incidente",
    "DescripciÃ³n Evento/ Incidente","Sistema","Area","UbicaciÃ³n","Impacto",
    "ClasificaciÃ³n","AcciÃ³n Inmediata","SoluciÃ³n","Area de GTIC - Coordinando",
    "Encargado SI","Fecha y Hora de Cierre","Tiempo SoluciÃ³n","Estado",
    "Vulnerabilidad","Causa","ID Amenaza","Amenaza"
]

# Valores vÃ¡lidos / normalizadores rÃ¡pidos
MODO_VALIDOS = {"correo","jira","telÃ©fono","telefono","monitoreo","webex","whatsapp","otro"}
IMPACTO_VALIDOS = {"alto","medio","bajo"}
ESTADO_VALIDOS = {"cerrado","en investigaciÃ³n"}

# ---------------------------
# GuÃ­as (texto de referencia)
# ---------------------------

CODE_RE = re.compile(r'^\d+\.\d+$')

# ---------------------------
# Clasificaciones vÃ¡lidas (lista cerrada)
# ---------------------------
CLASIF_CANON = {
    "acceso no autorizado": "Acceso no autorizado",
    "modificaciÃ³n de recursos no autorizado": "ModificaciÃ³n de recursos no autorizado",
    "uso inapropiado de recursos": "Uso inapropiado de recursos",
    "no disponibilidad de recursos": "No disponibilidad de recursos",
    "multicomponente": "Multicomponente",
    "exploraciÃ³n de vulnerabilidades": "ExploraciÃ³n de Vulnerabilidades",
    "otros": "Otros",
}
CLASIF_TEXTO = "\n".join([f"- {v}" for v in CLASIF_CANON.values()])

# ---------------------------
# Prompt (CODIGO lo genera backend y no se inventan fechas)
# ---------------------------
persona = f"""
Eres un asistente experto en seguridad informÃ¡tica. Convierte el reporte en UNA SOLA LÃNEA con exactamente 21 valores separados por | (pipe). Sin encabezados, sin markdown, sin explicaciones, sin saltos de lÃ­nea. Exactamente 20 pipes.
{COLUMNAS}

Reglas:
- Las claves 18-21 ("Vulnerabilidad","Causa","ID Amenaza","Amenaza") siempre vacÃ­as.
- No inventes fechas. Usa "YYYY-MM-DD HH:MM" solo si el texto menciona dÃ­a/mes/aÃ±o; si no, deja vacÃ­o.
- Zona horaria: America/La_Paz. En el aÃ±o 2025
- NO inventes ni completes los campos 18 (Vulnerabilidad), 19 (Causa), 20 (ID Amenaza) y 21 (Amenaza).
  DÃ©jalos vacÃ­os siempre.
- NO inventes fechas: si el reporte no incluye una fecha explÃ­cita con dÃ­a/mes/aÃ±o (p. ej., "2025-08-10", "10/08/2025" o "10 de agosto de 2025"), deja vacÃ­os los campos de fecha. Si solo hay horas, no pongas fecha.
- Importante: NO uses el carÃ¡cter | dentro de ningÃºn campo. Si necesitas separar ideas usa ; (punto y coma).
- Responde Ãºnicamente la lÃ­nea con 21 campos separados por | (exactamente 20 pipes), sin comentarios ni texto adicional.

Columnas y formato:
1. CODIGO â†’ (dejar vacÃ­o; lo genera el sistema).
2. Fecha y Hora de Apertura â†’ YYYY-MM-DD HH:MM, solo si se menciona (con dÃ­a/mes/aÃ±o explÃ­citos).
3. Modo Reporte â†’ valores vÃ¡lidos (Correo, Jira, TelÃ©fono, Monitoreo, â€¦).
4. Evento/ Incidente â†’ Evento | Incidente.
5. DescripciÃ³n Evento/ Incidente â†’ resumen claro y profesional.
6. Sistema â†’ (VPN, Correo, Active Directory, â€¦).
7. Area
8. UbicaciÃ³n
9. Impacto â†’ Alto | Medio | Bajo.
10. ClasificaciÃ³n â†’ elige exactamente UNO de: 
{CLASIF_TEXTO}
11. AcciÃ³n Inmediata
12. SoluciÃ³n
13. Area de GTIC - Coordinando â†’ (DSEC - Seguridad, DITC - Infraestructura, DSTC - Soporte TÃ©cnico, DISC - Sistemas, â€¦).
14. Encargado SI â†’ solo si se menciona; no inventes nombres.
15. Fecha y Hora de Cierre â†’ YYYY-MM-DD HH:MM, solo si se menciona (con dÃ­a/mes/aÃ±o explÃ­citos).
16. Tiempo SoluciÃ³n â†’ â€œX horas Y minutosâ€ si puedes calcular (Cierre âˆ’ Apertura); si no, vacÃ­o.
17. Estado â†’ Cerrado | En investigaciÃ³n.
18. Vulnerabilidad â†’ Vacio
19. Causa â†’ vacÃ­o.
20. ID Amenaza â†’ Vacio
21. Amenaza â†’ vacÃ­o.

[REPORTE DE ENTRADA]:
"""

# ---------------------------
# Utilidades de saneamiento / validaciÃ³n
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
    # Mapea por nombre â†’ orden canÃ³nico
    fila = [ (rec.get(col) or "").strip() for col in COLUMNAS ]
    return fila

def fallback_parse_pipes(raw: str) -> list[str]:
    cleaned = sanitize_text(raw)
    parts, _ = normalize_21_fields(cleaned)
    # â€œEvento/ Incidenteâ€ a valor canÃ³nico
    parts[3] = norm_evento_incidente(parts[3])
    # Forzar vacÃ­os 18â€“21
    parts[17] = ""; parts[18] = ""; parts[19] = ""; parts[20] = ""
    return parts
    
def sanitize_text(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^```.*?\n", "", s, flags=re.DOTALL)
    s = re.sub(r"```$", "", s)
    s = s.replace("```", "")
    s = s.replace("\n", " ").replace("\r", " ")
    s = s.replace("â€œ", '"').replace("â€", '"').replace("â€™", "'")
    m = re.search(r"[^|\n]*\|[^|\n]*\|", s)
    if m:
        s = s[m.start():]
    return s.strip().strip('"').strip()

def assert_20_pipes(s: str):
    """Muestra un aviso si la lÃ­nea no tiene exactamente 20 pipes (21 campos)."""
    cnt = s.count("|")
    if cnt != 20:
        st.info(f"Se detectaron {cnt+1} campos; se fusionarÃ¡ el excedente en 'DescripciÃ³n'.")

def normalize_21_fields(raw: str) -> Tuple[List[str], List[str]]:
    avisos = []
    parts = [p.strip() for p in raw.split("|")]
    original_count = len(parts)
    if original_count > 21:
        # Fusiona el excedente en 'DescripciÃ³n' (columna 5)
        keep_tail = 16  # columnas 6..21
        left_end = max(4, original_count - keep_tail)
        desc = " | ".join(parts[4:left_end])
        parts = parts[:4] + [desc] + parts[left_end:]
        avisos.append(f"Se detectaron {original_count} campos; se fusionÃ³ el excedente en 'DescripciÃ³n'.")
    if len(parts) < 21:
        faltan = 21 - len(parts)
        avisos.append(f"Se detectaron {len(parts)} campos; se completaron {faltan} vacÃ­os.")
        parts += [""] * faltan
    parts = [p.strip() for p in parts]
    return parts, avisos

def is_empty_token(x: str) -> bool:
    # Por ahora, solo vacÃ­o literal (""), como pediste
    return x.strip().lower() in {""}

def clean_empty_tokens(parts: list[str]) -> list[str]:
    """Quita espacios extra en cada token sin alterar posiciones."""
    return [(p or "").strip() for p in parts]

def norm_opcion(valor: str, opciones: list[str]) -> str:
    """Normaliza por similitud bÃ¡sica contra un set de opciones."""
    v = (valor or "").strip().lower()
    for op in opciones:
        if v == op.lower():
            return op
    # sinonimos rÃ¡pidos
    if v in ("telefono","telÃ©fono","tel"): return "TelÃ©fono"
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
    - Si hay dÃ­a+mes (con o sin aÃ±o) y horas, usa esa fecha (aÃ±o actual si falta).
    - Si solo hay horas, usa fecha de hoy.
    - Si no hay horas, retorna ("","").
    - Si hay dos o mÃ¡s horas, cierre = Ãºltima; si la Ãºltima < primera, suma 1 dÃ­a.
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
# Inferencia de UbicaciÃ³n / Modo / AcciÃ³n / SoluciÃ³n / ClasificaciÃ³n / Ãrea GTIC / Sistema / Ãrea
# ---------------------------
DEPTS_BO = {
    "la paz": ["la paz", "lpz", "senkata"],
    "santa cruz": ["santa cruz", "scz", "santa cruz de la sierra", "pau"],
    "cochabamba": ["cochabamba", "cbba", "cbb"],
    "chuquisaca": ["chuquisaca", "sucre"],
    "oruro": ["oruro"],
    "potosÃ­": ["potosi", "potosÃ­"],
    "beni": ["beni", "trinidad"],
    "pando": ["pando", "cobija"],
    "tarija": ["tarija", "yacuiba", "villa montes"],
}
def detectar_ubicacion_ext(texto: str) -> str:
    t = texto.lower()
    if "a nivel nacional" in t or "nivel nacional" in t:
        return "Bolivia (nivel nacional)"
    m = re.search(r"(sucursal|oficina|sede)\s+([a-zÃ¡Ã©Ã­Ã³ÃºÃ± ]+)", t)
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
    if any(x in t for x in ["telÃ©fono", "telefono", "llam", "llamada", "celular", "whatsapp"]):
        return "TelÃ©fono"
    if any(x in t for x in ["correo", "e-mail", "email", "mail", "outlook"]):
        return "Correo"
    return "TelÃ©fono"

def extraer_encargado(texto: str) -> str:
    """
    Busca frases como 'el encargado es <NOMBRE>' o 'responsable <NOMBRE>'.
    Devuelve el nombre si lo encuentra.
    """
    t = texto.lower()
    m = re.search(r"(encargad[oa]|responsable)\s+(es\s+)?([a-zÃ¡Ã©Ã­Ã³ÃºÃ±\s]+)", texto, re.IGNORECASE)
    if m:
        nombre = m.group(3).strip()
        # Cortar si hay 'del Ã¡rea' o frases largas
        nombre = re.split(r"\s+(del|de la|de los|de las)\b", nombre, 1)[0].strip()
        return nombre.title()
    return ""

ACCION_RULES = [
    (r"reinici(ar|Ã³|o|amos|aron).*(equipo|pc|servicio|servidor)", "Reinicio de servicios/equipo"),
    (r"(verific(ar|Ã³|aron).*(conectividad|ping|traz))", "VerificaciÃ³n de conectividad"),
    (r"(bloque(o|ar|Ã³).*(cuenta)|forz[oÃ³].*contraseÃ±|cambio de contraseÃ±)", "Bloqueo/cambio de contraseÃ±as"),
    (r"aisl(ar|ado|amiento).*(equipo)|segmentaci[oÃ³]n", "Aislamiento del equipo"),
]
SOLUCION_RULES = [
    (r"(desbloque(o|ar)|reset).*cuenta|restablecimi?ento.*contraseÃ±", "Desbloqueo / reseteo de cuenta"),
    (r"(limpieza|eliminaci[oÃ³]n).*(malware|virus|troyano)", "Limpieza de malware"),
    (r"(regla|permit|bloque).*(firewall|fw|ips|waf)", "Ajuste de reglas en firewall/WAF"),
    (r"(whitelist|allowlist|excepci[oÃ³]n)", "CreaciÃ³n de excepciÃ³n/allowlist"),
    (r"(reconfiguraci[oÃ³]n|ajuste).*(pol[iÃ­]tica|configuraci[oÃ³]n)", "ReconfiguraciÃ³n de polÃ­ticas"),
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
        r"acceso no autoriz", r"intrus", r"suplantaci[oÃ³]n",
        r"credenciales? (compromet|filtrad|robadas)", r"elevaci[oÃ³]n de privilegios",
        r"cuenta comprometida|login irregular",
    ],
    "ModificaciÃ³n de recursos no autorizado": [
        r"defacement|desfiguraci[oÃ³]n", r"alteraci[oÃ³]n|modificaci[oÃ³]n.*no autoriz",
        r"borrad(o|a) (no autoriz|accidental)", r"integridad.*(afectad|compromet)",
    ],
    "Uso inapropiado de recursos": [
        r"uso inapropiad|uso indebido|violaci[oÃ³]n.*pol[Ã­i]tica.*uso", r"usb no autoriz",
    ],
    "No disponibilidad de recursos": [
        r"ca[iÃ­]da|indisponibil|no disponible|servicio.*no responde|interrupci[oÃ³]n|apag[oÃ³]n|fuera de servicio|vpn.*ca[iÃ­]da|ddos|denegaci[oÃ³]n",
    ],
    "ExploraciÃ³n de Vulnerabilidades": [
        r"escane[oÃ³]|scan|nmap|nessus|openvas|enumeraci[oÃ³]n|port scan|sondeo de puertos",
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
        return "DSTC - Soporte TÃ©cnico"
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
    if re.search(r"portal web|sitio web|web p[Ãºu]blica|p[aÃ¡]gina web", t): return "Portal Web"
    if re.search(r"base de datos|postgres|oracle|mysql|sql server|mssql", t): return "Base de Datos"
    return ""

def infer_area(texto: str) -> str:
    t = texto.lower()
    m = re.search(r"(Ã¡rea|area|departamento|unidad)\s+de\s+([a-zÃ¡Ã©Ã­Ã³ÃºÃ± ]+)", t)
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
# Generador de CODIGO: INC-<dÃ­a>-<mes>-<NNN>
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
    placeholder="Ej: A las 8:00am el Ã¡rea de Contabilidad reporta por Correo que no puede acceder al sistema de Correo corporativo. Como acciÃ³n inmediata, el usuario reiniciÃ³ el equipo y Mesa de Ayuda validÃ³ conectividad sin resultados. Seguridad InformÃ¡tica coordinÃ³ la atenciÃ³n y reiniciÃ³ el servicio de Correo en el servidor, verificando autenticaciÃ³n y entrega de mensajes. A las 10:15am el servicio quedÃ³ restablecido y se cerrÃ³ el incidente.",
    help="Incluye: Fecha/hora de apertura, Sistema, Ãrea, AcciÃ³n inmediata, SoluciÃ³n, Ãrea GTIC que coordinÃ³ y Fecha/hora de cierre."
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

        # 2) Saneo + normalizaciÃ³n a 21 columnas
        cleaned = sanitize_text(response_text)
        cleaned = re.sub(r"\s\|\s", " ; ", cleaned)
        assert_20_pipes(cleaned)
        fila, avisos = normalize_21_fields(cleaned)
        fila = clean_empty_tokens(fila)
        fila[3] = "Evento" if "evento" in (fila[3] or "").lower() else "Incidente"

        # Forzar vacÃ­os 18â€“21
        fila[17] = ""; fila[18] = ""; fila[19] = ""; fila[20] = ""

        # 3) Fechas: extraer del texto y defaults
        ap_auto, ci_auto = fechas_desde_texto(user_question)
        # Si el modelo no dio apertura, usa ahora
        if not fila[1].strip():
            fila[1] = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
        # Si no hay cierre y el extractor encontrÃ³, Ãºsalo
        if not fila[14].strip() and ci_auto:
            fila[14] = ci_auto

        # 4) Realineo semÃ¡ntico mÃ­nimo (corrige campos corridos)
                # 4) Realineo semÃ¡ntico reforzado (corrige campos corridos)
        CIUDADES = {"la paz","el alto","santa cruz","cochabamba","tarija","potosÃ­","potosi","sucre","beni","pando","oruro","bolivia"}
        IMPACTOS = {"alto","medio","bajo"}
        ESTADOS  = {"cerrado","en investigaciÃ³n","en investigacion"}
        MODO_OPC = ["Correo","Jira","TelÃ©fono","Monitoreo","Webex","WhatsApp"]
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
            """Escribe en idx solo si estÃ¡ vacÃ­o."""
            if not (fila[idx] or "").strip() and (val or "").strip():
                fila[idx] = val
                return True
            return False

        # Limpieza bÃ¡sica
        fila = [(x or "").strip() for x in fila]

        # A) Impacto mal ubicado (a veces cae en Sistema/Ãrea/UbicaciÃ³n/ClasificaciÃ³nâ€¦)
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

        # E) Ãrea GTIC (DSEC/DITC/DSTC/DISC) detectada en otro lado
        for i in range(21):
            if i == 12: 
                continue
            t = (fila[i] or "").lower()
            if any(k in t for k in ["dsec","ditc","dstc","disc"]):
                _put(12, fila[i])
                if i != 12:
                    fila[i] = ""

        # F) Encargado: del texto libre o si cayÃ³ en otra columna
        if not fila[13].strip():
            enc = extraer_encargado(user_question)
            if enc:
                fila[13] = enc
        # Si nombres cortos quedaron en otras columnas, muÃ©velos
        for i in (5,6,7,9,10,11,12):
            t = (fila[i] or "").strip()
            if re.fullmatch(r"[A-Za-zÃÃ‰ÃÃ“ÃšÃœÃ¡Ã©Ã­Ã³ÃºÃ±Ã‘]+(?:\s+[A-Za-zÃÃ‰ÃÃ“ÃšÃœÃ¡Ã©Ã­Ã³ÃºÃ±Ã‘]+)?", t) and len(t.split()) <= 2:
                if t and t[0].isalpha() and t[0].isupper():
                    if _put(13, t): 
                        fila[i] = ""

        # G) â€œAGETICâ€ â†’ Ãrea (si estÃ¡ en otra columna)
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

        # I) UbicaciÃ³n: si hay ciudad en otras columnas, muÃ©vela; si vacÃ­a, infiere del texto
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

        # J) AcciÃ³n inmediata / SoluciÃ³n mal ubicadas (verbos tÃ­picos en otras columnas)
        if not fila[10].strip():
            fila[10] = infer_accion_inmediata(user_question)
        if not fila[11].strip():
            fila[11] = infer_solucion(user_question)

        for i in (5,6,7,9):
            t = (fila[i] or "").lower()
            if re.search(r"\b(reinici|bloque|verific|restablec|permit|desbloque|allow|whitelist)\b", t):
                # Si no hay soluciÃ³n â†’ va a SoluciÃ³n; si hay â†’ a AcciÃ³n inmediata
                if not fila[11].strip():
                    fila[11] = fila[i]
                elif not fila[10].strip():
                    fila[10] = fila[i]
                fila[i] = ""

        # K) ClasificaciÃ³n final (catÃ¡logo + inferencia)
        fila[9] = normaliza_clasificacion_final(fila[9]) or infer_clasificacion(user_question) or "Otros"

        # L) CorrecciÃ³n de valores imposibles en Sistema/Ãrea/UbicaciÃ³n
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

        # 5) Tiempo de soluciÃ³n
        if not fila[15].strip():
            fila[15] = calcula_tiempo_solucion(fila[1], fila[14])
        if not fila[15].strip():
            fila[15] = calcula_tiempo_desde_texto(user_question)

        # 6) Inferencias y normalizaciones
        # Modo Reporte
        fila[2] = norm_opcion(fila[2] or detectar_modo_reporte(user_question),
                              ["Correo","Jira","TelÃ©fono","Monitoreo","Webex","WhatsApp"]) or "Otro"

        # UbicaciÃ³n (si quedÃ³ vacÃ­a)
        if not fila[7].strip():
            fila[7] = detectar_ubicacion_ext(user_question) or "La Paz, Bolivia"

        # AcciÃ³n inmediata y SoluciÃ³n
        if not fila[10].strip():
            fila[10] = infer_accion_inmediata(user_question)
        if not fila[11].strip():
            fila[11] = infer_solucion(user_question)

        # ClasificaciÃ³n
        fila[9] = normaliza_clasificacion_final(fila[9]) or infer_clasificacion(user_question) or "Otros"

        # Ãrea de GTIC / Encargado
        if not fila[12].strip():
            fila[12] = infer_area_coordinando(user_question)
        if not fila[13].strip():
            fila[13] = extraer_encargado(user_question)

        # Sistema / Ãrea
        if not fila[5].strip():
            fila[5] = infer_sistema(user_question) or "Firewall"
        if not fila[6].strip():
            fila[6] = infer_area(user_question)

        # Estado por defecto
        if not fila[16].strip():
            fila[16] = "Cerrado" if fila[14].strip() else "En investigaciÃ³n"

        # 7) Validaciones finales
        if len(fila) != 21:
            st.error(f"La salida quedÃ³ con {len(fila)} columnas (esperado: 21).")
            st.code(cleaned, language="text")
            st.stop()

        # 8) CÃ³digo + timestamp
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
