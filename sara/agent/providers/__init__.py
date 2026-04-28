import os
from dotenv import load_dotenv

load_dotenv()


def obtener_proveedor():
    proveedor = os.getenv("WHATSAPP_PROVIDER", "twilio").lower()
    if proveedor == "twilio":
        from agent.providers.twilio import TwilioProveedor
        return TwilioProveedor()
    raise ValueError(f"Proveedor no soportado: {proveedor}")
