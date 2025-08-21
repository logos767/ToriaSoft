import requests
from flask import current_app

def obtener_tasa_p2p_binance():
    """
    Obtiene la tasa de cambio USDT/VES desde el mercado P2P de Binance.
    Filtra los anuncios para obtener un precio más representativo.
    """
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    
    payload = {
        "asset": "USDT",
        "fiat": "VES",
        "tradeType": "SELL",
        "merchantCheck": False,
        "page": 1,
        "rows": 20,
        "payTypes": [],
        "countries": []
    }
    
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('code') != '000000' or not data.get('data'):
            current_app.logger.warning(f"La API de Binance P2P no devolvió datos exitosos. Mensaje: {data.get('message', 'N/A')}")
            return None
            
        prices = []
        for item in data['data']:
            adv = item.get('adv')
            if not adv:
                continue
            
            try:
                price = float(adv.get('price'))
                available_amount = float(adv.get('surplusAmount', 0))
                
                if available_amount > 50:
                    prices.append(price)
            except (ValueError, TypeError, KeyError) as e:
                current_app.logger.debug(f"Omitiendo anuncio P2P por datos inválidos: {adv}. Error: {e}")
                continue
        
        if not prices:
            current_app.logger.warning("No se encontraron anuncios de P2P válidos para calcular la tasa.")
            return None
        
        prices.sort()
        sample_size = min(5, len(prices)) 
        avg_price = sum(prices[:sample_size]) / sample_size
        
        return round(avg_price, 2)
        
    except Exception as e:
        current_app.logger.error(f"Error inesperado procesando datos de Binance P2P: {e}")
        return None