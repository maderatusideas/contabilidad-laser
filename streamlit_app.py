import streamlit as st
from datetime import datetime
import io
import gspread

from google.oauth2.service_account import Credentials
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
# CREDENCIALES DE LA CUENTA DE SERVICIO
# ============================================================

scopes_google = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]


@st.cache_resource
def obtener_credenciales():
    info_claves = dict(st.secrets["gcp_service_account"])

    # Streamlit Secrets puede guardar los saltos de línea
    # de la clave privada como \n
    info_claves["private_key"] = info_claves["private_key"].replace(
        "\\n",
        "\n"
    )

    return Credentials.from_service_account_info(
        info_claves,
        scopes=scopes_google
    )


# ============================================================
# GOOGLE SHEETS
# ============================================================

@st.cache_resource
def conectar_google():
    try:
        credenciales = obtener_credenciales()
        return gspread.authorize(credenciales)

    except Exception as e:
        st.error(
            f"Error crítico en la configuración de la cuenta de servicio: {e}"
        )
        return None


cliente = conectar_google()


# ============================================================
# LOGIN DEL USUARIO
# ============================================================

if not st.user.is_logged_in:

    st.info(
        "🔐 Para utilizar el Panel de Contabilidad Láser "
        "necesitas iniciar sesión con tu cuenta de Google."
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
# GOOGLE DRIVE
#
# IMPORTANTE:
# Drive NO utiliza el token de st.login().
# Utiliza la misma cuenta de servicio que Sheets.
# ============================================================

@st.cache_resource
def conectar_drive():
    try:
        credenciales = obtener_credenciales()

        return build(
            "drive",
            "v3",
            credentials=credenciales
        )

    except Exception as e:
        st.error(
            f"Error al conectar con Google Drive: {e}"
        )
        return None


drive = conectar_drive()


# ============================================================
# GOOGLE SHEETS - ABRIR DOCUMENTO
# ============================================================

if cliente:

    try:

        id_sheet = st.secrets["google_sheets"]["id_documento"]

        documento = cliente.open_by_key(id_sheet)

        hojas = documento.worksheets()

        hoja_ingresos = hojas[0]
        hoja_gastos = hojas[1]

        st.success(
            f"🟢 Conectado con éxito a: {documento.title}"
        )

    except Exception as e:

        st.error(
            f"🔴 Error al acceder a las pestañas del documento: {e}"
        )

        hoja_ingresos = None
        hoja_gastos = None

else:

    st.error(
        "🔴 No se ha podido validar la cuenta de servicio de Google."
    )

    hoja_ingresos = None
    hoja_gastos = None


# ============================================================
# CARPETA PRINCIPAL DE GOOGLE DRIVE
# ============================================================

try:

    id_carpeta_principal = st.secrets[
        "google_drive"
    ]["id_carpeta_principal"]

except Exception as e:

    st.error(
        f"🔴 No se ha podido obtener la carpeta principal de Drive: {e}"
    )

    id_carpeta_principal = None


# ============================================================
# BUSCAR CARPETA EN DRIVE
# ============================================================

def buscar_carpeta(nombre, carpeta_padre):

    if drive is None:
        raise Exception(
            "La conexión con Google Drive no está disponible."
        )

    if not carpeta_padre:
        raise Exception(
            "No se ha definido la carpeta principal de Google Drive."
        )

    consulta = (
        f"name = '{nombre}' "
        f"and '{carpeta_padre}' in parents "
        f"and mimeType = 'application/vnd.google-apps.folder' "
        f"and trashed = false"
    )

    resultado = drive.files().list(
        q=consulta,
        spaces="drive",
        fields="files(id, name)"
    ).execute()

    archivos = resultado.get("files", [])

    if archivos:
        return archivos[0]["id"]

    return None


# ============================================================
# OBTENER O CREAR CARPETA
# ============================================================

def obtener_carpeta_drive(nombre, carpeta_padre):

    if drive is None:
        raise Exception(
            "La conexión con Google Drive no está disponible."
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
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [carpeta_padre]
        },

        fields="id"

    ).execute()

    return resultado["id"]


# ============================================================
# CREAR RUTA:
#
# CARPETA PRINCIPAL
#       └── 2026
#             └── T4
#                   ├── GASTOS
#                   └── INGRESOS
# ============================================================

def obtener_ruta_contabilidad(tipo):

    if drive is None:
        raise Exception(
            "Google Drive no está conectado."
        )

    if not id_carpeta_principal:
        raise Exception(
            "No existe una carpeta principal de Google Drive."
        )

    ahora_local = datetime.now()

    anio = str(ahora_local.year)

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
# SUBIR ARCHIVO A GOOGLE DRIVE
# ============================================================

