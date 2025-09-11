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
SHEET_ID = "1UP_fwvXam8-1IXI-oUbkNqGzb0_T0XNrYsU7ziJVAqE"  # ideal: mover a secrets
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
2. **Modo de reporte** - Si lo reportaron por correo, JIRA, monitoreo, llamada, etc.
3. **Sistema afectado** — Por ejemplo: Correo, VPN, Antivirus, Firewall, etc.  
4. **Área afectada** — El departamento o unidad donde se detectó el problema.  
5. **Acción inmediata tomada** — Lo que hizo el usuario para mitigar el problema.  
6. **Solución aplicada** — Acción final que resolvió el incidente.  
7. **Área de GTIC que coordinó** — Infraestructura, Seguridad, Soporte Técnico, etc.  
8. **Encargado** - El que encargado de todo el incidente/alerta.
9. **Fecha y hora de cierre** — Cuando se resolvió el incidente.
""")

# ---------------------------
# Guías (texto de referencia)
# ---------------------------
guia_vuln = """  
1.1 - Ausencia o carencia de personal idóneo.
1.2 - Ausencia o carencia de conocimientos y habilidades en informática.
1.3 - Desconocimiento de políticas, normas, o procedimientos de Seguridad de la Información.
1.4 - Falta de conciencia en el reporte de incidentes de Seguridad de la Información.
1.5 - Ausencia o carencia de conocimiento para el manejo de herramientas de seguridad informática.
1.6 - Falta de conciencia en Seguridad de la Información.
1.7 - Desconocimiento de las políticas para el buen uso de los activos de información (Red, Correo, Internet, Sistemas de Información, Chat, Redes Sociales, etc.).
1.8 - Desconocimiento del marco legal y regulatorio de seguridad de la información.
1.9 - Desconocimiento de los controles de seguridad informática aplicados a los activos de información que son de su responsabilidad.
1.10 - Desconocimiento del marco legal y regulatorio de la protección de los datos personales.
1.11 - Falta de conciencia en Protección de Datos Personales
1.12 - Desconocimiento de políticas, normas, o procedimientos para el tratamiento de los datos personales.
1.13 - Sobrecarga en la asignación de funciones.
1.14 - Ausencia de personal de respaldo para los cargos críticos
1.15 - Capacidad reducida del proceso en cuanto a recursos humanos

2.1 - Ausencia de segregación de funciones o separación de deberes.
2.2 - Ausencia de lineamientos para la divulgación de información al público.
2.3 - Ausencia de procedimientos para la clasificación, etiquetado y manejo de la información.
2.4 - Ausencia de lineamientos de seguridad de la información en todo el ciclo de la relación con los proveedores.
2.5 - Ausencia de lineamientos de seguridad de la información para antes de asumir el empleo, durante la ejecución del empleo y para la terminación y cambio del empleo.
2.6 - Ausencia de pruebas de vulnerabilidades técnicas de forma regular.
2.7 - Ausencia de medidas apropiadas para corregir las vulnerabilidades técnicas. 
2.8 - Ausencia de registros sobre las actividades del usuario, excepciones, fallas y eventos.
2.9 - Falta de revisión periódica de los registros de eventos de auditoría.
2.10 - Falta de documentación técnica sobre los componentes tecnológicos.
2.11 - Falta de integrar la seguridad de la información en todas las fases de la gestión del proyecto.
2.12 - Ausencia de lineamientos para el tratamiento de los datos personales. 
2.13 - Falta definición de requisitos contractuales para la transmisión o transferencia de datos personales. 
2.14 - Ausencia de procedimientos claros y de herramientas adecuadas para garantizar la eliminación segura de la información o datos personales cuando ya no se requieran.
2.15 - Carencia de procedimientos y herramientas para la atención de consultas, reclamos, peticiones de rectificación, actualización y supresión de datos personales.
2.16 - Falta de la autorización por parte del titular para el tratamiento de los datos personales.
2.17 - Falta de contactos apropiados con las autoridades y grupos de interés de seguridad de la información.
2.18 - Inadecuada gestión de los medios removibles.
2.19 - Falta o deficiencia de los procedimientos para el control en los cambios en instalaciones de procesamiento de información.
2.20 - Ausencia de procedimientos para controlar la instalación de software.
2.21 - Falta de reglas para instalación de software por parte de los colaboradores.
2.22 - Falta de acuerdos de confidencialidad.
2.23 - Falta de acuerdos para la transferencia de información.
2.24 - Inadecuada gestión de incidentes y debilidades de seguridad.
2.25 - Falta de considerar la seguridad en Planes de Continuidad.
2.26 - Falta de revisiones periódicas de cumplimiento.
2.27 - Ausencia de notificación de cambios técnicos y operativos.
2.28 - Falta de verificación de la continuidad de seguridad.
2.29 - Ausencia de controles para restringir acceso a códigos fuente.
2.30 - Ausencia de controles sobre los datos de pruebas.
2.31 - Ausencia de controles para proteger ambientes de desarrollo.
2.32 - Ausencia de controles para proteger integridad de datos en redes públicas.
2.33 - Falta de revisión de integridad en cambios.
2.34 - Falta de revisión técnica tras cambios de plataforma.

