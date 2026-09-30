import streamlit as st
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# Configuración estética de la app para el móvil
st.set_page_config(page_title="Control Láser NT", page_icon="⚡", layout="centered")
st.title("⚡ Panel de Contabilidad Láser")

# 1. Conexión segura con Google usando los Secrets de Streamlit
scopes = [
    "https://googleapis.com",
    "https://googleapis.com"
]

@st.cache_resource
def conectar_google():
    info_claves = dict(st.secrets["gcp_service_account"])
    # Corregir posibles problemas con los saltos de línea de la clave privada
    info_claves["private_key"] = info_claves["private_key"].replace("\\n", "\n")
    credenciales = Credentials.from_service_account_info(info_claves, scopes=scopes)
    return gspread.authorize(credenciales)

try:
    cliente = conectar_google()
    id_sheet = st.secrets["google_sheets"]["id_documento"]
    documento = cliente.open_by_key(id_sheet)
    hoja_ingresos = documento.worksheet("INGRESOS")
    hoja_gastos = documento.worksheet("GASTOS")
    st.success("🟢 Conectado con éxito a Google Sheets")
except Exception as e:
    st.error(f"🔴 Error de conexión: {e}")

# 2. Interfaz de usuario para tu móvil y el de tu mujer
opcion = st.radio("Operación:", ["🛒 REGISTRAR COMPRA (Gasto)", "💰 REGISTRAR VENTA (Ingreso)"], horizontal=True)

ahora = datetime.now()
fecha_str = ahora.strftime("%Y-%m-%d")
hora_str = ahora.strftime("%H:%M:%S")

if "REGISTRAR VENTA" in opcion:
    st.markdown("### 📈 Nuevo Ingreso (Venta)")
    
    # Cálculo automático del número de factura correlativo leyendo el Excel
    try:
        filas_existentes = len(hoja_ingresos.get_all_values())
        codigo_factura = f"F-{ahora.strftime('%Y')}-{(filas_existentes):03d}"
    except:
        codigo_factura = "Error leyendo filas"
        
    st.info(f"Número de Factura asignado: **{codigo_factura}**")
    
    concepto = st.text_input("Concepto del pedido:")
    total_cobrado = st.number_input("Total cobrado con IVA (€):", min_value=0.0, step=1.0)
    foto_venta = st.camera_input("Foto del producto terminado:")
    
    if st.button("🚀 Guardar e Inyectar en Excel"):
        if concepto and total_cobrado > 0:
            base_imponible = round(total_cobrado / 1.21, 2)
            iva_21 = round(total_cobrado - base_imponible, 2)
            
            try:
                # Subir datos al Excel de Google Sheets
                hoja_ingresos.append_row([
                    fecha_str, hora_str, codigo_factura, concepto, 
                    base_imponible, iva_21, total_cobrado, "Foto capturada"
                ])
                st.success(f"¡Venta registrada con éxito! Añadida al Excel en tiempo real.")
            except Exception as e:
                st.error(f"Error al escribir en Excel: {e}")
        else:
            st.warning("Faltan datos obligatorios.")

else:
    st.markdown("### 📉 Nuevo Gasto (Compra / Inversión)")
    
    proveedor = st.text_input("Proveedor:")
    concepto_gasto = st.text_input("Concepto del gasto:")
    total_pagado = st.number_input("Total pagado (€):", min_value=0.0, step=1.0)
    foto_compra = st.camera_input("Hacer foto al ticket/factura:")
    
    if st.button("💾 Enviar Factura al Gestor"):
        if proveedor and concepto_gasto and total_pagado > 0:
            base_imponible = round(total_pagado / 1.21, 2)
            iva_soportado = round(total_pagado - base_imponible, 2)
            
            try:
                # Subir datos a la pestaña GASTOS
                hoja_gastos.append_row([
                    fecha_str, hora_str, proveedor, concepto_gasto, 
                    base_imponible, iva_soportado, total_pagado, "Foto archivada"
                ])
                st.success(f"¡Gasto enviado! Tu gestor ya puede ver la fila reflejada.")
            except Exception as e:
                st.error(f"Error al escribir en Excel: {e}")
        else:
            st.warning("Por favor, rellena los campos obligatorios.")
