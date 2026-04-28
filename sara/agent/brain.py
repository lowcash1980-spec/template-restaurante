import os
import json
import yaml
import logging
import httpx
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

logger = logging.getLogger(__name__)

DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CORE_URL = os.getenv("CORE_URL", "http://core:8000")
CRM_URL  = os.getenv("CRM_URL",  "http://crm:8003")

BASE_DIR = Path(__file__).resolve().parent.parent
PROMPTS_PATH = BASE_DIR / "config" / "prompts.yaml"
BUSINESS_PATH = BASE_DIR / "config" / "business.yaml"
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
ESPECIALES_PATH = KNOWLEDGE_DIR / "especiales.json"

try:
    with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
        _BASE_PROMPT = yaml.safe_load(f)["system_prompt"]
except FileNotFoundError:
    logger.warning(f"No se encontró {PROMPTS_PATH} — usando prompt genérico")
    _BASE_PROMPT = "Eres un asistente virtual de un restaurante. Responde con amabilidad y ayuda a los clientes."

try:
    with open(BUSINESS_PATH, "r", encoding="utf-8") as f:
        business_config = yaml.safe_load(f)
    NEGOCIO = business_config["negocio"]
    AGENTE_NOMBRE = business_config["agente"]["nombre"]
except FileNotFoundError:
    logger.warning(f"No se encontró {BUSINESS_PATH} — usando config genérica")
    business_config = {"negocio": {"nombre": "el restaurante"}, "agente": {"nombre": "Sara"}}
    NEGOCIO = business_config["negocio"]
    AGENTE_NOMBRE = "Sara"

RESTAURANTE_WHATSAPP = (
    os.getenv("RESTAURANTE_WHATSAPP")
    or business_config.get("admin", {}).get("notificacion_whatsapp", "")
)

# Cargar archivos .md de knowledge (carta, mesas, etc.) — excluye especiales_hoy.md si existe
_knowledge_parts = []
for md_file in sorted(KNOWLEDGE_DIR.glob("*.md")):
    if "especiales" not in md_file.name:
        _knowledge_parts.append(md_file.read_text(encoding="utf-8"))

_KNOWLEDGE_STATIC = "\n\n---\n\n".join(_knowledge_parts) if _knowledge_parts else ""


def _formatear_especiales() -> str:
    """Lee especiales.json en tiempo real para tener siempre el stock actualizado."""
    if not ESPECIALES_PATH.exists():
        return ""
    with open(ESPECIALES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    fuera = [p for p in data.get("fuera_de_carta", []) if p["unidades"] > 0]
    especiales = [p for p in data.get("elaboracion_especial", []) if p["unidades"] > 0]

    if not fuera and not especiales:
        return "## Platos especiales\nHoy no hay platos fuera de carta ni de elaboración especial disponibles."

    lineas = ["## Platos especiales (stock actualizado en tiempo real)\n"]

    if fuera:
        lineas.append("### Fuera de carta (unidades limitadas)")
        for p in fuera:
            lineas.append(f"- **{p['plato']}** — {p['precio']} — {p['unidades']} uds disponibles. {p['descripcion']}")

    if especiales:
        lineas.append("\n### Elaboración especial (mínimo 24h de antelación)")
        for p in especiales:
            lineas.append(f"- **{p['plato']}** — {p['precio']} — {p['unidades']} uds disponibles. {p['descripcion']}")

    return "\n".join(lineas)


def _build_system_prompt() -> str:
    """Construye el prompt completo con los especiales frescos del JSON."""
    parts = [_BASE_PROMPT]
    if _KNOWLEDGE_STATIC:
        parts.append("## Base de conocimiento detallada:\n\n" + _KNOWLEDGE_STATIC)
    especiales = _formatear_especiales()
    if especiales:
        parts.append(especiales)
    return "\n\n".join(parts)

TOOLS = [
    {
        "name": "confirmar_reserva",
        "description": (
            "Usa esta herramienta cuando hayas recogido TODOS los datos de la reserva: "
            "nombre completo, fecha, hora, número de personas y teléfono. "
            "No la uses si falta algún dato obligatorio."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre completo del cliente"},
                "fecha": {"type": "string", "description": "Fecha de la reserva (ej: sábado 26 de abril)"},
                "hora": {"type": "string", "description": "Hora de la reserva (ej: 14:00)"},
                "personas": {"type": "integer", "description": "Número de comensales"},
                "telefono": {"type": "string", "description": "Teléfono de contacto del cliente"},
                "notas": {
                    "type": "string",
                    "description": "Peticiones especiales, alergias, celebración, zona preferida, etc. Vacío si no hay."
                },
            },
            "required": ["nombre", "fecha", "hora", "personas", "telefono"],
        },
    },
    {
        "name": "solicitar_plato_especial",
        "description": (
            "Usa esta herramienta cuando un cliente quiera reservar un plato fuera de carta "
            "o un plato de elaboración especial (arroces, etc.). "
            "Notifica al restaurante para que confirmen disponibilidad y lo preparen."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre_cliente": {"type": "string", "description": "Nombre del cliente que hace la solicitud"},
                "telefono_cliente": {"type": "string", "description": "Teléfono de contacto del cliente"},
                "fecha_reserva": {"type": "string", "description": "Fecha de la reserva para la que se solicita el plato"},
                "plato": {"type": "string", "description": "Nombre del plato solicitado"},
                "cantidad": {"type": "integer", "description": "Número de raciones o personas para ese plato"},
                "tipo": {
                    "type": "string",
                    "enum": ["fuera_de_carta", "elaboracion_especial"],
                    "description": "Si es un plato fuera de carta con stock limitado o un plato de elaboración especial como arroces"
                },
                "notas": {"type": "string", "description": "Cualquier detalle adicional del cliente sobre el plato"},
            },
            "required": ["nombre_cliente", "telefono_cliente", "fecha_reserva", "plato", "cantidad", "tipo"],
        },
    },
]


