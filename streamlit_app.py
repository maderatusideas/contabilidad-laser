import streamlit as st
from datetime import datetime
import io
import gspread
import json
import base64
import httpx
from datetime import date

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


# ============================================================
# CONEXIÓN GOOGLE DRIVE - OAUTH CON RENOVACIÓN AUTOMÁTICA
# ============================================================

def conectar_drive_usuario():

    try:
        configuracion_oauth = dict(st.secrets["google_drive_oauth"])

        credenciales_oauth = OAuthCredentials(
            token=None,
            refresh_token=configuracion_oauth["refresh_token"],
            token_uri=configuracion_oauth.get(
                "token_uri",
                "https://oauth2.googleapis.com/token"
            ),
            client_id=configuracion_oauth["client_id"],
            client_secret=configuracion_oauth["client_secret"],
            scopes=scopes_drive
        )

        return build(
            "drive",
            "v3",
            credentials=credenciales_oauth,
            cache_discovery=False
        )

    except KeyError:
        st.error(
            "Falta configurar google_drive_oauth en los secretos "
            "de Streamlit. Drive necesita un refresh_token de OAuth."
        )
        return None

    except Exception:

        st.error(
            "No se pudo preparar la conexión con Google Drive. "
            "Revisa la configuración OAuth de Drive en los secretos "
            "de Streamlit."
        )

        return None


drive = conectar_drive_usuario()


# ============================================================
# CONEXIÓN CON GOOGLE SHEETS
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
# GOOGLE DRIVE
# ============================================================

id_carpeta_principal = st.secrets["google_drive"][
    "id_carpeta_principal"
]


def buscar_carpeta(nombre, carpeta_padre):

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


def obtener_carpeta_drive(nombre, carpeta_padre):

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


def obtener_ruta_contabilidad(tipo, fecha_factura):

    # El año y el trimestre salen de la FECHA DE LA FACTURA,
    # no del día en que se sube (importante para el IVA).
    anio = str(fecha_factura.year)

    trimestre = (
        f"T{((fecha_factura.month - 1) // 3) + 1}"
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


def subir_archivo_drive(archivo, carpeta_id):

    contenido = archivo.getvalue()

    media = MediaIoBaseUpload(
        io.BytesIO(contenido),
        mimetype=archivo.type,
        resumable=True
    )

    archivo_drive = drive.files().create(
        body={
            "name": archivo.name,
            "parents": [carpeta_id]
        },
        media_body=media,
        fields="id, webViewLink"
    ).execute()

    return archivo_drive.get(
        "webViewLink",
        f"https://drive.google.com/file/d/{archivo_drive['id']}/view"
    )


# ============================================================
# FECHA Y HORA
# ============================================================

ahora = datetime.now()

hora_str = ahora.strftime("%H:%M:%S")


# ============================================================
# LECTURA AUTOMÁTICA DE FACTURAS CON GEMINI
# ============================================================

MODELO_GEMINI = st.secrets.get("gemini", {}).get(
    "modelo", "gemini-3.5-flash-lite"
)

INSTRUCCIONES_LECTURA = """
Eres un asistente contable español. Lee esta factura o ticket de COMPRA
y devuelve SOLO un JSON con estas claves:
- proveedor: nombre comercial del emisor (texto corto)
- fecha: fecha de emisión en formato AAAA-MM-DD
- numero_factura: número de factura o ticket ("" si no aparece)
- concepto: resumen breve de lo comprado (máx. 8 palabras)
- base_imponible: número, suma de bases imponibles
- iva: número, suma de cuotas de IVA
- total: número, total pagado
Si hay varios tipos de IVA, suma las bases y las cuotas.
Si un dato no aparece, usa "" o 0. No inventes datos.
"""


def leer_factura_gemini(contenido, tipo_mime):
    """Envía la factura a Gemini y devuelve un diccionario con los datos."""

    clave = st.secrets.get("gemini", {}).get("api_key")

    if not clave:
        raise RuntimeError(
            "Falta la clave de Gemini en los secretos ([gemini] api_key)."
        )

    respuesta = httpx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{MODELO_GEMINI}:generateContent",
        headers={"x-goog-api-key": clave},
        json={
            "contents": [{
                "parts": [
                    {"text": INSTRUCCIONES_LECTURA},
                    {"inline_data": {
                        "mime_type": tipo_mime,
                        "data": base64.b64encode(contenido).decode()
                    }}
                ]
            }],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0
            }
        },
        timeout=60
    )

    respuesta.raise_for_status()

    texto = (
        respuesta.json()["candidates"][0]["content"]["parts"][0]["text"]
    )

    return json.loads(texto)


