from dotenv import load_dotenv
load_dotenv()

import os
import hmac
import hashlib
import yaml
from pathlib import Path
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
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
ADMIN_PIN      = _business.get("admin", {}).get("pin", "")
INTERNAL_KEY   = os.getenv("INTERNAL_KEY", "")
TWILIO_TOKEN   = os.getenv("TWILIO_AUTH_TOKEN", "")
logger.info(f"[STARTUP] ADMIN_PIN cargado: '{ADMIN_PIN}'")


def _verify_twilio_signature(request_url: str, params: dict, signature: str) -> bool:
    """Valida la firma HMAC-SHA1 de Twilio. Devuelve True si es válida o si no hay token configurado."""
    if not TWILIO_TOKEN or not signature:
        return not TWILIO_TOKEN  # sin token configurado, se permite (dev)
    s = request_url + "".join(f"{k}{v}" for k, v in sorted(params.items()))
    expected = __import__("base64").b64encode(
        hmac.new(TWILIO_TOKEN.encode(), s.encode(), hashlib.sha1).digest()
    ).decode()
    return hmac.compare_digest(expected, signature)


def _check_internal_key(key: str) -> bool:
    if not INTERNAL_KEY:
        return True
    return hmac.compare_digest(str(key or ""), INTERNAL_KEY)


proveedor = obtener_proveedor()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("Base de datos lista")
    iniciar_scheduler(proveedor)
    yield

app = FastAPI(title="SARA — Agente WhatsApp", lifespan=lifespan)

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/")
async def root():
    return {"status": "ok", "agente": "Sara"}


class NotificarIn(BaseModel):
    telefono: str
    mensaje: str

@app.post("/api/notificar")
async def api_notificar(n: NotificarIn, x_internal_key: str = Header(default=None)):
    """Envía un mensaje de WhatsApp saliente. Requiere X-Internal-Key si INTERNAL_KEY está configurado."""
    if not _check_internal_key(x_internal_key):
        raise HTTPException(status_code=401, detail="No autorizado")
    try:
        await proveedor.enviar_mensaje(n.telefono, n.mensaje)
        logger.info(f"Notificación saliente enviada a {n.telefono}")
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error enviando notificación saliente: {e}")
        return {"ok": False, "error": str(e)}


# ── Reservas (lista + asignacion de mesa) ────────────────────

@app.get("/api/reservas")
async def api_reservas_list(fecha: str | None = None):
    """Lista reservas para una fecha dada (YYYY-MM-DD). Si no se pasa, hoy."""
    from agent.memory import listar_reservas_dia
    return await listar_reservas_dia(fecha)


class AsignarMesaIn(BaseModel):
    mesa: int | None = None    # null para desasignar

@app.post("/api/reservas/{reserva_id}/asignar-mesa")
async def api_reserva_asignar(reserva_id: int, body: AsignarMesaIn):
    from agent.memory import asignar_mesa_reserva
    ok = await asignar_mesa_reserva(reserva_id, body.mesa)
    return {"ok": ok, "id": reserva_id, "mesa": body.mesa}


class EstadoReservaIn(BaseModel):
    estado: str   # pendiente | asignada | atendida | cancelada

@app.post("/api/reservas/{reserva_id}/estado")
async def api_reserva_estado(reserva_id: int, body: EstadoReservaIn):
    from agent.memory import cambiar_estado_reserva
    ok = await cambiar_estado_reserva(reserva_id, body.estado)
    return {"ok": ok, "id": reserva_id, "estado": body.estado}


@app.post("/webhook")
async def webhook(request: Request):
    try:
        form = await request.form()
        data = dict(form)

        # Validar firma Twilio si hay token configurado
        sig = request.headers.get("X-Twilio-Signature", "")
        url = str(request.url)
        if not _verify_twilio_signature(url, data, sig):
            logger.warning("[WEBHOOK] Firma Twilio inválida — petición rechazada")
            return PlainTextResponse("", status_code=403)

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
