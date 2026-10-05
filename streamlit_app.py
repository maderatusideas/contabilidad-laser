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
                            "GASTOS"
                        )
                    )

                    link_drive = subir_archivo_drive(
                        archivo_final,
                        carpeta_gastos
                    )

                except Exception as e:

                    error_drive = str(e)


            # ------------------------------------------------
            # GUARDAR SIEMPRE EL GASTO EN SHEETS
            # ------------------------------------------------

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
