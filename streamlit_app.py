import streamlit as st
from datetime import datetime
import io
import json
import hashlib
import hmac
import base64
import secrets

import gspread

from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as OAuthCredentials
from google_auth_oauthlib.flow import Flow
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
# GOOGLE SHEETS - CUENTA DE SERVICIO
# ============================================================

scopes_sheets = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]


@st.cache_resource
def obtener_credenciales():

    info_claves = dict(
        st.secrets["gcp_service_account"]
    )

    info_claves["private_key"] = (
        info_claves["private_key"]
        .replace("\\n", "\n")
    )

    return Credentials.from_service_account_info(
        info_claves,
        scopes=scopes_sheets
    )


@st.cache_resource
def conectar_google():

    try:

        credenciales = obtener_credenciales()

        return gspread.authorize(
            credenciales
        )

    except Exception as e:

        st.error(
            f"Error crítico en la configuración "
            f"de la clave: {e}"
        )

        return None


cliente = conectar_google()


# ============================================================
# LOGIN DEL USUARIO
# ============================================================

if not st.user.is_logged_in:

    st.info(
        "🔐 Para utilizar el Panel de Contabilidad "
        "Láser necesitas iniciar sesión con Google."
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


# ============================================================
# CONFIGURACIÓN OAUTH DRIVE
# ============================================================

DRIVE_SCOPE = (
    "https://www.googleapis.com/auth/drive"
)


def crear_firma_estado(valor):

    secreto = st.secrets["auth"]["cookie_secret"]

    firma = hmac.new(
        secreto.encode("utf-8"),
        valor.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return firma


def crear_estado_oauth():

    datos = {
        "nonce": secrets.token_urlsafe(32)
    }

    contenido = base64.urlsafe_b64encode(
        json.dumps(datos).encode("utf-8")
    ).decode("utf-8")

    firma = crear_firma_estado(
        contenido
    )

    return f"{contenido}.{firma}"


def validar_estado_oauth(estado):

    try:

        contenido, firma = estado.split(".", 1)

        firma_correcta = crear_firma_estado(
            contenido
        )

        if not hmac.compare_digest(
            firma,
            firma_correcta
        ):
            return False

        return True

    except Exception:

        return False


def crear_flow():

    configuracion = {
        "web": {
            "client_id": st.secrets[
                "google_drive_oauth"
            ]["client_id"],

            "client_secret": st.secrets[
                "google_drive_oauth"
            ]["client_secret"],

            "auth_uri":
                "https://accounts.google.com/o/oauth2/auth",

            "token_uri":
                "https://oauth2.googleapis.com/token",

            "redirect_uris": [
                st.secrets[
                    "google_drive_oauth"
                ]["redirect_uri"]
            ]
        }
    }

    flow = Flow.from_client_config(
        configuracion,
        scopes=[DRIVE_SCOPE]
    )

    flow.redirect_uri = st.secrets[
        "google_drive_oauth"
    ]["redirect_uri"]

    return flow


# ============================================================
# PROCESAR CALLBACK DE GOOGLE DRIVE
# ============================================================

parametros = st.query_params

codigo_oauth = parametros.get(
    "code"
)

estado_oauth = parametros.get(
    "state"
)

error_oauth = parametros.get(
    "error"
)


if error_oauth:

    st.error(
        f"❌ Google no autorizó Drive: {error_oauth}"
    )

    st.query_params.clear()


elif codigo_oauth and estado_oauth:

    if not validar_estado_oauth(
        estado_oauth
    ):

        st.error(
            "❌ Error de seguridad al validar "
            "la autorización de Google Drive."
        )

        st.query_params.clear()

    else:

        try:

            flow = crear_flow()

            flow.fetch_token(
                code=codigo_oauth
            )

            credenciales_drive = (
                flow.credentials
            )

            st.session_state[
                "drive_credentials"
            ] = {
                "token":
                    credenciales_drive.token,

                "refresh_token":
                    credenciales_drive.refresh_token,

                "token_uri":
                    credenciales_drive.token_uri,

                "client_id":
                    credenciales_drive.client_id,

                "client_secret":
                    credenciales_drive.client_secret,

                "scopes":
                    list(
                        credenciales_drive.scopes
                        or [DRIVE_SCOPE]
                    )
            }

            st.success(
                "✅ Google Drive autorizado correctamente."
            )

            st.query_params.clear()

            st.rerun()

        except Exception as e:

            st.error(
                f"❌ Error completando la autorización "
                f"de Google Drive: {e}"
            )


# ============================================================
# OBTENER CREDENCIALES DRIVE
# ============================================================

def obtener_credenciales_drive():

    datos = st.session_state.get(
        "drive_credentials"
    )

    if not datos:

        return None

    return OAuthCredentials(
        token=datos.get("token"),
        refresh_token=datos.get(
            "refresh_token"
        ),
        token_uri=datos.get(
            "token_uri"
        ),
        client_id=datos.get(
            "client_id"
        ),
        client_secret=datos.get(
            "client_secret"
        ),
        scopes=datos.get(
            "scopes"
        )
    )


def conectar_drive_usuario():

    credenciales = (
        obtener_credenciales_drive()
    )

    if credenciales is None:

        return None

    try:

        drive_api = build(
            "drive",
            "v3",
            credentials=credenciales
        )

        return drive_api

    except Exception as e:

        st.error(
            f"Error al conectar con Google Drive: {e}"
        )

        return None


# ============================================================
# AUTORIZACIÓN DRIVE
# ============================================================

drive = conectar_drive_usuario()


if drive is None:

    st.warning(
        "📁 Google Drive necesita autorización "
        "para guardar los justificantes."
    )

    estado = crear_estado_oauth()

    flow_autorizacion = crear_flow()

    url_autorizacion, _ = (
        flow_autorizacion.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=estado
        )
    )

    st.link_button(
        "🔐 Autorizar Google Drive",
        url_autorizacion,
        type="primary"
    )


# ============================================================
# CONEXIÓN GOOGLE SHEETS
# ============================================================

if cliente:

    try:

        id_sheet = st.secrets[
            "google_sheets"
        ]["id_documento"]

        documento = cliente.open_by_key(
            id_sheet
        )

        hojas = documento.worksheets()

        hoja_ingresos = hojas[0]
        hoja_gastos = hojas[1]

        st.success(
            f"🟢 Conectado con éxito a: "
            f"{documento.title}"
        )

    except Exception as e:

        st.error(
            "🔴 Error al acceder a las "
            f"pestañas del documento: {e}"
        )

        hoja_ingresos = None
        hoja_gastos = None

else:

    st.error(
        "🔴 No se ha podido validar "
        "la cuenta de servicio de Google."
    )

    hoja_ingresos = None
    hoja_gastos = None


# ============================================================
# GOOGLE DRIVE
# ============================================================

id_carpeta_principal = st.secrets[
    "google_drive"
]["id_carpeta_principal"]


def buscar_carpeta(
    nombre,
    carpeta_padre
):

    if drive is None:

        raise Exception(
            "Google Drive no está autorizado."
        )

    consulta = (
        f"name = '{nombre}' "
        f"and '{carpeta_padre}' in parents "
        f"and mimeType = "
        f"'application/vnd.google-apps.folder' "
        f"and trashed = false"
    )

    resultado = drive.files().list(
        q=consulta,
        spaces="drive",
        fields="files(id, name)"
    ).execute()

    archivos = resultado.get(
        "files",
        []
    )

    if archivos:

        return archivos[0]["id"]

    return None


def obtener_carpeta_drive(
    nombre,
    carpeta_padre
):

    carpeta = buscar_carpeta(
        nombre,
        carpeta_padre
    )

    if carpeta:

        return carpeta

    resultado = drive.files().create(
        body={
            "name": nombre,
            "mimeType":
                "application/vnd.google-apps.folder",
            "parents": [
                carpeta_padre
            ]
        },
        fields="id"
    ).execute()

    return resultado["id"]


def obtener_ruta_contabilidad(tipo):

    ahora_local = datetime.now()

    anio = str(
        ahora_local.year
    )

    trimestre = (
        f"T{((ahora_local.month - 1) // 3) + 1}"
    )

    id_anio = obtener_carpeta_drive(
        anio,
        id_carpeta_principal
    )

    id_trimestre = obtener_carpeta_drive(
        trimestre,
        id_anio
    )

    id_tipo = obtener_carpeta_drive(
        tipo,
        id_trimestre
    )

    return id_tipo


def subir_archivo_drive(
    archivo,
    carpeta_id
):

    if drive is None:

        raise Exception(
            "Google Drive no está autorizado."
        )

    contenido = archivo.getvalue()

    media = MediaIoBaseUpload(
        io.BytesIO(contenido),
        mimetype=archivo.type,
        resumable=True
    )

    archivo_drive = drive.files().create(
        body={
            "name": archivo.name,
            "parents": [
                carpeta_id
            ]
        },
        media_body=media,
        fields="id, webViewLink"
    ).execute()

    return archivo_drive.get(
        "webViewLink",
        f"https://drive.google.com/file/d/"
        f"{archivo_drive['id']}/view"
    )


# ============================================================
# FECHA Y HORA
# ============================================================

ahora = datetime.now()

fecha_str = ahora.strftime(
    "%Y-%m-%d"
)

hora_str = ahora.strftime(
    "%H:%M:%S"
)


# ============================================================
# SELECCIÓN DE OPERACIÓN
# ============================================================

opcion = st.radio(
    "Operación:",
    [
        "🛒 REGISTRAR COMPRA (Gasto)",
        "💰 REGISTRAR VENTA (Ingreso)"
    ],
    horizontal=True
)


# ============================================================
# INGRESOS
# ============================================================

if "REGISTRAR VENTA" in opcion:

    st.markdown(
        "### 📈 Nuevo Ingreso (Venta)"
    )

    if hoja_ingresos is not None:

        try:

            filas_existentes = len(
                hoja_ingresos.get_all_values()
            )

            codigo_factura = (
                f"F-{ahora.strftime('%Y')}-"
                f"{filas_existentes:03d}"
            )

        except Exception:

            codigo_factura = "F-ERROR"

    else:

        codigo_factura = "F-ERROR"

    st.info(
        f"Número de Factura asignado: "
        f"**{codigo_factura}**"
    )

    concepto = st.text_input(
        "Concepto del pedido:"
    )

    total_cobrado = st.number_input(
        "Total cobrado con IVA (€):",
        min_value=0.0,
        step=1.0
    )

    st.markdown(
        "#### 📎 Justificante"
    )

    foto_ingreso = st.camera_input(
        "📷 Hacer foto del justificante"
    )

    archivo_ingreso = st.file_uploader(
        "📎 Adjuntar justificante "
        "(PDF, foto, ticket o factura)",
        type=[
            "pdf",
            "jpg",
            "jpeg",
            "png"
        ],
        accept_multiple_files=False,
        key="archivo_ingreso"
    )

    archivo_final = (
        foto_ingreso
        if foto_ingreso is not None
        else archivo_ingreso
    )

    if st.button(
        "💾 Guardar ingreso",
        type="primary"
    ):

        if hoja_ingresos is None:

            st.error(
                "No hay conexión "
                "con la hoja de ingresos."
            )

        elif not concepto.strip():

            st.warning(
                "Introduce el concepto "
                "del pedido."
            )

        elif total_cobrado <= 0:

            st.warning(
                "Introduce un importe "
                "mayor que 0 €."
            )

        else:

            base = (
                total_cobrado / 1.21
            )

            iva = (
                total_cobrado - base
            )

            link_drive = ""

            error_drive = None

            if archivo_final is not None:

                try:

                    carpeta_ingresos = (
                        obtener_ruta_contabilidad(
                            "INGRESOS"
                        )
                    )

                    link_drive = (
                        subir_archivo_drive(
                            archivo_final,
                            carpeta_ingresos
                        )
                    )

                except Exception as e:

                    error_drive = str(e)

            try:

                hoja_ingresos.append_row(
                    [
                        fecha_str,
                        hora_str,
                        codigo_factura,
                        concepto,
                        round(base, 2),
                        round(iva, 2),
                        round(
                            total_cobrado,
                            2
                        ),
                        link_drive
                    ],
                    value_input_option="USER_ENTERED"
                )

                if error_drive:

                    st.warning(
                        "⚠️ Ingreso guardado en Sheets, "
                        "pero no se pudo subir "
                        "el justificante a Drive."
                    )

                    st.error(
                        "Detalle del error de Drive: "
                        f"{error_drive}"
                    )

                else:

                    st.success(
                        "✅ Ingreso registrado "
                        "correctamente."
                    )

                if link_drive:

                    st.markdown(
                        "📎 [Abrir justificante "
                        f"en Google Drive]({link_drive})"
                    )

            except Exception as e:

                st.error(
                    "❌ Error al guardar "
                    f"el ingreso: {e}"
                )


# ============================================================
# GASTOS
# ============================================================

else:

    st.markdown(
        "### 📉 Nuevo Gasto (Compra / Inversión)"
    )

    proveedor = st.text_input(
        "Proveedor (ej: xTool, Gestor):"
    )

    concepto_gasto = st.text_input(
        "Concepto del gasto:"
    )

    total_pagado = st.number_input(
        "Total pagado (€):",
        min_value=0.0,
        step=1.0
    )

    st.markdown(
        "#### 📎 Justificante"
    )

    foto_gasto = st.camera_input(
        "📷 Hacer foto del justificante"
    )

    archivo_gasto = st.file_uploader(
        "📎 Adjuntar justificante "
        "(PDF, foto, ticket o factura)",
        type=[
            "pdf",
            "jpg",
            "jpeg",
            "png"
        ],
        accept_multiple_files=False,
        key="archivo_gasto"
    )

    archivo_final = (
        foto_gasto
        if foto_gasto is not None
        else archivo_gasto
    )

    if st.button(
        "💾 Guardar gasto",
        type="primary"
    ):

        if hoja_gastos is None:

            st.error(
                "No hay conexión "
                "con la hoja de gastos."
            )

        elif not proveedor.strip():

            st.warning(
                "Introduce el proveedor."
            )

        elif not concepto_gasto.strip():

            st.warning(
                "Introduce el concepto "
                "del gasto."
            )

        elif total_pagado <= 0:

            st.warning(
                "Introduce un importe "
                "mayor que 0 €."
            )

        else:

            base = (
                total_pagado / 1.21
            )

            iva = (
                total_pagado - base
            )

            link_drive = ""

            error_drive = None

            if archivo_final is not None:

                try:

                    carpeta_gastos = (
                        obtener_ruta_contabilidad(
                            "GASTOS"
                        )
                    )

                    link_drive = (
                        subir_archivo_drive(
                            archivo_final,
                            carpeta_gastos
                        )
                    )

                except Exception as e:

                    error_drive = str(e)

            try:

                hoja_gastos.append_row(
                    [
                        fecha_str,
                        hora_str,
                        proveedor,
                        concepto_gasto,
                        round(base, 2),
                        round(iva, 2),
                        round(
                            total_pagado,
                            2
                        ),
                        link_drive
                    ],
                    value_input_option="USER_ENTERED"
                )

                if error_drive:

                    st.warning(
                        "⚠️ Gasto guardado en Sheets, "
                        "pero no se pudo subir "
                        "el justificante a Drive."
                    )

                    st.error(
                        "Detalle del error de Drive: "
                        f"{error_drive}"
                    )

                else:

                    st.success(
                        "✅ Gasto registrado "
                        "correctamente."
                    )

                if link_drive:

                    st.markdown(
                        "📎 [Abrir justificante "
                        f"en Google Drive]({link_drive})"
                    )

            except Exception as e:

                st.error(
                    "❌ Error al guardar "
                    f"el gasto: {e}"
                )
