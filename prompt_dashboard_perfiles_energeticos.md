# PROMPT DE DESARROLLO — DASHBOARD DE PERFILES ENERGÉTICOS

## 1. CONTEXTO DEL PROYECTO

Dispongo de un sistema de gestión de perfiles energéticos desarrollado en Python y expuesto mediante una API REST con FastAPI.

El sistema procesa datos de consumo energético, genera perfiles horarios, calcula coeficientes de reparto, consulta producción fotovoltaica mediante PVGIS y calcula resultados de autoconsumo.

La API existente **ya funciona y no debe modificarse inicialmente**.

El objetivo de este proyecto es desarrollar una **interfaz gráfica web para visualizar los resultados generados por los endpoints existentes**.

La aplicación debe desarrollarse de forma incremental, mediante tareas pequeñas y verificables. Después de cada tarea debe ser posible ejecutar la aplicación y comprobar visualmente el resultado.

Antes de desarrollar la interfaz gráfica, el primer objetivo es preparar un entorno de trabajo reproducible en mi portátil local con Ubuntu. El entorno debe permitir instalar las dependencias necesarias, crear un entorno virtual aislado de Python, estructurar el proyecto y ejecutar la app localmente sin depender de un entorno remoto.

---

# 2. OBJETIVO PRINCIPAL

Crear un dashboard web para analizar gráficamente los resultados generados por el sistema energético.

Tecnologías inicialmente recomendadas:

* Python
* Streamlit
* Pandas
* Plotly

La aplicación de visualización debe mantenerse inicialmente separada de la API FastAPI.

Arquitectura inicial:

```text
                API EXISTENTE
                  FastAPI
                 api36.py
                     │
                     │
                     ▼
                responses/
             JSON / CSV / TXT
                     │
                     ▼
              ┌─────────────┐
              │  Streamlit  │
              │   Dashboard │
              └──────┬──────┘
                     │
                     ▼
             Gráficos interactivos
```

No modificar la lógica de negocio existente salvo que sea estrictamente necesario.

---

# 3. ESTRUCTURA ACTUAL DEL SISTEMA

Los principales módulos existentes son:

* `api36.py`

  * Punto de entrada de la API REST FastAPI.
  * Define los endpoints y modelos de entrada.
  * Delega la lógica en los módulos de negocio.

* `perfil_diario_v9.py`

  * Generación de perfiles diarios.
  * Perfiles poruno mensuales.
  * Expansión a 8760 horas.
  * Validación.
  * Corrección/combinación.
  * Reparto de kWh.

* `perfil_comunidad_v1.py`

  * Generación del perfil comunitario a partir de perfiles individuales.

* `PVGIS_consulta_horaria_v03.py`

  * Consulta a PVGIS.
  * Ajuste horario a España.
  * Generación de fichero horario.

* `calculo_autoconsumida_v0.py`

  * Cálculo de energía autoconsumida.
  * Procesamiento de JSON de consumo.
  * Soporte para horas `24:00`.

* `consulta_baisca_v30.py`

  * Integración con DATADIS.
  * Generación/actualización de `reading_register.txt`.
  * Consulta de consumos.
  * Almacenamiento de respuestas JSON.

Directorios:

```text
responses/
community_profiles/
registers/
logs/
```

`responses/` es el directorio principal donde se almacenan los resultados de los procesos.

---

# 4. REGLA FUNDAMENTAL DE DESARROLLO

## Trabajar siempre en tareas cortas

No desarrollar todo el dashboard de una vez.

Cada tarea debe:

1. Ser pequeña.
2. Tener un objetivo concreto.
3. Modificar el mínimo número de archivos posible.
4. Poder ejecutarse inmediatamente.
5. Producir un resultado visible.
6. Ser comprobable antes de continuar.

Ejemplo:

```text
Tarea 1
    ↓
Dashboard arranca
    ↓
Comprobar resultado
    ↓
Tarea 2
    ↓
Mostrar JSON
    ↓
Comprobar resultado
    ↓
Tarea 3
    ↓
Mostrar gráfico
```

No implementar funcionalidades futuras antes de que la tarea actual esté funcionando.

---

# 5. PRIMER OBJETIVO

Crear el entorno de trabajo local en Ubuntu antes de desarrollar la interfaz. Este primer objetivo debe consistir en dejar preparado el proyecto para trabajar en mi portátil local con Python y poder ejecutar la aplicación en el mismo equipo.

