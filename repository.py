import streamlit as st
import gspread
import pandas as pd
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import google.generativeai as genai
from typing import List, Tuple

st.title("MATRIZ DE REPORTES DSEC")

# ---------------------------
# Conexiones y configuración
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

Reglas:
- Usa el ORDEN EXACTO de las 21 columnas de abajo.
- Si un campo llevaría |, reemplázalo por /.
- Si no puedes deducir un valor, déjalo vacío… EXCEPTO los campos 18 (Vulnerabilidad) y 20 (ID Amenaza), que son OBLIGATORIOS.
- Zona horaria: America/La_Paz.
- NO inventes fechas: si el reporte no incluye una fecha explícita con día/mes/año (p. ej., "2025-08-10", "10/08/2025" o "10 de agosto de 2025"), deja vacíos los campos de fecha. Si solo hay horas, no pongas fecha.

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
    # Aviso en vez de abortar; dejamos que normalize_21_fields repare
    if s.count("|") != 20:
        st.info(f"Aviso: el modelo devolvió {s.count('|')} pipes. Intentaré normalizar a 21 columnas.")

def normalize_21_fields(raw: str) -> Tuple[List[str], List[str]]:
    avisos = []
    parts = [p.strip() for p in raw.split("|")]
    original_count = len(parts)
    if original_count > 21:
        keep_tail = 21 - 5  # 16 últimas columnas (6..21)
        desc = " | ".join(parts[4: original_count - keep_tail])
        parts = parts[:4] + [desc] + parts[original_count - keep_tail:]
        avisos.append(f"Se detectaron {original_count} campos; se fusionó el excedente en 'Descripción'.")
    if len(parts) < 21:
        faltan = 21 - len(parts)
        avisos.append(f"Se detectaron {len(parts)} campos; se completaron {faltan} vacíos.")
        parts += [""] * faltan
    parts = [p.strip() for p in parts]
    return parts, avisos

def _is_empty_token(x: str) -> bool:
    return x.strip().lower() in {"vacio", "vacío", "na", "n/a", "none", "null"}

def clean_empty_tokens(parts: list[str]) -> list[str]:
    return [("" if _is_empty_token(p) else p) for p in parts]

def norm_evento_incidente(v: str) -> str:
    v2 = (v or "").strip().lower()
    if "inciden" in v2: 
        return "Incidente"
    if "evento" in v2:
        return "Evento"
    # Heurística: si el texto sugiere ataque/falla → Incidente
    return "Incidente"


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
# Fechas/horas del texto (am/pm y 24h) — para calcular "Tiempo Solución" por horas si aplica
# ---------------------------
MESES_ES = r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre"

def hay_fecha_explicita(texto: str) -> bool:
    """True solo si hay fecha con AÑO explícito."""
    t = texto.lower()
    if re.search(r"\b20\d{2}-\d{1,2}-\d{1,2}\b", t):  # 2025-08-10
        return True
    if re.search(r"\b\d{1,2}[/-]\d{1,2}/\d{4}\b", t):  # 10/08/2025 o 10-08-2025 (exige año)
        return True
    if re.search(rf"\b\d{{1,2}}\s+de\s+(?:{MESES_ES})\s+de\s+\d{{4}}\b", t):  # 10 de agosto de 2025
        return True
    return False

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

