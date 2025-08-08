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


# Prompt más compacto y robusto
persona = f"""
Eres un asistente experto en seguridad informática. Tu tarea es transformar un reporte de incidente en lenguaje natural en una fila estructurada para una hoja de cálculo. Cada campo debe llenarse según las siguientes instrucciones. Si no se puede deducir la información, deja el campo vacío. Usa tu criterio profesional.

COLUMNAS A LLENAR (en orden):

1. CODIGO:
   - Escribe "INC" seguido de la hora mencionada en el reporte en formato HHMM (ej: INC0830).
   - Si no se menciona hora, usa la hora actual en formato HHMM.

2. Fecha y Hora de Apertura:
   - Solo si se menciona explícitamente una hora de apertura en el reporte (ej: “a las 8am”).
   - Usa el formato "YYYY-MM-DD HH:MM".
   - Si no se menciona, deja vacío.

3. Modo Reporte:
   - Identifica cómo se reportó: puede ser "Jira", "Correo", "Teléfono", "Monitoreo", etc.

4. Evento/Incidente:
   - Escribe "Evento" si es una alerta puntual o "Incidente" si es una afectación mayor.

5. Descripción Evento/Incidente:
   - Redacta de forma clara y profesional lo ocurrido (ej. "Falla de acceso a WhatsApp por bloqueo en firewall").

6. Sistema:
   - Indica qué sistema fue afectado (ej. VPN, Correo, Active Directory, WhatsApp, etc.).

7. Área:
   - Indica el área institucional afectada o que reportó el incidente (ej. Contabilidad, Talento Humano).

8. Ubicación:
   - Si se menciona una sede o ubicación geográfica o interna, indícala. Si no, deja vacío.

9. Prioridad:
   - Interpreta si el incidente es de prioridad Alta, Media o Baja.
   - Esta clasificación está descrita en la hoja "Definiciones".

10. Clasificación:
   - Interpreta el tipo de clasificación del incidente según los términos establecidos (ej. "Acceso no autorizado", "Interrupción de servicio").
   - Usa únicamente clasificaciones válidas definidas en la hoja "Definiciones".

11. Acción Inmediata:
   - Si se menciona algo que el usuario hizo antes de reportar (ej. reinició el equipo, cambió contraseña), escríbelo.
   - Si no se menciona, deja vacío.

12. Solución:
   - Explica brevemente cómo se resolvió el incidente (ej. "Se reinició el servicio").

13. Área GTIC - Coordinando:
   - Indica qué área lideró la solución (Redes, Seguridad Informática, Soporte Técnico, etc.).

14. Encargado SI:
   - Si se menciona a una persona del equipo de seguridad informática, escríbela.
   - Usa los nombres disponibles en la hoja "Definiciones".
   - Si no se menciona, deja vacío.

15. Fecha y Hora de Cierre:
   - Solo si el reporte menciona una hora de resolución (ej: “a las 11am se resolvió”).
   - Usa formato "YYYY-MM-DD HH:MM". Si no se menciona, deja vacío.

16. Tiempo de Solución:
   - Calcula el tiempo entre apertura y cierre como "X horas Y minutos".
   - Si no hay hora de cierre, deja vacío.

17. Estado:
   - Escribe "Cerrado" si el incidente fue resuelto o "En investigación" si sigue activo.

18. Vulnerabilidad:
   - Usa solo el **ID numérico** de la vulnerabilidad según la guía de abajo (ej: "1.3").
   - No escribas texto descriptivo como "Denegación de servicio".

19. Causa:
   - Déjalo vacío. Se autocompletará en Excel.

20. ID Amenaza:
   - Usa solo el **ID numérico** de la amenaza (ej: "2.1"), **sin el texto**.
   - La descripción se completará automáticamente.

21. Amenaza:
   - Déjalo vacío. Se autocompletará en Excel.

---

INSTRUCCIONES:
- Entrega la fila como una **lista separada por comas**, sin explicaciones ni comillas.
- Si algún dato no puede ser deducido del reporte, deja ese campo vacío.
- Usa tu criterio profesional para interpretar los campos según el contexto del incidente.

ENTREGA:
Devuelve una sola línea de texto, sin comillas, sin saltos de línea, con exactamente 21 campos separados por "|".

GUIA DE VULNERABILIDADES:
{guia_vuln}

GUIA DE AMENAZAS:
{guia_amenazas}

[REPORTE DE ENTRADA]
"""

user_question = st.text_input("Describe el incidente:")

if st.button("Reportar", use_container_width=True):
    prompt = persona + "\n\n[REPORTE DE ENTRADA]\n" + user_question
    try:
        response = model.generate_content([prompt]).text.strip()

        # Limpieza y separación por tubería (|) — mejor que usar coma
        clean_response = response.replace('"', '').replace("\n", "").strip()
        fila = clean_response.split("|")  # Usa | como separador confiable

        if len(fila) == 21:
            ws.append_row(fila)
            st.success("Incidente registrado")
            st.write(fila)
        else:
            st.error(f"La salida tiene {len(fila)} columnas en lugar de 21. Revisa el prompt o la entrada.")
            st.code(clean_response, language="text")

    except Exception as e:
        st.error(f"Error al generar contenido: {e}")












