from dotenv import load_dotenv
load_dotenv()

import os
import yaml
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
from agent.memory import init_db, guardar_mensaje, obtener_historial
from agent.brain import generar_respuesta
from agent.admin import procesar_comando
from agent.scheduler import iniciar_scheduler
from agent.providers import obtener_proveedor
import logging
import traceback

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    _business = yaml.safe_load((Path(__file__).parent.parent / "config" / "business.yaml").read_text(encoding="utf-8"))
except FileNotFoundError:
    logger.warning("No se encontró business.yaml — usando config por defecto")
    _business = {}
ADMIN_PIN = _business.get("admin", {}).get("pin", "")
logger.info(f"[STARTUP] ADMIN_PIN cargado: '{ADMIN_PIN}'")


proveedor = obtener_proveedor()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("Base de datos lista")
    iniciar_scheduler(proveedor)
    yield

app = FastAPI(title="SARA — Agente WhatsApp", lifespan=lifespan)


@app.get("/")
async def root():
    return {"status": "ok", "agente": "Sara"}


class NotificarIn(BaseModel):
    telefono: str
    mensaje: str

@app.post("/api/notificar")
async def api_notificar(n: NotificarIn):
    """Envía un mensaje de WhatsApp saliente. Llamado por Delivery u otros servicios."""
    try:
        await proveedor.enviar_mensaje(n.telefono, n.mensaje)
        logger.info(f"Notificación saliente enviada a {n.telefono}")
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error enviando notificación saliente: {e}")
        return {"ok": False, "error": str(e)}


@app.post("/webhook")
async def webhook(request: Request):
    try:
        form = await request.form()
        data = dict(form)

        mensaje = proveedor.parsear_webhook(data)
        if not mensaje:
            return PlainTextResponse("")

        logger.info(f"Mensaje de {mensaje.telefono}: {mensaje.texto}")

        # Comandos de administración — formato: !PIN comando
        # Ejemplo: !1234 especiales  |  !1234 fuera Corvina | Desc | 35€ | 3
        prefix = f"!{ADMIN_PIN} "
        logger.info(f"[ADMIN] PIN='{ADMIN_PIN}' prefix='{prefix}' texto_repr={repr(mensaje.texto[:30])}")
        if ADMIN_PIN and mensaje.texto.startswith(prefix):
            comando = mensaje.texto[len(ADMIN_PIN) + 2:].strip()
            logger.info(f"[ADMIN] Comando recibido: {comando}")
            respuesta = procesar_comando(f"!{comando}")
            await proveedor.enviar_mensaje(mensaje.telefono, respuesta)
            return PlainTextResponse("")

        # Flujo normal — Sara responde al cliente
        historial = await obtener_historial(mensaje.telefono)
        respuesta = await generar_respuesta(historial, mensaje.texto, proveedor=proveedor, telefono=mensaje.telefono)

        await guardar_mensaje(mensaje.telefono, "user", mensaje.texto)
        await guardar_mensaje(mensaje.telefono, "assistant", respuesta)

        await proveedor.enviar_mensaje(mensaje.telefono, respuesta)
        logger.info(f"Respuesta enviada a {mensaje.telefono}")

        return PlainTextResponse("")

    except Exception as e:
        logger.error(f"Error en webhook: {e}")
        logger.error(traceback.format_exc())
        return PlainTextResponse("error", status_code=500)
