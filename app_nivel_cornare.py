"""
App básica de Streamlit — Nivel de ríos/quebradas (CORNARE / MARCO)
--------------------------------------------------------------------
Estudiante: Jhonatan Perea
Código de estación: 9

Para correrla:
    streamlit run app_nivel_cornare.py
"""

import requests
import pandas as pd
import numpy as np
import streamlit as st
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ------------------------------------------------------------------
# Coordenadas por defecto
# Se usan solo si la API no trae la latitud/longitud de la estación.
# ------------------------------------------------------------------
LAT_DEFECTO = 6.2773
LON_DEFECTO = -75.4475

API_BASE_URL = "https://marco.cornare.gov.co/api/v1/estaciones"

LLAVE_FECHA = "level_date"
LLAVE_VALOR = "level"

CANDIDATOS_LAT = [
    "lat",
    "latitude",
    "latitud"
]

CANDIDATOS_LON = [
    "lng",
    "lon",
    "longitude",
    "longitud"
]


# ------------------------------------------------------------------
# Configuración de la página
# ------------------------------------------------------------------
st.set_page_config(
    page_title="Nivel de estación — CORNARE",
    page_icon="🌊",
    layout="wide"
)


# ------------------------------------------------------------------
# Funciones de consulta
# ------------------------------------------------------------------
def obtener_serie_nivel(
    codigo_estacion,
    desde,
    hasta,
    calidad=1,
    timeout=30
):
    url = f"{API_BASE_URL}/{codigo_estacion}/nivel"

    params = {
        "desde": desde,
        "hasta": hasta,
        "calidad": calidad
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
    }

    try:

        resp = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=timeout,
            verify=False
        )

        if resp.status_code == 200:
            return resp.json(), None

        return None, f"HTTP {resp.status_code}"

    except requests.exceptions.RequestException as e:

        return None, f"Error de red: {e}"


# ------------------------------------------------------------------
# Obtener todas las páginas de la API
# ------------------------------------------------------------------
def obtener_todas_las_paginas(datos_json, timeout=30):

    registros = list(
        datos_json.get("values", [])
    )

    siguiente_url = datos_json.get("next")

    while siguiente_url:

        try:

            resp = requests.get(
                siguiente_url,
                timeout=timeout,
                verify=False
            )

        except requests.exceptions.RequestException:

            break

        if resp.status_code != 200:
            break

        pagina = resp.json()

        registros.extend(
            pagina.get("values", [])
        )

        siguiente_url = pagina.get("next")

    return registros


# ------------------------------------------------------------------
# Detectar coordenadas
# ------------------------------------------------------------------
def detectar_coordenadas(datos_json):

    """
    Busca lat/lon en las llaves raíz de la respuesta.
    Si no las encuentra, usa las coordenadas por defecto.
    """

    if not isinstance(datos_json, dict):

        return (
            LAT_DEFECTO,
            LON_DEFECTO,
            False
        )

    lat = next(
        (
            datos_json[k]
            for k in CANDIDATOS_LAT
            if k in datos_json
        ),
        None
    )

    lon = next(
        (
            datos_json[k]
            for k in CANDIDATOS_LON
            if k in datos_json
        ),
        None
    )

    if lat is not None and lon is not None:

        try:

            return (
                float(lat),
                float(lon),
                True
            )

        except (TypeError, ValueError):

            pass

    return (
        LAT_DEFECTO,
        LON_DEFECTO,
        False
    )


