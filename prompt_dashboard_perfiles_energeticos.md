# Dashboard de perfiles energéticos: estructura y visualizaciones

## 1. Archivos del dashboard

### Aplicación y páginas

| Archivo | Propósito y contenido actual |
|---|---|
| `dashboard/app.py` | Aplicación principal. Muestra el título «Dashboard de perfiles energéticos», enumera los archivos de `responses/`, permite seleccionar uno y, si es JSON, presenta su tamaño, número de elementos y contenido con `st.json`. |
| `dashboard/pages/02_Datos_disponibles.py` | Página «Datos disponibles». Permite inspeccionar un JSON de consumo horario mediante una gráfica y una tabla CSV de energía autoconsumida. |
| `dashboard/pages/02_Energía.py` | Página «Energía». Contiene las pestañas «Comunidad» y «Usuario», con métricas, tablas y gráficas mensuales, balances y perfiles horarios estacionales. |
| `dashboard/pages/01_resumen.py` | Página «Resumen energético». Actualmente solo muestra un mensaje informativo de que la página mostrará indicadores generales; no implementa gráficas ni tablas. |
| `dashboard/pages/03_poruno_8760.py` | Página «Perfiles poruno 8760». Actualmente solo muestra un mensaje informativo sobre futuros coeficientes horarios; no implementa gráficas ni tablas. |
| `dashboard/pages/04_validacion.py` | Página «Validación de coeficientes». Actualmente solo muestra un mensaje informativo sobre una futura validación; no implementa gráficas ni tablas. |
| `dashboard/pages/05_pvgis.py` | Página «Producción PVGIS». Actualmente solo muestra un mensaje informativo sobre futura producción fotovoltaica; no implementa gráficas ni tablas. |
| `dashboard/pages/06_reparto.py` | Página «Reparto energético». Actualmente solo muestra un mensaje informativo sobre futuros repartos; no implementa gráficas ni tablas. |
| `dashboard/pages/07_autoconsumo.py` | Página «Autoconsumo». Actualmente solo muestra un mensaje informativo sobre generación, consumo, importación y exportación; no implementa gráficas ni tablas. |
| `dashboard/pages/08_prueba.py` | Página «Resumen Prueba». Actualmente solo muestra un mensaje informativo; no implementa gráficas ni tablas. |

No se encontraron módulos Python bajo `dashboard/components/`. Los módulos
reutilizables de visualización están en `dashboard/utils/`.

### Utilidades de visualización

| Archivo | Responsabilidad |
|---|---|
| `dashboard/utils/consumption_chart.py` | Encuentra JSON de consumo, normaliza sus registros horarios y construye la gráfica temporal de consumo. |
| `dashboard/utils/autoconsumption_chart.py` | Encuentra y valida CSV de energía autoconsumida; carga los datos mensuales y construye el balance, los gráficos circulares por usuario y el porcentaje renovable. |
| `dashboard/utils/hourly_profile_chart.py` | Lee perfiles horarios comunitarios, individuales, ampliados y PVGIS; calcula promedios estacionales y construye perfiles horarios. |
| `dashboard/utils/work_directory.py` | Encuentra `responses/` y sus subdirectorios inmediatos `responses_*`; presenta el selector de directorio de trabajo y conserva la selección entre páginas. |
| `perfil_diario_v9.py` | Genera perfiles individuales weekday/weekend y perfiles ampliados desde los JSON de consumo. La utilidad también contiene la clasificación de festivos nacionales españoles usada por los perfiles ampliados y el cálculo de perfiles horarios. |

Las rutas de los datos que se describen a continuación son relativas al
repositorio salvo que se indique lo contrario. En las páginas «Datos
disponibles» y «Energía», el selector «Selecciona el directorio de trabajo»
permite elegir `responses/` o uno de sus subdirectorios inmediatos
`responses_*`. `responses/` es la opción inicial; la elección se conserva al
navegar entre esas páginas. Los archivos de datos y perfiles usados por dichas
páginas se leen desde el directorio elegido. La aplicación principal
`dashboard/app.py` sigue explorando directamente `responses/`.

