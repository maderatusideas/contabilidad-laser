import streamlit as st
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# Configuración estética de la app para el móvil
st.set_page_config(page_title="Control Láser NT", page_icon="⚡", layout="centered")
st.title("⚡ Panel de Contabilidad Láser")

# 1. Conexión segura con Google usando los Secrets de Streamlit
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def conectar_google():
    try:
        info_claves = dict(st.secrets["gcp_service_account"])
        info_claves["private_key"] = info_claves["private_key"].replace("\\n", "\n")
        credenciales = Credentials.from_service_account_info(info_claves, scopes=scopes)
        return gspread.authorize(credenciales)
    except Exception as e:
        st.error(f"Error crítico en la configuración de la clave: {e}")
        return None

@st.cache_resource
def conectar_drive():
    try:
        info_claves = dict(st.secrets["gcp_service_account"])
        info_claves["private_key"] = info_claves["private_key"].replace("\\n", "\n")
        credenciales = Credentials.from_service_account_info(info_claves, scopes=scopes)
        return build("drive", "v3", credentials=credenciales)
    except Exception as e:
        st.error(f"Error al conectar con Google Drive: {e}")
        return None

cliente = conectar_google()
drive = conectar_drive()
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
    return archivos[0]["id"] if archivos else None
    id_carpeta_principal = st.secrets["google_drive"]["id_carpeta_principal"]
    nombre_carpeta_prueba = buscar_carpeta("2026", id_carpeta_principal)
    
if cliente:
    try:
        id_sheet = st.secrets["google_sheets"]["id_documento"]
        documento = cliente.open_by_key(id_sheet)
        
        # OBTENEMOS LAS PESTAÑAS POR SU ORDEN FÍSICO
        hojas = documento.worksheets()
        hoja_ingresos = hojas[0]  # La primera pestaña de tu Excel
        hoja_gastos = hojas[1]     # La segunda pestaña de tu Excel
        
        st.success(f"🟢 Conectado con éxito a: {documento.title}")
    except Exception as e:
        st.error(f"🔴 Error al acceder a las pestañas del documento: {e}")
else:
    st.error("🔴 No se ha podido validar la cuenta de servicio de Google.")

# 2. Interfaz de usuario para vuestros teléfonos móviles
opcion = st.radio("Operación:", ["🛒 REGISTRAR COMPRA (Gasto)", "💰 REGISTRAR VENTA (Ingreso)"], horizontal=True)

ahora = datetime.now()
fecha_str = ahora.strftime("%Y-%m-%d")
hora_str = ahora.strftime("%H:%M:%S")

if "REGISTRAR VENTA" in opcion:
    st.markdown("### 📈 Nuevo Ingreso (Venta)")
    
    try:
        filas_existentes = len(hoja_ingresos.get_all_values())
        codigo_factura = f"F-{ahora.strftime('%Y')}-{(filas_existentes):03d}"
    except:
        codigo_factura = "F-ERROR"
        
    st.info(f"Número de Factura asignado: **{codigo_factura}**")
    
    concepto = st.text_input("Concepto del pedido:")
    total_cobrado = st.number_input("Total cobrado con IVA (€):", min_value=0.0, step=1.0)
    archivo_subido = st.file_uploader(
    "📎 Adjuntar justificante (PDF, foto, ticket o factura)",
    type=["pdf", "jpg", "jpeg", "png"],
    accept_multiple_files=False
)
    
    if st.button("🚀 Guardar e Inyectar en Excel ingresos"):
        if concepto and total_cobrado > 0:
            base_imponible = round(total_cobrado / 1.21, 2)
            iva_21 = round(total_cobrado - base_imponible, 2)
            
            estado_archivo = "Archivo Adjunto" if archivo_subido is not None else "Sin Archivo"
            try:
                hoja_ingresos.append_row([
                    fecha_str, hora_str, codigo_factura, concepto, 
                    base_imponible, iva_21, total_cobrado, estado_archivo
                ])
                st.success(f"¡Venta {codigo_factura} anotada en Ingresos! 🎉")
            except Exception as e:
                st.error(f"Error al escribir en Excel: {e}")
        else:
            st.warning("Por favor, rellena el concepto y el importe cobrado.")

else:
    st.markdown("### 📉 Nuevo Gasto (Compra / Inversión)")
    st.info("💡 ¡Sube aquí el PDF de la factura de vuestra xTool P3!")
    
    proveedor = st.text_input("Proveedor (ej: xTool, Gestor):")
    concepto_gasto = st.text_input("Concepto del gasto:")
    total_pagado = st.number_input("Total pagado (€):", min_value=0.0, step=1.0)
    archivo_subido = st.file_uploader(
    "📎 Adjuntar justificante (PDF, foto, ticket o factura)",
    type=["pdf", "jpg", "jpeg", "png"],
    accept_multiple_files=False
)
    
    if st.button("💾 Enviar Factura a la columna Gastos"):
        if proveedor and concepto_gasto and total_pagado > 0:
            base_imponible = round(total_pagado / 1.21, 2)
            iva_soportado = round(total_pagado - base_imponible, 2)
            
            estado_archivo = "PDF/Imagen Adjunto" if archivo_subido is not None else "Sin Archivo"
            try:
                hoja_gastos.append_row([
                    fecha_str, hora_str, proveedor, concepto_gasto, 
                    base_imponible, iva_soportado, total_pagado, estado_archivo
                ])
                st.success(f"¡Gasto de {proveedor} guardado con éxito! 💸")
            except Exception as e:
                st.error(f"Error al escribir en Excel: {e}")
        else:
            st.warning("Por favor, rellena los campos obligatorios.")
