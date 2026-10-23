# Sistema de gestión de perfiles energéticos

## Objetivo y alcance

La aplicación expone una API REST con FastAPI para consultar consumos en DATADIS, generar perfiles individuales y comunitarios, calcular coeficientes poruno horarios, validarlos y corregirlos, consultar generación fotovoltaica en PVGIS y calcular repartos y proyecciones de autoconsumo.

Esta documentación describe el comportamiento implementado en el repositorio, principalmente en `api36.py` y los módulos de negocio. Los nombres de rutas, valores por defecto y formatos de salida se deben contrastar con el código cuando este documento se actualice.

## Organización del proyecto
### Estructura de endpoints
ENDPOINTS DEFINIDOS EN api36.py
|
+-- Autenticacion comun
|   |
|   +--> authenticate()
|        (api36.py; dependencia HTTP Basic de todas las rutas)
|
+-- DATADIS
|   |
|   +-- GET /reading_register/{linea}
|   |   (endpoint: api36.py; funcion de negocio: consulta_baisca_v30.py)
|   |   |
|   |   +--> generar_reading_register()
|   |        (api36.py)
|   |        |
|   |        +--> generar_y_guardar_reading_register()
|   |             (consulta_baisca_v30.py)
|   |
|   +-- GET /ejecutar
|   |   (endpoint: api36.py; funcion de negocio: consulta_baisca_v30.py)
|   |   |
|   |   +--> ejecutar_script()
|   |        (api36.py)
|   |        |
|   |        +--> procesar_consumos()
|   |             (consulta_baisca_v30.py)
|   |             |
|   |             +--> obtener_key()
|   |             |    (consulta_baisca_v30.py)
|   |             +--> abrir_reading_register()
|   |             |    (consulta_baisca_v30.py)
|   |             +--> consulta_de_consumos()
|   |             |    (consulta_baisca_v30.py)
|   |             +--> guardar_response()
|   |                  (consulta_baisca_v30.py)
|   |
|   +-- POST /ejecutar/calculo_autoconsumida
|       (endpoint: api36.py; funcion de negocio: calculo_autoconsumida_v0.py)
|       |
|       +--> calculo_autoconsumida_endpoint()
|            (api36.py)
|            |
|            +--> calcular_energia_autoconsumida()
|                 (calculo_autoconsumida_v0.py)
|
+-- Perfiles individuales y comunitarios
|   |
|   +-- GET /generate_daily_profile
|   |   (endpoint: api36.py; funcion de negocio: perfil_diario_v9.py)
|   |   |
|   |   +--> generate_profile_endpoint()
|   |        (api36.py)
|   |        |
|   |        +--> generate_daily_profile()
|   |             (perfil_diario_v9.py)
|   |             |
|   |             +--> load_json_to_df()
|   |             |    (perfil_diario_v9.py)
|   |             +--> prepare_dataframe()
|   |             |    (perfil_diario_v9.py)
|   |             +--> compute_monthly_hourly_means()
|   |                  (perfil_diario_v9.py)
|   |                  |
|   |                  +--> compute_monthly_hourly_mean()
|   |                       (perfil_diario_v9.py)
|   |
|   +-- GET /generate_daily_profile_extended
|   |   (endpoint: api36.py; funcion de negocio: perfil_diario_v9.py)
|   |   |
|   |   +--> generate_extended_profile_endpoint()
|   |        (api36.py)
|   |        |
|   |        +--> generate_daily_profile_extended()
|   |             (perfil_diario_v9.py)
|   |             |
|   |             +--> _spanish_national_holidays()
|   |                  (perfil_diario_v9.py)
|   |
|   +-- POST /perfiles/comunidad
|   |   (endpoint: api36.py; funciones de negocio: perfil_comunidad_v1.py)
|   |   |
|   |   +--> guardar_perfil_comunitario_endpoint()
|   |        (api36.py)
|   |        |
|   |        +--> generar_perfil_comunitario()
|   |        |    (perfil_comunidad_v1.py)
|   |        |    |
|   |        |    +--> obtener_perfiles_validos()
|   |        |    |    (perfil_comunidad_v1.py)
|   |        |    +--> leer_perfil()
|   |        |         (perfil_comunidad_v1.py)
|   |        |
|   |        +--> guardar_perfil_comunitario()
|   |             (perfil_comunidad_v1.py)
|   |
|   +-- POST /perfiles/poruno_batch
|   |   (endpoint: api36.py; funcion de negocio: perfil_diario_v9.py)
|   |   |
|   |   +--> generar_poruno_batch()
|   |        (api36.py)
|   |        |
|   |        +--> generate_poruno_profiles_batch()
|   |             (perfil_diario_v9.py)
|   |             |
|   |             +--> _load_monthly_profile()
|   |             |    (perfil_diario_v9.py)
|   |             +--> _save_monthly_profile()
|   |                  (perfil_diario_v9.py)
|   |
|   +-- POST /perfiles/poruno_8760
|       (endpoint: api36.py; funcion de negocio: perfil_diario_v9.py)
|       |
|       +--> generar_poruno_8760_batch_endpoint()
|            (api36.py)
|            |
|            +--> generate_poruno_8760_batch()
|                 (perfil_diario_v9.py)
|                 |
|                 +--> _load_monthly_profile()
|                 |    (perfil_diario_v9.py)
|                 +--> _build_poruno_yearly_series()
|                 |    (perfil_diario_v9.py)
|                 |    |
|                 |    +--> _create_yearly_index()
|                 |    |    (perfil_diario_v9.py)
|                 |    +--> _spanish_national_holidays()
|                 |         (perfil_diario_v9.py)
|                 +--> _spanish_national_holidays()
|                      (perfil_diario_v9.py)
|
+-- Validacion y correccion poruno
|   |
|   +-- POST /validar/suma_poruno
|   |   (endpoint: api36.py; funcion de negocio: perfil_diario_v9.py)
|   |   |
|   |   +--> validar_suma_poruno_endpoint()
|   |        (api36.py)
|   |        |
|   |        +--> validar_suma_poruno_8760()
|   |             (perfil_diario_v9.py; procesa los ficheros directamente)
|   |
|   +-- POST /corregir/suma_poruno_y_combinar
|       (endpoint: api36.py; funcion de negocio: perfil_diario_v9.py)
|       |
|       +--> corregir_y_combinar_poruno_endpoint()
|            (api36.py)
|            |
|            +--> corregir_y_combinar_poruno_8760()
|                 (perfil_diario_v9.py; procesa, corrige y combina los ficheros directamente)
|
+-- PVGIS
|   |
|   +-- POST /pvgis/consulta_horaria
|   |   (endpoint: api36.py; funcion de negocio: PVGIS_consulta_horaria_v03.py)
|   |   |
|   |   +--> pvgis_consulta_horaria()
|   |        (api36.py)
|   |        |
|   |        +--> generar_pvgis_horario()
|   |             (PVGIS_consulta_horaria_v03.py)
|   |             |
|   |             +--> cargar_parametros_pvgis()
|   |             |    (PVGIS_consulta_horaria_v03.py)
|   |             +--> construir_url_pvgis()
|   |             |    (PVGIS_consulta_horaria_v03.py)
|   |             +--> ajustar_horario_spain()
|   |             |    (PVGIS_consulta_horaria_v03.py)
|   |             +--> guardar_txt_pvgis_spain()
|   |                  (PVGIS_consulta_horaria_v03.py)
|   |
|   +-- POST /pvgis/consulta_horaria/perfiles_medios
|       (endpoint: api36.py; funcion de negocio: pvgis_perfiles_medios.py)
|       |
|       +--> pvgis_perfiles_medios_por_usuario()
|            (api36.py)
|            |
|            +--> calcular_perfiles_medios_por_usuario()
|                 (pvgis_perfiles_medios.py)
|                 |
|                 +--> _local_timestamp_for_hour_offset()
|                      (pvgis_perfiles_medios.py)
|
+-- Reparto
    |
    +-- POST /reparto/cups_list
    |   (endpoint: api36.py; funcion de negocio: perfil_diario_v9.py)
    |   |
    |   +--> calcular_cups_list_reparto_endpoint()
    |        (api36.py)
    |        |
    |        +--> calcular_reparto_kwh_poruno()
    |             (perfil_diario_v9.py; procesa los CSV y TXT directamente)
    |
    +-- POST /reparto/proyeccion_autoconsumida
        (endpoint: api36.py; funcion de negocio: calculo_autoconsumida_v0.py)
        |
        +--> proyeccion_autoconsumida_endpoint()
             (api36.py)
             |
             +--> calcular_proyeccion_autoconsumida()
                  (calculo_autoconsumida_v0.py)
                  |
                  +--> _resolve_path()
                  |    (calculo_autoconsumida_v0.py)
                  +--> _load_proyeccion_json()
                  |    (calculo_autoconsumida_v0.py)
                  |    |
                  |    +--> _parse_date_time()
                  |         (calculo_autoconsumida_v0.py)
                  +--> _load_pvgis_energy()
                  |    (calculo_autoconsumida_v0.py)
                  +--> _load_poruno_coefficients()
                  |    (calculo_autoconsumida_v0.py)
                  +--> _parse_constant_coefficient()
                  |    (calculo_autoconsumida_v0.py)
                  +--> _append_historial()
                       (calculo_autoconsumida_v0.py)