async def generar_respuesta(historial: list[dict], mensaje_nuevo: str, proveedor=None, telefono: str = "") -> str:
    if DEMO_MODE or not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY.startswith("sk-ant-XXXX"):
        return _respuesta_demo(mensaje_nuevo)

    import anthropic
    from agent.memory import obtener_perfil_cliente
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    # Construir prompt con menú en tiempo real del Core + perfil del cliente
    prompt = _build_system_prompt()
    menu_core = await _fetch_menu_from_core()
    if menu_core:
        prompt += "\n\n" + menu_core

    if telefono and not historial:  # solo en el primer mensaje de la conversación
        perfil = await obtener_perfil_cliente(telefono)
        if perfil:
            prompt += (
                f"\n\n## Cliente conocido\n"
                f"Este cliente ya ha reservado antes. Sus datos son:\n"
                f"- Nombre: {perfil['nombre']}\n"
                f"- Teléfono: {perfil['telefono']}\n"
                f"No le pidas estos datos de nuevo si hace una nueva reserva. "
                f"Puedes saludarle por su nombre si es natural en el contexto."
            )

    mensajes = historial + [{"role": "user", "content": mensaje_nuevo}]

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=prompt,
        messages=mensajes,
        tools=TOOLS,
    )

    # Clasificar bloques de respuesta
    tool_blocks = []
    text_parts = []
    for block in response.content:
        if block.type == "tool_use":
            tool_blocks.append(block)
        elif block.type == "text":
            text_parts.append(block.text)

    if not tool_blocks:
        return text_parts[0] if text_parts else ""

    # Procesar cada herramienta y construir los tool_results
    tool_results = []
    for tb in tool_blocks:
        if tb.name == "confirmar_reserva":
            await _guardar_reserva_bd(tb.input)
            await _registrar_en_crm(tb.input)
            if proveedor:
                await _notificar_restaurante(tb.input, proveedor)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tb.id,
                "content": "Reserva registrada correctamente. Notificación enviada al equipo del restaurante.",
            })
        elif tb.name == "solicitar_plato_especial":
            if proveedor:
                await _notificar_plato_especial(tb.input, proveedor)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tb.id,
                "content": "Solicitud de plato especial enviada al restaurante. Confirmarán disponibilidad con el cliente.",
            })

    # Continuar la conversación con los resultados
    mensajes_con_tool = mensajes + [
        {"role": "assistant", "content": response.content},
        {"role": "user", "content": tool_results},
    ]

    final = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=prompt,
        messages=mensajes_con_tool,
        tools=TOOLS,
    )

    for block in final.content:
        if block.type == "text":
            return block.text

    return "¡Perfecto, todo anotado! 😊"


