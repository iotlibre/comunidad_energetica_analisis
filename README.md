# Análisis de consumos y perfiles energéticos

Herramientas para consultar consumos eléctricos de DATADIS y procesar datos
energéticos de una comunidad. El proyecto incluye una API REST con FastAPI y un
dashboard interactivo con Streamlit.

## Funcionalidad

- Consulta consumos DATADIS para uno o varios CUPS.
- Calcula energía autoconsumida y genera perfiles horarios individuales y
  comunitarios.
- Procesa y valida coeficientes horarios poruno, consulta perfiles solares de
  PVGIS y calcula repartos y proyecciones energéticas.
- Permite explorar consumos, datos de autoconsumo, métricas y perfiles desde
  el dashboard. En «Datos disponibles» y «Energía» se puede elegir `responses/`
  o un subdirectorio `responses_*`.

## Documentación

- [PROMPT_SISTEMA_PORUNO_8760.md](./PROMPT_SISTEMA_PORUNO_8760.md): referencia
  del sistema de perfiles energéticos y de los endpoints de la API, sus
  entradas, procesos, salidas y validaciones.
- [prompt_consultar_consumos_por_grupos.md](./prompt_consultar_consumos_por_grupos.md):
  especificaciones para desarrollar los endpoints de consulta DATADIS por
  grupos y generación por lotes de perfiles diarios.
- [prompt_dashboard_perfiles_energeticos.md](./prompt_dashboard_perfiles_energeticos.md):
  descripción de las páginas del dashboard, sus datos de origen y el cálculo y
  presentación de sus visualizaciones.
- [instrucciones_entornos_dashboard_api.md](./instrucciones_entornos_dashboard_api.md):
  preparación de entornos Python separados para Streamlit y FastAPI,
  instalación de dependencias y comandos para ejecutar ambas aplicaciones.

## Ejecución local

Consulta las [instrucciones de entorno y ejecución](./instrucciones_entornos_dashboard_api.md)
para configurar las dependencias. Desde la raíz del proyecto:

```bash
streamlit run dashboard/app.py --server.port 8501
```

Para iniciar la API localmente:

```bash
uvicorn api36:app --host 0.0.0.0 --port 8000 --reload
```
