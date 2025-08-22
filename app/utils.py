import requests
from flask import current_app
import logging

# Configure logger
logger = logging.getLogger(__name__)

def obtener_tasa_dolar_ves():
    """
    Obtiene la tasa de cambio USD/VES desde una API pública y confiable.
    Este método es más estable que el anterior de Binance P2P.
    """
    # URL de una API pública y conocida para la tasa en Venezuela
    url = "https://s3.amazonaws.com/dolartoday/data.json"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        # Se usa un GET request, que es más simple
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Lanza un error si la respuesta no es 200 OK
        
        data = response.json()
        
        # Extraer el valor del dólar promedio. Se verifica que las claves existan.
        if 'USD' in data and 'promedio' in data['USD']:
            rate = float(data['USD']['promedio'])
            if rate > 0:
                logger.info(f"Tasa de cambio obtenida exitosamente: {rate}")
                return rate
            else:
                logger.warning("La tasa de cambio obtenida es cero o negativa.")
                return None
        else:
            logger.warning("La estructura de la respuesta de la API ha cambiado o no contiene los datos esperados.")
            return None
            
    except requests.exceptions.RequestException as e:
        # Captura errores de red (timeout, DNS, etc.)
        logger.error(f"Error de red al obtener la tasa de cambio: {e}")
        return None
    except (ValueError, KeyError) as e:
        # Captura errores si el JSON está mal formado o falta una clave
        logger.error(f"Error procesando los datos de la tasa de cambio: {e}")
        return None
    except Exception as e:
        # Captura cualquier otro error inesperado
        logger.error(f"Error inesperado al obtener la tasa de cambio: {e}")
        return None

