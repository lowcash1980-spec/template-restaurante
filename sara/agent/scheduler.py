import json
import os
import yaml
import logging
import httpx
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from agent.memory import (
    obtener_reservas_para_recordatorio, marcar_recordatorio_enviado,
    obtener_reservas_para_bienvenida, marcar_bienvenida_enviada,
)

CORE_URL = os.getenv("CORE_URL", "http://core:8000")

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


async def _fetch_fuera_carta() -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{CORE_URL}/api/fuera-carta")
            return r.json() if r.status_code == 200 else []
    except Exception:
        return []


def _build_bienvenida(reserva, fuera_carta: list[dict]) -> str:
    nombre = reserva.nombre.split()[0]
    hora = reserva.hora_texto
    personas = reserva.personas

    msg = (
        f"¡Hola {nombre}! 🎉 Os esperamos hoy en *{NEGOCIO_NOMBRE}* a las {hora}.\n\n"
        f"👥 *Personas:* {personas}\n\n"
        f"Esperamos que tengáis una experiencia increíble. "
        f"Si necesitáis algo antes de llegar, aquí estamos. 😊"
    )

    activos = [f for f in fuera_carta if f.get("unidades", 0) > 0]
    if activos:
        lineas = ["\n\n🌟 *Hoy tenemos disponible fuera de carta:*"]
        for f in activos:
            lineas.append(f"  • {f['nombre']} — {f['precio']:.2f}€ ({f['unidades']} uds)")
        lineas.append(
            "\nSi queréis reservar alguno, avisadnos respondiendo a este mensaje. "
            "Los platos especiales necesitan preparación con antelación 🙂"
        )
        msg += "\n".join(lineas)

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


async def check_bienvenidas(proveedor):
    try:
        reservas = await obtener_reservas_para_bienvenida()
        if not reservas:
            return

        fuera_carta = await _fetch_fuera_carta()
        logger.info(f"[SCHEDULER] {len(reservas)} bienvenida(s) pendiente(s)")

        for reserva in reservas:
            mensaje = _build_bienvenida(reserva, fuera_carta)
            await proveedor.enviar_mensaje(reserva.telefono, mensaje)
            await marcar_bienvenida_enviada(reserva.id)
            logger.info(f"[SCHEDULER] Bienvenida enviada a {reserva.telefono} ({reserva.nombre})")

    except Exception as e:
        logger.error(f"[SCHEDULER] Error enviando bienvenidas: {e}")


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
    scheduler.add_job(
        check_bienvenidas,
        trigger="interval",
        minutes=5,
        args=[proveedor],
        id="bienvenidas",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("[SCHEDULER] Iniciado — recordatorios cada 30 min | bienvenidas cada 5 min")
    return scheduler
