import streamlit as st
import gspread
import pandas as pd
import re
from typing import Optional, List, Tuple
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

st.title("MATRIZ DE REPORTES DSEC")

# ---------------------------
# Conexiones y configuración
# ---------------------------
gc = gspread.service_account_from_dict(st.secrets["connections"]["gsheets"])
SHEET_ID = "1UP_fwvXam8-1IXI-oUbkNqGzb0_T0XNrYsU7ziJVAqE"
sh = gc.open_by_key(SHEET_ID)
ws = sh.worksheet("Reportes")

TZ = ZoneInfo("America/La_Paz")

st.markdown("""
### 📝 Instrucciones para registrar un incidente

Por favor, describe el incidente en **un solo párrafo** incluyendo:

- Fecha y hora de apertura (si solo hay horas, ponlas igual).
- Modo de reporte (Correo, Jira, Monitoreo, Teléfono, Webex, WhatsApp…).
- Sistema afectado (Correo, VPN, AD, Firewall, ERP, etc).
- Área afectada.
- Acción inmediata.
- Solución aplicada.
- Área de GTIC que coordinó (DSEC/DSTC/DITC/DISC).
- Encargado.
""")

# ---------------------------
# Utilidades
# ---------------------------
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
# Fechas/horas del texto
# ---------------------------
MESES_ES = r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre"
MESES_MAP = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}
ISO_FECHA_RE = re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b")
DMY_SLASH_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b")
DM_DE_MES_RE = re.compile(
    rf"\b(\d{{1,2}})\s+de\s+(?:{MESES_ES})(?:\s+de\s+(\d{{4}}))?\b", re.IGNORECASE
)
AMPM_RE = re.compile(
    r"\b(?P<hour>1[0-2]|0?[1-9])(?::(?P<minute>[0-5]\d))?\s*(?P<ampm>a\.?m\.?|am|p\.?m\.?|pm)\b",
    re.IGNORECASE
)
H24_RE = re.compile(r"\b(?P<hour>[01]?\d|2[0-3]):(?P<minute>[0-5]\d)\b")

def _safe_int(x: str) -> Optional[int]:
    try:
        return int(x)
    except Exception:
        return None

def _year_or_current(y: Optional[str]) -> int:
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

# ---------------------------
# Inferencias semánticas
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
    if "webex" in t:
        return "Webex"
    if any(x in t for x in ["correo", "e-mail", "email", "mail", "outlook"]):
        return "Correo"
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
    (r"bloque(o|ar).*(dominio|domain)", "Bloqueo de dominio"),
    (r"an[aá]lisis.*(url|enlace|link)", "Análisis de URLs"),
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

CLASIF_CANON = {
    "acceso no autorizado": "Acceso no autorizado",
    "modificación de recursos no autorizado": "Modificación de recursos no autorizado",
    "uso inapropiado de recursos": "Uso inapropiado de recursos",
    "no disponibilidad de recursos": "No disponibilidad de recursos",
    "multicomponente": "Multicomponente",
    "exploración de vulnerabilidades": "Exploración de Vulnerabilidades",
    "otros": "Otros",
}
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

def infer_clasificacion(texto: str) -> str:
    hits = []
    t = texto.lower()
    for nombre, pats in CLASIF_PATTERNS.items():
        if any(re.search(p, t) for p in pats):
            hits.append(nombre)
    if len(hits) >= 2: return "Multicomponente"
    if len(hits) == 1: return hits[0]
    return "Otros"

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

def norm_evento_incidente(texto: str) -> str:
    t = texto.lower()
    if "evento" in t: return "Evento"
    return "Incidente"

# Encargado
PERSON_RE = re.compile(r'^[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,3}$')
def extraer_encargado(texto: str) -> str:
    m = re.search(r"(encargad[oa]|responsable)\s+(?:es\s+)?([a-záéíóúñ\s]+)", texto, re.IGNORECASE)
    if m:
        nombre = m.group(2).strip()
        nombre = re.split(r"\s+(del|de la|de los|de las)\b", nombre, 1, flags=re.IGNORECASE)[0].strip()
        if nombre and len(nombre.split()) <= 4:
            return " ".join(w.capitalize() for w in nombre.split())
    # fallback: si aparece un Nombre Apellido y no está en solución
    posibles = re.findall(r"\b([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,2})\b", texto)
    for p in posibles:
        if 2 <= len(p.split()) <= 3:
            return p
    return ""

def limpiar_solucion_si_es_nombre(sol: str, encargado: str) -> str:
    s = (sol or "").strip()
    e = (encargado or "").strip()
    if not s:
        return s
    if PERSON_RE.match(s):  # parece nombre propio
        return ""
    if e and (s.lower() == e.lower() or s.lower() in e.lower() or e.lower() in s.lower()):
        return ""
    return s