### Código principal

| Fichero | Responsabilidad |
| --- | --- |
| `api36.py` | Aplicación FastAPI, autenticación, modelos de solicitud y definición de rutas. |
| `consulta_baisca_v30.py` | Integración con DATADIS, creación del registro de lectura y guardado de respuestas. |
| `perfil_diario_v9.py` | Perfiles diarios, perfiles poruno, expansión anual a 8760 horas, validación, corrección y reparto. |
| `perfil_comunidad_v1.py` | Cálculo de perfiles comunitarios a partir de perfiles individuales. |
| `PVGIS_consulta_horaria_v03.py` | Consulta de la serie horaria a PVGIS y escritura del TXT horario. |
| `pvgis_perfiles_medios.py` | Cálculo de perfiles medios estacionales de generación por usuario. |
| `calculo_autoconsumida_v0.py` | Cálculo mensual de autoconsumo y proyección de autoconsumo horaria. |

### Datos, configuración y salidas

| Ruta | Uso actual |
| --- | --- |
| `responses/` | Respuestas JSON de DATADIS y ficheros de trabajo/salida de los endpoints. |
| `registers/` | Registro de lectura de DATADIS y ficheros relacionados con la autenticación de ese servicio. |
| `logs/` | Logs del proceso de consulta a DATADIS. |
| `community_profiles/` | Perfiles de ejemplo o datos comunitarios del proyecto. |
| `config_datadis.ini`, `config_datadis_ea.ini` | Configuración de la integración con DATADIS. |
| `requirements_clean.txt` | Dependencias declaradas del proyecto. |