## 2. Convenciones de lectura

- Los datos mensuales de energía se seleccionan desde archivos del directorio
  de trabajo con el patrón
  `energia_autoconsumida_<AAAA>_<MM>_<AAAA>_<MM>.csv`.
- La utilidad `load_autoconsumption_data` interpreta las columnas `cups` y
  las columnas mensuales `AAAA-MM_con`, `AAAA-MM_sur`, `AAAA-MM_gen` y
  `AAAA-MM_self`. Estas últimas se convierten, respectivamente, en
  `energia_importada_kWh`, `energia_exportada_kWh`,
  `energia_generada_kWh` y `energia_autoconsumida_kWh`.
- El archivo mensual se transforma en filas por CUPS y mes. La columna `mes`
  conserva la forma `AAAA-MM`.
- Cuando se habla de días representados, las gráficas estacionales toman los
  meses presentes en el CSV seleccionado y cuentan los días naturales de cada
  mes completo. No ponderan según el número de lecturas diarias individuales
  en el CSV mensual.
- Las gráficas horarias muestran las horas de 0 a 23. Cuando un generador
  normaliza una entrada `24:00`, la desplaza a las 00:00 del día siguiente.
- Las unidades y fórmulas indicadas a continuación son las que muestra o
  calcula el código actual. No se debe interpretar una etiqueta como una
  fórmula diferente a la descrita.

## 3. Página «Dashboard de perfiles energéticos»

### Selector e inspección de archivos

- **Nombre y ubicación:** título «Dashboard de perfiles energéticos» en
  `dashboard/app.py`.
- **Propósito:** explorar los archivos regulares disponibles directamente en
  `responses/`.
- **Datos de origen:** nombres de archivo enumerados en el directorio
  `responses/`.
- **Cálculo:** no hay cálculo energético. Para el archivo seleccionado se
  muestra su tamaño en bytes; para JSON se muestra `len(data)` cuando la raíz
  JSON es una lista o un objeto, y también se presenta el JSON con `st.json`.
- **Interacción y comportamiento inicial:** selector «Selecciona un fichero»,
  ordenado alfabéticamente. El primer elemento de la lista queda seleccionado
  por Streamlit; si no hay archivos, el selector contiene «No hay ficheros».
- **Validaciones y casos sin datos:** informa si no existe `responses/`, indica
  cuántos archivos encontró y muestra un error si no puede leer o decodificar
  el JSON. No se presenta una tabla ni una gráfica en esta página.

## 4. Página «Datos disponibles»

### «Consumo horario»

- **Nombre y ubicación:** sección «Consumo horario», en
  `dashboard/pages/02_Datos_disponibles.py`.
- **Propósito:** inspeccionar la serie temporal de consumo de un archivo JSON.
- **Directorio de trabajo:** selector «Selecciona el directorio de trabajo»,
  compartido con la página «Energía».
- **Datos de origen:** archivos en el directorio de trabajo seleccionado cuyo
  nombre coincide con `ES..._<AAAA>_<MM>_<AAAA>_<MM>.json`. Se requieren los
  campos `date`, `time` y `consumptionKWh`.
- **Cálculo:** `date` y `time` se combinan en una marca temporal; el separador
  de fecha `/` se normaliza a `-`. El valor `24:00` se representa como 00:00
  del día siguiente. El consumo se convierte a valor numérico; marcas
  temporales o consumos no válidos se omiten, y los registros se ordenan por
  fecha y hora. No se agregan ni promedian los registros.
- **Ejes, unidades y series:** eje X «Fecha y hora», eje Y «Consumo (kWh)»;
  una línea con el valor `consumptionKWh` de cada registro.
- **Interacción y comportamiento inicial:** selector «Selecciona un fichero
  JSON», con los archivos ordenados; el título de la gráfica es
  «Consumo horario: <nombre del archivo>». Se informa el número de registros
  representados y el hover es unificado por instante.