def calcula_tiempo_desde_texto(texto: str) -> str:
    # Si hay al menos dos horas en el texto, calcula diferencia en el día actual (sin inventar fecha en columnas)
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
        last_err, response_text = None, None
        for _ in range(2):
            try:
                response = model.generate_content([prompt], generation_config={"temperature": 0.2})
                response_text = response.text if hasattr(response, "text") else str(response)
                break
            except Exception as e:
                last_err = e
        if response_text is None:
            st.error(f"Error al generar contenido: {last_err}")
            st.stop()

        cleaned = sanitize_text(response_text)
        # (opcional) assert_20_pipes(cleaned)   # solo si quieres el aviso
        fila, avisos = normalize_21_fields(cleaned)

        # Si el texto NO trae fecha explícita (con año), vacía campos 2 y 15 (no inventar fechas)
        if not hay_fecha_explicita(user_question):
            fila[1] = ""   # Fecha y Hora de Apertura
            fila[14] = ""  # Fecha y Hora de Cierre

        # --- NO autocompletar fechas desde horas (para cumplir la regla de no inventar fechas) ---
        # Tiempo de solución: intentar por fechas (si existen)
        if not fila[15].strip():
            fila[15] = calcula_tiempo_solucion(fila[1], fila[14])
        # Si no se puede por fechas, calcular por horas mencionadas en el texto (no escribe fechas en columnas)
        if not fila[15].strip():
            fila[15] = calcula_tiempo_desde_texto(user_question)

        # Completar / normalizar desde el texto (si faltan) — hacerlo ANTES de validar requeridos
        fila[2] = norm_opcion(fila[2] or detectar_modo_reporte(user_question), ["Correo", "Jira", "Teléfono", "Monitoreo"]) or "Teléfono"

        if not fila[7].strip():
            fila[7] = detectar_ubicacion_ext(user_question) or "La Paz, Bolivia"

        if not fila[10].strip():
            fila[10] = infer_accion_inmediata(user_question)

        if not fila[11].strip():
            fila[11] = infer_solucion(user_question)

        fila[9] = normaliza_clasificacion_final(fila[9]) or infer_clasificacion(user_question) or "Otros"

        if not fila[12].strip():
            fila[12] = infer_area_coordinando(user_question)

        if not fila[5].strip():
            fila[5] = infer_sistema(user_question)

        if not fila[6].strip():
            fila[6] = infer_area(user_question)

        # Campos obligatorios de Vulnerabilidad (18) y ID Amenaza (20) — si faltan, inferir por reglas
        texto_ctx = " ".join([user_question, fila[4], fila[11], fila[12], fila[6], fila[10]])

        # 18 -> idx 17 (Vulnerabilidad): código
        if not fila[17].strip():
            # Reglas determinísticas de respaldo (Vulnerabilidad)
            _PAT_VULN = [
                (r"(contraseñ|password|clave).*(d[eé]bil|compartid|reutiliz)", "4.1"),
                (r"(sin mfa|sin 2fa|mfa deshabilitad|autenticaci[oó]n.*d[eé]bil)", "4.3"),
                (r"(permisos|roles|segregaci[oó]n|separaci[oó]n de deberes)", "4.2"),
                (r"(software|sistema).*(desactualiz|sin parche|obsolet)", "4.10"),
                (r"(parche|actualizaci[oó]n) (pendiente|faltante)", "4.11"),
                (r"(antivirus|antimalware|edr|xdr) (ausente|desactivado|no instalado)", "4.29"),
                (r"(alta disponibilidad|cluster|ha|redundan|punto [úu]nico de falla)", "4.39"),
                (r"(sin monitoreo|sin alertas|no hay alertas|no se monitorea)", "4.19"),
                (r"(capacidad|recurso(s)? de almacenamiento|cpu|memoria) (insuficiente|saturad)", "4.21"),
                (r"(respaldo|backup|copia(s)? de seguridad) (ausente|no configurad|no se realiza)", "4.30"),
            ]
            t = texto_ctx.lower()
            for pat, code in _PAT_VULN:
                if re.search(pat, t):
                    fila[17] = code
                    break
            if not fila[17].strip():
                # fallback genérico si el texto indica caída/indisponibilidad (riesgo de HA)
                if re.search(r"(ca[ií]da|no disponible|indisponibilidad)", t):
                    fila[17] = "4.39"

        # 20 -> idx 19 (ID Amenaza): código
        if not fila[19].strip():
            _PAT_AMENAZA = [
                (r"(phish|smish|vish|ingenier[íi]a social|suplantaci[oó]n)", "3.3"),
                (r"(ransom|cifrad[oa].*archivo|encrypt(ed)? files?)", "3.5"),
                (r"(malware|virus|troyano|payload|backdoor)", "3.11"),
                (r"(denegaci[oó]n|ddos)", "3.12"),
                (r"(intercept|sniff|escucha)", "3.4"),
                (r"(acceso no autorizado|elevaci[oó]n de privilegios)", "3.9"),
                (r"(corte de energ[ií]a|apag[oó]n|fallas? el[eé]ctric[ao])", "4.6"),
                (r"(temperatura|humedad)", "2.2"),
                (r"(incendio)", "2.10"),
                (r"(inundaci[oó]n)", "2.11"),
                (r"(ca[ií]da|no disponible|indisponibilidad|servicio.*no responde|reinici(ar|o) (servicio|servidor))", "4.1"),
            ]
            t = texto_ctx.lower()
            for pat, code in _PAT_AMENAZA:
                if re.search(pat, t):
                    fila[19] = code
                    break
            if not fila[19].strip():
                # fallback por caída/indisponibilidad
                if re.search(r"(ca[ií]da|no disponible|indisponibilidad|reinici(ar|o))", t):
                    fila[19] = "4.1"

        # Validaciones finales (después de inferencias)
        requeridos = [
            (fila[5], "Falta definir el **Sistema** afectado."),
            (fila[6], "Falta definir el **Área** que reportó el problema."),
            (fila[12], "Falta definir el **Área de GTIC que coordinó**."),
            (fila[13], "Falta definir el **Encargado**."),
            (fila[11], "Falta describir mejor la **Solución aplicada**.")
        ]
        for valor, msg in requeridos:
            if not (valor or "").strip():
                st.error(msg); st.stop()

        if not (fila[17] or "").strip() or not (fila[19] or "").strip():
            st.error("**Vulnerabilidad (18)** e **ID Amenaza (20)** son obligatorios. Añade contexto (p. ej., ‘contraseña débil’, ‘phishing’, ‘caída de servicio’) o ajusta reglas de inferencia.")
            st.stop()

        # Estado por defecto si falta
        if not fila[16].strip():
            fila[16] = "Cerrado" if fila[14].strip() else "En investigación"

        # Generar CODIGO backend (col 1) según Fecha Apertura (col 2) o fecha actual
        codigo = generar_codigo_inc(ws, fila[1] if fila[1].strip() else None)
        fila[0] = codigo

        # Confirmación final de 21 campos
        if len(fila) != 21:
            st.error(f"La salida quedó con {len(fila)} columnas tras saneo (esperado: 21).")
            st.code(cleaned, language="text")
            st.stop()

        # Timestamp servidor (col 22 solo para hoja de cálculo)
        registro_ts = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
        fila_con_ts = fila + [registro_ts]
        
        # Encabezados para la vista previa (22 columnas)
        columnas = [
            "CODIGO","Fecha y Hora de Apertura","Modo Reporte","Evento/ Incidente","Descripción Evento/ Incidente",
            "Sistema","Area","Ubicación","Impacto","Clasificación","Acción Inmediata","Solución",
            "Area de GTIC - Coordinando","Encargado SI","Fecha y Hora de Cierre","Tiempo Solución",
            "Estado","Vulnerabilidad","Causa","ID Amenaza","Amenaza",
            "Fecha y Hora de Registro"
        ]
        
        df_prev = pd.DataFrame([fila_con_ts], columns=columnas)
        st.subheader("Vista previa")
        st.dataframe(df_prev, use_container_width=True)

        # Avisos de saneo (si hubo)
        if avisos:
            st.info(" | ".join(avisos))

        # Guardado
        try:
            ws.append_row(fila_con_ts, value_input_option="RAW")
            st.success("Incidente registrado correctamente.")
        except Exception as e:
            st.error(f"No se pudo escribir en la hoja: {e}")