Los endpoints de perfiles, poruno y reparto utilizan `responses/` como directorio por defecto. No se debe asumir que los subdirectorios `responses/profile/`, `responses/poruno/` o `responses/reparto/` se creen o utilicen automáticamente: las salidas se escriben en el directorio recibido o en la ruta fija que indique cada implementación.

### Autenticación

Todas las rutas de `api36.py` requieren autenticación HTTP Basic. Las credenciales están configuradas en el código de la aplicación; no se reproducen aquí. Una solicitud sin credenciales válidas recibe HTTP 401.

## Convenciones de las fichas

Cada endpoint se documenta con la misma estructura: **Objetivo**, **Implementación**, **Solicitud**, **Entradas**, **Proceso**, **Salidas** y **Errores**. Cuando una categoría no aplique, se indica expresamente. Las rutas relativas de ficheros se muestran respecto al directorio del proyecto o al valor de `directorio`, según corresponda.

## Endpoints

### 1. `GET /reading_register/{linea}`

**Objetivo**  
Crear o actualizar el registro que utilizará la consulta de consumos de DATADIS.

**Implementación**  
Handler `generar_reading_register`; delega en `generar_y_guardar_reading_register` de `consulta_baisca_v30.py`.

**Solicitud**  
Parámetro de ruta `linea`: texto con ocho campos separados por comas: `CUPS,CIF,distributorCode,pointType,year_ultima,month_ultima,year_final,month_final`. Ejemplo: `ES0021000011297631SM,09404423E,8,5,2025,10,2025,10`. No tiene cuerpo.

**Entradas**  
La línea recibida en la ruta. No requiere ficheros de entrada.

**Proceso**  
Valida que haya ocho campos, convierte los años y meses a números y determina el último día del mes final para construir el registro de DATADIS.

**Salidas**  
Escribe `registers/reading_register.txt`. En éxito devuelve el resultado del módulo, que incluye el estado y la información del registro generado.

**Errores**  
Los errores de validación o escritura se devuelven como JSON con `status: "error"` y `detail`; el handler no los convierte explícitamente en códigos HTTP de error.

### 2. `GET /ejecutar`

**Objetivo**  
Consultar a DATADIS los consumos indicados en el registro de lectura.

**Implementación**  
Handler `ejecutar_script`; delega en `procesar_consumos` de `consulta_baisca_v30.py`.

