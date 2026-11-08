''' Notas
tipos de varialbles en python
https://www.codigofuente.org/variables-en-python/
Para ver lo que se esta enviando al servidor
mosquitto_sub -d -h  data-test.endef.com -p 1883 -u xxxxxxx -P xxxxxxxx -t "datadis/#"
'''
#!/usr/bin/env python
import configparser
import json
from datetime import datetime
from datetime import timedelta
from datetime import date
import calendar
# import pickle
import http.client
import os
import time
import requests
import logging
from logging.handlers import RotatingFileHandler


''' Niveles de logging
Para obtener _TODO_ el detalle: level=logging.DEBUG
Para comprobar los posibles problemas level=logging.WARNINg
Para comprobar el funcionamiento: level=logging.INFO
'''
logging.basicConfig(
        level=logging.DEBUG,
        handlers=[RotatingFileHandler('./logs/log_datadis.log', maxBytes=10000000, backupCount=4)],
        format='%(asctime)s %(levelname)s %(message)s',
        datefmt='%m/%d/%Y %I:%M:%S %p')

parser = configparser.ConfigParser()
key_path = "registers/temporal_key.txt"

''' ver reading_register con formato json
cat registers/reading_register.txt | python -m json.tool
'''
def abrir_reading_register():
    rr_path = "registers/reading_register.txt"
    lectura=open(rr_path, "r", encoding="utf-8")
    data = json.load(lectura)
    lectura.close()
    return data


'''datos necesarios para la consulta
---------------------------------
cupsQ="ES00311041XXXXXXXXXX0F
cifQ = "XXXXXXX4B
startDateQ="2022/04/06"
endDateQ="2022/04/09"
'''
def consulta_de_consumos(x):
    logging.debug("++++ Inicio de la consulta de consumos")

    cupsQ = list(x.keys())[0]
    logging.debug(cupsQ)

    cifQ = x[cupsQ]["cif"]
    distributorCodeQ = x[cupsQ]["distributorCode"]
    pointTypeQ = x[cupsQ]["pointType"]

    last_date_r = x[cupsQ]["ultima"] # last date registered
    # ultima fecha del registro en formato datetime
    star_date_d = date(last_date_r["year"],
                  last_date_r["month"],
                  last_date_r["day"])

    # Damos formato a startDateQ
    # Se parte de star_date_d
    star_day_str = str(star_date_d.day)
    if (star_date_d.day <= 9):
        star_day_str = "0" + str(star_date_d.day)
    star_month_str = str(star_date_d.month)
    if (star_date_d.month <= 9):
        star_month_str = "0" + str(star_date_d.month)
    # startDateQ = str(star_date_d.year) + "/" + star_month_str + "/" + star_day_str
    startDateQ = str(star_date_d.year) + "/" + star_month_str


    end_date_rr = x[cupsQ]["final"] # end date de reading_register
    end_date_d = date(end_date_rr["year"],
                  end_date_rr["month"],
                  end_date_rr["day"])
    
    # Damos formato a endDateQ
    # Se parte de end_date_d
    end_day_str = str(end_date_d.day)
    if (end_date_d.day <= 9):
        end_day_str = "0" + str(end_date_d.day)
    end_month_str = str(end_date_d.month)
    if (end_date_d.month <= 9):
        end_month_str = "0" + str(end_date_d.month)
    # endDateQ = str(end_date_d.year) + "/" + end_month_str + "/" + end_day_str
    endDateQ = str(end_date_d.year) + "/" + end_month_str


    url = "http://datadis.es/api-private/api/get-consumption-data?authorizedNif="
    url += cifQ
    url += "&cups="
    url += cupsQ
    url += "&distributorCode="
    url += distributorCodeQ
    url += "&startDate="
    url += startDateQ
    url += "&endDate="
    url += endDateQ
    url += "&measurementType=0&pointType="
    url += pointTypeQ

    logging.info(url)

    # Consulta de los consumos
    payload={}

    # key_path = "registers/temporal_key.txt"
    key_file_open=open(key_path, "r", encoding="utf-8")
    key_file_red = key_file_open.read()
    key_file_open.close()
    logging.debug(key_file_red)

    headers = {  'Authorization': 'Bearer ' + key_file_red
    }

    response = requests.request("GET", url, headers=headers, data=payload)
    response_text = response.text
    return response_text

