import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
ESPECIALES_PATH = BASE_DIR / "knowledge" / "especiales.json"


def _cargar() -> dict:
    if not ESPECIALES_PATH.exists():
        return {"fuera_de_carta": [], "elaboracion_especial": []}
    with open(ESPECIALES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _guardar(data: dict) -> None:
    with open(ESPECIALES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _buscar(lista: list, nombre: str) -> int:
    nombre_lower = nombre.strip().lower()
    for i, item in enumerate(lista):
        if item["plato"].lower() == nombre_lower:
            return i
    return -1


def _formatear_lista(data: dict) -> str:
    lineas = ["📋 *Platos especiales actuales*\n"]

    fuera = [p for p in data.get("fuera_de_carta", []) if p["unidades"] > 0]
    especiales = [p for p in data.get("elaboracion_especial", []) if p["unidades"] > 0]

    if fuera:
        lineas.append("⭐ *Fuera de carta:*")
        for p in fuera:
            lineas.append(f"  • {p['plato']} — {p['precio']} ({p['unidades']} uds)\n    _{p['descripcion']}_")
    else:
        lineas.append("⭐ *Fuera de carta:* ninguno")

    lineas.append("")

    if especiales:
        lineas.append("🍚 *Elaboración especial (24h):*")
        for p in especiales:
            lineas.append(f"  • {p['plato']} — {p['precio']} ({p['unidades']} uds)\n    _{p['descripcion']}_")
    else:
        lineas.append("🍚 *Elaboración especial:* ninguno")

    lineas.append("\n_Para editar usa: !fuera, !especial, !stock, !quitar o !limpiar_")
    return "\n".join(lineas)


def procesar_comando(texto: str) -> str:
    """
    Procesa un comando de administración y devuelve la respuesta.
    Comandos disponibles:
      !especiales
      !fuera Nombre | Descripción | Precio | Unidades
      !especial Nombre | Descripción | Precio | Unidades
      !stock Nombre | Unidades
      !quitar Nombre
      !limpiar
    """
    texto = texto.strip()
    cmd = texto.lower()

    # ── !especiales ──────────────────────────────────────────
    if cmd == "!especiales":
        return _formatear_lista(_cargar())

    # ── !limpiar ─────────────────────────────────────────────
    if cmd == "!limpiar":
        _guardar({"fuera_de_carta": [], "elaboracion_especial": []})
        return "✅ Lista de especiales limpiada. Todos los platos eliminados."

    # ── !fuera / !especial ───────────────────────────────────
    if cmd.startswith("!fuera ") or cmd.startswith("!especial "):
        es_fuera = cmd.startswith("!fuera ")
        clave = "fuera_de_carta" if es_fuera else "elaboracion_especial"
        contenido = texto[7:].strip() if es_fuera else texto[10:].strip()
        partes = [p.strip() for p in contenido.split("|")]

        if len(partes) < 4:
            return (
                "⚠️ Formato incorrecto. Usa:\n"
                "  `!fuera Nombre | Descripción | Precio | Unidades`\n"
                "  Ejemplo: `!fuera Corvina a la sal | Para 2 personas | 35€ | 3`"
            )

        nombre, descripcion, precio = partes[0], partes[1], partes[2]
        try:
            unidades = int(partes[3])
        except ValueError:
            return "⚠️ Las unidades deben ser un número entero."

        data = _cargar()
        idx = _buscar(data[clave], nombre)
        plato = {"plato": nombre, "descripcion": descripcion, "precio": precio, "unidades": unidades}

        if idx >= 0:
            data[clave][idx] = plato
            accion = "actualizado"
        else:
            data[clave].append(plato)
            accion = "añadido"

        _guardar(data)
        tipo_label = "fuera de carta" if es_fuera else "elaboración especial"
        return f"✅ Plato {accion}: *{nombre}* ({tipo_label}) — {unidades} uds a {precio}"

    # ── !stock ────────────────────────────────────────────────
    if cmd.startswith("!stock "):
        contenido = texto[7:].strip()
        partes = [p.strip() for p in contenido.split("|")]
        if len(partes) < 2:
            return "⚠️ Formato: `!stock Nombre del plato | Unidades`"

        nombre = partes[0]
        try:
            unidades = int(partes[1])
        except ValueError:
            return "⚠️ Las unidades deben ser un número entero."

        data = _cargar()
        actualizado = False
        for clave in ("fuera_de_carta", "elaboracion_especial"):
            idx = _buscar(data[clave], nombre)
            if idx >= 0:
                data[clave][idx]["unidades"] = unidades
                actualizado = True
                break

        if not actualizado:
            return f"⚠️ No encontré el plato *{nombre}*. Comprueba el nombre exacto con !especiales"

        _guardar(data)
        estado = "agotado ❌" if unidades == 0 else f"{unidades} uds disponibles ✅"
        return f"✅ Stock actualizado: *{nombre}* → {estado}"

    # ── !quitar ───────────────────────────────────────────────
    if cmd.startswith("!quitar "):
        nombre = texto[8:].strip()
        data = _cargar()
        eliminado = False
        for clave in ("fuera_de_carta", "elaboracion_especial"):
            idx = _buscar(data[clave], nombre)
            if idx >= 0:
                data[clave].pop(idx)
                eliminado = True
                break

        if not eliminado:
            return f"⚠️ No encontré el plato *{nombre}*. Comprueba el nombre con !especiales"

        _guardar(data)
        return f"✅ Plato eliminado: *{nombre}*"

    # ── Comando desconocido ───────────────────────────────────
    return (
        "❓ Comando no reconocido. Comandos disponibles:\n\n"
        "• `!especiales` — ver lista actual\n"
        "• `!fuera Nombre | Desc | Precio | Uds` — añadir fuera de carta\n"
        "• `!especial Nombre | Desc | Precio | Uds` — añadir elaboración especial\n"
        "• `!stock Nombre | Uds` — actualizar unidades\n"
        "• `!quitar Nombre` — eliminar plato\n"
        "• `!limpiar` — borrar todos"
    )
