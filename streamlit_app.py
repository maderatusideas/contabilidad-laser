import streamlit as st
from datetime import datetime
import io
import gspread
import threading
from decimal import Decimal, InvalidOperation

from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as OAuthCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload


# ============================================================
# CONFIGURACIÓN
# ============================================================

st.set_page_config(
    page_title="Control Láser NT",
    page_icon="⚡",
    layout="centered"
)

st.title("⚡ Panel de Contabilidad Láser")


# ============================================================
# CONEXIÓN GOOGLE SHEETS - CUENTA DE SERVICIO
# ============================================================

scopes_sheets = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

scopes_drive = [
    "https://www.googleapis.com/auth/drive"
]


@st.cache_resource
def obtener_credenciales():
    info_claves = dict(st.secrets["gcp_service_account"])

    info_claves["private_key"] = info_claves["private_key"].replace(
        "\\n",
        "\n"
    )

    return Credentials.from_service_account_info(
        info_claves,
        scopes=scopes_sheets
    )


@st.cache_resource
def conectar_google():
    try:
        credenciales = obtener_credenciales()
        return gspread.authorize(credenciales)

    except Exception as e:
        st.error(
            f"Error crítico en la configuración de la clave: {e}"
        )
        return None


cliente = conectar_google()


# ============================================================
# INICIO DE SESIÓN DEL USUARIO
# ============================================================

if not st.user.is_logged_in:

    st.info(
        "🔐 Para utilizar Google Drive necesitas iniciar sesión "
        "con tu cuenta de Google."
    )

    if st.button(
        "🔑 Iniciar sesión con Google",
        type="primary"
    ):
        st.login("google")

    st.stop()


st.success(
    f"👤 Google conectado: {st.user.email}"
)

