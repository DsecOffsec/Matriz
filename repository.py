import streamlit as st
import gspread
import pandas as pd
import time
import google.generativeai as genai
from datetime import datetime

st.title("MATRIZ DE REPORTES DSEC")

# Acceso a Google Sheets
gc = gspread.service_account_from_dict(st.secrets["connections"]["gsheets"])
SHEET_ID = "1UP_fwvXam8-1IXI-oUbkNqGzb0_T0XNrYsU7ziJVAqE"
sh = gc.open_by_key(SHEET_ID)
ws = sh.worksheet("Reportes")

# API Gemini
api_key = st.secrets["GOOGLE_API_KEY"]
genai.configure(api_key=api_key)
model = genai.GenerativeModel("gemini-1.5-flash")  # versión más estable

# Prompt más compacto y robusto
persona = """
Eres un asistente de seguridad informática. Tu tarea es transformar un reporte de incidente en lenguaje natural en una fila estructurada de datos para una hoja de cálculo, llenando las siguientes columnas según su interpretación:

COLUMNAS:
1. CODIGO: inicia con "INC" seguido de la hora del reporte en formato HHMM (por ejemplo: INC0830).
2. Fecha y Hora de Apertura: si se menciona en el reporte una hora explícita de apertura (ej. "a las 8am"), regístrala como "HH:MM" del día actual en formato ISO completo (por ejemplo: "2025-08-05 08:00").
3. Modo Reporte: puede ser "Jira" si fue reportado por ticket, "Monitoreo" si fue automático, o cualquier otro medio explícito como "Correo", "Teléfono", etc.
4. Evento/Incidente: identifica si se trata de un **evento** (una alerta o anomalía puntual) o un **incidente** (compuesto por uno o más eventos que afectan servicios). Usa solamente "Evento" o "Incidente".
5. Descripción Evento/Incidente: redáctala de forma clara, breve y profesional, resumiendo lo ocurrido con precisión (ej. "Falla de acceso a WhatsApp por bloqueo en firewall").
6. Sistema: deduce qué sistema se vio afectado (ej. correo, red, VPN, Active Directory, WhatsApp, etc.).
7. Área: deduce qué área institucional reportó o fue afectada, si se menciona (ej. Recursos Humanos, Contabilidad, etc.).
8. Ubicación: si se menciona alguna ubicación geográfica o interna (sede, edificio, planta), escríbela. Si no se menciona, deja vacío.
9. Solución: explica cómo se resolvió el incidente (ej. "Se desbloqueó en el firewall", "Se reinició el servicio", etc.). Si no se resolvió, deja vacío.
10. Área de GTIC - Coordinando: escribe el área que lideró o coordinó la solución, según se mencione (ej. Redes, Seguridad Informática, Soporte Técnico, etc.).
11. Encargado SI: si se menciona una persona específica de seguridad informática que atendió el incidente, anótala. Si no, deja vacío.
12. Fecha y Hora de Cierre: si el incidente fue resuelto, usa la hora indicada como resolución (ej. “a las 11am se cerró el caso”) o usa la hora actual si no se especifica.
13. Tiempo Solución: calcula el tiempo transcurrido entre Fecha y Hora de Apertura y de Cierre, expresado como "X horas Y minutos". Si no hay cierre, deja vacío.
14. Estado: escribe "Cerrado" si el incidente fue resuelto o "En investigación" si sigue abierto.
15. Vulnerabilidad: si se menciona alguna causa técnica como fallo de configuración, falta de parcheo, error humano, etc., escribe el tipo de vulnerabilidad. Si no, deja vacío.
16. Causa: indica brevemente la causa raíz si se puede deducir (ej. “bloqueo en firewall”, “configuración errónea”, “usuario externo”, etc.).
17. ID Amenaza: si se puede mapear el incidente a un ID o categoría de amenaza de seguridad, escríbela. Si no, deja vacío.
18. Amenaza: redacta el tipo de amenaza si aplica (ej. “phishing”, “malware”, “fuga de datos”, etc.). Si no aplica, deja vacío.

INSTRUCCIONES:
- Entrega la fila como una **lista separada por comas**, sin explicaciones ni comillas.
- Si algún dato no puede ser deducido del reporte, deja ese campo vacío.
- Usa tu criterio profesional para interpretar los campos según el contexto del incidente.

EJEMPLO DE SALIDA ESPERADA:
INC0800, 2025-08-05 08:00, Jira, Incidente, Usuario no puede acceder a WhatsApp, WhatsApp, Soporte Técnico, , Se desbloqueó puerto en firewall, Seguridad Informática, Juan Pérez, 2025-08-05 08:30, 0 horas 30 minutos, Cerrado, , Bloqueo de firewall, , Acceso no autorizado

Ahora, con base en el siguiente reporte en lenguaje natural, genera la fila:

[REPORTE DE ENTRADA]
"""

user_question = st.text_input("Describe el incidente:")

if st.button("Reportar", use_container_width=True):
    prompt = persona + "\n\n[REPORTE DE ENTRADA]\n" + user_question
    try:
        response = model.generate_content([prompt]).text.strip()
        fila = response.split(",")  # genera la fila en orden de columnas
        ws.append_row(fila)  # se insertará en la matriz correctamente
        st.success("Incidente registrado")
        st.write(fila)
    except Exception as e:
        st.error(f"Error al generar contenido: {e}")





