# Instrucciones para preparar los entornos de trabajo

## 1) Crear la carpeta de entornos

```bash
mkdir -p <directorio_de_entornos>
```

Los bloqueos de versiones se guardan en el directorio `requirements/` del proyecto:

```text
requirements/requirements-dash-lock.txt
requirements/requirements-api-lock.txt
```

Genéralos en el servidor anterior, después de comprobar que los entornos funcionan correctamente:

```bash
cd <directorio_del_proyecto>
source <directorio_de_entornos>/.dash/bin/activate
python -m pip freeze --all > requirements/requirements-dash-lock.txt
deactivate

source <directorio_de_entornos>/.api/bin/activate
python -m pip freeze --all > requirements/requirements-api-lock.txt
deactivate
```

En este equipo usamos Python 3.10.12 en los dos entornos, igual que en producción:

```bash
PYTHON_BIN=<ruta_al_python_3.10.12>
```

## 2) Crear el entorno del dashboard (.dash)

```bash
$PYTHON_BIN -m venv <directorio_de_entornos>/.dash
```

## 3) Activar el entorno del dashboard

```bash
source <directorio_de_entornos>/.dash/bin/activate
```

## 4) Verificar la versión de Python del entorno del dashboard

```bash
python --version
    Python 3.10.12
which python


## 5) Instalar dependencias del dashboard

```bash
cd <directorio_del_proyecto>
python3 -m pip install -r requirements-dash-lock.txt
```

Ejecuta este paso después de copiar el archivo de bloqueo generado en el ordenador anterior.

desplegar el fichero config_datadis.ini

## 6) Arrancar la app del dashboard

```bash
cd <directorio_del_proyecto>
source <directorio_de_entornos>/.dash/bin/activate
streamlit run dashboard/app.py --server.port 8501
```

Abre en el navegador:

```text
http://localhost:8501
```

---

## 7) Crear el entorno de FastAPI (.api)

```bash
$PYTHON_BIN -m venv <directorio_de_entornos>/.api
```

## 8) Activar el entorno de FastAPI

```bash
source <directorio_de_entornos>/.api/bin/activate
```

## 9) Verificar la versión de Python del entorno de FastAPI

```bash
python --version
    Python 3.10.12
which python


## 10) Instalar dependencias de FastAPI

```bash
cd <directorio_del_proyecto>
python -m pip install -r requirements/requirements-api-lock.txt
```

Ejecuta este paso después de copiar el archivo de bloqueo generado en el ordenador anterior.
El archivo generado con `pip freeze --all` fija también las versiones de `pip`,
`setuptools` y `wheel`; por tanto, no es necesario instalarlas con versiones
separadas en este paso.

## 11) Ejemplo de arrancar la API localmente

```bash
cd <directorio_del_proyecto>
source <directorio_de_entornos>/.api/bin/activate
uvicorn api36:app --host 0.0.0.0 --port 8000 --reload
```

Abre en el navegador:

```text
http://localhost:8000/docs
```

---

## 12) Recomendación para evitar conflictos

No mezcles dependencias en el mismo entorno. Mantén dos entornos separados:

- `.dash` para Streamlit
- `.api` para FastAPI

Esto evita incompatibilidades de versiones y hace más fácil desplegar en el servidor.

## 13) Recomendación para el servidor

Lo ideal es desplegar cada parte con su propio entorno y, si es posible, usar Docker para que la versión de Python y las librerías sean reproducibles en producción.

## 14) Regla práctica

Si el proyecto en el servidor necesita simultáneamente dashboard y API, conviene desplegar ambos con la misma versión de Python y usando sus requirements separados.

## 15) Instalar y desplegar File Browser

### Instalar el binario

Instala `curl` y ejecuta el instalador oficial de File Browser:

```bash
sudo apt install curl
curl -fsSL https://raw.githubusercontent.com/filebrowser/get/master/get.sh | bash
```

Comprueba que se haya instalado correctamente:

```bash
filebrowser version
which filebrowser
```

### Inicializar la base de datos

Indica un directorio para los datos de File Browser y crea la base de datos:

```bash
mkdir -p <directorio_de_filebrowser>
filebrowser -d <directorio_de_filebrowser>/filebrowser.db config init
```

Usa siempre la opción `-d` con la misma ruta para que los comandos y el servidor utilicen esa base de datos.

### Configurar el servicio

Detén File Browser antes de cambiar su configuración. Define el directorio que podrá gestionar, el puerto y la dirección de escucha:

```bash
filebrowser -d <directorio_de_filebrowser>/filebrowser.db config set --root <directorio_que_filebrowser_gestiona>
filebrowser -d <directorio_de_filebrowser>/filebrowser.db config set --port 8080
filebrowser -d <directorio_de_filebrowser>/filebrowser.db config set --address 0.0.0.0
filebrowser -d <directorio_de_filebrowser>/filebrowser.db config cat
```

El valor `0.0.0.0` permite conexiones a través de todas las interfaces de red. Limita el acceso mediante el cortafuegos o un proxy inverso y no expongas el servicio directamente a Internet sin protegerlo.

Comprueba que el usuario que ejecutará File Browser tenga permisos sobre su directorio de datos y sobre el directorio raíz configurado.

### Crear el usuario administrador

Reemplaza los marcadores por un nombre de usuario y una contraseña segura:

```bash
filebrowser -d <directorio_de_filebrowser>/filebrowser.db users add <usuario_administrador> <contraseña_segura> --perm.admin
```

### Arrancar el servidor

Para ejecutarlo en primer plano:

```bash
filebrowser -d <directorio_de_filebrowser>/filebrowser.db
```

Como alternativa, puedes iniciarlo en segundo plano desde el directorio donde quieras guardar el registro:

```bash
cd <directorio_de_trabajo>
nohup filebrowser -d <directorio_de_filebrowser>/filebrowser.db > filebrowser.log 2>&1 &
```

Para que un watchdog compruebe y reinicie el servicio periódicamente, instala o configura el script correspondiente y añade una tarea de cron:

```bash
chmod +x <ruta_al_script_watchdog>
crontab -e
```

Añade esta línea al crontab para ejecutar el watchdog cada hora, por ejemplo en el minuto 56:

```cron
56 * * * * <ruta_al_script_watchdog>
```

Configura el watchdog para que utilice la misma base de datos y los permisos adecuados. Asegúrate de que compruebe si File Browser ya está activo antes de iniciarlo, para evitar procesos duplicados.
