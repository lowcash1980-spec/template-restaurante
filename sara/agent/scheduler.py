import json
import yaml
import logging
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from agent.memory import obtener_reservas_para_recordatorio, marcar_recordatorio_enviado

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
ESPECIALES_PATH = BASE_DIR / "knowledge" / "especiales.json"

with open(BASE_DIR / "config" / "business.yaml", "r", encoding="utf-8") as f:
    _biz = yaml.safe_load(f)
NEGOCIO_NOMBRE = _biz["negocio"]["nombre"]
NEGOCIO_TELEFONO = _biz["negocio"]["telefono"]


def _texto_especiales() -> str:
    if not ESPECIALES_PATH.exists():
        return ""
    with open(ESPECIALES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    fuera = [p for p in data.get("fuera_de_carta", []) if p["unidades"] > 0]
    especiales = [p for p in data.get("elaboracion_especial", []) if p["unidades"] > 0]

    if not fuera and not especiales:
        return ""

    lineas = []
    if fuera:
        lineas.append("🐟 *Fuera de carta (unidades limitadas):*")
        for p in fuera:
            lineas.append(f"  • {p['plato']} — {p['precio']} ({p['unidades']} uds)")
    if especiales:
        lineas.append("🍚 *Elaboración especial (con 24h de antelación):*")
        for p in especiales:
            lineas.append(f"  • {p['plato']} — {p['precio']} ({p['unidades']} uds)")

    return "\n".join(lineas)


def _build_recordatorio(reserva) -> str:
    nombre = reserva.nombre.split()[0]  # solo el nombre de pila
    fecha = reserva.fecha_texto
    hora = reserva.hora_texto
    personas = reserva.personas

    msg = (
        f"¡Hola {nombre}! 👋 Te recordamos que mañana tienes reserva en *{NEGOCIO_NOMBRE}*.\n\n"
        f"📅 *Fecha:* {fecha}\n"
        f"🕐 *Hora:* {hora}\n"
        f"👥 *Personas:* {personas}\n"
    )

    especiales = _texto_especiales()
    if especiales:
        msg += (
            f"\n¿Sabías que mañana tenemos disponible?\n\n"
            f"{especiales}\n\n"
            "Si queréis reservar alguno, avisadnos hoy mismo respondiendo a este mensaje. "
            "Los arroces y platos especiales necesitan al menos 24h de antelación 🙂"
        )
    else:
        msg += "\n¡Os esperamos! Si necesitáis algo, respondéis a este mensaje. 😊"

    msg += f"\n\n_{NEGOCIO_NOMBRE} — {NEGOCIO_TELEFONO}_"
    return msg


async def check_recordatorios(proveedor):
    try:
        reservas = await obtener_reservas_para_recordatorio()
        if not reservas:
            return

        logger.info(f"[SCHEDULER] {len(reservas)} recordatorio(s) pendiente(s)")

        for reserva in reservas:
            mensaje = _build_recordatorio(reserva)
            await proveedor.enviar_mensaje(reserva.telefono, mensaje)
            await marcar_recordatorio_enviado(reserva.id)
            logger.info(f"[SCHEDULER] Recordatorio enviado a {reserva.telefono} ({reserva.nombre})")

    except Exception as e:
        logger.error(f"[SCHEDULER] Error enviando recordatorios: {e}")


def iniciar_scheduler(proveedor) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_recordatorios,
        trigger="interval",
        minutes=30,
        args=[proveedor],
        id="recordatorios",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("[SCHEDULER] Iniciado — comprobación cada 30 minutos")
    return scheduler
