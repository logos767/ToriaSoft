import requests
import logging

# Configure logger
logger = logging.getLogger(__name__)

def obtener_tasa_p2p_binance():
    """Obtiene la tasa de compra de USDT en VES desde el mercado P2P de Binance."""
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    payload = {
        "page": 1,
        "rows": 1,
        "payTypes": [],  # Busca todos los métodos de pago para mayor compatibilidad
        "asset": "USDT",
        "tradeType": "BUY",  # Es el precio al que la gente VENDE USDT, o sea, el precio de compra para nosotros.
        "fiat": "VES",
        "publisherType": None
    }
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get('code') == '000000' and data.get('data'):
            return float(data['data'][0]['adv']['price'])
        logger.warning(f"Respuesta de Binance P2P no exitosa: {data.get('message')}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error al obtener la tasa P2P de Binance: {e}")
        return None