- **Validaciones y casos sin datos:** avisa si no existe el directorio de
  trabajo o no contiene JSON elegibles; muestra errores por campos requeridos
  ausentes, errores de lectura o ausencia de datos válidos.

### «Energía autoconsumida»

- **Nombre y ubicación:** sección «Energía autoconsumida» en
  `dashboard/pages/02_Datos_disponibles.py`.
- **Propósito:** inspeccionar los datos agregados de energía calculada.
- **Datos de origen:** CSV del directorio de trabajo seleccionado con patrón
  `energia_autoconsumida_<AAAA>_<MM>_<AAAA>_<MM>.csv`.
- **Presentación y cálculo:** se carga el contenido tabular del CSV con pandas
  y se muestra directamente; esta vista no vuelve a calcular ni agrega sus
  valores.
- **Columnas y unidades:** conserva las columnas del archivo seleccionado.
  La página indica el formato temporal `YYYY_MM`; no impone una unidad común a
  todas las columnas en la tabla.
- **Interacción y validación:** el selector «Fichero de energía autoconsumida»
  permite elegir entre los archivos del directorio seleccionado; si no hay
  archivos, muestra un aviso. Si la lectura falla, presenta un error.

## 5. Página «Energía»

La página se divide en las pestañas «Comunidad» y «Usuario». Ambas dependen del
CSV de energía autoconsumida seleccionado en la pestaña «Comunidad». La
selección del CUPS en «Usuario» filtra los datos de ese usuario dentro del
CSV.

### Pestaña «Comunidad»

#### «Estado de la comunidad»

En el directorio de trabajo elegido se busca un CSV de energía autoconsumida
con el patrón descrito en «Convenciones de lectura». El control «Fichero de
energía autoconsumida» permite elegirlo. Los datos se agrupan por `mes` y se
suman entre CUPS. Se calcula además:

```text
energia_consumida_kWh = energia_importada_kWh + energia_autoconsumida_kWh
```

Si no hay archivos, se muestra una advertencia; si el archivo no es válido,
se muestra un error y no se preparan las visualizaciones que dependen de él.

#### Métricas de la comunidad

- **Nombre y ubicación:** tarjetas bajo «Total de la comunidad energética».
- **Propósito:** mostrar totales del período del archivo seleccionado.
- **Datos de origen y cálculo:** sumas comunitarias de
  `energia_importada_kWh`, `energia_autoconsumida_kWh`,
  `energia_exportada_kWh` y `energia_generada_kWh`.
- **Etiquetas y unidades:** «Importada», «Autoconsumida», «Exportada» y
  «Generada», en kWh.
- **Comportamiento inicial:** todas las tarjetas se muestran cuando el CSV se
  pudo procesar.

#### Gráfica «Evolución mensual de la comunidad energética»

- **Propósito:** comparar mensualmente las cantidades de energía de la
  comunidad.
- **Datos de origen:** sumas por `mes` del CSV seleccionado.
- **Cálculo:** los grupos apilados corresponden a autoconsumida + importada y
  autoconsumida + exportada. La serie de autoconsumida aparece en ambos grupos;
  la figura no dibuja una serie independiente de energía generada.
- **Ejes, unidades y series:** X «Mes», Y «Energía (kWh)»; magnitudes de la
  leyenda «Autoconsumida», «Importada» y «Exportada». El grupo de exportación
  repite «Autoconsumida» sin una segunda entrada de leyenda.
- **Estilos e interacción:** barras apiladas agrupadas por mes. Colores:
  importada `#c62828`, autoconsumida `#66bb6a` y exportada `#1976d2`.
  La escala se ajusta automáticamente; la leyenda se titula «Magnitud».

#### Tabla de resumen anual de la comunidad

- **Nombre y ubicación:** tabla adyacente a la gráfica mensual bajo «Total de
  la comunidad energética».
- **Propósito:** resumir tres medidas y su porcentaje respecto al total
  comunitario de la misma medida.
