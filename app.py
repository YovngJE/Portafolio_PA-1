Sistema de Alerta Temprana Hidrométrica
Quebrada La Brizuela  Sector Empresa New Stetic
Municipio de Guarne, Antioquia

Desarrollado para: Alcaldía de Guarne — Oficina de Gestión del Riesgo
                    de Desastres (OGRD)
Fuente de datos:    API MARCO / CORNARE — Estación 9
Autor:              Jhonatan Perea

Para correrla:
    streamlit run app_nivel_guarne.py

UMBRALES DE ALERTA
-------------------
Los valores de alerta amarilla / naranja / roja que trae este script
corresponden a los niveles definidos para la estación. Quedan
visibles y editables en la barra lateral por si en algún momento la
Oficina de Gestión del Riesgo necesita ajustarlos.
"""

import requests
import pandas as pd
import numpy as np
import streamlit as st
import altair as alt
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ------------------------------------------------------------------
# Identidad institucional
# ------------------------------------------------------------------
MUNICIPIO = "Guarne, Antioquia"
DEPENDENCIA = "Oficina de Gestión del Riesgo de Desastres (OGRD)"
NOMBRE_QUEBRADA = "Quebrada La Brizuela"
SECTOR = "Sector Empresa New Stetic — vía Guarne"
LINEA_EMERGENCIA_NACIONAL = "123"
LINEA_OGRD_GUARNE = "[Línea OGRD Guarne — pendiente de confirmar por la Alcaldía]"

COLOR_INSTITUCIONAL = "#1B5E20"   # verde institucional
COLOR_ACENTO = "#F9A825"          # amarillo de alerta


# ------------------------------------------------------------------
# Coordenadas por defecto (se usan solo si la API no trae lat/lon)
# Ubicación aproximada del sector La Brizuela, Guarne
# ------------------------------------------------------------------
LAT_DEFECTO = 6.2773
LON_DEFECTO = -75.4475

API_BASE_URL = "https://marco.cornare.gov.co/api/v1/estaciones"

LLAVE_FECHA = "level_date"
LLAVE_VALOR = "level"

CANDIDATOS_LAT = ["lat", "latitude", "latitud"]
CANDIDATOS_LON = ["lng", "lon", "longitude", "longitud"]


# ------------------------------------------------------------------
# Configuración de la página
# ------------------------------------------------------------------
st.set_page_config(
    page_title="SAT Quebrada La Brizuela — Alcaldía de Guarne",
    page_icon="🌊",
    layout="wide"
)

st.markdown(
    f"""
    <style>
    .encabezado-institucional {{
        background-color: {COLOR_INSTITUCIONAL};
        padding: 18px 24px;
        border-radius: 8px;
        color: white;
        margin-bottom: 18px;
    }}
    .encabezado-institucional h1 {{
        color: white;
        margin-bottom: 4px;
        font-size: 26px;
    }}
    .encabezado-institucional p {{
        color: #E8F5E9;
        margin: 0;
        font-size: 14px;
    }}
    .banner-alerta {{
        padding: 16px 20px;
        border-radius: 8px;
        font-size: 18px;
        font-weight: 600;
        margin-bottom: 14px;
    }}
    </style>
    """,
    unsafe_allow_html=True
)


# ------------------------------------------------------------------
# Funciones de consulta a la API
# ------------------------------------------------------------------
def obtener_serie_nivel(codigo_estacion, desde, hasta, calidad=1, timeout=30):

    url = f"{API_BASE_URL}/{codigo_estacion}/nivel"

    params = {"desde": desde, "hasta": hasta, "calidad": calidad}

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout, verify=False)
        if resp.status_code == 200:
            return resp.json(), None
        return None, f"HTTP {resp.status_code}"
    except requests.exceptions.RequestException as e:
        return None, f"Error de red: {e}"


def obtener_todas_las_paginas(datos_json, timeout=30):

    registros = list(datos_json.get("values", []))
    siguiente_url = datos_json.get("next")

    while siguiente_url:
        try:
            resp = requests.get(siguiente_url, timeout=timeout, verify=False)
        except requests.exceptions.RequestException:
            break

        if resp.status_code != 200:
            break

        pagina = resp.json()
        registros.extend(pagina.get("values", []))
        siguiente_url = pagina.get("next")

    return registros


def detectar_coordenadas(datos_json):
    """Busca lat/lon en las llaves raíz de la respuesta de la API."""

    if not isinstance(datos_json, dict):
        return (LAT_DEFECTO, LON_DEFECTO, False)

    lat = next((datos_json[k] for k in CANDIDATOS_LAT if k in datos_json), None)
    lon = next((datos_json[k] for k in CANDIDATOS_LON if k in datos_json), None)

    if lat is not None and lon is not None:
        try:
            return (float(lat), float(lon), True)
        except (TypeError, ValueError):
            pass

    return (LAT_DEFECTO, LON_DEFECTO, False)


def calcular_indice_calidad(df):
    """Índice 0-100: completitud de la serie (70%) + ausencia de outliers (30%)."""

    if df.empty or len(df) < 2:
        return 0.0, 0, 0

    df_idx = df.set_index("fecha")

    frecuencia_tipica = df["fecha"].diff().dropna().mode()
    if len(frecuencia_tipica) == 0:
        return 0.0, 0, 0
    frecuencia_tipica = frecuencia_tipica[0]

    rango_completo = pd.date_range(
        start=df_idx.index.min(), end=df_idx.index.max(), freq=frecuencia_tipica
    )
    esperados = len(rango_completo)
    huecos = esperados - len(df_idx)
    completitud = max(0.0, 1 - (huecos / esperados)) if esperados > 0 else 0.0

    Q1 = df["nivel"].quantile(0.25)
    Q3 = df["nivel"].quantile(0.75)
    IQR = Q3 - Q1
    lim_inf = Q1 - 1.5 * IQR
    lim_sup = Q3 + 1.5 * IQR

    es_outlier = (df["nivel"] < lim_inf) | (df["nivel"] > lim_sup) | (df["nivel"] < 0)
    proporcion_outliers = es_outlier.mean()

    indice = (completitud * 0.7 + (1 - proporcion_outliers) * 0.3) * 100

    return round(indice, 1), int(huecos), int(es_outlier.sum())


def evaluar_alerta(nivel_actual, umbral_amarilla, umbral_naranja, umbral_roja):
    """
    Clasifica el nivel actual según los umbrales definidos por la OGRD.
    Devuelve: (etiqueta, color_fondo, color_texto, recomendación)
    """

    if nivel_actual >= umbral_roja:
        return (
            "🔴 ALERTA ROJA",
            "#C62828",
            "white",
            "Nivel crítico. Activar protocolo de evacuación preventiva en el "
            "sector La Brizuela / New Stetic y notificar de inmediato a la OGRD "
            "y a los organismos de socorro."
        )
    if nivel_actual >= umbral_naranja:
        return (
            "🟠 ALERTA NARANJA",
            "#EF6C00",
            "white",
            "Nivel alto. Restringir el paso por puntos bajos de la vía, alistar "
            "equipos de respuesta y aumentar la frecuencia de monitoreo."
        )
    if nivel_actual >= umbral_amarilla:
        return (
            "🟡 ALERTA AMARILLA",
            "#F9A825",
            "black",
            "Nivel en ascenso. Mantener vigilancia activa de la estación y "
            "comunicar el estado a la comunidad y a la empresa New Stetic."
        )
    return (
        "🟢 SIN ALERTA",
        "#2E7D32",
        "white",
        "Nivel dentro del rango normal. Monitoreo rutinario."
    )


# ==================================================================
# PARÁMETROS FIJOS DE LA ESTACIÓN
# ==================================================================

codigo_estacion = "9"


# ------------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------------
# NOTA: si la Alcaldía entrega el escudo oficial en un archivo local,
# se puede mostrar aquí con: st.sidebar.image("escudo_guarne.png", width=80)

st.sidebar.header("📋 Parámetros de consulta")

st.sidebar.write(f"**Municipio:** {MUNICIPIO}")
st.sidebar.write(f"**Dependencia:** {DEPENDENCIA}")
st.sidebar.write(f"**Estación:** {codigo_estacion} — {NOMBRE_QUEBRADA}")

st.sidebar.divider()

fecha_desde = st.sidebar.date_input(
    "Desde", pd.to_datetime("2026-08-23")
).strftime("%Y-%m-%d")

fecha_hasta = st.sidebar.date_input(
    "Hasta", pd.to_datetime("2026-08-30")
).strftime("%Y-%m-%d")

calidad = st.sidebar.selectbox(
    "Calidad del dato", [1, 0], index=0, help="1 = solo datos validados"
)

st.sidebar.divider()

st.sidebar.subheader("⚠️ Umbrales de alerta (m)")
st.sidebar.caption(
    "Umbrales definidos para esta estación. Editables aquí si la "
    "OGRD determina un ajuste."
)

umbral_amarilla = st.sidebar.number_input("Alerta amarilla", value=0.80, step=0.05)
umbral_naranja = st.sidebar.number_input("Alerta naranja", value=1.20, step=0.05)
umbral_roja = st.sidebar.number_input("Alerta roja", value=1.80, step=0.05)

st.sidebar.divider()

consultar = st.sidebar.button("🔍 Consultar", type="primary")


# ==================================================================
# ENCABEZADO INSTITUCIONAL
# ==================================================================

st.markdown(
    f"""
    <div class="encabezado-institucional">
        <h1>🌊 Sistema de Alerta Temprana — {NOMBRE_QUEBRADA}</h1>
        <p>{DEPENDENCIA} · Alcaldía de {MUNICIPIO}</p>
        <p>{SECTOR} — Estación de monitoreo N.° {codigo_estacion}</p>
    </div>
    """,
    unsafe_allow_html=True
)

with st.expander("ℹ️ ¿Por qué se monitorea este punto?"):
    st.write(
        f"La estación {codigo_estacion} registra el nivel de la "
        f"{NOMBRE_QUEBRADA} en el {SECTOR}. Este tramo es de interés "
        "para la OGRD porque combina tránsito vehicular constante, "
        "presencia de infraestructura industrial y viviendas cercanas "
        "al cauce. El monitoreo continuo permite anticipar crecientes "
        "súbitas y activar protocolos de respuesta antes de que el "
        "nivel comprometa la vía o las instalaciones aledañas."
    )


# ==================================================================
# CONSULTA Y PROCESAMIENTO
# ==================================================================

if consultar:

    with st.spinner("Consultando la API MARCO / CORNARE..."):
        datos_crudos, error = obtener_serie_nivel(
            codigo_estacion, fecha_desde, fecha_hasta, calidad
        )

    if error:
        st.error(f"❌ No fue posible consultar la estación: {error}")

    else:
        registros = obtener_todas_las_paginas(datos_crudos)

        if not registros:
            st.warning(
                "No hay registros para esta estación y rango de fechas."
            )

        else:
            df = pd.DataFrame(registros)
            df = df.rename(columns={LLAVE_FECHA: "fecha", LLAVE_VALOR: "nivel"})
            df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
            df["nivel"] = pd.to_numeric(df["nivel"], errors="coerce")

            df = (
                df.dropna(subset=["fecha", "nivel"])
                .sort_values("fecha")
                .reset_index(drop=True)
            )

            lat, lon, coords_reales = detectar_coordenadas(datos_crudos)
            indice_calidad, huecos, n_outliers = calcular_indice_calidad(df)

            nivel_actual = df["nivel"].iloc[-1]
            fecha_ultimo_dato = df["fecha"].iloc[-1]

            etiqueta_alerta, color_fondo, color_texto, recomendacion = evaluar_alerta(
                nivel_actual, umbral_amarilla, umbral_naranja, umbral_roja
            )

            # ======================================================
            # BANNER DE ALERTA
            # ======================================================

            st.markdown(
                f"""
                <div class="banner-alerta" style="background-color:{color_fondo}; color:{color_texto};">
                    {etiqueta_alerta} — Nivel actual: {nivel_actual:.2f} m
                    (dato del {fecha_ultimo_dato.strftime('%Y-%m-%d %H:%M')})
                    <br><span style="font-size:14px; font-weight:400;">{recomendacion}</span>
                </div>
                """,
                unsafe_allow_html=True
            )

            # ======================================================
            # MÉTRICAS PRINCIPALES
            # ======================================================

            st.subheader("📊 Métricas principales")

            col1, col2, col3, col4, col5 = st.columns(5)

            with col1:
                st.metric("Lecturas", len(df))

            with col2:
                st.metric("Nivel actual", f"{nivel_actual:.2f} m")

            with col3:
                st.metric("Nivel promedio", f"{df['nivel'].mean():.2f} m")

            with col4:
                st.metric("Índice de calidad", f"{indice_calidad} / 100")

            with col5:
                st.metric("Outliers detectados", n_outliers)

            # ======================================================
            # GRÁFICO CON UMBRALES DE ALERTA
            # ======================================================

            st.subheader("📈 Serie de nivel y umbrales de alerta")

            base = alt.Chart(df).mark_line(color=COLOR_INSTITUCIONAL).encode(
                x=alt.X("fecha:T", title="Fecha"),
                y=alt.Y("nivel:Q", title="Nivel (m)"),
                tooltip=["fecha:T", "nivel:Q"]
            )

            lineas_umbral = pd.DataFrame({
                "umbral": ["Amarilla", "Naranja", "Roja"],
                "valor": [umbral_amarilla, umbral_naranja, umbral_roja],
                "color": ["#F9A825", "#EF6C00", "#C62828"]
            })

            reglas = alt.Chart(lineas_umbral).mark_rule(strokeDash=[6, 4]).encode(
                y="valor:Q",
                color=alt.Color("umbral:N", scale=alt.Scale(
                    domain=["Amarilla", "Naranja", "Roja"],
                    range=["#F9A825", "#EF6C00", "#C62828"]
                ), legend=alt.Legend(title="Umbral de alerta")),
                tooltip=["umbral:N", "valor:Q"]
            )

            st.altair_chart((base + reglas).interactive(), use_container_width=True)

            # ======================================================
            # MAPA
            # ======================================================

            st.subheader("📍 Ubicación de la estación")

            if not coords_reales:
                st.caption(
                    f"Ubicación aproximada — {SECTOR}, municipio de {MUNICIPIO}. "
                    "La API no reportó coordenadas exactas para esta consulta."
                )

            st.map(pd.DataFrame({"lat": [lat], "lon": [lon]}), zoom=13)

            # ======================================================
            # IMÁGENES DE LA ESTACIÓN
            # ======================================================

            st.subheader("📷 Registro fotográfico de la estación")

            col1, col2, col3 = st.columns(3)

            with col1:
                st.image(
                    "La_Brizuela_1.jpg",
                    caption=f"Estación {codigo_estacion} — {NOMBRE_QUEBRADA}",
                    use_container_width=True
                )

            with col2:
                st.image(
                    "La_Brizuela_3.jpg",
                    caption="Vista del cauce, sector New Stetic",
                    use_container_width=True
                )

            with col3:
                st.image(
                    "La_Brizuela_4.jpg",
                    caption="Entorno vial y de infraestructura cercana",
                    use_container_width=True
                )

            # ======================================================
            # DETALLE DEL ÍNDICE DE CALIDAD
            # ======================================================

            with st.expander("🔎 Detalle del índice de calidad del dato"):
                st.write(f"- Huecos de reporte detectados: **{huecos}**")
                st.write(
                    f"- Outliers (IQR + nivel negativo): **{n_outliers}** "
                    f"de {len(df)} lecturas"
                )
                st.write(
                    "El índice combina completitud de la serie (70%) y "
                    "proporción de datos sin outliers (30%). Un índice bajo "
                    "sugiere revisar el sensor o la conectividad de la estación "
                    "antes de tomar decisiones operativas con estos datos."
                )

            # ======================================================
            # TABLA DE DATOS
            # ======================================================

            with st.expander("📋 Ver datos crudos"):
                st.dataframe(df, use_container_width=True)

            # ======================================================
            # DESCARGAR CSV
            # ======================================================

            csv = df.to_csv(index=False).encode("utf-8")

            st.download_button(
                "⬇️ Descargar CSV para reporte OGRD",
                csv,
                file_name=f"nivel_{NOMBRE_QUEBRADA.replace(' ', '_')}_estacion_{codigo_estacion}.csv",
                mime="text/csv"
            )

            # ======================================================
            # CONTACTO / REPORTE A GESTIÓN DEL RIESGO
            # ======================================================

            st.subheader("📞 Reportar una novedad a la OGRD")
            st.info(
                f"Línea de emergencias nacional: **{LINEA_EMERGENCIA_NACIONAL}**  \n"
                f"Línea directa OGRD Guarne: **{LINEA_OGRD_GUARNE}**  \n"
                "Ante un cambio brusco de nivel o desbordamiento, reportar de "
                "inmediato indicando estación, hora y nivel observado."
            )

else:
    st.info(
        "Presiona **🔍 Consultar** en la barra lateral para cargar los "
        f"datos de la estación {codigo_estacion} sobre la {NOMBRE_QUEBRADA}."
    )


st.divider()
st.caption(
    f"Sistema desarrollado por Jhonatan Perea para la Alcaldía de {MUNICIPIO} — "
    "Oficina de Gestión del Riesgo de Desastres. Datos: API MARCO / CORNARE."
)