3.1 - Insuficiencia o mal funcionamiento de controles de acceso físico.
3.2 - Falta de monitoreo en controles de acceso físico.
3.3 - Falta de mantenimiento a la infraestructura física.
3.4 - Ubicación en área susceptible de inundación.
3.5 - Ausencia de protección contra humedad, polvo y suciedad.
3.6 - Insuficiencia de archivadores para almacenamiento.
3.7 - Ausencia de controles antisísmicos.
3.8 - Ausencia de controles de prevención de incendios.
3.9 - Documentos impresos sin protección.
3.10 - Manejo inadecuado de la información.
3.11 - Zona susceptible a vandalismo, protestas.
3.12 - Acceso sin control a zonas seguras.

4.1 - Gestión deficiente de contraseñas.
4.2 - Asignación errada de privilegios.
4.3 - Ausencia o debilidad en mecanismos de autenticación.
4.4 - Segregación inadecuada de funciones o roles.
4.5 - Sin revisión periódica de permisos.
4.6 - Notificación tardía de novedades de usuarios.
4.7 - Documentación de sistemas desactualizada.
4.8 - Ausencia de protección a datos en pruebas.
4.9 - Uso de software no conforme a requerimientos.
4.10 - Uso de software desactualizado o vulnerable.
4.11 - Falta de control en actualizaciones.
4.12 - Falta de pruebas de aceptación en los sistemas.
4.13 - Ausencia o insuficiencia de pruebas de la funcionalidad de la seguridad de los sistemas.
4.14 - Conexiones a redes públicas sin mecanismos de protección.
4.15 - Configuraciones por defecto.
4.16 - Los ambientes de pruebas, desarrollo y producción no se encuentran separados.
4.17 - Incapacidad del sistema para atender un alto volumen de conexiones.
4.18 - Permitir la ejecución de sesiones simultáneas del mismo usuario en el sistema de información o servicio.
4.19 - Ausencia de alertas de seguridad en los componentes tecnológicos.
4.20 - Uso de protocolos con vulnerabilidades para la protección de la confidencialidad o integridad.
4.21 - Ausencia o deficiencia en los recursos de almacenamiento y procesamiento.
4.22 - Ausencia o deficiencia de seguimiento y monitoreo a los recursos de almacenamiento y procesamiento de información.
4.23 - Habilitación de servicios de red innecesarios.
4.24 - Ausencia de documentación de los puertos que utilizan los sistemas de información o servicios informáticos.
4.25 - Ausencia de líneas base para la instalación de los componentes tecnológicos.
4.26 - Ausencia de control para "terminar sesión" luego de un tiempo determinado de inactividad.
4.27 - Ausencia de controles criptográficos o uso de cifrado débil.
4.28 - Inadecuado uso y protección a las llaves criptográficas durante su ciclo de vida.
4.29 - Ausencia de controles de detección, de prevención y de recuperación para proteger contra códigos maliciosos.
4.30 - Ausencia de copias de respaldo de la información, software e imágenes de los sistemas.
4.31 - Falta de pruebas de verificación de las copias de respaldo.
4.32 - Inadecuada protección de la información de registro.
4.33 - Protección inadecuada de la información en las redes de la información.
4.34 - Protección inadecuada a la información manejada por mensajería electrónica.
4.35 - Falta de integrar la seguridad de la información durante todo el ciclo de vida de los sistemas.
4.36 - Falta o fallas de sincronización de los relojes de los sistemas de procesamiento de información.
4.37 - Ausencia de Planes de Recuperación de Desastres (DRP).
4.38 - Falta de pruebas de verificación a los planes de recuperación de desastres.
4.39 - Ausencia de sistemas redundantes (Alta Disponibilidad), que permita dar una respuesta más rápida en eventos de falla.
4.40 - Sistemas publicados expuestos al acceso general.

