from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import date, datetime, timedelta, time
from typing import Optional, List
import sqlite3, json, os, logging, secrets, threading
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -- Config -- todo desde .env del cliente -------------------------
def _time(env: str, default: str) -> time:
    try:
        h, m = os.getenv(env, default).split(":")
        return time(int(h), int(m))
    except Exception:
        h, m = default.split(":")
        return time(int(h), int(m))

NOMBRE_NEGOCIO   = os.getenv("NOMBRE_NEGOCIO", "Mi Restaurante")
BRAND_COLOR      = os.getenv("BRAND_COLOR", "#FF6B35")
HORARIO_INICIO   = _time("HORARIO_INICIO", "13:00")
HORARIO_FIN      = _time("HORARIO_FIN", "23:00")
MAX_DOMICILIO    = int(os.getenv("MAX_DOMICILIO", "2"))
MAX_RECOGIDA     = int(os.getenv("MAX_RECOGIDA", "3"))
RESERVA_SEGUNDOS = int(os.getenv("RESERVA_SEGUNDOS", "90"))
ADMIN_PASS         = os.getenv("ADMIN_PASS", "admin1234")
ESLOGAN_NEGOCIO    = os.getenv("ESLOGAN_NEGOCIO", "")
TELEFONO_NEGOCIO   = os.getenv("TELEFONO_NEGOCIO", "")
DB_PATH            = "pedidos.db"
CORE_URL         = os.getenv("CORE_URL", "http://core:8000")
CRM_URL          = os.getenv("CRM_URL", "http://crm:8003")
SARA_URL         = os.getenv("SARA_URL", "http://sara:8002")
_dias = os.getenv("DIAS_CERRADO", "")
DIAS_CERRADO     = [int(d) for d in _dias.split(",") if d.strip().isdigit()]
# ------------------------------------------------------------------


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pedidos (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo         TEXT    NOT NULL,
                nombre       TEXT    NOT NULL,
                telefono     TEXT    NOT NULL,
                direccion    TEXT,
                fecha        TEXT    NOT NULL,
                hora         TEXT    NOT NULL,
                items        TEXT    NOT NULL,
                subtotal     REAL    NOT NULL,
                cargo_cajas  REAL    NOT NULL DEFAULT 0,
                total        REAL    NOT NULL,
                estado       TEXT    NOT NULL DEFAULT 'pendiente',
                notas        TEXT    DEFAULT '',
                metodo_pago  TEXT    DEFAULT 'efectivo',
                created_at   TEXT    DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reservas_temp (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo       TEXT NOT NULL,
                fecha      TEXT NOT NULL,
                hora       TEXT NOT NULL,
                token      TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL
            )
        """)
        conn.commit()
        for col_sql in [
            "ALTER TABLE pedidos ADD COLUMN metodo_pago TEXT DEFAULT 'efectivo'",
        ]:
            try:
                conn.execute(col_sql)
                conn.commit()
            except Exception:
                pass


init_db()

app = FastAPI(title=NOMBRE_NEGOCIO)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


# -- Helpers -------------------------------------------------------

def _limpiar_temp(conn):
    ahora = datetime.utcnow().isoformat()
    conn.execute("DELETE FROM reservas_temp WHERE expires_at <= ?", (ahora,))


def _contar_slot(conn, tipo, fecha, hora):
    confirmados = conn.execute(
        "SELECT COUNT(*) FROM pedidos WHERE fecha=? AND hora=? AND tipo=?",
        (fecha, hora, tipo)
    ).fetchone()[0]
    temporales = conn.execute(
        "SELECT COUNT(*) FROM reservas_temp WHERE fecha=? AND hora=? AND tipo=? AND expires_at > ?",
        (fecha, hora, tipo, datetime.utcnow().isoformat())
    ).fetchone()[0]
    return confirmados + temporales


def _slots_para(tipo: str, fecha: str) -> list:
    maximo = MAX_DOMICILIO if tipo == "domicilio" else MAX_RECOGIDA
    ahora = datetime.now()
    try:
        fecha_dt = date.fromisoformat(fecha)
    except ValueError:
        return []

    if fecha_dt.isoweekday() in DIAS_CERRADO:
        return []

    slots = []
    inicio = datetime.combine(fecha_dt, HORARIO_INICIO)
    if HORARIO_FIN <= HORARIO_INICIO:
        fin = datetime.combine(fecha_dt + timedelta(days=1), HORARIO_FIN)
    else:
        fin = datetime.combine(fecha_dt, HORARIO_FIN)

    with sqlite3.connect(DB_PATH) as conn:
        _limpiar_temp(conn)
        conn.commit()
        actual = inicio
        while actual < fin:
            hora_str = actual.strftime("%H:%M")
            if actual <= ahora:
                actual += timedelta(minutes=15)
                continue
            count = _contar_slot(conn, tipo, fecha, hora_str)
            disponibles = max(0, maximo - count)
            slots.append({
                "hora": hora_str,
                "disponibles": disponibles,
                "maximo": maximo,
                "lleno": disponibles == 0,
            })
            actual += timedelta(minutes=15)
    return slots


# -- API -----------------------------------------------------------

@app.get("/api/config")
def api_config():
    return {
        "dias_cerrado": DIAS_CERRADO,
        "horario_inicio": HORARIO_INICIO.strftime("%H:%M"),
        "horario_fin": HORARIO_FIN.strftime("%H:%M"),
    }


@app.get("/api/slots")
def api_slots(tipo: str, fecha: str):
    return _slots_para(tipo, fecha)


class ReservaSlotIn(BaseModel):
    tipo: str
    fecha: str
    hora: str


@app.post("/api/reservar-slot")
def api_reservar_slot(r: ReservaSlotIn):
    maximo = MAX_DOMICILIO if r.tipo == "domicilio" else MAX_RECOGIDA

    with sqlite3.connect(DB_PATH) as conn:
        _limpiar_temp(conn)
        count = _contar_slot(conn, r.tipo, r.fecha, r.hora)
        if count >= maximo:
            return {"ok": False, "error": "Ese horario ya no tiene hueco disponible."}

        token = secrets.token_urlsafe(16)
        expires_at = (datetime.utcnow() + timedelta(seconds=RESERVA_SEGUNDOS)).isoformat()
        conn.execute(
            "INSERT INTO reservas_temp (tipo, fecha, hora, token, expires_at) VALUES (?,?,?,?,?)",
            (r.tipo, r.fecha, r.hora, token, expires_at)
        )
        conn.commit()

    logger.info(f"Slot reservado: {r.tipo} {r.fecha} {r.hora} -> token {token[:8]}...")
    return {"ok": True, "token": token, "segundos": RESERVA_SEGUNDOS}


@app.delete("/api/reservar-slot/{token}")
def api_liberar_slot(token: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM reservas_temp WHERE token=?", (token,))
        conn.commit()
    return {"ok": True}


class ItemIn(BaseModel):
    nombre: str
    descripcion: Optional[str] = ""
    precio: float
    cantidad: int
    es_pizza: bool = False


class PedidoIn(BaseModel):
    tipo: str
    nombre: str
    telefono: str
    direccion: Optional[str] = None
    fecha: str
    hora: str
    items: List[ItemIn]
    subtotal: float
    cargo_cajas: float
    total: float
    notas: Optional[str] = ""
    metodo_pago: Optional[str] = "efectivo"
    token: str


@app.post("/api/pedido")
def api_crear_pedido(p: PedidoIn):
    maximo = MAX_DOMICILIO if p.tipo == "domicilio" else MAX_RECOGIDA
    ahora = datetime.utcnow().isoformat()

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("BEGIN EXCLUSIVE")
        _limpiar_temp(conn)

        temp = conn.execute(
            "SELECT id FROM reservas_temp WHERE token=? AND expires_at > ?",
            (p.token, ahora)
        ).fetchone()
        if not temp:
            return {"ok": False, "error": "El tiempo de reserva ha expirado. Por favor elige hora de nuevo."}

        confirmados = conn.execute(
            "SELECT COUNT(*) FROM pedidos WHERE fecha=? AND hora=? AND tipo=?",
            (p.fecha, p.hora, p.tipo)
        ).fetchone()[0]
        if confirmados >= maximo:
            conn.execute("DELETE FROM reservas_temp WHERE token=?", (p.token,))
            conn.commit()
            return {"ok": False, "error": "Este horario ya esta completo. Por favor elige otro."}

        cursor = conn.execute(
            """INSERT INTO pedidos
               (tipo,nombre,telefono,direccion,fecha,hora,items,subtotal,cargo_cajas,total,notas,metodo_pago)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (p.tipo, p.nombre, p.telefono, p.direccion,
             p.fecha, p.hora,
             json.dumps([i.model_dump() for i in p.items], ensure_ascii=False),
             p.subtotal, p.cargo_cajas, p.total, p.notas or "",
             p.metodo_pago or "efectivo")
        )
        pedido_id = cursor.lastrowid
        conn.execute("DELETE FROM reservas_temp WHERE token=?", (p.token,))
        conn.commit()

    logger.info(f"Pedido #{pedido_id} | {p.tipo} | {p.nombre} | {p.hora} | {p.total:.2f}EUR")

    threading.Thread(
        target=_post_pedido_notifications,
        args=(pedido_id, p.nombre, p.telefono, p.direccion, p.tipo,
              p.fecha, p.hora, [i.model_dump() for i in p.items], p.total,
              p.metodo_pago or "efectivo"),
        daemon=True
    ).start()

    return {"ok": True, "id": pedido_id}