Debe incluir, como mínimo:

* comprobar que Ubuntu tiene Python 3 instalado;
* crear un entorno virtual (`venv` o `conda`) para aislar dependencias;
* instalar las librerías base del proyecto: `streamlit`, `pandas`, `plotly`, `fastapi`, `uvicorn`, `requests` y cualquier dependencia mínima que haga falta;
* crear la estructura inicial del repositorio (`dashboard/`, `pages/`, `components/`, `utils/`);
* crear un archivo de requisitos o entorno reproducible;
* verificar que la aplicación puede arrancar localmente con un comando simple;
* comprobar que el proyecto reconoce el directorio `responses/` y que se puede listar su contenido desde la app.

La primera versión NO debe:

* modificar FastAPI;
* ejecutar endpoints complejos del sistema;
* modificar ficheros de `responses/`;
* realizar cálculos energéticos avanzados;
* implementar autenticación;
* introducir una base de datos.

La prioridad inicial es:

```text
UBUNTU LOCAL → ENTORNO REPRODUCIBLE → STREAMLIT ARRANCA → FICHERO VISIBLE
```

Solo cuando el entorno esté funcionando correctamente se debe avanzar al siguiente paso, que será mostrar una primera pantalla mínima con título, listado de ficheros y selector de archivo.

---

# 6. ESTRUCTURA PROPUESTA DEL DASHBOARD

Crear inicialmente:

```text
dashboard/
│
├── app.py
│
├── pages/
│   ├── 01_resumen.py
│   ├── 02_Datos_disponibles.py
│   ├── 02_Energía.py
│   ├── 03_poruno_8760.py
│   ├── 04_validacion.py
│   ├── 05_pvgis.py
│   ├── 06_reparto.py
│   └── 07_autoconsumo.py
│
├── components/
│
├── utils/
│
└── requirements.txt
```

No es obligatorio crear todos estos archivos desde el principio.

Crear solamente los necesarios para cada tarea.

---

# 7. FUNCIONALIDAD DE LOS ENDPOINTS EXISTENTES

## 7.1 GET `/reading_register/{linea}`

Función:

```text
generar_y_guardar_reading_register(linea_datos)
```

Entrada:

Una cadena con información de DATADIS.

Ejemplo:

```text
ES0021000011297631SM,09404423E,8,5,2025,10,2025,10
```

Salida:

```text
registers/reading_register.txt
```

Respuesta:

```text
status
message
num_registros
```

Objetivo del endpoint:

Construir un `reading_register.txt` válido para consultar consumos posteriormente en DATADIS.

Este endpoint no requiere inicialmente una visualización gráfica.

---

# 8. GET `/ejecutar`

Función:

```text
procesar_consumos()
```

No recibe body.

Utiliza:

```text
registers/reading_register.txt
config_datadis.ini
```

Genera:

```text
responses/CUPS_YYYY_MM_YYYY_MM.json
```

y:

```text
logs/log_datadis.log
```

Su función es consultar los consumos de los CUPS registrados en DATADIS.

El dashboard deberá posteriormente permitir visualizar los JSON obtenidos.

---

# 9. POST `/ejecutar/calculo_autoconsumida`

Función:

```text
calcular_energia_autoconsumida(
    directorio,
    mes_inicio,
    anio_inicio,
    mes_fin,
    anio_fin
)
```

Entrada:

```text
directorio
mes_inicio
anio_inicio
mes_fin
anio_fin
```

Lee:

```text
responses/*.json
```

Los JSON contienen datos como:

```text
date
cups
consumptionKWh
surplusEnergyKWh
generationEnergyKWh
selfConsumptionEnergyKWh
```

Genera:

```text
responses/energia_autoconsumida_YYYY_MM_YYYY_MM.csv
```

El dashboard debe poder visualizar posteriormente:

* consumo;
* generación;
* autoconsumo;
* excedentes;
* datos mensuales;
* datos por usuario.

---

# 10. GET `/generate_daily_profile`

Función:

```text
generate_daily_profile(input_file)
```

Entrada:

```text
file_path
```

El fichero está dentro de:

```text
responses/
```

Ejemplo:

```text
ES0021000004444444ZZ_2025_01_2025_12.json
```

Genera:

```text
responses/<ultimos_5_caracteres_CUPS>_weekday_profile.csv
responses/<ultimos_5_caracteres_CUPS>_weekend_profile.csv
```

El sistema:

* normaliza horas `24:00`;
* calcula `total_consumption`;
* utiliza:

```text
consumptionKWh + selfConsumptionEnergyKWh
```

cuando `selfConsumptionEnergyKWh` está disponible;

* clasifica los registros como `weekday` o `weekend`.

El dashboard deberá representar:

* perfil horario medio;
* weekday;
* weekend;
* comparación entre ambos;
* evolución mensual si los datos disponibles lo permiten.

---

# 11. POST `/perfiles/comunidad`

Función:

```text
generar_perfil_comunitario(directorio)
```

y:

```text
guardar_perfil_comunitario(...)
```

Entrada:

```text
directorio
```

Lee:

```text
responses/*_profile.csv
```

Genera:

```text
responses/perfil_comunitario_weekday.csv
responses/perfil_comunitario_weekend.csv
```

El sistema calcula la media mensual por hora para cada categoría.

El dashboard deberá representar el perfil comunitario y permitir compararlo con perfiles individuales.

---

# 12. POST `/perfiles/poruno_batch`

Función:

```text
generate_poruno_profiles_batch(
    directory,
    num_users_ce
)
```

Entrada:

```text
directorio
num_users_ce
```

Utiliza:

```text
perfil_comunitario_weekday.csv
perfil_comunitario_weekend.csv

*_weekday_profile.csv
*_weekend_profile.csv
```

Genera:

```text
*_weekday_poruno.csv
*_weekend_poruno.csv
```

El dashboard deberá permitir seleccionar usuarios y visualizar sus perfiles poruno.

---

# 13. POST `/perfiles/poruno_8760`

Función:

```text
generate_poruno_8760_batch(
    directory,
    year
)
```

Entrada:

```text
directorio
year
```

Utiliza:

```text
cups_list.csv
*_weekday_poruno.csv
*_weekend_poruno.csv
```

Genera:

```text
responses/{CUPS}_8760_poruno_{year}.txt
```

Formato:

```text
CUPS;hora;coeficiente
```

Las horas son:

```text
0001
0002
...
8760
```

El coeficiente tiene 6 decimales.

El dashboard debe incluir una visualización específica para estos datos.

### Visualizaciones previstas

1. Curva de coeficiente de las 8760 horas.
2. Selección de CUPS.
3. Heatmap:

```text
        00  01  02 ... 23
Día 1
Día 2
Día 3
...
Día 365
```

4. Estadísticas:

* mínimo;
* máximo;
* media;
* suma;
* desviación.

---

# 14. POST `/validar/suma_poruno`

Función:

```text
validar_suma_poruno_8760(
    directory,
    year
)
```

Entrada:

```text
directorio
year
```

Lee:

```text
*_8760_poruno_{year}.txt
```

Genera:

```text
responses/validacion_suma_poruno_{year}.txt
```

La regla fundamental es:

```text
SUMA DE COEFICIENTES = 1
```

para cada una de las 8760 horas.

La validación devuelve:

```text
total_hours
hours_with_exact_sum
hours_with_deviation
max_deviation
min_deviation
mean_deviation
```

### Dashboard

Crear una pantalla de validación con:

* indicador OK / ERROR;
* número de horas correctas;
* número de horas con desviación;
* desviación máxima;
* desviación mínima;
* desviación media;
* gráfico de desviación por hora.

Debe quedar visualmente muy claro si el conjunto de perfiles es válido.

---

# 15. POST `/corregir/suma_poruno_y_combinar`

Función:

```text
corregir_y_combinar_poruno_8760(
    directory,
    year
)
```

Lee:

```text
*_8760_poruno_{year}.txt
```

Genera:

```text
responses/todos_usuarios_8760_poruno_{year}.txt
```

Además modifica el último fichero encontrado de usuario.

Devuelve:

```text
status
year
num_users
last_user_corrected
other_users
combined_file
last_user_file
verification_errors
message
```

La corrección solo es válida cuando el ajuste por hora está dentro de:

```text
[-0.0001, 0.0001]
```

El dashboard deberá mostrar posteriormente:

* resultado antes de corrección;
* resultado después de corrección;
* errores;
* usuarios;
* fichero combinado.

---

# 16. POST `/pvgis/consulta_horaria`

Función:

```text
generar_pvgis_horario(
    parametros,
    output_path=None
)
```

Entrada:

```text
lat
lon
startyear
endyear
peakpower
angle
azimuth
loss
directorio
```

