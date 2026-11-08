# Prompt de desarrollo: API DATADIS

## Endpoint `POST /consultar_consumos_por_grupos`

Implementa en la aplicación FastAPI un endpoint llamado
`POST /consultar_consumos_por_grupos` para consultar secuencialmente los
consumos DATADIS de los CUPS de `responses/cups_list.csv`.

### Contexto y límites

- Revisa primero `api36.py`, `consultar_consumos_cups_api.py`, los módulos
  llamados por la API y las pruebas existentes.
- Conserva el comportamiento del script CLI y de los endpoints actuales.
- Implementa el endpoint dentro de la API. No delegues la funcionalidad al
  script CLI ni dupliques innecesariamente la lógica de negocio que ya ofrece
  la API.
- Limita los cambios al endpoint, su integración y las pruebas necesarias.
- No realices consultas reales a DATADIS durante el desarrollo o las pruebas.

### Entrada y autenticación

- Lee siempre el CSV `responses/cups_list.csv`, con las columnas `cups` y
  `cif`.
- Antes de consultar, valida que el CSV se pueda leer, que su cabecera sea
  exactamente `cups,cif` y esté en ese orden, que contenga registros, que sus
  valores no estén vacíos y que no haya CUPS repetidos. Los CIF pueden
  repetirse: la unicidad se valida por CUPS, no por CIF. Informa claramente de
  errores de entrada.
- Protege el endpoint con el mecanismo de autenticación ya utilizado por la
  aplicación. Reutiliza sus credenciales y configuración; no solicites ni
  expongas credenciales en el cuerpo de la petición, las respuestas o los
  registros.

### Parámetros

Define un modelo de petición JSON con estos parámetros configurables:

| Parámetro | Predeterminado | Validación |
|---|---:|---|
| `distributor` | `8` | Entero no negativo |
| `CodepointType` | `5` | Entero no negativo |
| `ano_de_inicio` | `2025` | Entero mayor o igual que 1 |
| `mes_inicio` | `1` | Entero de 1 a 12 |
| `ano_final` | `2025` | Entero mayor o igual que 1 |
| `mes_final` | `12` | Entero de 1 a 12 |
| `threshold` | `200` | Entero no negativo; el criterio es estrictamente mayor |
| `output_file` | `cups_consultation_results.json` | Nombre de archivo, no una ruta |

Valida antes de iniciar las consultas que el período inicial no sea posterior
al período final. El endpoint debe operar en `responses/`; no añadas un
parámetro para cambiar ese directorio.

Para cada fila, construye exactamente la línea:

```text
<CUPS>,<cif>,<distributor>,<CodepointType>,<ano_de_inicio>,<mes_inicio>,<ano_final>,<mes_final>
```

### Protección de la salida

- Resuelve el fichero de informe dentro de `responses/`.
- Si ya existe antes de empezar, no configures ni ejecutes consultas, no leas
  los CUPS para procesarlos ni sobrescribas el fichero. Devuelve un evento
  `already_exists`.
- Al crear el informe, evita sobrescribir una salida creada concurrentemente.
- Antes de configurar o ejecutar la consulta de cada CUPS, comprueba si ya
  existe su JSON de respuesta para el período solicitado. Si existe, omite ese
  CUPS con estado `skipped_existing`, informa del nombre del fichero y no
  modifiques su contenido.
- No atribuyas a la consulta actual resultados JSON antiguos. Para cada CUPS
  que sí se consulte, comprueba que el fichero esperado se haya creado durante
  esa consulta antes de leerlo.

### Flujo secuencial y progreso

Para cada CUPS, en el orden del CSV:

1. Emite un evento de progreso `processing` con el CUPS, el total y el número
   completado hasta ese momento.
2. Configura la consulta usando la función de negocio ya llamada por
   `GET /reading_register/{linea}` y comprueba que la configuración terminó
   correctamente.
3. Solo entonces ejecuta la función ya llamada por `GET /ejecutar`.
4. Examina el resultado de ese CUPS antes de configurar el siguiente.
5. Emite un evento de progreso `completed` que incluya el estado y el número
   de registros, si se pudo contar.

Impide que una consulta por grupos se intercale con las operaciones
individuales de configuración/ejecución que comparten el estado de DATADIS.
Usa el mecanismo de sincronización compartido por esos endpoints.

Devuelve la respuesta como `application/x-ndjson`, con un objeto JSON por
línea. Al terminar, emite un evento `summary` con el período, el umbral, el
resumen y los resultados por CUPS. Documenta el endpoint, sus parámetros,
errores y formato de respuesta en OpenAPI.

### Clasificación y errores

- Cuenta los elementos de la lista JSON correspondiente al CUPS y período
  actual.
- Clasifica como `with_readings` solo los resultados con más registros que
  `threshold`.
- Clasifica los resultados con `threshold` registros o menos como
  `insufficient_readings`.
- Informa los fallos por CUPS como `error`, separando su categoría y un
  mensaje útil. No los confundas con la ausencia de lecturas.
- Trata como errores la configuración fallida, la ejecución fallida, la falta
  de archivo, JSON inválido, una estructura de respuesta inesperada o un
  resultado que no se haya actualizado.
- No devuelvas detalles sensibles ni incluyas credenciales en los mensajes.
- Continúa con el siguiente CUPS cuando un fallo individual pueda registrarse
  de forma segura; errores globales de entrada o validación deben impedir que
  empiecen las consultas.

El informe JSON debe contener:

- el período consultado;
- `record_threshold_exclusive`;
- `summary` con `processed`, `with_readings`, `insufficient_readings` y
  `errors` y `skipped_existing`;
- `results`, con un resultado único por CUPS, su estado, el número de
  registros cuando esté disponible y el error cuando corresponda.

### Pruebas

Añade o actualiza pruebas unitarias simulando las funciones de consulta, sin
acceso a DATADIS. Comprueba:

- valores predeterminados y parámetros personalizados;
- formato de la línea enviada y orden secuencial de procesamiento;
- progreso `processing`/`completed` y resumen NDJSON;
- validación de meses, años y orden del período antes de cualquier consulta;
- lectura y validación del CSV, incluidas columnas ausentes, campos vacíos y
  CUPS duplicados;
- umbral estricto: `threshold` registros son insuficientes y
  `threshold + 1` son lecturas;
- errores por CUPS y continuación del lote;
- JSON de respuesta ya existente: omisión, sin llamadas a DATADIS y sin
  modificar su contenido;
- ausencia, invalidez o falta de actualización del archivo de respuesta;
- fichero de salida existente, sin consultas ni modificaciones;
- autenticación, documentación OpenAPI y tipo de contenido NDJSON.

Ejecuta las pruebas específicas y las comprobaciones de sintaxis/estilo
disponibles en el proyecto. Informa de los archivos modificados y de los
resultados de validación.

## Endpoint `POST /generate_daily_profile_batch`

Añade a la API FastAPI el endpoint `POST /generate_daily_profile_batch` para
generar los perfiles diarios de los CUPS incluidos en
`responses/cups_list.csv`.

### Revisión y reutilización

- Antes de modificar el código, revisa `POST /generate_daily_profile`, su
  generador `generate_daily_profile`, los modelos, las pruebas existentes y
  las convenciones de nombres y rutas del proyecto.
- Reutiliza `generate_daily_profile` para cada archivo de consumo. No uses
  `generate_daily_profile_extended`: este endpoint debe generar los dos CSV
  existentes de perfiles `weekday` y `weekend`.
- Conserva el comportamiento predeterminado del endpoint individual.

### Selección de entradas

- Lee los CUPS de `responses/cups_list.csv`. Comprueba que el CSV se puede leer,
  contiene la columna `cups` y tiene registros con valores no vacíos y sin
  duplicados.
- Para cada CUPS de la lista, busca en `responses/` archivos de consumo con el
  formato:
  ```text
  <CUPS>_<año_inicio>_<mes_inicio>_<año_final>_<mes_final>.json
  ```
- El período se obtiene del nombre del archivo. El endpoint no debe requerir
  parámetros de año o mes ni un cuerpo de petición.
- Acepta los formatos de mes con uno o dos dígitos, siempre que sean meses
  válidos del 1 al 12.
- Procesa únicamente CUPS de la lista que tengan un archivo correspondiente;
  no proceses archivos de otros usuarios.
- Si no existe archivo para un CUPS, devuélvelo con estado `missing_input`.
- Si hay varios archivos posibles para un CUPS, no elijas uno arbitrariamente:
  informa la ambigüedad y marca ese CUPS como error.

### Generación y protección de archivos

- Procesa los usuarios secuencialmente mediante `generate_daily_profile`.
- No consultes DATADIS ni ningún otro servicio externo; usa los archivos de
  consumo disponibles.
- Mantén las rutas, los formatos CSV y los nombres de salida existentes:
  `<últimos_5_caracteres_CUPS>_weekday_profile.csv` y
  `<últimos_5_caracteres_CUPS>_weekend_profile.csv`.
- Detecta antes de generar colisiones de nombres de salida entre CUPS. No
  proceses los CUPS afectados.
- No sobrescribas CSV de perfiles existentes. Informa el conflicto por CUPS y
  continúa con los demás cuando sea seguro.
- Un error al procesar un CUPS no debe detener el lote. Devuelve para cada
  usuario su CUPS, estado, nombre de entrada, nombres de salida cuando se
  generen y un mensaje claro cuando haya error.

### Endpoint, respuesta y seguridad

- Registra `POST /generate_daily_profile_batch` en FastAPI y usa el mismo
  mecanismo de autenticación que los demás endpoints.
- Documenta en OpenAPI el propósito del endpoint, que no requiere parámetros
  ni cuerpo, los estados de resultado y los errores globales.
- Devuelve un resumen con `total`, `generated`, `missing_input` y `errors`,
  además de un resultado individual por cada CUPS del CSV.
- No incluyas credenciales, secretos ni datos sensibles en las respuestas o
  registros.

### Pruebas y validación

Añade pruebas simuladas, sin consultas externas, para cubrir:

- procesamiento solo de CUPS incluidos en el CSV y con archivo disponible;
- formatos de nombres de archivo con meses de uno y dos dígitos;
- CSV sin columna `cups`, vacío, con CUPS vacío o duplicado;
- archivos de entrada ausentes o ambiguos;
- reutilización de `generate_daily_profile` y continuación tras errores;
- colisiones de los nombres de salida por sufijo CUPS;
- protección de perfiles CSV existentes frente a sobrescritura;
- resumen y resultados individuales;
- endpoint autenticado y ausencia de cuerpo requerido en OpenAPI;
- conservación del comportamiento del endpoint individual.

Ejecuta las pruebas específicas, las comprobaciones de sintaxis y
`git diff --check`. Informa de los archivos modificados y los resultados de
validación.