# -- Carta (proxy al Core) -----------------------------------------

@app.get("/api/carta")
def api_carta():
    try:
        r = httpx.get(f"{CORE_URL}/api/menu", timeout=5)
        return r.json()
    except Exception as e:
        logger.warning(f"Core no disponible: {e}")
        return []


@app.get("/api/restaurante-info")
def api_restaurante_info():
    return {
        "nombre": NOMBRE_NEGOCIO,
        "color": BRAND_COLOR,
        "eslogan": ESLOGAN_NEGOCIO,
        "telefono": TELEFONO_NEGOCIO,
    }


# -- Notificaciones post-pedido (hilo daemon) ----------------------

def _post_pedido_notifications(pedido_id: int, nombre: str, telefono: str,
                                direccion, tipo: str, fecha: str, hora: str,
                                items: list, total: float, metodo_pago: str = "efectivo"):
    try:
        httpx.post(
            f"{CRM_URL}/api/interaccion",
            json={
                "telefono": telefono, "tipo": "pedido", "nombre": nombre,
                "direccion": direccion or "",
                "resumen": f"Pedido {tipo} -- {total:.2f}EUR", "importe": total,
            },
            timeout=5,
        )
    except Exception:
        pass

    if not SARA_URL:
        return
    try:
        tipo_label  = "a domicilio" if tipo == "domicilio" else "para recoger"
        entrega     = "Entrega" if tipo == "domicilio" else "Recogida"
        aviso       = "salga hacia tu direccion" if tipo == "domicilio" else "este listo"
        nombre_corto = nombre.split()[0] if nombre else nombre
        items_txt   = "\n".join(
            f"- {i['cantidad']}x {i['nombre']} -- {i['precio']:.2f}EUR" for i in items
        )
        pago_emoji = "tarjeta" if metodo_pago == "tarjeta" else "efectivo"
        mensaje = (
            f"Hola {nombre_corto}! Hemos recibido tu pedido.\n\n"
            f"Pedido #{pedido_id} -- {tipo_label}\n"
            f"{items_txt}\n\n"
            f"Entrega/Recogida: {hora} -- {fecha}\n"
            f"Total: {total:.2f}EUR - Pago: {pago_emoji}\n\n"
            f"Te avisaremos cuando {aviso}. Gracias!"
        )
        httpx.post(f"{SARA_URL}/api/notificar",
                   json={"telefono": telefono, "mensaje": mensaje}, timeout=5)
    except Exception:
        pass