**Solicitud**  
No tiene parámetros ni cuerpo.

**Entradas**  
`registers/reading_register.txt` y la configuración de DATADIS disponible para el proceso.

**Proceso**  
Procesa los registros y consulta los consumos correspondientes a cada CUPS.

**Salidas**  
Guarda las respuestas JSON en `responses/`, normalmente con nombres `CUPS_YYYY_MM_YYYY_MM.json`. También utiliza `logs/log_datadis.log`. En éxito devuelve `status` y `message`.

**Errores**  
Las excepciones se devuelven como JSON con `status: "error"` y `detail`; el handler no las convierte explícitamente en códigos HTTP de error.

### 3. `POST /ejecutar/calculo_autoconsumida`

**Objetivo**  
Consolidar por CUPS y mes los datos energéticos de los JSON de consumo para un rango de fechas.

**Implementación**  
Handler `calculo_autoconsumida_endpoint`; delega en `calcular_energia_autoconsumida` de `calculo_autoconsumida_v0.py`.

**Solicitud**  
Cuerpo JSON:
- `directorio` (cadena; por defecto `"responses"`).
- `mes_inicio` (entero), `anio_inicio` (entero), `mes_fin` (entero), `anio_fin` (entero).

**Entradas**  
Lee los ficheros `.json` del directorio indicado. Los registros de consumo utilizan campos como `date`, `cups`, `consumptionKWh`, `surplusEnergyKWh`, `generationEnergyKWh` y `selfConsumptionEnergyKWh`.

**Proceso**  
Filtra los registros por el rango de fechas, agrupa por CUPS y mes, suma los campos energéticos y calcula totales por usuario. No suma los campos de cosumo (para obtener la energía consumida es necesario sumar el consumo a el autoconsumo).

**Salidas**  
Escribe `energia_autoconsumida_{anio_inicio}_{mes_inicio:02d}_{anio_fin}_{mes_fin:02d}.csv` en el directorio indicado. La respuesta incluye `status`, `directorio`, `rango_fechas`, `usuarios_procesados` y `output_file`.

**Errores**  
Si el módulo devuelve `status: "error"`, la API responde HTTP 400. Las excepciones no previstas se devuelven como HTTP 500. Los meses fuera de rango pueden provocar un error de fecha durante el cálculo.

### 4. `GET /generate_daily_profile`

**Objetivo**  
Generar los perfiles mensuales medios por hora de un CUPS para días laborables y fines de semana.

**Implementación**  
Handler `generate_profile_endpoint`; delega en `generate_daily_profile` de `perfil_diario_v9.py`.

**Solicitud**  
Parámetro de consulta obligatorio `file_path`, normalmente el nombre de un JSON de consumo dentro de `responses/`. Ejemplo: `?file_path=ES0021000004444444ZZ_2025_01_2025_12.json`. No tiene cuerpo.

**Entradas**  
El JSON de consumo debe contener, al menos, `date`, `time` y `consumptionKWh`; puede incluir `selfConsumptionEnergyKWh`.

**Proceso**  
Calcula medias mensuales por hora y clasifica los registros según el día de la semana. Normaliza las horas que comienzan por `24` como las `00:00` del día siguiente. `total_consumption` suma `consumptionKWh` y `selfConsumptionEnergyKWh` cuando este campo está disponible.

**Salidas**  
Genera en el directorio del JSON `{ultimos_5_caracteres_CUPS}_weekday_profile.csv` y `{ultimos_5_caracteres_CUPS}_weekend_profile.csv`. La respuesta contiene `status`, `message`, `weekday_file` y `weekend_file`.

**Errores**  
Las excepciones se devuelven como JSON con `status: "error"` y `detail`; el handler no asigna códigos HTTP de error explícitos.

### 5. `GET /generate_daily_profile_extended`

**Objetivo**  
Generar perfiles mensuales por hora ampliados, con medias de consumo, autoconsumo y generación para laborables y fines de semana/festivos.

**Implementación**  
Handler `generate_extended_profile_endpoint`; delega en `generate_daily_profile_extended` de `perfil_diario_v9.py`.

**Solicitud**  
Parámetro de consulta obligatorio `file_path`. Acepta el nombre del JSON o una ruta relativa prefijada por `responses/`; no acepta rutas absolutas ni rutas que salgan de `responses/`. No tiene cuerpo.