# ------------------------------------------------------------------
# Calcular índice de calidad
# ------------------------------------------------------------------
def calcular_indice_calidad(df):

    """
    Índice simple de 0 a 100.

    Combina:
    - Completitud de la serie: 70%
    - Datos sin outliers: 30%
    """

    if df.empty or len(df) < 2:

        return 0.0, 0, 0

    df_idx = df.set_index("fecha")

    frecuencia_tipica = (
        df["fecha"]
        .diff()
        .dropna()
        .mode()
    )

    if len(frecuencia_tipica) == 0:

        return 0.0, 0, 0

    frecuencia_tipica = frecuencia_tipica[0]

    rango_completo = pd.date_range(
        start=df_idx.index.min(),
        end=df_idx.index.max(),
        freq=frecuencia_tipica
    )

    esperados = len(rango_completo)

    huecos = esperados - len(df_idx)

    if esperados > 0:

        completitud = max(
            0.0,
            1 - (huecos / esperados)
        )

    else:

        completitud = 0.0

    # --------------------------------------------------------------
    # Detección de outliers mediante IQR
    # --------------------------------------------------------------
    Q1 = df["nivel"].quantile(0.25)
    Q3 = df["nivel"].quantile(0.75)

    IQR = Q3 - Q1

    lim_inf = Q1 - 1.5 * IQR
    lim_sup = Q3 + 1.5 * IQR

    es_outlier = (
        (df["nivel"] < lim_inf)
        |
        (df["nivel"] > lim_sup)
        |
        (df["nivel"] < 0)
    )

    proporcion_outliers = es_outlier.mean()

    indice = (
        completitud * 0.7
        +
        (1 - proporcion_outliers) * 0.3
    ) * 100

    return (
        round(indice, 1),
        int(huecos),
        int(es_outlier.sum())
    )


# ==================================================================
# PARÁMETROS FIJOS DEL ESTUDIANTE
# ==================================================================

nombre_estudiante = "Jhonatan Perea"

codigo_estacion = "9"


# ------------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------------
st.sidebar.header(
    "📋 Parámetros de la consulta"
)

st.sidebar.write(
    f"**Estudiante:** {nombre_estudiante}"
)

st.sidebar.write(
    f"**Código de estación:** {codigo_estacion}"
)

fecha_desde = st.sidebar.date_input(
    "Desde",
    pd.to_datetime("2026-08-23")
).strftime("%Y-%m-%d")

fecha_hasta = st.sidebar.date_input(
    "Hasta",
    pd.to_datetime("2026-08-30")
).strftime("%Y-%m-%d")

calidad = st.sidebar.selectbox(
    "Calidad",
    [1, 0],
    index=0,
    help="1 = solo datos validados"
)

consultar = st.sidebar.button(
    "🔍 Consultar",
    type="primary"
)


# ==================================================================
# TÍTULO
# ==================================================================

st.title(
    "🌊 Nivel de ríos y quebradas — CORNARE"
)

st.caption(
    f"Estudiante: **{nombre_estudiante}** "
    f"· Estación: **{codigo_estacion}**"
)


# ==================================================================
# CONSULTA Y PROCESAMIENTO
# ==================================================================