def a_numero(valor):
    try:
        return round(float(str(valor).replace(",", ".")), 2)
    except (TypeError, ValueError):
        return 0.0


# Los datos leídos se aplican a los campos ANTES de dibujarlos
if "lectura_pendiente" in st.session_state:
    for clave_campo, valor in st.session_state.pop(
        "lectura_pendiente"
    ).items():
        st.session_state[clave_campo] = valor


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
# FECHA DE LA FACTURA (decide el trimestre del IVA)
# ============================================================

if "fecha_factura" not in st.session_state:
    st.session_state["fecha_factura"] = ahora.date()

fecha_factura = st.date_input(
    "📅 Fecha de la factura:",
    max_value=ahora.date(),
    format="DD/MM/YYYY",
    key="fecha_factura"
)

fecha_str = fecha_factura.strftime("%Y-%m-%d")

st.caption(
    f"Se archivará en {fecha_factura.year} · "
    f"T{((fecha_factura.month - 1) // 3) + 1}"
)


# ============================================================
# INGRESOS
# ============================================================

if "REGISTRAR VENTA" in opcion:

    st.markdown("### 📈 Nuevo Ingreso (Venta)")

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


    st.markdown("#### 📎 Justificante")


    # ========================================================
    # CÁMARA - 1080p
    # ========================================================

    foto_ingreso = st.camera_input(
        "📷 Hacer foto del justificante",
        resolution="1080p"
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

            base = total_cobrado / 1.21

            iva = total_cobrado - base

            link_drive = ""

            error_drive = None


            # ------------------------------------------------
            # INTENTAR SUBIR JUSTIFICANTE
            # ------------------------------------------------

            if archivo_final is not None:

                try:

                    carpeta_ingresos = (
                        obtener_ruta_contabilidad(
                            "INGRESOS",
                            fecha_factura
                        )
                    )

                    link_drive = subir_archivo_drive(
                        archivo_final,
                        carpeta_ingresos
                    )

                except Exception:

                    error_drive = (
                        "Comprueba la autorización OAuth de Drive y "
                        "el acceso a la carpeta principal."
                    )


            # ------------------------------------------------
            # GUARDAR SIEMPRE EL INGRESO EN SHEETS
            # ------------------------------------------------

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


                if error_drive:

                    st.warning(
                        "⚠️ Ingreso guardado en Sheets, "
                        "pero no se pudo subir el justificante a Drive."
                    )

                    st.error(
                        f"Detalle del error de Drive: {error_drive}"
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


    st.markdown("#### 📎 Justificante")


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


    # ========================================================
    # CÁMARA - 1080p
    # ========================================================

    foto_gasto = st.camera_input(
        "📷 O haz una foto del justificante",
        resolution="1080p"
    )


    archivo_final = (
        foto_gasto
        if foto_gasto is not None
        else archivo_gasto
    )


    # ========================================================
    # LEER FACTURA AUTOMÁTICAMENTE
    # ========================================================

    if archivo_final is not None and st.button(
        "🤖 Leer factura automáticamente"
    ):

        with st.spinner("Leyendo la factura..."):

            try:

                tipo_mime = (
                    getattr(archivo_final, "type", None)
                    or "image/jpeg"
                )

                datos = leer_factura_gemini(
                    archivo_final.getvalue(),
                    tipo_mime
                )

                pendiente = {
                    "g_proveedor": str(datos.get("proveedor", "")),
                    "g_concepto": str(datos.get("concepto", "")),
                    "g_num_factura": str(
                        datos.get("numero_factura", "")
                    ),
                    "g_total": a_numero(datos.get("total")),
                    "g_base": a_numero(datos.get("base_imponible")),
                    "g_iva": a_numero(datos.get("iva")),
                }

                try:
                    fecha_leida = date.fromisoformat(
                        str(datos.get("fecha", ""))[:10]
                    )
                    if fecha_leida <= ahora.date():
                        pendiente["fecha_factura"] = fecha_leida
                except ValueError:
                    pass

                st.session_state["lectura_pendiente"] = pendiente
                st.session_state["lectura_ok"] = True
                st.rerun()

            except Exception as e:

                st.error(
                    "No se pudo leer la factura automáticamente. "
                    f"Rellena los datos a mano. ({e})"
                )


    if st.session_state.pop("lectura_ok", False):

        st.success(
            "✅ Factura leída. REVISA los datos antes de guardar."
        )


    st.markdown("#### 🧾 Datos de la factura")


    proveedor = st.text_input(
        "Proveedor (ej: xTool, Gestor):",
        key="g_proveedor"
    )


    concepto_gasto = st.text_input(
        "Concepto del gasto:",
        key="g_concepto"
    )


    num_factura_gasto = st.text_input(
        "Nº de factura (opcional):",
        key="g_num_factura"
    )


    total_pagado = st.number_input(
        "Total pagado (€):",
        min_value=0.0,
        step=1.0,
        key="g_total"
    )


    col_base, col_iva = st.columns(2)

    with col_base:
        base_leida = st.number_input(
            "Base imponible (€):",
            min_value=0.0,
            step=1.0,
            key="g_base",
            help="Si lo dejas en 0 se calcula con IVA del 21 %."
        )

    with col_iva:
        iva_leido = st.number_input(
            "IVA soportado (€):",
            min_value=0.0,
            step=1.0,
            key="g_iva"
        )


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

            if base_leida > 0:

                base = base_leida

                iva = (
                    iva_leido
                    if iva_leido > 0
                    else total_pagado - base_leida
                )

            else:

                base = total_pagado / 1.21

                iva = total_pagado - base

            link_drive = ""

            error_drive = None


            # ------------------------------------------------
            # INTENTAR SUBIR JUSTIFICANTE
            # ------------------------------------------------

            if archivo_final is not None:

                try:

                    carpeta_gastos = (
                        obtener_ruta_contabilidad(
                            "GASTOS",
                            fecha_factura
                        )
                    )

                    link_drive = subir_archivo_drive(
                        archivo_final,
                        carpeta_gastos
                    )

                except Exception:

                    error_drive = (
                        "Comprueba la autorización OAuth de Drive y "
                        "el acceso a la carpeta principal."
                    )


            # ------------------------------------------------
            # GUARDAR SIEMPRE EL GASTO EN SHEETS
            # ------------------------------------------------

            try:

                hoja_gastos.append_row(
                    [
                        fecha_str,
                        hora_str,
                        proveedor,
                        (
                            f"{concepto_gasto} (Fra. {num_factura_gasto})"
                            if num_factura_gasto.strip()
                            else concepto_gasto
                        ),
                        round(base, 2),
                        round(iva, 2),
                        round(total_pagado, 2),
                        link_drive
                    ],
                    value_input_option="USER_ENTERED"
                )


                if error_drive:

                    st.warning(
                        "⚠️ Gasto guardado en Sheets, "
                        "pero no se pudo subir el justificante a Drive."
                    )

                    st.error(
                        f"Detalle del error de Drive: {error_drive}"
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
