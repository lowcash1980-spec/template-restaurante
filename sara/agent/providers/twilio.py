import os
import base64
import logging
import httpx
from agent.providers.base import ProveedorWhatsApp, MensajeEntrante

logger = logging.getLogger(__name__)


class TwilioProveedor(ProveedorWhatsApp):
    def __init__(self):
        self.account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        self.auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        self.from_number = os.environ.get("TWILIO_PHONE_NUMBER", "")
        logger.info(f"TwilioProveedor iniciado. SID: {self.account_sid[:6] if self.account_sid else 'VACIO'}")

    def parsear_webhook(self, data: dict) -> MensajeEntrante | None:
        texto = data.get("Body", "").strip()
        telefono = data.get("From", "").replace("whatsapp:", "")
        nombre = data.get("ProfileName", "")
        if not texto or not telefono:
            return None
        return MensajeEntrante(telefono=telefono, texto=texto, nombre=nombre)

    async def enviar_mensaje(self, telefono: str, texto: str) -> bool:
        credentials = base64.b64encode(f"{self.account_sid}:{self.auth_token}".encode()).decode()
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        headers = {"Authorization": f"Basic {credentials}"}
        payload = {
            "From": f"whatsapp:{self.from_number}",
            "To": f"whatsapp:{telefono}",
            "Body": texto,
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=payload, headers=headers)
            logger.info(f"Twilio response: {response.status_code} - {response.text[:100]}")
            return response.status_code == 201