**Entradas**  
JSON en `responses/` con una lista de registros que incluya `date`, `time` y `consumptionKWh`. `selfConsumptionEnergyKWh` y `surplusEnergyKWh` son opcionales. Acepta fechas `YYYY/MM/DD` o `YYYY-MM-DD` y horas `HH:MM`, `HH:MM:SS`, `24:00` o `24:00:00`.

**Proceso**  
Normaliza `24:00` a medianoche del día siguiente y clasifica sábados, domingos y festivos nacionales españoles como `weekend`. Calcula medias por mes y hora de `total_consumption_kWh` (`consumptionKWh + selfConsumptionEnergyKWh`), `self_consumption_kWh` y `total_generation` (`selfConsumptionEnergyKWh + surplusEnergyKWh`). Los campos opcionales ausentes o nulos se tratan como cero; las combinaciones mes/hora sin muestras se representan con `null`. No utiliza los CSV de perfiles mensuales existentes.

**Salidas**  
Escribe `responses/{ultimos_5_caracteres_CUPS}_day_profile_extended.json`. El JSON tiene las claves `weekday_consumption` y `weekend_consumption`, cada una con 12 objetos mensuales y 24 horas (`"0"`–`"23"`). La respuesta de la API incluye `status`, `message` y `output_file`.

**Errores**  
HTTP 404 si falta el fichero; HTTP 400 para rutas, JSON o datos inválidos; HTTP 500 ante errores de lectura/escritura.

### 6. `POST /perfiles/comunidad`

**Objetivo**  
Calcular perfiles comunitarios medios separados por tipo de día.

**Implementación**  
Handler `guardar_perfil_comunitario_endpoint`; utiliza `generar_perfil_comunitario` y `guardar_perfil_comunitario` de `perfil_comunidad_v1.py`.

**Solicitud**  
Cuerpo JSON con `directorio` (cadena; por defecto `"responses"`).

**Entradas**  
Ficheros `*_profile.csv` existentes en el directorio. Los nombres que contienen `weekday` o `weekend` determinan la categoría; los que no contienen ninguno se clasifican como `weekday`.

**Proceso**  
Agrupa los perfiles por tipo de día y calcula las medias comunitarias por mes y hora. Guarda el resultado en el mismo directorio de entrada.

**Salidas**  
Puede generar `perfil_comunitario_weekday.csv` y `perfil_comunitario_weekend.csv`. La respuesta incluye `status`, `archivos_procesados`, `archivos_procesados_weekday`, `archivos_procesados_weekend`, `archivos_guardados` y `mensaje`.

**Errores**  
Si el módulo devuelve un error (por ejemplo, no hay perfiles válidos), la API responde HTTP 400. Las excepciones no previstas responden HTTP 500.

### 7. `POST /perfiles/poruno_batch`

**Objetivo**  
Generar los perfiles poruno mensuales de cada usuario con respecto al perfil comunitario.

**Implementación**  
Handler `generar_poruno_batch`; delega en `generate_poruno_profiles_batch` de `perfil_diario_v9.py`.

**Solicitud**  
Cuerpo JSON:
- `directorio` (cadena; por defecto `"responses"`).
- `num_users_ce` (entero obligatorio).

**Entradas**  
En el directorio indicado: `perfil_comunitario_weekday.csv`, `perfil_comunitario_weekend.csv` y perfiles individuales `*_weekday_profile.csv` / `*_weekend_profile.csv`.

**Proceso**  
Calcula los coeficientes mensuales por usuario y tipo de día a partir de los perfiles individuales y comunitarios.

**Salidas**  
Genera ficheros `*_weekday_poruno.csv` y `*_weekend_poruno.csv` en el directorio indicado. La respuesta del módulo incluye `status`, `num_users_ce`, `users_processed`, `skipped_users`, `generated_files`, `errors` y `message`.

**Errores**  
`FileNotFoundError` y `ValueError` responden HTTP 400; las demás excepciones responden HTTP 500.

### 8. `POST /perfiles/poruno_8760`

**Objetivo**  
Expandir los perfiles poruno mensuales a una serie anual horaria por usuario.

**Implementación**  
Handler `generar_poruno_8760_batch_endpoint`; delega en `generate_poruno_8760_batch` de `perfil_diario_v9.py`.

**Solicitud**  
Cuerpo JSON:
- `directorio` (cadena; por defecto `"responses"`).
- `year` (entero; por defecto `2027`).

**Entradas**  
Ficheros `*_weekday_poruno.csv` y `*_weekend_poruno.csv`, además de `cups_list.csv` en el directorio indicado. El CSV de CUPS contiene `cups,cif`; se espera que no tenga cabecera.