Consulta PVGIS.

Genera:

```text
responses/pvgis_indextime_spain.txt
```

Formato:

```text
0001;valor_horario_en_kWh
0002;valor_horario_en_kWh
...
8760;valor_horario_en_kWh
```

La aplicación realiza ajustes de horario a España.

Los valores se almacenan en:

```text
kWh/hora
```

### Dashboard

Crear visualizaciones de:

* generación anual;
* generación mensual;
* generación diaria;
* curva horaria;
* heatmap 365 × 24;
* parámetros utilizados.

---

# 17. POST `/reparto/cups_list`

Función:

```text
calcular_reparto_kwh_poruno(
    directory,
    year
)
```

Utiliza:

```text
responses/cups_list.csv
responses/pvgis_indextime_spain.txt
responses/{CUPS}_8760_poruno_{year}.txt
```

Genera:

```text
responses/cups_list_reparto.csv
```

Columnas:

```text
cups
cif
kwh_asignado
pct_kwh_total
```

El cálculo es:

```text
kwh_asignado =
SUM(
    coeficiente_hora *
    energia_disponible_hora
)
```

Es decir:

```text
kwh_asignado = Σ(poruno_h × pvgis_h)
```

El porcentaje es:

```text
pct_kwh_total =
(kwh_asignado / total_available_kwh) × 100
```

### Dashboard

Mostrar:

* tabla de usuarios;
* kWh asignados;
* porcentaje;
* total disponible;
* gráfico de barras;
* gráfico circular;
* ranking de usuarios.

---

# 18. POST `/reparto/proyeccion_autoconsumida`

Función:

```text
calcular_proyeccion_autoconsumida(
    archivo_json,
    pvgis_file=None,
    coef_file=None,
    historial_file=None
)
```

Entrada:

```text
archivo_json
pvgis_file
coef_file
historial_file
```

Utiliza:

```text
responses/pvgis_indextime_spain.txt
responses/{CUPS}_8760_poruno_{year}.txt
responses/CUPS_YYYY_MM_YYYY_MM.json
```

Genera:

```text
responses/resultados_calculo_autoconsumida.json
```

Para cada hora calcula:

```text
generada = pvgis_h × coef_h

consumida =
    consumptionKWh +
    selfConsumptionEnergyKWh

neto = generada - consumida
```

Si:

```text
neto >= 0
```

entonces:

```text
energia_exportada += neto
energia_autoconsumida += consumida
```

Si:

```text
neto < 0
```

entonces:

```text
energia_importada += abs(neto)
energia_autoconsumida += generada
```

El resultado contiene:

```text
energia_exportada
energia_autoconsumida
energia_importada
```

además de información sobre:

* CUPS;
* año;
* horas incluidas;
* horas disponibles;
* fechas;
* fichero PVGIS;
* fichero de coeficientes.

### Dashboard

Crear una pantalla específica para autoconsumo con:

* energía generada;
* energía consumida;
* energía autoconsumida;
* energía importada;
* energía exportada;
* porcentaje de autoconsumo;
* evolución mensual;
* evolución horaria;
* balance energético.

---

# 19. REGLAS DE NEGOCIO

Respetar estrictamente:

### Perfiles mensuales

Deben tener:

```text
12 filas
```

y:

```text
25 columnas
```

Una columna:

```text
month
```

más 24 horas.

### Año de 8760 horas

La expansión anual debe mantener exactamente:

```text
8760 horas
```

excluyendo el 29 de febrero.

### Validación

La suma de los coeficientes de todos los usuarios debe ser:

```text
1
```

para cada hora.

### Corrección

Solo aceptar ajustes dentro de:

```text
[-0.0001, 0.0001]
```

### Festivos

Los festivos nacionales españoles se consideran como fines de semana para clasificar perfiles.

### Horas 24:00

Los datos pueden utilizar:

```text
24:00
```

y deben interpretarse correctamente.

No realizar conversiones horarias simplificadas que puedan alterar las 8760 horas.

---

# 20. DISEÑO DEL DASHBOARD

La interfaz debe ser sencilla y técnica.

Priorizar:

* claridad;
* información energética;
* gráficos interactivos;
* filtros;
* selección de CUPS;
* selección de año;
* tablas;
* indicadores KPI.

No sobrecargar la interfaz.

Utilizar Plotly para gráficos interactivos.

---

# 21. PÁGINAS PROPUESTAS

