import streamlit as st
import gspread
import pandas as pd
import time
import google.generativeai as genai
from datetime import datetime

st.title("MATRIZ DE REPORTES DSEC")

gc = gspread.service_account_from_dict(st.secrets["connections"]["gsheets"])
SHEET_ID = "1UP_fwvXam8-1IXI-oUbkNqGzb0_T0XNrYsU7ziJVAqE"
sh = gc.open_by_key(SHEET_ID)
ws = sh.worksheet("Reportes")         # usa otra worksheet si quieres separarlo

api_key = st.secrets["GOOGLE_API_KEY"]
genai.configure(api_key="api_key")
model = genai.GenerativeModel("gemini-2.5-flash")

persona = """
Eres un asistente de seguridad informática. Dado un reporte de incidente en lenguaje natural, debes estructurarlo como una fila de datos organizada en las siguientes columnas:

1. ID del incidente: usa el formato INC-día-mes-número_del_día (por ejemplo, INC-4-8-001).
2. Hora de apertura del incidente: extrae la hora del incidente reportado (ejemplo: 08:00).
3. Detectado por Jira/Monitoreo: determina si fue reportado manualmente (Jira) o automáticamente (Monitoreo).
4. Severidad: bajo, medio, alto o crítico según lo expresado en el texto.
5. Descripción del incidente: redacta una breve descripción clara.
6. Estado del caso (cerrado/en investigación): según si el incidente fue resuelto o aún está pendiente.

Entrega la respuesta como una lista separada por comas, sin explicaciones. Ejemplo:
INC-4-8-001, 08:00, Jira, Crítico, Usuario recibe spam en su correo, Cerrado
"""

user_question = st.text_input("Describe el incidente:")
if st.button("Reportar", use_container_width=True):
    prompt = persona + "\n\nEntrada del usuario:\n" + user_question
    response = model.generate_content([prompt]).text.strip()

    # Separar por coma y guardar como fila
    fila = [datetime.now().isoformat()] + response.split(",")
    ws.append_row(fila[:7])  # Fecha + 6 columnas
    st.success("Incidente registrado")

    st.write(fila)
