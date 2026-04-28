from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class MensajeEntrante:
    telefono: str
    texto: str
    nombre: str = ""


class ProveedorWhatsApp(ABC):
    @abstractmethod
    def parsear_webhook(self, data: dict) -> MensajeEntrante | None:
        pass

    @abstractmethod
    async def enviar_mensaje(self, telefono: str, texto: str) -> bool:
        pass