## Página 1 — Resumen

Mostrar:

```text
Nº CUPS
Energía PV
Energía asignada
Autoconsumo
Importación
Exportación
```

Además:

* resumen de perfiles;
* estado de validación;
* reparto energético.

---

## APP

La pestaña APP conserva el explorador general de `responses/`: muestra el directorio y el número de archivos, permite seleccionar un archivo y, si es JSON, muestra su tamaño, número de registros y contenido. No incluir aquí el selector específico de JSON de consumo ni su gráfica horaria.

## Datos disponibles

En esta pestaña, dentro de la sección **Consumo horario**:

* mostrar el número de JSON de consumo válidos encontrados en `responses/`;
* permitir seleccionar un archivo con el selector «Selecciona un fichero JSON»;
* mostrar la gráfica de consumo horario correspondiente y el número de registros representados.

Incluir también una sección **Energía autoconsumida** para consultar resultados del endpoint `calcular_energia_autoconsumida`:

* indicar cuántos CSV válidos se encontraron;
* mostrar el patrón `energia_autoconsumida_<fecha_inicio>_<fecha_final>.csv`;
* permitir seleccionar un CSV y mostrar todo su contenido original en una tabla, sin modificarlo.

El selector JSON y su gráfica pertenecen a Datos disponibles, no a APP ni a Energía.

## Página Energía

La pestaña Energía debe contener dos apartados del mismo nivel: **Comunidad** y **Energía autoconsumida**. El selector de CSV `energia_autoconsumida_<fecha_inicio>_<fecha_final>.csv` está en Comunidad y el archivo seleccionado alimenta los dos apartados. El selector de CUPS permanece en Energía autoconsumida.

### Comunidad

Mostrar cuatro KPI comunitarios: energía importada, autoconsumida, exportada y generada. Añadir una gráfica mensual con dos columnas apiladas por mes:

* **Autoconsumida + Importada**: autoconsumida como segmento inferior e importada encima.
* **Autoconsumida + Exportada**: autoconsumida como segmento inferior y exportada encima.

Conservar los colores actuales de las series autoconsumida, importada y exportada. La autoconsumida debe ser la base de ambas columnas; mostrar una leyenda que permita identificar claramente cada segmento. No representar en esta gráfica las magnitudes consumida ni generada. Mostrar también una tabla resumen comunitaria con tres medidas y porcentajes; al usar el total comunitario como numerador y denominador, mostrar 100 % si el total es distinto de cero y «—» si es cero.

Incluir cuatro gráficas horarias, en dos filas:

* **Invierno** (octubre-marzo) y **verano** (abril-septiembre): mostrar estas cuatro series horarias, alineadas por hora:
  * **Consumo medio de los usuarios**, calculado con los perfiles horarios comunitarios existentes.
  * **Generación PVGIS proporcional**, cargada desde `pvgis_spain_profile_winter_2025.json` o `pvgis_spain_profile_summer_2025.json`.
  * **Autoconsumida media de los usuarios** y **Energía generada media de los usuarios**, calculadas desde todos los archivos `*_day_profile_extended.json` del directorio `responses/` (directorio predeterminado). Para cada CUPS, calcular la media estacional por hora ponderando las medias mensuales de `weekday` y `weekend` por los días representados en cada mes y categoría. Clasificar sábados, domingos y festivos nacionales españoles como `weekend`; los demás días son `weekday`. Después, calcular el promedio aritmético de las medias estacionales de los CUPS con dato válido para cada hora: cada CUPS tiene el mismo peso y se excluyen de esa hora los valores `null`.

  Mostrar las cuatro series en el mismo eje Y, con unidad por usuario `kWh/usuario/hora`, y una escala Y común para las gráficas de invierno y verano, de modo que puedan compararse entre sí. Mantener para autoconsumo y generación los colores, estilos de línea, marcadores y rellenos de sus series equivalentes del apartado Energía autoconsumida. Si el directorio no existe, no contiene perfiles o algún perfil es inválido, mostrar un error explícito en lugar de resultados parciales.
* **Día festivo** y **día laborable**: mostrar únicamente el perfil horario comunitario correspondiente (`perfil_comunitario_weekend.csv` o `perfil_comunitario_weekday.csv`); no incluir ni comparar perfiles individuales de CUPS.