5.1 - Mantenimiento insuficiente o inoportuno de los componentes de hardware.
5.2 - Ausencia de mantenimientos preventivos programados.
5.3 - Debilidades en la seguridad perimetral de la red de datos.
5.4 - Arquitectura de red de datos sin cumplir con los requerimientos de seguridad de la información.
5.5 - Ausencia de control sobre dispositivos móviles.
5.6 - Dependencia de un sólo proveedor de Internet.
5.7 - Ausencia o insuficiencia de ANS (Acuerdos de Niveles de Servicio).
5.8 - Susceptibilidad a las variaciones de temperatura.
5.9 - Susceptibilidad a las variaciones de voltaje.
5.10 - Obsolescencia tecnológica.
5.11 - Uso inadecuado de los componentes tecnológicos (equipos de cómputo, dispositivos de red, servidores, etc.).
"""

guia_amenazas = """  
1.1 - Sobrecarga laboral.
1.2 - Ingeniería social.
1.3 - Coacción.
1.4 - Sabotaje.
1.5 - Errores humanos en el cumplimiento de las labores.
1.6 - Acciones fraudulentas 
1.7 - Entrega indebida de la información.
1.8 - Modificación indebida de la información.
1.9 - Situaciones administrativas durante la relación laboral (incapacidades, vacaciones, muerte, licencias).

2.1 - Contaminación, Polvo, Corrosión.
2.2 - Niveles de temperatura o humedad por fuera de los rangos aceptables.
2.3 - Fallas de electricidad.
2.4 - Señales de interferencia.
2.5 - Daño en instalaciones físicas.
2.6 - Fallas en el aire acondicionado.
2.7 - Fallas en las UPS.
2.8 - Fallas en la planta eléctrica.
2.9 - Desastres naturales.
2.10 - Incendio.
2.11 - Inundación.
2.12 - Asonada/Conmoción civil / Terrorismo/Vandalismo.
2.13 - Desastre accidental.
2.14 - Daño en componentes tecnológicos

3.1 - Ataque informático para acceder a información reservada o clasificada.
3.2 - Ataque informático para modificar datos.
3.3 - Ingeniería social.
3.4 - Interceptación de información.
3.5 - Cifrado no autorizado de la información por malware o acción mal intencionada.
3.6 - Corrupción de los datos por fallas en el software.
3.7 - Suplantación de usuarios.
3.8 - Abuso de privilegios.
3.9 - Elevación de privilegios.
3.10 - Exposición de información confidencial y de uso interno por errores de configuración.
3.11 - Malware / software malicioso.
3.12 - Denegación de servicios.
3.13 - Alteración de la información
3.14 - Divulgación de la información
3.15 - Uso indebido de la información
3.16 - Uso no autorizado de la información

