import streamlit as st
import requests
import time
import uuid
import re  # <-- NEW: para validar correo

st.set_page_config(page_title="Acompañamiento para el docente", page_icon="💬")
st.title("Acompañamiento para el docente")

# ---------- Constantes de estado ----------
EMAIL_KEY = "user_email"
SESSION_KEY = "session_id"
MSGS_KEY = "messages"
HISTORY_URL = "http://demo-acompanamiento.southcentralus.azurecontainer.io/history"

# ---------- Helpers ----------
def is_valid_email(email: str) -> bool:
    # Validación sencilla (ajusta si necesitas reglas más estrictas)
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", str(email).strip()))

def typewriter_effect(text, speed=0.01):
    placeholder = st.empty()
    displayed_text = ""
    for char in text:
        displayed_text += char
        placeholder.markdown(displayed_text)
        time.sleep(speed)
    return displayed_text

# ---------- Inicialización de estado ----------
if SESSION_KEY not in st.session_state:
    st.session_state[SESSION_KEY] = str(uuid.uuid4())

if MSGS_KEY not in st.session_state:
    st.session_state[MSGS_KEY] = []

if EMAIL_KEY not in st.session_state:
    st.session_state[EMAIL_KEY] = None

# ---------- Gate de correo ----------
if not st.session_state[EMAIL_KEY]:
    st.info("Antes de chatear, por favor ingresa tu correo 👇")

    with st.form("email_gate", clear_on_submit=False):
        email = st.text_input("Correo electrónico", placeholder="tucorreo@ejemplo.com")
        submitted = st.form_submit_button("Continuar")
        if submitted:
            if not is_valid_email(email):
                st.error("Por favor ingresa un correo válido.")
            else:
                st.session_state[EMAIL_KEY] = email.strip()

                # Intentar obtener el historial de los últimos mensajes para este correo
                try:
                    with st.spinner("Cargando historial..."):
                        resp = requests.post(
                            HISTORY_URL,
                            json={"email": st.session_state[EMAIL_KEY]},
                            timeout=30,
                        )
                    if resp.status_code == 200:
                        # La API retorna la estructura:
                        # { "email": ..., "limit": 20, "history": [ {"sent_by": "user"|"bot", "message": "...", "created_at": "..."}, ... ] }
                        payload = resp.json()
                        msgs_raw = None
                        if isinstance(payload, dict):
                            msgs_raw = payload.get("history") or payload.get("messages")
                        elif isinstance(payload, list):
                            msgs_raw = payload

                        if isinstance(msgs_raw, list):
                            # Tomar solo los últimos 20 mensajes
                            msgs_slice = msgs_raw[-20:]
                            # Mapear a formato {role, content}
                            role_map = {"user": "user", "bot": "assistant", "assistant": "assistant", "system": "assistant"}
                            valid_msgs = []
                            for item in msgs_slice:
                                if not isinstance(item, dict):
                                    continue
                                # Soportar dos posibles formas: sent_by/message o role/content
                                if "role" in item and "content" in item:
                                    role = str(item.get("role"))
                                    content = item.get("content")
                                else:
                                    sent_by = str(item.get("sent_by", "")).lower()
                                    role = role_map.get(sent_by, "assistant")
                                    content = item.get("message")

                                if content and isinstance(content, str):
                                    valid_msgs.append({"role": role, "content": content})

                            st.session_state[MSGS_KEY] = valid_msgs
                            st.info(f"Se cargaron {len(valid_msgs)} mensajes de historial.")
                        else:
                            st.session_state[MSGS_KEY] = []
                            st.info("No se encontró historial para este correo.")
                    else:
                        st.session_state[MSGS_KEY] = []
                        st.warning(f"No se pudo cargar el historial (HTTP {resp.status_code}).")
                except Exception as e:
                    st.session_state[MSGS_KEY] = []
                    st.warning(f"Error al cargar historial: {e}")

                st.success("¡Listo! Ya puedes chatear.")

    st.stop()  # <-- IMPORTANTE: evita renderizar el resto hasta que haya correo

# ---------- Barra superior con correo y acción para cambiarlo ----------
left, right = st.columns([1, 0.25])
with left:
    st.caption(f"Usuario: **{st.session_state[EMAIL_KEY]}**")
with right:
    if st.button("Cambiar correo", use_container_width=True):
        st.session_state[EMAIL_KEY] = None
        st.rerun()

# ---------- Mostrar historial de la conversación ----------
for message in st.session_state[MSGS_KEY]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ---------- Entrada del usuario (habilitada porque ya hay correo) ----------
if prompt := st.chat_input("Escribe tu pregunta:"):
    # Agregar la pregunta del usuario al historial
    st.session_state[MSGS_KEY].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Enviar la pregunta + session_id + email a la API de FastAPI
    with st.spinner("El agente está pensando..."):
        try:
            response = requests.post(
                "http://demo-acompanamiento.southcentralus.azurecontainer.io/bot",
                json={
                    "message": prompt,
                    "email": st.session_state[EMAIL_KEY],
                    "is_test": False # Marca como prueba para no guardar en base de datos
                },
                timeout=60,
            )

            if response.status_code == 200:
                # Ajusta la clave si tu API responde distinto
                agent_response = response.json().get("message", "Sin respuesta")
            else:
                agent_response = f"Error al conectar con el agente (HTTP {response.status_code})."
        except Exception as e:
            agent_response = f"Error: {str(e)}"

    # Mostrar la respuesta del agente con efecto typewriter
    st.session_state[MSGS_KEY].append({"role": "assistant", "content": agent_response})
    with st.chat_message("assistant"):
        typewriter_effect(agent_response)