**Proceso**  
Asocia el prefijo de usuario de los perfiles con el CUPS completo de `cups_list.csv`. Los perfiles incompletos o los CUPS sin correspondencia se omiten o se reportan como errores, respectivamente. La serie anual generada tiene 8760 horas.

**Salidas**  
Genera `{CUPS}_8760_poruno_{year}.txt`, con líneas `CUPS;hora(0001-8760);coeficiente` (seis decimales). La respuesta incluye `year`, `users_processed`, `skipped_users`, `generated_files`, `errors`, `global_sum_info` y `message`.

**Errores**  
`FileNotFoundError` y `ValueError` responden HTTP 400; las demás excepciones responden HTTP 500.

### 9. `POST /validar/suma_poruno`

**Objetivo**  
Comprobar si la suma de coeficientes de todos los usuarios es 1 en cada hora del año.

**Implementación**  
Handler `validar_suma_poruno_endpoint`; delega en `validar_suma_poruno_8760` de `perfil_diario_v9.py`.

**Solicitud**  
Cuerpo JSON:
- `directorio` (cadena; por defecto `"responses"`).
- `year` (entero; por defecto `2027`).

**Entradas**  
Ficheros `{CUPS}_8760_poruno_{year}.txt` del directorio indicado.

**Proceso**  
Suma los coeficientes por índice horario y calcula estadísticas de las diferencias respecto a 1.

**Salidas**  
Escribe `validacion_suma_poruno_{year}.txt`, con comentarios iniciales y una línea por hora con la diferencia entre 1 y la suma obtenida. La respuesta incluye `status`, `year`, `users_processed`, `num_users`, `output_file`, `stats`, `errors` y `message`; `stats` incluye horas totales, horas exactas, desviaciones y estadísticas de desviación.

**Errores**  
`FileNotFoundError` y `ValueError` responden HTTP 400; las demás excepciones responden HTTP 500.

### 10. `POST /corregir/suma_poruno_y_combinar`

**Objetivo**  
Corregir el último usuario para que la suma de coeficientes por hora sea 1 y combinar los ficheros.

**Implementación**  
Handler `corregir_y_combinar_poruno_endpoint`; delega en `corregir_y_combinar_poruno_8760` de `perfil_diario_v9.py`.

**Solicitud**  
Cuerpo JSON:
- `directorio` (cadena; por defecto `"responses"`).
- `year` (entero; por defecto `2027`).

**Entradas**  
Ficheros `{CUPS}_8760_poruno_{year}.txt` del directorio indicado.

**Proceso**  
Selecciona el último fichero de usuario según el orden aplicado por la función y ajusta sus coeficientes para compensar la suma de los demás. La corrección solo se acepta si el ajuste por hora está dentro de `[-0.0001, 0.0001]`.

**Salidas**  
Escribe `todos_usuarios_8760_poruno_{year}.txt` y modifica el fichero del último usuario. La respuesta incluye `status`, `year`, `num_users`, `last_user_corrected`, `other_users`, `combined_file`, `last_user_file`, `verification_errors` y `message`.

**Errores**  
Si el resultado del módulo indica `status: "error"`, la API responde HTTP 400. `FileNotFoundError` y `ValueError` responden HTTP 400; las demás excepciones responden HTTP 500. Un ajuste fuera del rango permitido no debe aplicarse.

### 11. `POST /pvgis/consulta_horaria`

**Objetivo**  
Consultar la generación horaria estimada a PVGIS y guardarla como serie indexada.

**Implementación**  
Handler `pvgis_consulta_horaria`; delega en `generar_pvgis_horario` de `PVGIS_consulta_horaria_v03.py`.

**Solicitud**  
Cuerpo JSON con:
- `lat` (43.38), `lon` (-2.58).
- `startyear` (2023), `endyear` (2023).
- `peakpower` (100), `angle` (21), `azimuth` (0), `loss` (14).
- `directorio` (cadena; por defecto `"responses"`).

**Entradas**  
Los parámetros enviados. No requiere ficheros previos; consulta `https://re.jrc.ec.europa.eu/api/v5_3/seriescalc`.

**Proceso**  
Lee la respuesta horaria de PVGIS, ajusta los valores mediante la lógica de horario local y convierte Wh a kWh/hora. La lógica de ajuste horario emplea índices fijos basados en 2023; el cálculo no es una conversión general de zona horaria para cualquier año.