4.1 - Fallas en los componentes de hardware. 
4.2 - Falla de medios de respaldo y recuperación.
4.3 - Fallas en el aire acondicionado.
4.4 - Uso de equipos no autorizados como piñas, videocámaras, y grabadoras entre otros.
4.5 - Hurto de equipos, medios magnéticos o documentos.
4.6 - Fallas en el suministro de energía eléctrica
4.7 - Acceso a información confidencial y de uso interno desde componentes tecnológicos reciclados o desechados.
"""

# Conjuntos válidos y patrones
ID_VULN_VALIDOS = set(re.findall(r'(\d+\.\d+)\s*-\s', guia_vuln))
ID_AMENAZA_VALIDOS = set(re.findall(r'(\d+\.\d+)\s*-\s', guia_amenazas))
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
13. Area de GTIC - Coordinando → (Redes, Seguridad Informática, Soporte Técnico, Sistemas, …).
14. Encargado SI → solo si se menciona; no inventes nombres.
15. Fecha y Hora de Cierre → YYYY-MM-DD HH:MM, solo si se menciona (con día/mes/año explícitos).
16. Tiempo Solución → “X horas Y minutos” si puedes calcular (Cierre − Apertura); si no, vacío.
17. Estado → Cerrado | En investigación.
18. Vulnerabilidad → SOLO un código con formato N.N tomado de la “Guia Vuln”.
19. Causa → vacío.
20. ID Amenaza → SOLO un código con formato N.N tomado de la “Guia Amenazas”.
21. Amenaza → vacío.

Guía de Vulnerabilidades:
{guia_vuln}

Guía de Amenazas:
{guia_amenazas}

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

def valida_id(code: str, validos: set) -> str:
    code = code.strip()
    if re.fullmatch(r"\d+\.\d+", code) and code in validos:
        return code
    return ""

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

def hay_fecha_explicita(texto: str) -> bool:
    """True solo si hay fecha con AÑO explícito."""
    t = texto.lower()
    if re.search(r"\b20\d{2}-\d{1,2}-\d{1,2}\b", t):  # 2025-08-10
        return True
    if re.search(r"\b\d{1,2}[/-]\d{1,2}/\d{4}\b", t):  # 10/08/2025 o 10-08-2025 (exige año de 4 dígitos)
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

def fechas_desde_horas_si_aplica(texto: str) -> tuple[str, str]:
    """Si no hay fecha con año explícito, usa la fecha de hoy con las horas encontradas."""
    if hay_fecha_explicita(texto):
        return "", ""
    hh = extraer_horas_any(texto)
    if not hh:
        return "", ""
    today = datetime.now(TZ).date()
    apertura = f"{today} {hh[0]}"
    cierre = f"{today} {hh[-1]}" if len(hh) > 1 else ""
    return apertura, cierre

# ---------------------------
# Reubicador de códigos mal colocados (Causa/Amenaza)
# ---------------------------
def reubicar_codigos_mal_colocados(fila: List[str]) -> List[str]:
    movimientos = []
    if fila[18].strip() and CODE_RE.fullmatch(fila[18].strip()):
        code = fila[18].strip()
        if code in ID_AMENAZA_VALIDOS and not fila[19].strip():
            fila[19] = code; movimientos.append("ID Amenaza <- Causa")
        elif code in ID_VULN_VALIDOS and not fila[17].strip():
            fila[17] = code; movimientos.append("Vulnerabilidad <- Causa")
        fila[18] = ""
    if fila[20].strip() and CODE_RE.fullmatch(fila[20].strip()):
        code = fila[20].strip()
        if code in ID_AMENAZA_VALIDOS and not fila[19].strip():
            fila[19] = code; movimientos.append("ID Amenaza <- Amenaza")
        elif code in ID_VULN_VALIDOS and not fila[17].strip():
            fila[17] = code; movimientos.append("Vulnerabilidad <- Amenaza")
        fila[20] = ""
    return movimientos

# ---------------------------
# Reglas determinísticas de respaldo (Amenaza/Vulnerabilidad)
# ---------------------------
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

def infer_amenaza(texto: str) -> str:
    t = texto.lower()
    for pat, code in _PAT_AMENAZA:
        if re.search(pat, t): return code
    if re.search(r"(ca[ií]da|no disponible|indisponibilidad|reinici(ar|o))", t):
        return "4.1"
    return ""

def infer_vulnerabilidad(texto: str) -> str:
    t = texto.lower()
    for pat, code in _PAT_VULN:
        if re.search(pat, t): return code
    if re.search(r"(ca[ií]da|no disponible|indisponibilidad)", t):
        return "4.39"
    return ""

# ---------------------------
# Inferencia de Ubicación / Modo / Acción / Solución / Clasificación / Área GTIC / Sistema / Área
# ---------------------------
DEPTS_BO = {
    "la paz": ["la paz", "lpz", "senkata"],
    "santa cruz": ["santa cruz", "scz", "santa cruz de la sierra","PAU"],
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
    if "jira" in t: return "Jira"
    if "monitoreo" in t or "alerta" in t: return "Monitoreo"
    if "teléfono" in t or "telefono" in t or "llam" in t: return "Teléfono"
    if "correo" in t or "e-mail" in t or "email" in t: return "Correo"
    return ""

ACCION_RULES = [
    (r"reinici(ar|ó|o|amos|aron).*(equipo|pc|servicio|servidor)", "Reinicio de servicios/equipo"),
    (r"verific(ar|ó|aron).*conectividad|ping|traz", "Verificación de conectividad"),
    (r"bloque(o|ar|ó).*cuenta|forz[oó].*contraseñ|cambio de contraseñ", "Bloqueo/cambio de contraseñas"),
    (r"aisl(ar|ado|amiento).*equipo|segmentaci[oó]n", "Aislamiento del equipo"),
]
SOLUCION_RULES = [
    (r"reinici(ar|ó).*(servicio|servidor)", "Reinicio de servicios"),
    (r"ampli(ar|ación).*(licencia|licencias)", "Ampliación de licencias"),
    (r"aplicar(on)? (parches|actualizaciones)|actualiz(ar|ó)", "Aplicación de actualizaciones"),
    (r"restaur(ar|ó).*(backup|respaldo|copias)", "Restauración desde respaldo"),
    (r"mitigaci[oó]n.*(waf|ddos)|\bwaf\b", "Mitigación en WAF"),
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
    if "seguridad" in t: return "Seguridad Informática"
    if "redes" in t or "vpn" in t or "cisco" in t: return "Redes"
    if "infraestructura" in t: return "Infraestructura"
    if "soporte" in t or "mesa de ayuda" in t: return "Soporte Técnico"
    if "sistemas" in t or "erp" in t or "base de datos" in t: return "Sistemas"
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
        fila, avisos = normalize_21_fields(cleaned)

        # Si el texto NO trae fecha explícita (con año), vacía campos 2 y 15
        if not hay_fecha_explicita(user_question):
            fila[1] = ""   # Fecha y Hora de Apertura
            fila[14] = ""  # Fecha y Hora de Cierre

        # Completar fechas a partir de horas si solo hay horas (am/pm o 24h)
        ap_auto, ci_auto = fechas_desde_horas_si_aplica(user_question)
        if not fila[1].strip() and ap_auto: fila[1] = ap_auto
        if not fila[14].strip() and ci_auto: fila[14] = ci_auto

        # Reubicar si Gemini metió códigos en Causa/Amenaza
        movimientos = reubicar_codigos_mal_colocados(fila)

        # Validaciones de códigos
        fila[17] = valida_id(fila[17], ID_VULN_VALIDOS)     # Vulnerabilidad
        fila[19] = valida_id(fila[19], ID_AMENAZA_VALIDOS)  # ID Amenaza

        # Fallback determinístico si faltan Vulnerabilidad/Amenaza
        texto_ctx = " ".join([user_question, fila[4], fila[11], fila[12], fila[6], fila[10]])
        if not fila[19]:
            fila[19] = valida_id(infer_amenaza(texto_ctx), ID_AMENAZA_VALIDOS)
        if not fila[17]:
            fila[17] = valida_id(infer_vulnerabilidad(texto_ctx), ID_VULN_VALIDOS)

        # Enfoque estricto: Causa (19) y Amenaza (21) SIEMPRE vacías
        fila[18] = ""
        fila[20] = ""

        if not fila[5]:
            st.error("Falta definir que sistema fue afectado")
            st.stop()
        if not fila[12]:
            st.error("Falta definir Con la Area de GTIC que se coordino")
            st.stop()
        if not fila[13]:
            st.error("Falta definir quien es el encargado")
            st.stop()
        if not fila[14]:
            st.error("Falta definir la hora del cierre del incidente")
            st.stop()

        # Completar otros campos desde el texto si faltan
        if not fila[2].strip():
            fila[2] = detectar_modo_reporte(user_question)
        if not fila[7].strip():
            fila[7] = detectar_ubicacion_ext(user_question)
        if not fila[10].strip():
            fila[10] = infer_accion_inmediata(user_question)
        if not fila[11].strip():
            fila[11] = infer_solucion(user_question)
        # Clasificación (normaliza o infiere; lista cerrada)
        fila[9] = normaliza_clasificacion_final(fila[9]) or infer_clasificacion(user_question) or "Otros"
        # Área GTIC coordinando
        if not fila[12].strip():
            fila[12] = infer_area_coordinando(user_question)
        # Sistema (VPN, Correo, etc.)
        if not fila[5].strip():
            fila[5] = infer_sistema(user_question)
        # Área (Contabilidad, etc.)
        if not fila[6].strip():
            fila[6] = infer_area(user_question)

        # Tiempo de solución: por fechas o, si no, por horas
        if not fila[15].strip():
            fila[15] = calcula_tiempo_solucion(fila[1], fila[14])
        if not fila[15].strip():
            fila[15] = calcula_tiempo_desde_texto(user_question)

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

        # Vista previa
        columnas = [
            "CODIGO","Fecha y Hora de Apertura","Modo Reporte","Evento/ Incidente","Descripción Evento/ Incidente",
            "Sistema","Area","Ubicación","Impacto","Clasificación","Acción Inmediata","Solución",
            "Area de GTIC - Coordinando","Encargado SI","Fecha y Hora de Cierre","Tiempo Solución",
            "Estado","Vulnerabilidad","Causa","ID Amenaza","Amenaza"
        ]
        df_prev = pd.DataFrame([fila], columns=columnas)
        st.subheader("Vista previa")
        st.dataframe(df_prev, use_container_width=True)

        # Info de correcciones automáticas (si las hubo)
        avisos_extra = []
        if movimientos:
            avisos_extra.append("Se reubicaron códigos: " + ", ".join(movimientos))
        if avisos or avisos_extra:
            st.info(" | ".join(avisos + avisos_extra))

        # Guardado
        try:
            ws.append_row(fila, value_input_option="RAW")
            st.success("Incidente registrado correctamente.")
        except Exception as e:
            st.error(f"No se pudo escribir en la hoja: {e}")








