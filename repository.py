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
genai.configure(api_key=api_key)  # ✅ corregido
model = genai.GenerativeModel("gemini-1.5-flash")  # versión más estable

# Prompt más compacto y robusto
persona = (
    "Analiza esta frase y extrae los siguientes datos separados por comas:\n"
    "ID del incidente (formato INC-dia-mes-numero), "
    "Hora de apertura, "
    "Origen del reporte (Jira o Monitoreo), "
    "Severidad (Bajo/Medio/Alto/Crítico), "
    "Descripción corta, "
    "Estado (Cerrado o En investigación).\n\n"
    "Ejemplo de salida:\n"
    "INC-4-8-001, 08:00, Jira, Crítico, Usuario recibe spam, Cerrado\n\n"
    "Frase:"
)

user_question = st.text_input("Describe el incidente:")

if st.button("Reportar", use_container_width=True):
    prompt = persona + " " + user_question
    try:
        response = model.generate_content([prompt]).text  # ✅ corregido
        fila = [datetime.now().isoformat()] + response.split(",")
        ws.append_row(fila[:7])  # Fecha + 6 columnas
        st.success("Incidente registrado")
        st.write(fila)
    except Exception as e:
        st.error(f"Error al generar contenido: {e}")