**Salidas**  
Escribe `pvgis_indextime_spain.txt` en el directorio indicado, con filas `0001;valor_horario_en_kWh`. La respuesta incluye `status`, `output_file`, `hours`, `parameters` y `url`.

**Errores**  
Los errores de consulta o procesamiento se devuelven como HTTP 500.

### 12. `POST /pvgis/consulta_horaria/perfiles_medios`

**Objetivo**  
Calcular perfiles horarios medios de generación por usuario para verano e invierno.

**Implementación**  
Handler `pvgis_perfiles_medios_por_usuario`; delega en `calcular_perfiles_medios_por_usuario` de `pvgis_perfiles_medios.py`.

**Solicitud**  
Cuerpo JSON:
- `num_usuarios` (entero estricto mayor que cero; obligatorio).
- `year` (entero entre 1 y 9999; por defecto `2023`).
- `directorio` (cadena; por defecto `"responses"`).

**Entradas**  
`{directorio}/pvgis_indextime_spain.txt`, con filas consecutivas `0001;valor_horario_en_kWh`. Debe contener 8760 filas en año no bisiesto o 8784 en año bisiesto, y los índices deben ser consecutivos desde 0001.

**Proceso**  
Asigna las muestras a horas locales `Europe/Madrid` a partir de la medianoche local del 1 de enero y avanza por horas físicas. Verano comprende abril-septiembre; invierno, octubre-marzo. Promedia cada hora local por estación y divide el resultado por `num_usuarios`. En el cambio de otoño, las dos muestras de las 02:00 cuentan en el promedio de esa hora.

**Salidas**  
Genera `pvgis_spain_profile_summer_{year}.json` y `pvgis_spain_profile_winter_{year}.json` en el directorio del TXT. Cada fichero incluye año, número de usuarios, estación, meses, unidad y 24 valores horarios con número de muestras y generación media. La respuesta contiene `status`, `year`, `num_usuarios`, `fichero_origen` y `ficheros_generados`.

**Errores**  
Si falta el TXT o su estructura/datos son inválidos, responde HTTP 400. Las demás excepciones responden HTTP 500.

### 13. `POST /reparto/cups_list`

**Objetivo**  
Calcular la energía PVGIS asignada a cada usuario según sus coeficientes poruno y el porcentaje sobre la energía total.

**Implementación**  
Handler `calcular_cups_list_reparto_endpoint`; delega en `calcular_reparto_kwh_poruno` de `perfil_diario_v9.py`.

**Solicitud**  
Cuerpo JSON:
- `directorio` (cadena; por defecto `"responses"`).
- `year` (entero; por defecto `2026`).

**Entradas**  
`cups_list.csv` con cabecera y columnas `cups,cif`; `pvgis_indextime_spain.txt`; y ficheros `{CUPS}_8760_poruno_{year}.txt`.

**Proceso**  
Calcula `kwh_asignado = Σ_h (poruno_h × pvgis_h)` y `pct_kwh_total = (kwh_asignado / total_available_kwh) × 100`. Los valores PVGIS se interpretan en kWh por hora. Los CUPS sin fichero 8760 y los ficheros 8760 sin correspondencia se reportan por separado.

**Salidas**  
Escribe `cups_list_reparto.csv` con columnas `cups`, `cif`, `kwh_asignado` y `pct_kwh_total`. La respuesta incluye `status`, `cups_list_reparto`, `total_available_kwh`, `rows`, `missing_8760_files`, `unknown_8760_files` y `message`. Para usuarios sin coeficientes, `kwh_asignado` queda nulo.

**Errores**  
`FileNotFoundError` y `ValueError` responden HTTP 400; las demás excepciones responden HTTP 500.

### 14. `POST /reparto/proyeccion_autoconsumida`

**Objetivo**  
Calcular por hora la energía exportada, autoconsumida e importada para un JSON de consumo.

**Implementación**  
Handler `proyeccion_autoconsumida_endpoint`; delega en `calcular_proyeccion_autoconsumida` de `calculo_autoconsumida_v0.py`.

**Solicitud**  
Cuerpo JSON:
- `archivo_json` (por defecto, una ruta de ejemplo bajo `responses/`).
- `pvgis_file` (por defecto `responses/pvgis_indextime_spain.txt`).
- `coef_file` (por defecto una ruta de ejemplo a un fichero poruno; también puede ser un coeficiente constante expresado como texto numérico).
- `historial_file` (por defecto `responses/resultados_calculo_autoconsumida.json`).