Las gráficas horarias deben mostrar 24 horas, usar líneas y marcadores y mantener la leyenda debajo. Las gráficas estacionales deben compartir la misma escala Y entre invierno y verano; las de día festivo y día laborable también deben compartir una escala Y entre sí. Las gráficas estacionales incluyen PVGIS; las de festivo y laborable no.

### Energía autoconsumida

Mantener aquí el selector «Selecciona un CUPS». Los datos proceden del CSV seleccionado en Comunidad. Mostrar:

* cuatro KPI del CUPS seleccionado: energía importada, autoconsumida, exportada y generada;
* una gráfica mensual del usuario con dos columnas apiladas por mes: **Autoconsumida + Importada** (autoconsumida abajo e importada encima) y **Autoconsumida + Exportada** (autoconsumida abajo y exportada encima). Conservar los colores actuales de autoconsumida, importada y exportada; usar autoconsumida como base en ambas columnas y una leyenda que identifique claramente los segmentos. No representar consumida ni generada en esta gráfica. Mantener el mismo criterio y estilo que en la gráfica mensual de Comunidad;
* una tabla resumen de tres medidas, con porcentajes respecto al total comunitario. Calcular el consumo como energía importada más autoconsumida y cada porcentaje como `100 × valor del CUPS / total comunitario`; mostrar «—» si el denominador es cero;
* dos gráficos circulares junto a la tabla: consumo y generación del CUPS seleccionado frente al resto de la comunidad. Mostrar porcentajes sin títulos internos ni leyendas; usar rojo `#ef5350` para consumo, verde `#2e7d32` para generación y gris para el resto.

Incluir cuatro gráficas horarias, en dos filas:

* **Invierno** y **verano**: comparar perfil horario del usuario, perfil comunitario y generación PVGIS. Usar los archivos individuales `<prefijo>_weekday_profile.csv` y `<prefijo>_weekend_profile.csv`, donde el prefijo son los últimos cinco caracteres del CUPS, junto con los perfiles comunitarios y el JSON PVGIS correspondiente. Ponderar weekday/weekend según los días representados y alinear las series por hora.
* **Día festivo** y **día laborable**: comparar el perfil del CUPS con el comunitario usando, respectivamente, los archivos `weekend` y `weekday` del usuario y de la comunidad.

Las gráficas horarias deben mostrar 24 horas, líneas y marcadores, una leyenda horizontal debajo y un máximo Y compartido dentro de cada pareja. En las gráficas de festivo/laborable, usar `#ef5350` y marcador circular para el CUPS, y `#ef9a9a` con marcador cuadrado para la comunidad. En las gráficas estacionales, la serie PVGIS usa verde `#2e7d32` y relleno semitransparente. Mantener el diseño y las convenciones actuales del dashboard.

---

## Página 3 — Poruno 8760

Permitir seleccionar:

* CUPS;
* año.

Mostrar:

* curva 8760;
* heatmap 365 × 24;
* estadísticas.

---

## Página 4 — Validación

Mostrar:

* OK / ERROR;
* suma horaria;
* desviaciones;
* estadísticas;
* gráfico de desviación.

---

## Página 5 — PVGIS

Mostrar:

* parámetros;
* producción;
* curva horaria;
* producción mensual;
* heatmap anual.

---

## Página 6 — Reparto

Mostrar:

* usuarios;
* CUPS;
* kWh;
* porcentaje;
* ranking;
* gráfico de barras;
* gráfico circular.

---

## Página 7 — Autoconsumo

Mostrar:

* generación;
* consumo;
* autoconsumo;
* importación;
* exportación;
* evolución temporal;
* balance energético.

---

# 22. ARCHIVOS Y FORMATOS

El dashboard debe ser capaz de leer:

```text
JSON
CSV
TXT
```

No modificar los ficheros originales al visualizarlos.

Los ficheros existentes son la fuente de datos inicial.

---

# 23. SEPARACIÓN DE RESPONSABILIDADES

Es muy importante mantener separadas:

```text
API / cálculo
       │
       ▼
resultados
       │
       ▼
visualización
```

El dashboard no debe duplicar la lógica de negocio de FastAPI.

No volver a implementar en Streamlit cálculos que ya realiza la API si el resultado puede obtenerse del fichero generado.

---

# 24. FUTURA INTEGRACIÓN CON FASTAPI

Inicialmente:

```text
Streamlit → lee responses/
```

Posteriormente se podrá implementar:

```text
Streamlit
    │
    ▼
FastAPI
    │
    ▼
responses/
```

