# Instrucciones para preparar los entornos de trabajo

## 1) Crear la carpeta de entornos

```bash
mkdir -p /home/oscar/sw/envs
```

Los bloqueos de versiones se guardan en el directorio `requirements/` del proyecto:

```text
requirements/requirements-dash-lock.txt
requirements/requirements-api-lock.txt
```

Genéralos en el ordenador anterior, después de comprobar que los entornos funcionan correctamente:

```bash
cd /home/oscar/Dropbox/22_IoE/_01_i+D/circulink/sw/sw/datadis_hitorico
source /home/oscar/sw/envs/.dash/bin/activate
python -m pip freeze --all > requirements/requirements-dash-lock.txt
deactivate

source /home/oscar/sw/envs/.api/bin/activate
python -m pip freeze --all > requirements/requirements-api-lock.txt
deactivate
```

Después, copia esos dos archivos al mismo directorio del nuevo ordenador.

En este equipo usamos Python 3.10.12 en los dos entornos, igual que en producción:

```bash
PYTHON_BIN=/home/oscar/.pyenv/versions/3.10.12/bin/python
```

## 2) Crear el entorno del dashboard (.dash)

```bash
$PYTHON_BIN -m venv /home/oscar/sw/envs/.dash
```

## 3) Activar el entorno del dashboard

```bash
source /home/oscar/sw/envs/.dash/bin/activate
```

## 4) Verificar la versión de Python del entorno del dashboard

```bash
python --version
    Python 3.10.12
which python
    /home/oscar/sw/envs/.dash/bin/python
```

## 5) Instalar dependencias del dashboard

```bash
cd /home/oscar/Dropbox/22_IoE/_01_i+D/circulink/sw/sw/datadis_hitorico
python -m pip install -r requirements/requirements-dash-lock.txt
```

Ejecuta este paso después de copiar el archivo de bloqueo generado en el ordenador anterior.

## 6) Crear la estructura mínima del dashboard

```bash
mkdir -p /home/oscar/Dropbox/22_IoE/_01_i+D/circulink/sw/sw/datadis_hitorico/dashboard/pages \
         /home/oscar/Dropbox/22_IoE/_01_i+D/circulink/sw/sw/datadis_hitorico/dashboard/components \
         /home/oscar/Dropbox/22_IoE/_01_i+D/circulink/sw/sw/datadis_hitorico/dashboard/utils
```

## 7) Crear la primera app mínima de Streamlit

```bash
cat > /home/oscar/Dropbox/22_IoE/_01_i+D/circulink/sw/sw/datadis_hitorico/dashboard/app.py <<'PY'
import streamlit as st
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
responses_dir = BASE / "responses"

st.set_page_config(page_title="Dashboard Energético", layout="wide")
st.title("Dashboard de perfiles energéticos")

if responses_dir.exists():
    files = sorted(p.name for p in responses_dir.iterdir() if p.is_file())
    st.success(f"Directorio detectado: {responses_dir}")
    st.write(f"Ficheros encontrados: {len(files)}")
    selected = st.selectbox("Selecciona un fichero", files if files else ["No hay ficheros"])
    st.write("Archivo seleccionado:", selected)
else:
    st.warning(f"No se encontró el directorio: {responses_dir}")
PY
```

## 8) Arrancar la app del dashboard

```bash
cd /home/oscar/Dropbox/22_IoE/_01_i+D/circulink/sw/sw/datadis_hitorico
source /home/oscar/sw/envs/.dash/bin/activate
streamlit run dashboard/app.py --server.port 8501
```

Abre en el navegador:

```text
http://localhost:8501
```

---

## 10) Crear el entorno de FastAPI (.api)

```bash
$PYTHON_BIN -m venv /home/oscar/sw/envs/.api
```

## 11) Activar el entorno de FastAPI

```bash
source /home/oscar/sw/envs/.api/bin/activate
```

## 12) Verificar la versión de Python del entorno de FastAPI

```bash
python --version
    Python 3.10.12
which python
    /home/oscar/sw/envs/.api/bin/python
```

## 13) Instalar dependencias de FastAPI

```bash
cd /home/oscar/Dropbox/22_IoE/_01_i+D/circulink/sw/sw/datadis_hitorico
python -m pip install -r requirements/requirements-api-lock.txt
```

Ejecuta este paso después de copiar el archivo de bloqueo generado en el ordenador anterior.
El archivo generado con `pip freeze --all` fija también las versiones de `pip`,
`setuptools` y `wheel`; por tanto, no es necesario instalarlas con versiones
separadas en este paso.

## 14) Alternativa sin archivo de bloqueo

```bash
cat > /home/oscar/Dropbox/22_IoE/_01_i+D/circulink/sw/sw/datadis_hitorico/requirements_api.txt <<'EOF'
fastapi
uvicorn
pydantic
requests
pandas
EOF

python -m pip install -r requirements_api.txt
```

Verificar la instalación:

```bash
python --version
    Python 3.10.12

python -c "import fastapi, uvicorn; print('FastAPI y Uvicorn OK')"
```

## 15) Ejemplo de arrancar la API localmente

```bash
cd /home/oscar/Dropbox/22_IoE/_01_i+D/circulink/sw/sw/datadis_hitorico
source /home/oscar/sw/envs/.api/bin/activate
uvicorn api36:app --host 0.0.0.0 --port 8000 --reload
```

Abre en el navegador:

```text
http://localhost:8000/docs
```

---

## 16) Recomendación para evitar conflictos

No mezcles dependencias en el mismo entorno. Mantén dos entornos separados:

- `.dash` para Streamlit
- `.api` para FastAPI

Esto evita incompatibilidades de versiones y hace más fácil desplegar en el servidor.

## 17) Recomendación para el servidor

Lo ideal es desplegar cada parte con su propio entorno y, si es posible, usar Docker para que la versión de Python y las librerías sean reproducibles en producción.

## 18) Regla práctica

Si el proyecto en el servidor necesita simultáneamente dashboard y API, conviene desplegar ambos con la misma versión de Python y usando sus requirements separados.