def _parsear_fecha(fecha_texto: str, hora_texto: str):
    try:
        import dateparser
        from zoneinfo import ZoneInfo
        texto = f"{fecha_texto} {hora_texto}"
        dt = dateparser.parse(
            texto,
            languages=["es"],
            settings={"PREFER_DATES_FROM": "future", "RETURN_AS_TIMEZONE_AWARE": True, "TIMEZONE": "Europe/Madrid"},
        )
        if dt:
            return dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        return None
    except Exception:
        return None


async def _guardar_reserva_bd(datos: dict) -> None:
    from agent.memory import guardar_reserva
    try:
        fecha_dt = _parsear_fecha(datos.get("fecha", ""), datos.get("hora", ""))
        await guardar_reserva(
            nombre=datos.get("nombre", ""),
            telefono=datos.get("telefono", ""),
            fecha_texto=datos.get("fecha", ""),
            hora_texto=datos.get("hora", ""),
            personas=int(datos.get("personas", 0)),
            notas=datos.get("notas", ""),
            fecha_datetime=fecha_dt,
        )
        logger.info(f"Reserva guardada en BD — fecha_datetime={fecha_dt}")
    except Exception as e:
        logger.error(f"Error guardando reserva en BD: {e}")


async def _notificar_plato_especial(datos: dict, proveedor) -> None:
    nombre = datos.get("nombre_cliente", "—")
    telefono = datos.get("telefono_cliente", "—")
    fecha = datos.get("fecha_reserva", "—")
    plato = datos.get("plato", "—")
    cantidad = datos.get("cantidad", "—")
    tipo = datos.get("tipo", "")
    notas = datos.get("notas", "")

    emoji = "🍚" if tipo == "elaboracion_especial" else "⭐"
    tipo_label = "Elaboración especial (24h)" if tipo == "elaboracion_especial" else "Fuera de carta"

    mensaje = (
        f"{emoji} *Solicitud de plato especial — Sara*\n\n"
        f"📋 *Tipo:* {tipo_label}\n"
        f"🍽️ *Plato:* {plato}\n"
        f"🔢 *Raciones:* {cantidad}\n"
        f"📅 *Fecha reserva:* {fecha}\n"
        f"👤 *Cliente:* {nombre}\n"
        f"📞 *Teléfono:* {telefono}\n"
    )
    if notas:
        mensaje += f"📝 *Notas:* {notas}\n"
    mensaje += "\n_Por favor, confirmad disponibilidad al cliente directamente._"

    try:
        await proveedor.enviar_mensaje(RESTAURANTE_WHATSAPP, mensaje)
        logger.info(f"Notificación plato especial enviada a {RESTAURANTE_WHATSAPP}")
    except Exception as e:
        logger.error(f"Error enviando notificación plato especial: {e}")


async def _notificar_restaurante(datos: dict, proveedor) -> None:
    nombre = datos.get("nombre", "—")
    fecha = datos.get("fecha", "—")
    hora = datos.get("hora", "—")
    personas = datos.get("personas", "—")
    telefono = datos.get("telefono", "—")
    notas = datos.get("notas", "")

    mensaje = (
        f"🍽️ *Nueva reserva — Sara*\n\n"
        f"👤 *Nombre:* {nombre}\n"
        f"📅 *Fecha:* {fecha}\n"
        f"🕐 *Hora:* {hora}\n"
        f"👥 *Personas:* {personas}\n"
        f"📞 *Teléfono:* {telefono}\n"
    )
    if notas:
        mensaje += f"📝 *Notas:* {notas}\n"

    try:
        await proveedor.enviar_mensaje(RESTAURANTE_WHATSAPP, mensaje)
        logger.info(f"Notificación reserva enviada a {RESTAURANTE_WHATSAPP}")
    except Exception as e:
        logger.error(f"Error enviando notificación reserva: {e}")


async def _fetch_menu_from_core() -> str:
    """Obtiene la carta del Restaurante Core en tiempo real para incluirla en el prompt."""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{CORE_URL}/api/menu")
            categorias = r.json()
    except Exception:
        return ""

    if not categorias:
        return ""

    lineas = ["## Carta del restaurante (datos en tiempo real)\n"]
    for cat in categorias:
        lineas.append(f"### {cat.get('icono', '🍽️')} {cat['nombre']}")
        for p in cat.get("platos", []):
            disp = "" if p.get("disponible", True) else " *(Agotado hoy)*"
            desc = f" — {p['descripcion']}" if p.get("descripcion") else ""
            lineas.append(f"- **{p['nombre']}** {p['precio']:.2f}€{desc}{disp}")
        lineas.append("")

    return "\n".join(lineas)