# -- Pedido en camino / listo --------------------------------------

@app.post("/api/pedido/{pedido_id}/en-camino")
def api_pedido_en_camino(pedido_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT nombre, telefono, tipo, COALESCE(metodo_pago,'efectivo') FROM pedidos WHERE id=?",
            (pedido_id,)
        ).fetchone()

    if not row:
        return {"ok": False, "error": "Pedido no encontrado"}

    nombre, telefono, tipo, metodo_pago = row
    if not SARA_URL:
        return {"ok": False, "error": "SARA no configurada (SARA_URL vacio)"}

    nombre_corto = nombre.split()[0] if nombre else "Cliente"
    pago_label = "Tarjeta" if metodo_pago == "tarjeta" else "Efectivo"
    if tipo == "domicilio":
        mensaje = f"Hola {nombre_corto}! Tu pedido #{pedido_id} ya esta en camino. Pago: {pago_label}. Que aproveche!"
    else:
        mensaje = f"Hola {nombre_corto}! Tu pedido #{pedido_id} esta listo para recoger. Pago: {pago_label}. Te esperamos!"

    try:
        r = httpx.post(f"{SARA_URL}/api/notificar",
                       json={"telefono": telefono, "mensaje": mensaje}, timeout=5)
        return {"ok": r.status_code == 200}
    except Exception as e:
        logger.error(f"Error notificando via SARA: {e}")
        return {"ok": False, "error": str(e)}


