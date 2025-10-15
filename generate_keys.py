# generate_keys.py
import os
import base64

# CORRECCIÓN FINAL: Importar desde 'py_vapid', que es el nombre real del módulo.
from vapid import Vapid
    
    

try:
    # MÉTODO INFALIBLE: Crear una instancia de Vapid para que genere las claves.
    vapid = Vapid()
    
    # Convertir las claves de bytes a string en formato base64 url-safe
    private_key = base64.urlsafe_b64encode(vapid.private_key).rstrip(b'=').decode('utf-8')
    public_key = base64.urlsafe_b64encode(vapid.public_key).rstrip(b'=').decode('utf-8')
    
    print("¡Claves VAPID generadas exitosamente!")
    print("-" * 40)
    print(f"VAPID_PRIVATE_KEY={private_key}")
    print(f"VAPID_PUBLIC_KEY={public_key}")
    print("-" * 40)
    print("\nInstrucciones:")
    print("1. Copia la línea completa 'VAPID_PRIVATE_KEY=...' y pégala en tu archivo de configuración (.env).")
    print("2. Copia SOLO la clave pública (el valor después de 'VAPID_PUBLIC_KEY=') y pégala en tu archivo 'base.html'.")

except Exception as e:
    print(f"Ocurrió un error al generar las claves: {e}")
    print("Por favor, asegúrate de que la librería 'py-vapid' está instalada correctamente en tu entorno virtual ('pip install py-vapid').")