- **Datos y cálculo:** suma de las columnas comunitarias en todo el período
  seleccionado. Las filas son «Consumo total [kWh/año]»,
  «Consumo FV [kWh/año]» y «Generación correspondiente [kWh/año]»,
  correspondientes a `energia_consumida_kWh`,
  `energia_autoconsumida_kWh` y `energia_generada_kWh`. Al ser la comunidad
  comparada consigo misma, el porcentaje es 100 % cuando el denominador no es
  cero.
- **Columnas:** `Medida`, `Valores` (formateado sin decimales) y `Porcentual`
  (un decimal). No se muestra índice.

#### «Perfil horario de consumo en invierno» y «Perfil horario de consumo en verano»

- **Nombre y ubicación:** dos gráficas paralelas bajo «Estado de la comunidad».
- **Propósito:** comparar el consumo medio comunitario, la generación PVGIS
  proporcional y las energías medias por hora derivadas de perfiles ampliados.
- **Datos de origen:** perfiles mensuales
  `perfil_comunitario_weekday.csv` y `perfil_comunitario_weekend.csv`; todos
  los `*_day_profile_extended.json` directamente en el directorio de trabajo
  seleccionado; y, si está disponible, el JSON PVGIS estacional
  `pvgis_spain_profile_winter_2025.json` o
  `pvgis_spain_profile_summer_2025.json`. Los meses usados proceden del CSV de
  autoconsumo seleccionado.
- **Estaciones:** invierno = octubre, noviembre, diciembre, enero, febrero y
  marzo; verano = abril, mayo, junio, julio, agosto y septiembre.
- **Cálculo:** los perfiles comunitarios mensuales weekday/weekend se
  ponderan por los días de cada categoría realmente representados en los
  meses de la estación. En esta ponderación comunitaria, sábados, domingos y
  festivos nacionales españoles cuentan como weekend; los demás días, como
  weekday. Para cada perfil ampliado/CUPS, se ponderan primero sus valores
  mensuales weekday y weekend por los días representados; para cada hora se
  promedian después los valores de CUPS dando el mismo peso a cada CUPS. Se
  excluyen `null` por hora, no se convierten en cero. Se usan
  `self_consumption_kWh` y `total_generation` del perfil ampliado. El perfil
  PVGIS se lee del campo `generacion_media` y debe declarar la unidad
  `kWh/usuario/hora` y una muestra válida por hora.
- **Series y estilos:** «Consumo medio de los usuarios» (`#ef9a9a`, línea
  continua, cuadrado); «Generación PVGIS proporcional» (`#2e7d32`, línea
  continua, círculo y relleno semitransparente);
  «Autoconsumida media de los usuarios» (`#1b5e20`, línea discontinua,
  rombo y relleno semitransparente); y «Energía generada media de los
  usuarios» (`#ba68c8`, línea de puntos, triángulo hacia arriba y relleno
  semitransparente).
- **Ejes y escala:** 24 horas, marcas cada hora; eje Y «Energía media
  (kWh/usuario/hora)». Invierno y verano comparten una escala Y que empieza en
  cero y usa un margen superior del 5 % calculado a partir de los valores
  presentes en ambas figuras disponibles.
- **Comportamiento inicial:** «Generación PVGIS proporcional» está oculta en
  la leyenda hasta que se activa. Las otras series están visibles. La leyenda
  es horizontal debajo de la gráfica.
- **Validaciones y casos sin datos:** faltas de perfiles comunitarios,
  archivos ampliados ausentes o inválidos y meses/horas requeridos ausentes
  producen errores explícitos y no se muestra una gráfica incompleta. Si falta
  el archivo PVGIS de una estación, se advierte su nombre y se presentan las
  demás series, sin inventar datos.

#### «Perfil horario de consumo en invierno: día festivo y día laborable» y
#### «Perfil horario de consumo en verano: día festivo y día laborable»

- **Propósito:** comparar por separado los perfiles comunitarios de día
  festivo y laborable para cada estación.