La conexión mediante API debe hacerse después de validar que las visualizaciones son correctas.

---

# 25. FUTURA CONTENERIZACIÓN

Una vez validado el dashboard:

```text
Docker
│
├── API
│   └── FastAPI
│
└── Dashboard
    └── Streamlit
```

No crear Docker como primera tarea.

Primero conseguir que la aplicación funcione localmente.

---

# 26. METODOLOGÍA DE TRABAJO CON LA IA DE PROGRAMACIÓN

La IA debe trabajar como un desarrollador que colabora conmigo.

Para cada tarea:

### 1. Explicar brevemente qué se va a hacer

Máximo unas pocas líneas.

### 2. Indicar los archivos que se van a crear/modificar

No modificar otros archivos.

### 3. Proporcionar el código completo necesario

Evitar fragmentos ambiguos cuando sea posible.

### 4. Indicar cómo ejecutar la tarea

Por ejemplo:

```bash
source venv/bin/activate
streamlit run app.py
```

### 5. Indicar qué resultado debo observar

Por ejemplo:

```text
Debe aparecer una página con:
- título
- número de ficheros
- selector de fichero
```

### 6. Esperar mi confirmación

No continuar automáticamente con la siguiente tarea.

---

# 27. PRIMERAS TAREAS

Implementar en este orden:

## TAREA 1

Crear Streamlit mínimo.

Resultado:

```text
Dashboard funcionando
+
lista de ficheros de responses/
```

---

## TAREA 2

Seleccionar un fichero JSON.

Mostrar:

* nombre;
* tamaño;
* contenido;
* número de registros.

---

## TAREA 3

En la pestaña **Datos disponibles**, seleccionar un JSON de consumo y mostrar su gráfica horaria. Mantener esta gráfica fuera de la pestaña Energía.

Mostrar también el número de registros representados.

---

## TAREA 4

Mostrar:

```text
weekday
weekend
```

de un usuario.

---

## TAREA 5

Mostrar perfil comunitario.

---

## TAREA 6

Mostrar un fichero poruno de 8760 horas.

---

## TAREA 7

Crear heatmap 365 × 24.

---

## TAREA 8

Visualizar validación de suma.

---

## TAREA 9

Visualizar PVGIS.

---

## TAREA 10

Visualizar reparto.

---

## TAREA 11

Visualizar autoconsumo.

---

## TAREA 12

Crear página Resumen.

---

## TAREA 13

Conectar con FastAPI.

---

## TAREA 14

Preparar Docker.

---

# 28. RESTRICCIONES

No realizar cambios innecesarios en la API existente.

No cambiar nombres de endpoints.

No cambiar formatos de ficheros existentes.

No cambiar las reglas de negocio.

No inventar datos.

No asumir que un fichero existe: comprobarlo.

Controlar correctamente:

* ficheros inexistentes;
* JSON inválidos;
* CSV vacíos;
* usuarios sin fichero 8760;
* años diferentes;
* datos incompletos;
* valores nulos.

Los errores deben mostrarse de forma comprensible en la interfaz.

---

# 29. ESTILO DE DESARROLLO

El código debe ser:

* sencillo;
* modular;
* mantenible;
* comentado cuando sea necesario;
* compatible con Linux/Ubuntu;
* preparado para ejecutarse posteriormente en Docker.

Evitar sobreingeniería.

No introducir frameworks adicionales salvo que exista una razón clara.

La prioridad es:

```text
FUNCIONA
    ↓
SE VE
    ↓
SE VALIDA
    ↓
SE MEJORA
```

---

# 30. CRITERIO GENERAL

El sistema actual es el motor energético.

El nuevo dashboard debe convertirse en una herramienta para **entender visualmente qué está haciendo el motor**.

La prioridad inicial no es construir una aplicación web compleja.

La prioridad es poder responder visualmente preguntas como:

* ¿Cómo consume cada usuario?
* ¿Cómo es el perfil comunitario?
* ¿Cómo se distribuyen los coeficientes?
* ¿Suman 1 los coeficientes?
* ¿Cómo evoluciona el coeficiente durante las 8760 horas?
* ¿Cuánta energía PV hay disponible?
* ¿Cómo se reparte entre los CUPS?
* ¿Cuánta energía autoconsume cada usuario?
* ¿Cuánta energía se importa?
* ¿Cuánta se exporta?

Construir la aplicación **paso a paso**, validando cada resultado antes de continuar.
