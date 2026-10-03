import streamlit as st
from datetime import datetime
import io
import gspread

from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as OAuthCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from streamlit_oauth import OAuth2Component


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
            "Error crítico en la configuración "
            f"de la cuenta de servicio: {e}"
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

st.write("LOGIN OK")


# ============================================================
# GOOGLE SHEETS
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
# CONFIGURACIÓN OAUTH DE GOOGLE DRIVE
# ============================================================

DRIVE_SCOPE = (
    "https://www.googleapis.com/auth/drive"
)

DRIVE_AUTHORIZE_URL = (
    "https://accounts.google.com/o/oauth2/v2/auth"
)

DRIVE_TOKEN_URL = (
    "https://oauth2.googleapis.com/token"
)

DRIVE_REVOKE_URL = (
    "https://oauth2.googleapis.com/revoke"
)

DRIVE_REDIRECT_URI = (
    "https://maderatusideas-contabilidad-laser-"
    "streamlit-app-hikvam.streamlit.app/"
    "component/streamlit_oauth.authorize_button"
)


# ============================================================
# OAUTH COMPONENT
# ============================================================

try:

    drive_client_id = st.secrets[
        "google_drive_oauth"
    ]["client_id"]

    drive_client_secret = st.secrets[
        "google_drive_oauth"
    ]["client_secret"]

except Exception as e:

    st.error(
        "🔴 Falta la configuración "
        f"google_drive_oauth en Secrets: {e}"
    )

    st.stop()


oauth2 = OAuth2Component(

    client_id=drive_client_id,

    client_secret=drive_client_secret,

    authorize_endpoint=DRIVE_AUTHORIZE_URL,

    token_endpoint=DRIVE_TOKEN_URL,

    refresh_token_endpoint=DRIVE_TOKEN_URL,

    revoke_token_endpoint=DRIVE_REVOKE_URL
)


# ============================================================
# AUTORIZACIÓN DRIVE
# ============================================================

if "drive_token" not in st.session_state:

    st.info(
        "📁 Google Drive necesita autorización "
        "para guardar los justificantes."
    )

    resultado_oauth = oauth2.authorize_button(

        "🔐 Autorizar Google Drive",

        DRIVE_REDIRECT_URI,

        DRIVE_SCOPE,

        key="autorizar_drive",

        extras_params={

            "access_type": "offline",

            "prompt": "consent",

            "include_granted_scopes": "true",

            "login_hint": st.user.email
        }
    )

    if (
        resultado_oauth
        and "token" in resultado_oauth
    ):

        st.session_state.drive_token = (
            resultado_oauth["token"]
        )

        st.rerun()

    drive = None

else:

    # --------------------------------------------------------
    # TOKEN YA DISPONIBLE
    # --------------------------------------------------------

    try:

        token_drive = (
            st.session_state["drive_token"]
        )

        # Intentamos renovar automáticamente
        # si el access token ha caducado.

        token_drive = oauth2.refresh_token(
            token_drive
        )

        st.session_state["drive_token"] = (
            token_drive
        )

        access_token = token_drive.get(
            "access_token"
        )

        refresh_token = token_drive.get(
            "refresh_token"
        )

        if not access_token:

            raise Exception(
                "No se recibió un access token "
                "válido de Google Drive."
            )

        if not refresh_token:

            # Puede ocurrir si Google no devuelve
            # refresh token en una autorización
            # posterior. El primer consentimiento
            # debería proporcionarlo.

            raise Exception(
                "Google no ha proporcionado "
                "refresh_token. "
                "Será necesario volver a autorizar Drive."
            )

        credenciales_drive = OAuthCredentials(

            token=access_token,

            refresh_token=refresh_token,

            token_uri=DRIVE_TOKEN_URL,

            client_id=drive_client_id,

            client_secret=drive_client_secret,

            scopes=[DRIVE_SCOPE]
        )

        drive = build(
            "drive",
            "v3",
            credentials=credenciales_drive
        )

        st.success(
            "🟢 Google Drive autorizado"
        )

    except Exception as e:

        st.session_state.pop(
            "drive_token",
            None
        )

        drive = None

        st.warning(
            "⚠️ La autorización de Google Drive "
            "debe realizarse de nuevo."
        )

        st.error(
            f"Detalle de autorización Drive: {e}"
        )


# ============================================================
# CARPETA PRINCIPAL DE DRIVE
# ============================================================

try:

    id_carpeta_principal = st.secrets[
        "google_drive"
    ]["id_carpeta_principal"]

except Exception as e:

    st.error(
        "🔴 No se ha podido obtener la "
        f"carpeta principal de Drive: {e}"
    )

    id_carpeta_principal = None


# ============================================================
# BUSCAR CARPETA
# ============================================================

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


# ============================================================
# OBTENER / CREAR CARPETA
# ============================================================

def obtener_carpeta_drive(
    nombre,
    carpeta_padre
):

    if drive is None:

        raise Exception(
            "Google Drive no está autorizado."
        )

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


# ============================================================
# RUTA DE CONTABILIDAD
# ============================================================

def obtener_ruta_contabilidad(
    tipo
):

    if drive is None:

        raise Exception(
            "Google Drive no está autorizado."
        )

    if not id_carpeta_principal:

        raise Exception(
            "No existe una carpeta principal "
            "de Google Drive."
        )

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


# ============================================================
# SUBIR ARCHIVO
# ============================================================

def subir_archivo_drive(
    archivo,
    carpeta_id
):

    if drive is None:

        raise Exception(
            "Google Drive no está autorizado."
        )

    contenido = archivo.getvalue()

    mimetype = (
        getattr(
            archivo,
            "type",
            None
        )
        or "application/octet-stream"
    )

    nombre_archivo = (
        getattr(
            archivo,
            "name",
            None
        )
        or "justificante"
    )

    media = MediaIoBaseUpload(

        io.BytesIO(contenido),

        mimetype=mimetype,

        resumable=True
    )

    archivo_drive = drive.files().create(

        body={

            "name": nombre_archivo,

            "parents": [
                carpeta_id
            ]
        },

        media_body=media,

        fields="id, webViewLink"

    ).execute()

    enlace = archivo_drive.get(
        "webViewLink"
    )

    if enlace:

        return enlace

    return (
        "https://drive.google.com/file/d/"
        + archivo_drive["id"]
        + "/view"
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
# OPERACIÓN
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
                "No hay conexión con "
                "la hoja de ingresos."
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

        elif drive is None:

            st.error(
                "🔐 Primero debes autorizar "
                "Google Drive."
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

                    value_input_option=
                        "USER_ENTERED"
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
                        "en Google Drive]"
                        f"({link_drive})"
                    )

            except Exception as e:

                st.error(
                    f"❌ Error al guardar "
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
                "No hay conexión con "
                "la hoja de gastos."
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

        elif drive is None:

            st.error(
                "🔐 Primero debes autorizar "
                "Google Drive."
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

                    value_input_option=
                        "USER_ENTERED"
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
                        "en Google Drive]"
                        f"({link_drive})"
                    )

            except Exception as e:

                st.error(
                    f"❌ Error al guardar "
                    f"el gasto: {e}"
                )