- **Datos de origen:** `perfil_comunitario_weekend.csv` y
  `perfil_comunitario_weekday.csv`; meses representados en el CSV de energía
  seleccionado.
- **Cálculo:** promedios mensuales por hora ponderados por los días de la
  categoría en los meses de la estación. La ponderación comunitaria cuenta
  sábados, domingos y festivos nacionales españoles como festivo/weekend.
- **Series y estilos:** «Día festivo», `#ef9a9a`, línea continua y marcador
  cuadrado; «Día laborable», `#1a0000`, línea discontinua y marcador cuadrado.
- **Ejes e interacción:** X «Hora del día», horas de 0 a 23 con marcas cada
  hora; Y «Consumo medio (kWh)». La leyenda horizontal aparece debajo.
- **Escala y errores:** ambas estaciones comparten escala Y desde cero, con
  margen superior del 5 %. Si faltan los perfiles o los datos requeridos, se
  muestra un error y no se presentan gráficas parciales.

#### «Porcentaje de energía renovable por usuario»

- **Ubicación:** aparece antes de «Balance energético por usuario» en la
  pestaña «Comunidad».
- **Propósito:** comparar el porcentaje renovable de cada CUPS y su posición
  respecto al porcentaje comunitario de referencia y al 100 %.
- **Datos y cálculo:** valores mensuales agregados por CUPS. El porcentaje se
  calcula como:
  ```text
  (autoconsumida + exportada) / (autoconsumida + importada) × 100
  ```
  El porcentaje comunitario de referencia es la generación comunitaria total
  dividida por el consumo comunitario total, multiplicada por 100. La generación
  corresponde a `energia_generada_kWh`; el consumo corresponde a
  `energia_consumida_kWh` (autoconsumida + importada), de acuerdo con la tabla
  de resumen de la comunidad.
- **Ejes, etiquetas y altura:** barras horizontales, eje X «Porcentaje de
  energía renovable (%)» y eje Y «Usuario», sin etiquetas CUPS visibles en el
  eje. El CUPS se conserva en el hover junto al porcentaje. Las etiquetas de
  valor muestran un decimal; si no hay consumo, muestran «Sin consumo».
  Usuarios ordenados por consumo total descendente. La altura es
  `max(160, 11 × número de CUPS + 48)` píxeles.
- **Colores de barras:** verde `#2e7d32` por debajo de la referencia
  comunitaria; morado `#7b1fa2` desde esa referencia hasta el 100 %, ambos
  límites incluidos; azul `#1976d2` por encima del 100 %. Si no hay referencia,
  los valores hasta el 100 % son morados y los superiores son azules. Si la
  referencia supera el 100 %, los valores hasta el 100 % son verdes y los
  superiores a 100 % son azules.
- **Líneas de referencia:** línea verde en el porcentaje comunitario, cuando
  está definido, y línea morada en el 100 %, ambas con etiquetas en la parte
  superior. La escala X se amplía para incluir las barras y las líneas.
- **Descarga CSV:** un botón junto a la gráfica descarga una fila por CUPS con
  las columnas `CUPS`, `Generada [kWh]` (autoconsumida + exportada),
  `Consumida [kWh]` (autoconsumida + importada),
  `Porcentaje de energía renovable` y
  `Porcentaje comunitario de referencia`. Los valores numéricos se redondean a
  dos decimales en el archivo. Si un usuario no tiene consumo, su porcentaje
  renovable queda vacío; si el consumo comunitario total es cero, la referencia
  comunitaria queda vacía.
- **Casos sin datos:** requiere un CSV seleccionado y procesable. Si el consumo
  comunitario es cero, no se dibuja la línea de referencia verde; la línea del
  100 % se mantiene.

#### «Balance energético por usuario»

- **Propósito:** comparar para cada CUPS dos balances energéticos del período.
- **Datos de origen:** columnas mensuales del CSV seleccionado, agrupadas y
  sumadas por CUPS.
- **Cálculo:** consumo = autoconsumida + importada; la magnitud exportada del
  segundo grupo se calcula como energía generada − autoconsumida. No se usa
  aquí directamente la columna `energia_exportada_kWh` para esa barra.