async def _registrar_en_crm(datos: dict) -> None:
    """Registra la reserva en el CRM para campañas de WhatsApp."""
    telefono = datos.get("telefono", "")
    if not telefono:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"{CRM_URL}/api/interaccion",
                json={
                    "telefono": telefono,
                    "tipo": "reserva",
                    "nombre": datos.get("nombre", ""),
                    "resumen": (
                        f"Reserva el {datos.get('fecha', '')} a las {datos.get('hora', '')} "
                        f"para {datos.get('personas', '')} persona(s)"
                    ),
                },
            )
        logger.info(f"Reserva registrada en CRM — {telefono}")
    except Exception as e:
        logger.warning(f"No se pudo registrar en CRM: {e}")


def _respuesta_demo(mensaje: str) -> str:
    nombre = AGENTE_NOMBRE
    restaurante = NEGOCIO.get("nombre", "el restaurante")
    telefono = NEGOCIO.get("telefono", "nuestro número")
    msg = mensaje.lower()

    if any(p in msg for p in ["hola", "buenas", "hey", "saludos"]):
        return f"¡Hola! Soy {nombre}, la asistente de {restaurante} 😊 ¿En qué te puedo ayudar?"

    if any(p in msg for p in ["horario", "hora", "abierto", "cierra", "abre"]):
        horarios = business_config.get("horarios", {})
        lineas = "\n".join(f"• {d.capitalize()}: {h}" for d, h in horarios.items())
        return f"Nuestro horario es:\n{lineas}"

    if any(p in msg for p in ["mesa", "zona", "terraza", "salon", "porche", "sitio", "capacidad"]):
        return (
            "Tenemos varias zonas 😊\n\n"
            "🏠 *Salón interior* — hasta 40 personas, con reserva\n"
            "🌿 *Porche interior* — hasta 16 personas, con reserva\n"
            "☀️ *Terraza* — hasta 40 personas, con reserva\n"
            "🍺 *Mesas altas exterior* — hasta 12 personas, sin reserva\n\n"
            "¿Quieres hacer una reserva?"
        )

    if any(p in msg for p in ["alerg", "celiaco", "intoler", "gluten", "lacteos"]):
        return (
            "Puedo consultarte los alérgenos de cualquier plato 🙂\n"
            "¿Qué plato quieres que te compruebe?"
        )

    if any(p in msg for p in ["vino", "bebida", "maridaje"]):
        return (
            "Tenemos una carta de vinos muy completa — tintos, blancos, rosados, generosos y cavas 🍷\n"
            "El maridaje te lo recomienda nuestro camarero directamente en mesa según lo que pidas. ¡Es parte de la experiencia!"
        )

    if any(p in msg for p in ["carta", "menu", "menú", "comer", "plato", "precio"]):
        return (
            "Tenemos una carta mediterránea con producto de calidad 🍽️\n\n"
            "Entrantes desde 4,50€ · Pescados desde 14€ · Carnes desde 13€ · Postres desde 4,70€\n"
            "También tenemos menú infantil por 5,50€–6€.\n\n"
            "¿Quieres saber más sobre alguna sección?"
        )

    if any(p in msg for p in ["reserva", "reservar"]):
        return (
            "¡Claro! Para hacer tu reserva necesito:\n\n"
            "1️⃣ Tu nombre completo\n"
            "2️⃣ Fecha y hora\n"
            "3️⃣ Número de personas\n"
            "4️⃣ Tu teléfono de contacto\n\n"
            "¿Me lo dices y lo apunto?"
        )

    if any(p in msg for p in ["donde", "dirección", "direccion", "ubicacion", "llegar"]):
        return f"Estamos en {NEGOCIO.get('direccion', '')}. ¿Necesitas indicaciones?"

    if any(p in msg for p in ["evento", "boda", "comunion", "bautizo", "celebracion", "grupo"]):
        return (
            "¡Para eventos especiales nos encanta ayudarte! 🎉\n"
            "Déjame tu nombre y teléfono y un responsable te contactará para organizarlo todo al detalle."
        )

    return (
        f"Gracias por escribirnos 😊 Soy {nombre} de {restaurante}.\n"
        "Puedo ayudarte con la carta, alérgenos, horarios, zonas, reservas o cualquier consulta.\n"
        "¿En qué te puedo ayudar?"
    )