# -- Admin ---------------------------------------------------------

_ADMIN_SCRIPT = """<script>
async function avisarCliente(id) {
  const btn = document.getElementById('btn-avisar-' + id);
  if (!btn) return;
  btn.disabled = true; btn.textContent = 'Enviando...';
  try {
    const r = await fetch('/api/pedido/' + id + '/en-camino', {method:'POST'});
    const d = await r.json();
    if (d.ok) { btn.textContent = 'Enviado'; btn.style.background='#16a34a'; }
    else { btn.textContent = 'Error'; btn.style.background='#dc2626'; btn.disabled=false; }
  } catch(e) { btn.textContent = 'Sin conexion'; btn.disabled=false; }
}
</script>"""


@app.get("/admin", response_class=HTMLResponse)
def admin_page(clave: str = "", fecha: str = ""):
    if clave != ADMIN_PASS:
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:40px;background:{BRAND_COLOR}">
        <h2>Acceso restringido</h2>
        <form><input name="clave" placeholder="Contrasena" type="password" style="padding:8px;font-size:16px">
        <button style="padding:8px 16px;font-size:16px">Entrar</button></form>
        </body></html>""", status_code=401)

    if not fecha:
        fecha = date.today().isoformat()

    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """SELECT id, tipo, nombre, telefono, direccion, fecha, hora, items,
                      subtotal, cargo_cajas, total, estado, notas,
                      COALESCE(metodo_pago,'efectivo') AS metodo_pago,
                      created_at
               FROM pedidos WHERE fecha=? ORDER BY hora, created_at""",
            (fecha,)
        ).fetchall()

    cols = ["id","tipo","nombre","telefono","direccion","fecha","hora",
            "items","subtotal","cargo_cajas","total","estado","notas",
            "metodo_pago","created_at"]
    pedidos = []
    for row in rows:
        d = dict(zip(cols, row))
        d["items"] = json.loads(d["items"])
        pedidos.append(d)

    filas = ""
    for p in pedidos:
        emoji = "Domicilio" if p["tipo"] == "domicilio" else "Recogida"
        pago_icon = "Tarjeta" if p.get("metodo_pago") == "tarjeta" else "Efectivo"
        dir_html  = f"<br>Dir: {p['direccion']}" if p["direccion"] else ""
        notas_html = f"<br>Notas: {p['notas']}" if p.get("notas") else ""

        items_html = "".join(
            f"<li>{i['cantidad']}x {i['nombre']} &mdash; {i['precio']:.2f}&euro;</li>"
            for i in p["items"]
        )
        turno_label = ""
        turno_btn = ""

        avisar_label = "En camino" if p["tipo"] == "domicilio" else "Listo para recoger"
        filas += f"""
        <div style="background:#fff;border-radius:12px;padding:16px;margin-bottom:12px;box-shadow:0 2px 8px rgba(0,0,0,.1)">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
            <div>
              <strong style="font-size:18px">{p['hora']} &mdash; {p['nombre']}</strong>
              <div style="font-size:13px;color:#555;margin-top:2px">{emoji} &bull; {pago_icon}{dir_html}{notas_html}</div>
            </div>
            <span style="font-size:18px;font-weight:700;white-space:nowrap">{p['total']:.2f}&euro;</span>
          </div>
          <ul style="margin:10px 0 0 16px;color:#333">{items_html}</ul>
          <div style="display:flex;align-items:center;justify-content:space-between;margin-top:12px;flex-wrap:wrap;gap:8px">
            <span style="font-size:12px;color:#999">Pedido #{p['id']}</span>
            <div>
              {turno_btn}
              <button id="btn-avisar-{p['id']}" onclick="avisarCliente({p['id']})"
                      style="padding:6px 14px;background:#25D366;color:#fff;border:none;border-radius:8px;font-size:13px;font-weight:700;cursor:pointer">
                {avisar_label}</button>
            </div>
          </div>
        </div>"""

    if not filas:
        filas = "<p style='text-align:center;color:#555;padding:40px'>No hay pedidos todavia.</p>"

    total_dia = sum(p["total"] for p in pedidos)

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="es"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Admin -- {NOMBRE_NEGOCIO}</title>
<style>
  body{{font-family:sans-serif;background:{BRAND_COLOR};min-height:100vh;margin:0}}
  .checker{{height:18px;background:repeating-conic-gradient(#111 0% 25%,{BRAND_COLOR} 0% 50%) 0 0/18px 18px}}
  .header{{padding:16px;text-align:center;font-size:28px;font-weight:900;letter-spacing:2px}}
  .container{{max-width:640px;margin:0 auto;padding:12px}}
  .total-bar{{background:#111;color:#fff;border-radius:12px;padding:14px 20px;margin-bottom:16px;font-size:18px;font-weight:700;display:flex;justify-content:space-between}}
  form{{text-align:center;margin-bottom:12px}}
  input[type=date]{{padding:8px 12px;border-radius:8px;border:2px solid #111;font-size:15px;margin-right:8px}}
  button{{padding:8px 18px;background:#111;color:#fff;border:none;border-radius:8px;font-size:15px;cursor:pointer}}
</style></head>
<body>
<div class="checker"></div>
<div class="header">{NOMBRE_NEGOCIO} -- Pedidos del dia</div>
<div class="container">
  <form method="get">
    <input type="hidden" name="clave" value="{clave}">
    <input type="date" name="fecha" value="{fecha}">
    <button type="submit">Ver</button>
  </form>
  <div class="total-bar">
    <span>Total del dia</span>
    <span>{total_dia:.2f}EUR ({len(pedidos)} pedidos)</span>
  </div>
  {filas}
</div>
<div class="checker"></div>
</body>
{_ADMIN_SCRIPT}
</html>""")


# -- Static --------------------------------------------------------
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
    return FileResponse("static/index.html")