- **Ejes, unidad y series:** barras horizontales apiladas; X «Energía (kWh)»,
  Y «Usuario». Grupos de «Autoconsumida» + «Importada» y
  «Autoconsumida» + «Exportada».
- **Estilos e interacción:** autoconsumida `#66bb6a`, importada `#c62828` y
  exportada `#1976d2`. Usuarios ordenados de mayor a menor consumo total. Las
  series, incluida «Exportada», están visibles inicialmente. La leyenda permite
  alternar grupos.
- **Dimensiones y legibilidad:** la gráfica ocupa el ancho completo disponible.
  Su altura crece con el número de CUPS, reservando aproximadamente 21 píxeles
  por usuario más 120 píxeles de margen, con una altura mínima de 400 píxeles
  y sin un máximo fijo. El eje Y ajusta automáticamente sus márgenes para que
  las etiquetas de CUPS sean visibles. El hover de cada barra identifica el
  CUPS, la magnitud y el valor en kWh.
- **Casos sin datos:** requiere un CSV seleccionado y procesable; si falta o
  es inválido, muestra un aviso en vez del balance.

#### «Consumo por usuario» y «Energía renovable por usuario»

- **Propósito:** mostrar la proporción del consumo total y de la energía
  renovable atribuida a cada CUPS de la comunidad.
- **Datos de origen:** columnas `energia_autoconsumida_kWh`,
  `energia_importada_kWh` y `energia_exportada_kWh`, agregadas por CUPS.
- **Cálculo:** consumo por CUPS = autoconsumida + importada; energía renovable
  por CUPS = autoconsumida + exportada. Los sectores representan el porcentaje
  respecto al total de la magnitud de cada gráfica. Ambos gráficos ordenan los
  CUPS de mayor a menor consumo total (autoconsumida + importada); los empates
  conservan el orden alfabético inicial de CUPS. Ese mismo orden determina
  también el orden de los sectores de energía renovable.
- **Presentación:** gráficos circulares en paralelo, sin porcentajes escritos
  sobre los sectores y sin leyenda o tabla independiente «Usuario (CUPS)».
  Alternan dos colores de alto contraste en el orden de los sectores:
  oscuro `#263238` y claro `#cfd8dc`, empezando por el oscuro. El hover
  identifica el CUPS y muestra su porcentaje y valor en kWh.
- **Casos sin datos:** si el total de una magnitud es cero, no se dibuja ese
  gráfico y se muestra un aviso específico. Valores negativos provocan un
  error de preparación.

### Pestaña «Usuario»

#### «Estado de un usuario»: selector, métricas y gráfica mensual

- **Interacción:** el selector «Selecciona un CUPS» contiene los CUPS del CSV
  de energía seleccionado, ordenados alfabéticamente. No requiere que los
  perfiles horarios individuales estén presentes en el directorio de trabajo;
  si faltan, se informa al preparar las gráficas correspondientes. El primer
  CUPS queda seleccionado inicialmente.
- **Datos de origen:** filas del CSV seleccionado filtradas por el CUPS. Se
  calcula para cada mes `energia_consumida_kWh` como importada + autoconsumida.
- **Métricas:** «Consumo total [kWh/año]», «Consumo FV [kWh/año]» y
  «Generación correspondiente [kWh/año]», calculadas mediante la suma del
  período del CUPS seleccionado.
- **Gráfica:** título dinámico «Evolución mensual del usuario <CUPS>»;
  barras apiladas mensuales y ejes iguales a la gráfica comunitaria
  «Evolución mensual de la comunidad energética». Muestra las magnitudes
  «Autoconsumida», «Importada» y «Exportada» según los grupos descritos para
  esa gráfica. La escala se ajusta automáticamente.
- **Casos sin datos:** si no se seleccionó o no se pudo leer un CSV válido en
  «Comunidad», no se muestran las visualizaciones del usuario y se informa
  mediante un aviso.