def pedir_nuevo_key():
    logging.debug('El Key no se ha obtenido hoy. Pedimos un nuevo key')
    datadis_login = parser.get('datadis','datadis_login')
    datadis_password = parser.get('datadis','datadis_password')

    conn = http.client.HTTPSConnection("datadis.es")
    payload =  "username="
    payload += datadis_login
    payload += "&password="
    payload += datadis_password
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
            }
    conn.request("POST", "/nikola-auth/tokens/login", payload, headers)
    res = conn.getresponse()
    data = res.read()
    logging.debug(data.decode("utf-8"))
    key = data.decode("utf-8")
    key_f=open(key_path, "w", encoding="utf-8")
    key_f.write(key)
    key_f.close()


'''Si el key no es de hoy pido un nuevo key
date.today()
<class 'datetime.date'>
'''
def obtener_key():
    try:
        m_time = os.path.getmtime(key_path)
        # logging.debug(type(m_time)) # <class 'float'>
    except:
        m_time =1.1
    # logging.debug('time_m: ' + str (m_time))

    today = date.today()
    m_file_time = date.fromtimestamp(m_time)
    # logging.debug('m_file_time: ')
    # logging.debug(m_file_time) # 1970-01-01
    # logging.debug(type(m_file_time)) # <class 'datetime.date'>
    if (date.today() != m_file_time):
        pedir_nuevo_key()


def guardar_response(cups, response_text, start_date=None, end_date=None):
    """Guarda la respuesta de consumos en un fichero.

    Si se proporcionan `start_date` y `end_date` (ambos objetos
    datetime.date), el nombre del fichero incorpora año/mes de esas
    fechas en lugar del timestamp actual. El formato es:

        CUPS_YYYY_MM_YYYY_MM.json

    Ejemplo:
        ES0021000006766354KG_2025_01_2025_12.json

    Los parámetros `start_date` y `end_date` se extraen del
    `reading_register.txt` en `procesar_consumos`.
    """
    if not os.path.exists('responses'):
        os.makedirs('responses')

    if start_date and end_date:
        # Formatear sólo año y mes, asegurando dos dígitos para el mes
        start_str = f"{start_date.year}_{start_date.month:02d}"
        end_str = f"{end_date.year}_{end_date.month:02d}"
        filename = f"responses/{cups}_{start_str}_{end_str}.json"
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"responses/{cups}_{timestamp}.json"

    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(response_text)
        logging.info(f"Respuesta guardada en: {filename}")
    except Exception as e:
        logging.error(f"Error al guardar respuesta: {e}")

def procesar_consumos():
    """
    Procesa los consumos de todos los usuarios registrados.
    
    Lee los datos de consumo de la API de datadis para cada usuario
    en el reading_register y guarda las respuestas en ficheros JSON.
    """
    #************************
    #** LOGICA DE PROCESO ***
    #************************
    # Credenciales de datadis
    parser.read('config_datadis.ini')

    obtener_key()

    '''Cada x en reading_register_
    ----------------------------
    reading_register es un fichero con los datos de cada usuario que incluye los datos de la última lectura valida
    El formato es: Lista de diccionarios
    cada elemento del listado, "x":
    {"ES00XXXXXXXXXXXXXXXX0F": {"cif": "XXXXXXX4B", "energy": 146.747, "ultima": {"year": 2022, "month": 6, "day": 18, "hour": 16, "minute": 0}}}
    <class 'dict'>
    '''
    reading_register_ = abrir_reading_register()

    for x in reading_register_:
        rr_index = reading_register_.index(x) #reading_register_ index
        # Extraer CUPS y fechas del registro
        cups = list(x.keys())[0]
        rr_data = x[cups]

        # construir fechas de inicio/fin (objetos date)
        last_date_r = rr_data.get("ultima")
        end_date_rr = rr_data.get("final")
        start_date = date(last_date_r["year"], last_date_r["month"], last_date_r.get("day", 1))
        end_date = date(end_date_rr["year"], end_date_rr["month"], end_date_rr.get("day", 1))

        response = consulta_de_consumos(x)
        
        # Guardar la respuesta usando las fechas para el nombre
        guardar_response(cups, response, start_date=start_date, end_date=end_date)
        
        logging.debug("++++response_txt: ")
        logging.debug(response)
        # logging.debug(type(response_txt))# <class 'str'>
        # data_red = formato_lectura(response_txt)# devuelve la lectura en formato json

    ''' Guarda todos los registros de lectura
    de todos los usuarios en un fichero
    los registros se han ido actualizando en cada bucle
    '''
    # Comentar esta linea para probar sin que se registre
    # save_reading_register(reading_register_)


