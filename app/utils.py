import requests
import logging
from flask import current_app

# Configure logger
logger = logging.getLogger(__name__)

def obtener_tasa_p2p_binance():
    """
    Obtiene la tasa de cambio USDT/VES desde el mercado P2P de Binance.
    Filtra los anuncios para obtener un precio más representativo y tiene un manejo de errores mejorado.
    """
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    
    payload = {
        "asset": "USDT",
        "fiat": "VES",
        "tradeType": "SELL", # Buscamos anuncios de venta de USDT (gente comprando VES)
        "merchantCheck": False,
        "page": 1,
        "rows": 20, # Aumentamos a 20 para tener una muestra más grande
        "payTypes": ["BancoDeVenezuela"], # Filtramos por un banco común para obtener tasas más realistas
        "countries": []
    }
    
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        logger.info("Intentando obtener la tasa de Binance P2P...")
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('code') != '000000' or not data.get('data'):
            logger.warning(f"La API de Binance P2P no devolvió datos exitosos. Código: {data.get('code')}. Mensaje: {data.get('message', 'N/A')}")
            return None
            
        prices = []
        for item in data['data']:
            adv = item.get('adv')
            if not adv:
                continue
            
            try:
                price = float(adv.get('price'))
                # Monto mínimo disponible en USDT para considerar el anuncio
                min_trade_limit = float(adv.get('minSingleTransAmount', 0))
                # Monto máximo disponible en USDT
                max_trade_limit = float(adv.get('dynamicMaxSingleTransAmount', 0))
                
                # Filtramos anuncios que sean relevantes (ej. entre 20 y 500 USDT)
                if 20 < min_trade_limit < 500 and max_trade_limit > 100:
                    prices.append(price)
            except (ValueError, TypeError, KeyError) as e:
                logger.debug(f"Omitiendo anuncio P2P por datos inválidos: {adv}. Error: {e}")
                continue
        
        if not prices:
            logger.warning("No se encontraron anuncios de P2P que cumplan con los criterios para calcular la tasa.")
            return None
        
        # Usar un promedio de los precios más bajos
        prices.sort()
        sample_size = min(5, len(prices)) 
        avg_price = sum(prices[:sample_size]) / sample_size
        
        if avg_price > 0:
            final_rate = round(avg_price, 2)
            logger.info(f"Tasa de Binance P2P calculada exitosamente: {final_rate}")
            return final_rate
        else:
            logger.warning(f"El promedio de la tasa calculada es cero o negativo: {avg_price}")
            return None
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error de red al contactar la API de Binance P2P: {e}")
        return None
    except Exception as e:
        logger.error(f"Error inesperado procesando datos de Binance P2P: {e}", exc_info=True)
        return None