#### Tabla de resumen del CUPS

- **Nombre y ubicación:** tabla junto a la gráfica mensual de usuario.
- **Datos y cálculo:** mismas tres medidas de la tabla comunitaria, sumadas
  para el CUPS seleccionado. `Porcentual` es la suma del CUPS dividida por la
  suma de la comunidad en la misma medida, multiplicada por 100.
- **Columnas:** `Medida`, `Valores` y `Porcentual`, con el mismo formato y
  etiquetas que en la tabla de la comunidad.

#### Gráficos circulares de composición del CUPS

- **Nombre y ubicación:** dos gráficos circulares junto al resumen del CUPS.
  El código no asigna títulos visibles propios a estos gráficos.
- **Propósito:** comparar la parte del CUPS seleccionado con el resto de la
  comunidad en consumo y generación.
- **Datos de origen y cálculo:** sumas del CUPS y de la comunidad en el CSV
  seleccionado. El gráfico izquierdo usa consumo = autoconsumida + importada;
  el derecho usa `energia_generada_kWh`. «Resto de la comunidad» se calcula
  restando el total del CUPS al total comunitario.
- **Etiquetas y estilo:** sectores «CUPS seleccionado» y «Resto de la
  comunidad»; colores de CUPS seleccionado `#ef5350` para consumo y `#2e7d32`
  para generación, resto `#b0bec5`. Se muestran porcentajes dentro de los
  sectores y el hover muestra porcentaje y kWh; no hay leyenda propia.

#### «Perfil horario de consumo en invierno» y «Perfil horario de consumo en verano»

- **Propósito:** comparar el CUPS seleccionado y la comunidad en un perfil
  medio estacional, con series adicionales de PVGIS y energía derivada del
  perfil ampliado cuando están disponibles.
- **Datos de origen:** perfiles individuales
  `<últimos_5_caracteres_CUPS>_weekday_profile.csv` y
  `<últimos_5_caracteres_CUPS>_weekend_profile.csv`; perfiles comunitarios
  `perfil_comunitario_weekday.csv` y `perfil_comunitario_weekend.csv`;
  `<últimos_5_caracteres_CUPS>_day_profile_extended.json`;
  `pvgis_spain_profile_winter_2025.json` o
  `pvgis_spain_profile_summer_2025.json`; y meses del CUPS en el CSV
  seleccionado.
- **Cálculo:** se ponderan los perfiles mensuales del usuario y la comunidad
  según días de semana y fin de semana de los meses representados. Esta
  ponderación usa días laborables de lunes a viernes y weekend sábado/domingo;
  no añade el conteo de festivos nacionales a los pesos de esta gráfica. Las
  métricas `self_consumption_kWh` y `total_generation` del JSON ampliado se
  ponderan por días disponibles en cada hora. PVGIS utiliza `generacion_media`
  en `kWh/usuario/hora`.
- **Series y comportamiento inicial:** «Usuario <CUPS>» está visible;
  «Toda la comunidad» y «Generación PVGIS por usuario» están ocultas
  inicialmente (`legendonly`). «Autoconsumida media por usuario» y
  «Energía generada media por usuario» se muestran cuando existe el perfil
  ampliado.
- **Estilos:** consumo individual `#ef5350`; perfil por usuario PVGIS verde
  `#2e7d32` con relleno; autoconsumida `#1b5e20`, línea discontinua y rombo;
  generación `#ba68c8`, línea de puntos y triángulo hacia arriba. El color de
  la serie del usuario y de la comunidad se asigna con la paleta categórica
  predeterminada de Plotly; no está fijado explícitamente en esta función.
- **Ejes y escala:** X «Hora del día», 0–23 con marcas horarias; Y
  «Energía media (kWh/usuario/hora)» cuando existen perfiles ampliados o PVGIS
  y, en caso contrario, «Consumo medio (kWh)». Las dos estaciones comparten
  una escala Y desde cero con 5 % de margen, calculada sobre las trazas de las
  figuras disponibles. Leyenda horizontal debajo.