**Entradas**  
JSON de consumo con registros horarios; serie PVGIS; y, salvo que `coef_file` sea un valor numérico, el fichero de coeficientes horarios. El JSON de consumo debe corresponder a un único año y seguir el patrón `CUPS_YYYY_MM_YYYY_MM.json`.

**Proceso**  
Interpreta las horas como tiempo local de `Europe/Madrid` y las convierte a índices físicos del año. Trata correctamente las horas `24:00` y las horas locales duplicadas por el cambio otoñal. Para cada hora coincidente, calcula generación como PVGIS por coeficiente y compara con el consumo (`consumptionKWh + selfConsumptionEnergyKWh`, considerando cero si falta el segundo campo) para acumular importación, exportación y autoconsumo. Un coeficiente numérico se aplica a todas las horas.

**Salidas**  
Añade el resultado al histórico indicado, que por defecto es `responses/resultados_calculo_autoconsumida.json`. La respuesta incluye `status`, `archivo_json`, `cups`, `year`, `horas_incluidas`, `horas_disponibles_json`, `missing_pvgis`, `missing_coef`, `primera_fecha`, `ultima_fecha`, `energia_exportada`, `energia_autoconsumida`, `energia_importada`, `pvgis_file`, `coef_file` y `historial_file`.

**Errores**  
Si el módulo devuelve `status: "error"`, la API responde HTTP 400. Las demás excepciones responden HTTP 500. No debe darse por válida una ejecución si faltan los ficheros PVGIS o los coeficientes requeridos.

## Funciones auxiliares relevantes

### `perfil_diario_v9.py`

- `prepare_dataframe`: prepara los registros horarios, normaliza `24:00` y clasifica laborables/fines de semana.
- `_load_monthly_profile` y `_save_monthly_profile`: leen y escriben perfiles mensuales.
- `_create_yearly_index`: crea el índice anual de 8760 horas.
- `_spanish_national_holidays`: obtiene los festivos nacionales españoles utilizados en la clasificación de días.
- `_build_poruno_yearly_series`: expande los perfiles mensuales a una serie anual.

### `perfil_comunidad_v1.py`

- `obtener_perfiles_validos`: localiza perfiles individuales `*_profile.csv`.
- `generar_perfil_comunitario`: calcula medias por mes y tipo de día.
- `guardar_perfil_comunitario`: persiste los perfiles comunitarios en CSV.

## Reglas de negocio y flujo recomendado

- Los perfiles mensuales utilizan 12 meses y 24 columnas horarias, además de la columna del mes.
- Los ficheros anuales poruno representan 8760 horas; la expansión excluye el 29 de febrero.
- La suma objetivo de coeficientes de los usuarios es 1 por hora.
- La corrección del último usuario solo se permite cuando todos los ajustes están dentro de `[-0.0001, 0.0001]`.
- Los sábados, domingos y festivos nacionales se clasifican como fines de semana en los flujos que aplican el calendario nacional.
- El reparto y la proyección requieren unidades horarias coherentes: los valores PVGIS se manejan en kWh por hora.

Flujo habitual de perfiles y reparto:

1. Consultar consumos con `/reading_register/{linea}` y `/ejecutar`.
2. Generar perfiles por CUPS con `/generate_daily_profile` o `/generate_daily_profile_extended`.
3. Crear los perfiles comunitarios con `/perfiles/comunidad`.
4. Generar poruno mensual y anual con `/perfiles/poruno_batch` y `/perfiles/poruno_8760`.
5. Validar y, si procede, corregir/combinar con `/validar/suma_poruno` y `/corregir/suma_poruno_y_combinar`.
6. Consultar PVGIS con `/pvgis/consulta_horaria`; opcionalmente obtener medias estacionales con `/pvgis/consulta_horaria/perfiles_medios`.
7. Calcular el reparto o la proyección con `/reparto/cups_list` o `/reparto/proyeccion_autoconsumida`.
8. Calcular el resumen mensual de energía con `/ejecutar/calculo_autoconsumida`.

## Pruebas relacionadas

- `tests/test_calculo_autoconsumida_v0.py`: escenarios del cálculo de autoconsumo y normalización de horas.
- `tests/test_generate_daily_profile_extended.py`: perfiles ampliados, clasificación, valores ausentes y validaciones de entrada.
- `tests/test_pvgis_profiles.py`: perfiles medios estacionales de PVGIS.