#************************
#** MAIN ENTRY POINT  ***
#************************
if __name__ == "__main__":
    procesar_consumos()

def generar_y_guardar_reading_register(linea_datos):
    """
    Genera y guarda automáticamente el fichero 'reading_register.txt' con todos los campos completos.
    
    Recibe datos simplificados (sin los días) y reconstruye la estructura JSON completa.
    - Día de 'ultima': 1 (primer día del mes)
    - Día de 'final': último día del mes
    
    Args:
        linea_datos (str or list): Cadena o lista de cadenas en formato simplificado.
                                   Formato: "CUPS,CIF,distributorCode,pointType,year_ultima,month_ultima,year_final,month_final"
                                   Ejemplo: "ES0021000011297631SM,09404423E,8,5,2025,10,2025,10"
    
    Returns:
        dict: Diccionario con status "ok" o "error" y mensaje descriptivo.
    
    Ejemplo:
        linea = "ES0021000011297631SM,09404423E,8,5,2025,10,2025,10"
        resultado = generar_y_guardar_reading_register(linea)
        
        # Genera reading_register.txt con:
        # [{
        #     "ES0021000011297631SM": {
        #         "cif": "09404423E",
        #         "distributorCode": "8",
        #         "pointType": "5",
        #         "ultima": {"year": 2025, "month": 10, "day": 1},
        #         "final": {"year": 2025, "month": 10, "day": 31}
        #     }
        # }]
    """
    rr_path = "registers/reading_register.txt"
    
    # Asegurar que la carpeta existe
    if not os.path.exists('registers'):
        os.makedirs('registers')
    
    try:
        # Convertir string a lista si es necesario
        if isinstance(linea_datos, str):
            linea_datos = [linea_datos]
        
        registros = []
        
        for linea in linea_datos:
            # Parsear la línea
            campos = linea.split(',')
            
            if len(campos) != 8:
                raise ValueError(f"Línea inválida. Se esperan 8 campos, se encontraron {len(campos)}: {linea}")
            
            cups = campos[0]
            cif = campos[1]
            distributor_code = campos[2]
            point_type = campos[3]
            year_ultima = int(campos[4])
            month_ultima = int(campos[5])
            year_final = int(campos[6])
            month_final = int(campos[7])
            
            # Obtener el último día del mes para 'final'
            ultimo_dia_final = calendar.monthrange(year_final, month_final)[1]
            
            # Construir la estructura JSON
            registro = {
                cups: {
                    "cif": cif,
                    "distributorCode": distributor_code,
                    "pointType": point_type,
                    "ultima": {
                        "year": year_ultima,
                        "month": month_ultima,
                        "day": 1
                    },
                    "final": {
                        "year": year_final,
                        "month": month_final,
                        "day": ultimo_dia_final
                    }
                }
            }
            registros.append(registro)
        
        # Convertir a JSON formateado
        contenido_json = json.dumps(registros, indent=4, ensure_ascii=False)
        
        # Guardar el contenido en el fichero
        with open(rr_path, "w", encoding="utf-8") as f:
            f.write(contenido_json)
        
        logging.info(f"reading_register.txt generado y guardado correctamente con {len(registros)} registro(s).")
        return {
            "status": "ok",
            "message": f"reading_register.txt generado y guardado con éxito ({len(registros)} registro(s)).",
            "file_path": rr_path,
            "records_count": len(registros)
        }
    except Exception as e:
        logging.error(f"Error al generar reading_register.txt: {e}")
        return {
            "status": "error",
            "message": f"Error al generar reading_register.txt: {e}"
        }