- **Validaciones:** perfiles horarios individuales y comunitarios ausentes
  provocan avisos y omiten estas gráficas. Si falta PVGIS, se informa del
  nombre del archivo y se presenta el resto. Si falta el perfil ampliado del
  usuario, se informa y se presentan las series que no dependen de él.

#### «Perfil horario de consumo en invierno: día festivo y día laborable» y
#### «Perfil horario de consumo en verano: día festivo y día laborable»

- **Propósito:** contrastar el CUPS seleccionado por tipo de día y estación,
  manteniendo como series de referencia los perfiles comunitarios.
- **Datos de origen:** archivos weekday/weekend del usuario y de la comunidad,
  junto con los meses representados para el CUPS en el CSV de autoconsumo.
- **Cálculo:** promedios mensuales horarios ponderados por el número de días
  laborables (lunes a viernes) o weekend (sábado/domingo) representados en los
  meses de la estación.
- **Series:** «Usuario <CUPS> — día festivo», «Usuario <CUPS> — día laborable»,
  «Toda la comunidad — día festivo» y «Toda la comunidad — día laborable».
- **Estilos:** día festivo usuario `#ef5350`, línea continua y círculo; día
  laborable usuario `#b71c1c`, línea discontinua y círculo; día festivo
  comunidad `#ef9a9a`, línea continua y cuadrado; día laborable comunidad
  `#1a0000`, línea discontinua y cuadrado. Las dos series de comunidad están
  ocultas inicialmente y pueden activarse desde la leyenda.
- **Ejes y escala:** X «Hora del día», 0–23; Y «Consumo medio (kWh)».
  Invierno y verano comparten una escala desde cero con margen del 5 %.
  Leyenda horizontal debajo.
- **Validaciones:** requiere los perfiles individuales y comunitarios
  weekday/weekend y datos para el tipo de día y estación. Ante errores de
  lectura o datos ausentes, muestra un error explícito.

## 6. Páginas informativas sin visualizaciones

En la implementación inspeccionada, las páginas siguientes muestran su título
y un mensaje `st.info`; no contienen todavía gráficos, tablas ni cálculos:

| Página | Mensaje actual |
|---|---|
| «Resumen energético» | «Esta página mostrará los indicadores generales del sistema.» |
| «Perfiles poruno 8760» | «Esta página mostrará los coeficientes horarios de 8760 horas.» |
| «Validación de coeficientes» | «Esta página mostrará la validación de la suma horaria de coeficientes.» |
| «Producción PVGIS» | «Esta página mostrará la producción fotovoltaica horaria.» |
| «Reparto energético» | «Esta página mostrará el reparto de energía entre los CUPS.» |
| «Autoconsumo» | «Esta página mostrará generación, consumo, importación y exportación.» |
| «Resumen Prueba» | «Esta página es una página de prueba.» |

## 7. Estructura requerida para documentar futuras visualizaciones

Al añadir o modificar una gráfica o tabla, documentarla bajo la pestaña y
sección donde aparece, usando la misma estructura:

1. **Nombre y ubicación:** título visible y página/pestaña/sección.
2. **Propósito:** análisis o comparación que permite.
3. **Datos de origen:** archivos, campos, columnas o perfiles.
4. **Cálculo:** normalización, filtros, agrupaciones, agregaciones,
   ponderaciones y fórmulas confirmadas en el código.
5. **Ejes, unidades y categorías:** dimensiones, unidades y períodos.
6. **Series o columnas:** significado, nombres, estilos y leyenda.
7. **Filtros e interacción:** controles y efecto sobre la visualización.
8. **Comportamiento inicial:** selecciones, series visibles y escalas.
9. **Validaciones y casos sin datos:** avisos, errores, valores omitidos y
   alternativas mostradas.

Documentar solo comportamiento que pueda verificarse en el código actual.
Cuando una regla o fórmula no esté implementada o no se pueda confirmar,
indicarlo explícitamente en lugar de inferirla.