def subir_archivo_drive(archivo, carpeta_id):

    if drive is None:
        raise Exception(
            "Google Drive no está conectado."
        )

    contenido = archivo.getvalue()

    mimetype = getattr(
        archivo,
        "type",
        None
    ) or "application/octet-stream"

    nombre_archivo = getattr(
        archivo,
        "name",
        None
    ) or "justificante"

    media = MediaIoBaseUpload(
        io.BytesIO(contenido),
        mimetype=mimetype,
        resumable=True
    )

    archivo_drive = drive.files().create(

        body={
            "name": nombre_archivo,
            "parents": [carpeta_id]
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
# SELECTOR PRINCIPAL
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

    # --------------------------------------------------------
    # NÚMERO DE FACTURA
    # --------------------------------------------------------

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
        f"Número de Factura asignado: **{codigo_factura}**"
    )


    # --------------------------------------------------------
    # DATOS
    # --------------------------------------------------------

    concepto = st.text_input(
        "Concepto del pedido:"
    )

    total_cobrado = st.number_input(

        "Total cobrado con IVA (€):",

        min_value=0.0,

        step=1.0
    )


    # --------------------------------------------------------
    # JUSTIFICANTE
    # --------------------------------------------------------

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


    # Si existe foto, se utiliza la foto.
    # Si no, se utiliza el archivo seleccionado.

    archivo_final = (
        foto_ingreso
        if foto_ingreso is not None
        else archivo_ingreso
    )


    # --------------------------------------------------------
    # GUARDAR INGRESO
    # --------------------------------------------------------

    if st.button(
        "💾 Guardar ingreso",
        type="primary"
    ):

        if hoja_ingresos is None:

            st.error(
                "No hay conexión con la hoja de ingresos."
            )

        elif not concepto.strip():

            st.warning(
                "Introduce el concepto del pedido."
            )

        elif total_cobrado <= 0:

            st.warning(
                "Introduce un importe mayor que 0 €."
            )

        else:

            # -----------------------------------------------
            # CALCULAR IVA
            # -----------------------------------------------

            base = total_cobrado / 1.21

            iva = total_cobrado - base


            link_drive = ""

            error_drive = None


            # -----------------------------------------------
            # SUBIR JUSTIFICANTE
            # -----------------------------------------------

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


            # -----------------------------------------------
            # GUARDAR EN SHEETS
            # -----------------------------------------------

            try:

                hoja_ingresos.append_row(

                    [

                        fecha_str,

                        hora_str,

                        codigo_factura,

                        concepto,

                        round(base, 2),

                        round(iva, 2),

                        round(total_cobrado, 2),

                        link_drive
                    ],

                    value_input_option="USER_ENTERED"
                )


                # -------------------------------------------
                # MENSAJE FINAL
                # -------------------------------------------

                if error_drive:

                    st.warning(
                        "⚠️ Ingreso guardado en Sheets, "
                        "pero no se pudo subir el justificante a Drive."
                    )

                    st.error(
                        f"Detalle del error de Drive: "
                        f"{error_drive}"
                    )

                else:

                    st.success(
                        "✅ Ingreso registrado correctamente."
                    )


                if link_drive:

                    st.markdown(
                        f"📎 [Abrir justificante en Google Drive]"
                        f"({link_drive})"
                    )


            except Exception as e:

                st.error(
                    f"❌ Error al guardar el ingreso: {e}"
                )


# ============================================================
# GASTOS
# ============================================================

else:

    st.markdown(
        "### 📉 Nuevo Gasto (Compra / Inversión)"
    )


    # --------------------------------------------------------
    # DATOS DEL GASTO
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # JUSTIFICANTE
    # --------------------------------------------------------

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


    # Foto de cámara tiene prioridad
    # sobre archivo subido.

    archivo_final = (
        foto_gasto
        if foto_gasto is not None
        else archivo_gasto
    )


    # --------------------------------------------------------
    # GUARDAR GASTO
    # --------------------------------------------------------

    if st.button(
        "💾 Guardar gasto",
        type="primary"
    ):

        if hoja_gastos is None:

            st.error(
                "No hay conexión con la hoja de gastos."
            )

        elif not proveedor.strip():

            st.warning(
                "Introduce el proveedor."
            )

        elif not concepto_gasto.strip():

            st.warning(
                "Introduce el concepto del gasto."
            )

        elif total_pagado <= 0:

            st.warning(
                "Introduce un importe mayor que 0 €."
            )

        else:

            # -----------------------------------------------
            # CALCULAR IVA
            # -----------------------------------------------

            base = total_pagado / 1.21

            iva = total_pagado - base


            link_drive = ""

            error_drive = None


            # -----------------------------------------------
            # SUBIR JUSTIFICANTE
            # -----------------------------------------------

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


            # -----------------------------------------------
            # GUARDAR EN SHEETS
            # -----------------------------------------------

            try:

                hoja_gastos.append_row(

                    [

                        fecha_str,

                        hora_str,

                        proveedor,

                        concepto_gasto,

                        round(base, 2),

                        round(iva, 2),

                        round(total_pagado, 2),

                        link_drive
                    ],

                    value_input_option="USER_ENTERED"
                )


                # -------------------------------------------
                # MENSAJE FINAL
                # -------------------------------------------

                if error_drive:

                    st.warning(
                        "⚠️ Gasto guardado en Sheets, "
                        "pero no se pudo subir el justificante a Drive."
                    )

                    st.error(
                        f"Detalle del error de Drive: "
                        f"{error_drive}"
                    )

                else:

                    st.success(
                        "✅ Gasto registrado correctamente."
                    )


                if link_drive:

                    st.markdown(
                        f"📎 [Abrir justificante en Google Drive]"
                        f"({link_drive})"
                    )


            except Exception as e:

                st.error(
                    f"❌ Error al guardar el gasto: {e}"
                )