# ---------------------------
# Generador de CODIGO: INC-<día>-<mes>-<NNN>
# ---------------------------
def generar_codigo_inc(ws, fecha_apertura: Optional[str]) -> str:
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

    codigos = ws.col_values(1)
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
    placeholder="Ej: El viernes 5 de septiembre a las 15:00, ...",
    help="Incluye: Fecha/hora de apertura, Sistema, Área, Acción inmediata, Solución, Área GTIC que coordinó y Fecha/hora de cierre."
)

if st.button("Reportar", use_container_width=True):
    if not user_question.strip():
        st.warning("Por favor, describe el incidente antes de continuar.")
        st.stop()

    with st.spinner("Extrayendo campos..."):

        # 1) Columnas por significado (nada de re-alinear)
        # 1. CODIGO (vacío por ahora)
        col1 = ""

        # 2 & 15 Fechas
        apertura, cierre = fechas_desde_texto(user_question)

        # 3 Modo
        modo = detectar_modo_reporte(user_question)

        # 4 Evento/Incidente
        ev_inc = norm_evento_incidente(user_question)

        # 5 Descripción (usa el texto; podrías resumir si quieres)
        desc = user_question.strip()

        # 6 Sistema
        sistema = infer_sistema(user_question)

        # 7 Área
        area = infer_area(user_question)

        # 8 Ubicación
        ubic = detectar_ubicacion_ext(user_question)

        # 9 Impacto (simple heurística)
        t = user_question.lower()
        if "crític" in t or "critico" in t or "alto" in t:
            impacto = "Alto"
        elif "medio" in t:
            impacto = "Medio"
        elif "bajo" in t:
            impacto = "Bajo"
        else:
            impacto = ""

        # 10 Clasificación
        clasif = infer_clasificacion(user_question)

        # 11 Acción inmediata
        accion = infer_accion_inmediata(user_question)

        # 12 Solución (y limpiar si es nombre)
        solucion = infer_solucion(user_question)
        encargado_tmp = extraer_encargado(user_question)
        solucion = limpiar_solucion_si_es_nombre(solucion, encargado_tmp)
        if not solucion:
            # si quedó vacío, intenta inferir de nuevo con más generosidad (opcional)
            solucion = infer_solucion(user_question)

        # 13 Área de GTIC coordinando
        area_gtic = infer_area_coordinando(user_question)

        # 14 Encargado
        encargado = encargado_tmp

        # 16 Tiempo de solución
        tiempo_sol = calcula_tiempo_solucion(apertura, cierre)
        if not tiempo_sol and apertura and not cierre:
            # Si no hay cierre, al menos no inventes tiempo
            tiempo_sol = ""

        # 17 Estado
        estado = "Cerrado" if cierre else "En investigación"

        # 18-21 SIEMPRE VACÍOS (por tu requerimiento)
        vulnerabilidad = ""
        causa = ""
        id_amenaza = ""
        amenaza = ""

        # Validaciones mínimas que quieras exigir
        if not sistema:
            st.error("Falta definir el **Sistema** afectado.")
            st.stop()

        # 1) Generar CODIGO
        codigo = generar_codigo_inc(ws, apertura)
        col1 = codigo

        # 2) Armar fila en el ORDEN exacto
        fila = [
            col1,                # 1 CODIGO
            apertura,            # 2 Fecha y Hora de Apertura
            modo,                # 3 Modo Reporte
            ev_inc,              # 4 Evento/Incidente
            desc,                # 5 Descripción
            sistema,             # 6 Sistema
            area,                # 7 Area
            ubic,                # 8 Ubicación
            impacto,             # 9 Impacto
            clasif,              # 10 Clasificación
            accion,              # 11 Acción Inmediata
            solucion,            # 12 Solución
            area_gtic,           # 13 Area de GTIC - Coordinando
            encargado,           # 14 Encargado SI
            cierre,              # 15 Fecha y Hora de Cierre
            tiempo_sol,          # 16 Tiempo Solución
            estado,              # 17 Estado
            vulnerabilidad,      # 18 Vulnerabilidad
            causa,               # 19 Causa
            id_amenaza,          # 20 ID Amenaza
            amenaza,             # 21 Amenaza
        ]

        # 3) Vista previa + guardar
        registro_ts = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
        fila_con_ts = fila + [registro_ts]

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

        try:
            ws.append_row(fila_con_ts, value_input_option="RAW")
            st.success("Incidente registrado correctamente.")
        except Exception as e:
            st.error(f"No se pudo escribir en la hoja: {e}")