if consultar:

    # --------------------------------------------------------------
    # Consulta a la API
    # --------------------------------------------------------------
    with st.spinner(
        "Consultando la API..."
    ):

        datos_crudos, error = obtener_serie_nivel(
            codigo_estacion,
            fecha_desde,
            fecha_hasta,
            calidad
        )


    # --------------------------------------------------------------
    # Error de consulta
    # --------------------------------------------------------------
    if error:

        st.error(
            f"❌ {error}"
        )


    else:

        # ----------------------------------------------------------
        # Obtener registros
        # ----------------------------------------------------------
        registros = obtener_todas_las_paginas(
            datos_crudos
        )


        # ----------------------------------------------------------
        # No hay registros
        # ----------------------------------------------------------
        if not registros:

            st.warning(
                "No hay registros para esta estación "
                "y rango de fechas."
            )


        else:

            # ------------------------------------------------------
            # Crear DataFrame
            # ------------------------------------------------------
            df = pd.DataFrame(
                registros
            )


            # ------------------------------------------------------
            # Cambiar nombres de columnas
            # ------------------------------------------------------
            df = df.rename(
                columns={
                    LLAVE_FECHA: "fecha",
                    LLAVE_VALOR: "nivel"
                }
            )


            # ------------------------------------------------------
            # Convertir fecha
            # ------------------------------------------------------
            df["fecha"] = pd.to_datetime(
                df["fecha"],
                errors="coerce"
            )


            # ------------------------------------------------------
            # Convertir nivel a número
            # ------------------------------------------------------
            df["nivel"] = pd.to_numeric(
                df["nivel"],
                errors="coerce"
            )


            # ------------------------------------------------------
            # Limpiar datos
            # ------------------------------------------------------
            df = (
                df
                .dropna(
                    subset=[
                        "fecha",
                        "nivel"
                    ]
                )
                .sort_values("fecha")
                .reset_index(drop=True)
            )


            # ------------------------------------------------------
            # Coordenadas
            # ------------------------------------------------------
            lat, lon, coords_reales = detectar_coordenadas(
                datos_crudos
            )


            # ------------------------------------------------------
            # Índice de calidad
            # ------------------------------------------------------
            indice_calidad, huecos, n_outliers = (
                calcular_indice_calidad(df)
            )


            # ======================================================
            # MÉTRICAS PRINCIPALES
            # ======================================================

            st.subheader(
                "📊 Métricas principales"
            )

            col1, col2, col3, col4 = st.columns(4)


            with col1:

                st.metric(
                    "Lecturas",
                    len(df)
                )


            with col2:

                st.metric(
                    "Nivel promedio",
                    f"{df['nivel'].mean():.2f}"
                )


            with col3:

                st.metric(
                    "Índice de calidad",
                    f"{indice_calidad} / 100"
                )


            with col4:

                st.metric(
                    "Outliers detectados",
                    n_outliers
                )


            # ======================================================
            # GRÁFICO
            # ======================================================

            st.subheader(
                "📈 Serie de nivel"
            )

            st.line_chart(
                df.set_index("fecha")["nivel"]
            )


            # ======================================================
            # MAPA
            # ======================================================

            st.subheader(
                "📍 Ubicación de la estación"
            )

            if not coords_reales:

                st.caption(
                    "Guarne, Quebrada La Brizuela, "
                    "Empresa New Stetic."
                )


            st.map(
                pd.DataFrame(
                    {
                        "lat": [lat],
                        "lon": [lon]
                    }
                ),
                zoom=10
            )


            # ======================================================
            # IMÁGENES DE LA ESTACIÓN
            # ======================================================

            st.subheader(
                "📷 Así es la estación"
            )

            col1, col2, col3 = st.columns(3)


            # ------------------------------------------------------
            # Imagen 1
            # ------------------------------------------------------
            with col1:

                st.image(
                    "La_Brizuela_1.jpg",
                    caption="Estación de monitoreo",
                    use_container_width=True
                )


            # ------------------------------------------------------
            # Imagen 2
            # ------------------------------------------------------
            with col2:

                st.image(
                    "La_Brizuela_3.jpg",
                    caption="Vista de la estación",
                    use_container_width=True
                )


            # ------------------------------------------------------
            # Imagen 3
            # ------------------------------------------------------
            with col3:

                st.image(
                    "La_Brizuela_4.jpg",
                    caption="Entorno de la estación",
                    use_container_width=True
                )


            # ======================================================
            # DETALLE DEL ÍNDICE DE CALIDAD
            # ======================================================

            with st.expander(
                "🔎 Detalle del índice de calidad"
            ):

                st.write(
                    f"- Huecos de reporte detectados: "
                    f"**{huecos}**"
                )

                st.write(
                    f"- Outliers (IQR + nivel negativo): "
                    f"**{n_outliers}** de {len(df)} lecturas"
                )

                st.write(
                    "El índice combina completitud de la serie "
                    "(70%) y proporción de datos sin outliers (30%)."
                )


            # ======================================================
            # TABLA DE DATOS
            # ======================================================

            with st.expander(
                "📋 Ver datos crudos"
            ):

                st.dataframe(
                    df,
                    use_container_width=True
                )


            # ======================================================
            # DESCARGAR CSV
            # ======================================================

            csv = df.to_csv(
                index=False
            ).encode("utf-8")


            st.download_button(
                "⬇️ Descargar CSV",
                csv,
                file_name=(
                    f"nivel_estacion_"
                    f"{codigo_estacion}.csv"
                ),
                mime="text/csv"
            )


# ==================================================================
# MENSAJE INICIAL
# ==================================================================

else:

    st.info(
        "Presiona **🔍 Consultar** para cargar "
        "los datos de la estación."
    )
