from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import sqlite3, json, os, logging, httpx
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────
ADMIN_PASS   = os.getenv("ADMIN_PASS", "admin1234")
DB_PATH      = "crm.db"
N8N_WEBHOOK  = os.getenv("N8N_WEBHOOK_URL", "")   # URL del webhook de n8n para enviar WA
# ──────────────────────────────────────────────────────────────


# ── Database ──────────────────────────────────────────────────
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS clientes (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre               TEXT DEFAULT '',
                telefono             TEXT UNIQUE NOT NULL,
                email                TEXT DEFAULT '',
                direccion            TEXT DEFAULT '',
                tags                 TEXT DEFAULT '[]',
                notas                TEXT DEFAULT '',
                total_pedidos        INTEGER DEFAULT 0,
                total_gastado        REAL DEFAULT 0.0,
                ultima_interaccion   TEXT,
                created_at           TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS interacciones (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id  INTEGER REFERENCES clientes(id) ON DELETE CASCADE,
                tipo        TEXT NOT NULL,
                resumen     TEXT DEFAULT '',
                datos       TEXT DEFAULT '{}',
                created_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS campanas (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre      TEXT NOT NULL,
                mensaje     TEXT NOT NULL,
                segmento    TEXT DEFAULT 'todos',
                estado      TEXT DEFAULT 'borrador',
                enviados    INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS config (
                clave TEXT PRIMARY KEY,
                valor TEXT DEFAULT ''
            );
        """)
        conn.execute("INSERT OR IGNORE INTO config (clave,valor) VALUES ('n8n_webhook',?)", (N8N_WEBHOOK,))
        conn.commit()

init_db()
# ──────────────────────────────────────────────────────────────


# ── Auth ──────────────────────────────────────────────────────
def auth(x_admin_pass: str = Header(default=None)):
    if x_admin_pass != ADMIN_PASS:
        raise HTTPException(status_code=401, detail="No autorizado")
# ──────────────────────────────────────────────────────────────


app = FastAPI(title="Restaurante CRM")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


# ── Helpers ───────────────────────────────────────────────────
def _get_segmento(conn, segmento: str) -> list:
    ahora = datetime.now()
    if segmento == "todos":
        return conn.execute("SELECT * FROM clientes ORDER BY ultima_interaccion DESC").fetchall()
    if segmento == "frecuentes":
        return conn.execute("SELECT * FROM clientes WHERE total_pedidos >= 3 ORDER BY total_gastado DESC").fetchall()
    if segmento == "nuevos":
        hace30 = (ahora - timedelta(days=30)).isoformat()
        return conn.execute("SELECT * FROM clientes WHERE created_at >= ? ORDER BY created_at DESC", (hace30,)).fetchall()
    if segmento == "inactivos_30":
        hace30 = (ahora - timedelta(days=30)).isoformat()
        return conn.execute("SELECT * FROM clientes WHERE (ultima_interaccion IS NULL OR ultima_interaccion < ?) ORDER BY ultima_interaccion", (hace30,)).fetchall()
    if segmento == "inactivos_60":
        hace60 = (ahora - timedelta(days=60)).isoformat()
        return conn.execute("SELECT * FROM clientes WHERE (ultima_interaccion IS NULL OR ultima_interaccion < ?) ORDER BY ultima_interaccion", (hace60,)).fetchall()
    # segmento personalizado = tag
    rows = conn.execute("SELECT * FROM clientes").fetchall()
    return [r for r in rows if segmento in json.loads(r["tags"] or "[]")]


def _personalizar(mensaje: str, cliente: dict) -> str:
    nombre = cliente.get("nombre") or "cliente"
    ultima = cliente.get("ultima_interaccion", "")[:10] if cliente.get("ultima_interaccion") else "hace tiempo"
    return (mensaje
        .replace("{{nombre}}", nombre.split()[0] if nombre else "")
        .replace("{{nombre_completo}}", nombre)
        .replace("{{ultima_visita}}", ultima)
        .replace("{{total_pedidos}}", str(cliente.get("total_pedidos", 0)))
        .replace("{{total_gastado}}", f"{cliente.get('total_gastado', 0):.2f}"))
# ──────────────────────────────────────────────────────────────


# ── API pública (usada por Delivery, SARA, Kmarero) ───────────

class InteraccionIn(BaseModel):
    telefono: str
    tipo: str                          # 'pedido' | 'chat_sara' | 'visita_kmarero' | 'reserva'
    nombre: Optional[str] = None
    email: Optional[str] = None
    direccion: Optional[str] = None
    resumen: Optional[str] = ""
    importe: Optional[float] = 0.0
    datos: Optional[dict] = {}

@app.post("/api/interaccion")
def registrar_interaccion(i: InteraccionIn):
    """Endpoint que llaman Delivery, SARA, etc. al tener contacto con un cliente."""
    with db() as conn:
        existing = conn.execute(
            "SELECT * FROM clientes WHERE telefono=?", (i.telefono,)
        ).fetchone()

        ahora = datetime.now().isoformat()

        if existing:
            cid = existing["id"]
            updates = {"ultima_interaccion": ahora}
            if i.nombre and not existing["nombre"]:
                updates["nombre"] = i.nombre
            if i.email and not existing["email"]:
                updates["email"] = i.email
            if i.direccion and not existing["direccion"]:
                updates["direccion"] = i.direccion
            if i.tipo == "pedido":
                updates["total_pedidos"] = existing["total_pedidos"] + 1
                updates["total_gastado"] = existing["total_gastado"] + (i.importe or 0)

            sets = ", ".join(f"{k}=?" for k in updates)
            conn.execute(f"UPDATE clientes SET {sets} WHERE id=?", [*updates.values(), cid])
        else:
            cur = conn.execute(
                "INSERT INTO clientes (nombre,telefono,email,direccion,total_pedidos,total_gastado,ultima_interaccion) VALUES (?,?,?,?,?,?,?)",
                (i.nombre or "", i.telefono, i.email or "", i.direccion or "",
                 1 if i.tipo == "pedido" else 0, i.importe if i.tipo == "pedido" else 0, ahora)
            )
            cid = cur.lastrowid

        conn.execute(
            "INSERT INTO interacciones (cliente_id,tipo,resumen,datos) VALUES (?,?,?,?)",
            (cid, i.tipo, i.resumen or "", json.dumps(i.datos or {}, ensure_ascii=False))
        )
        conn.commit()

    logger.info(f"Interacción registrada: {i.tipo} | {i.telefono}")
    return {"ok": True, "cliente_id": cid}


# ── API admin ─────────────────────────────────────────────────

@app.get("/api/clientes", dependencies=[Depends(auth)])
def listar_clientes(buscar: str = "", tag: str = "", skip: int = 0, limit: int = 50):
    with db() as conn:
        if buscar:
            rows = conn.execute(
                "SELECT * FROM clientes WHERE nombre LIKE ? OR telefono LIKE ? ORDER BY ultima_interaccion DESC LIMIT ? OFFSET ?",
                (f"%{buscar}%", f"%{buscar}%", limit, skip)
            ).fetchall()
        elif tag:
            all_rows = conn.execute("SELECT * FROM clientes ORDER BY ultima_interaccion DESC").fetchall()
            rows = [r for r in all_rows if tag in json.loads(r["tags"] or "[]")][skip:skip+limit]
        else:
            rows = conn.execute(
                "SELECT * FROM clientes ORDER BY ultima_interaccion DESC LIMIT ? OFFSET ?",
                (limit, skip)
            ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
    return {"total": total, "clientes": [dict(r) for r in rows]}


@app.get("/api/clientes/{cid}", dependencies=[Depends(auth)])
def detalle_cliente(cid: int):
    with db() as conn:
        c = conn.execute("SELECT * FROM clientes WHERE id=?", (cid,)).fetchone()
        if not c:
            raise HTTPException(404, "Cliente no encontrado")
        interacciones = conn.execute(
            "SELECT * FROM interacciones WHERE cliente_id=? ORDER BY created_at DESC LIMIT 20", (cid,)
        ).fetchall()
    return {**dict(c), "interacciones": [dict(i) for i in interacciones]}


@app.put("/api/clientes/{cid}", dependencies=[Depends(auth)])
def actualizar_cliente(cid: int, data: dict):
    allowed = {"nombre", "email", "direccion", "tags", "notas"}
    fields = {k: v for k, v in data.items() if k in allowed}
    if "tags" in fields and isinstance(fields["tags"], list):
        fields["tags"] = json.dumps(fields["tags"], ensure_ascii=False)
    if not fields:
        raise HTTPException(400, "Sin campos para actualizar")
    with db() as conn:
        sets = ", ".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE clientes SET {sets} WHERE id=?", [*fields.values(), cid])
        conn.commit()
    return {"ok": True}


@app.get("/api/stats", dependencies=[Depends(auth)])
def stats():
    with db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
        hace30 = (datetime.now() - timedelta(days=30)).isoformat()
        activos = conn.execute("SELECT COUNT(*) FROM clientes WHERE ultima_interaccion >= ?", (hace30,)).fetchone()[0]
        inactivos = conn.execute("SELECT COUNT(*) FROM clientes WHERE ultima_interaccion < ? OR ultima_interaccion IS NULL", (hace30,)).fetchone()[0]
        top = conn.execute("SELECT nombre, telefono, total_pedidos, total_gastado FROM clientes ORDER BY total_gastado DESC LIMIT 5").fetchall()
        campanas_enviadas = conn.execute("SELECT COUNT(*) FROM campanas WHERE estado='enviada'").fetchone()[0]
    return {
        "total_clientes": total,
        "activos_30d": activos,
        "inactivos_30d": inactivos,
        "campanas_enviadas": campanas_enviadas,
        "top_clientes": [dict(r) for r in top],
    }


# ── Campañas ──────────────────────────────────────────────────

class CampanaIn(BaseModel):
    nombre: str
    mensaje: str
    segmento: str = "todos"

@app.get("/api/campanas", dependencies=[Depends(auth)])
def listar_campanas():
    with db() as conn:
        rows = conn.execute("SELECT * FROM campanas ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]

@app.post("/api/campanas", dependencies=[Depends(auth)])
def crear_campana(c: CampanaIn):
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO campanas (nombre,mensaje,segmento) VALUES (?,?,?)",
            (c.nombre, c.mensaje, c.segmento)
        )
        conn.commit()
        camp = dict(conn.execute("SELECT * FROM campanas WHERE id=?", (cur.lastrowid,)).fetchone())
    return camp

@app.delete("/api/campanas/{cid}", dependencies=[Depends(auth)])
def eliminar_campana(cid: int):
    with db() as conn:
        conn.execute("DELETE FROM campanas WHERE id=?", (cid,))
        conn.commit()
    return {"ok": True}

@app.get("/api/campanas/{cid}/preview", dependencies=[Depends(auth)])
def preview_campana(cid: int):
    """Devuelve cuántos clientes recibirán la campaña y un ejemplo del mensaje."""
    with db() as conn:
        camp = conn.execute("SELECT * FROM campanas WHERE id=?", (cid,)).fetchone()
        if not camp:
            raise HTTPException(404)
        clientes = _get_segmento(conn, camp["segmento"])
        ejemplo = _personalizar(camp["mensaje"], dict(clientes[0]) if clientes else {"nombre": "Ejemplo"})
    return {"total_destinatarios": len(clientes), "mensaje_ejemplo": ejemplo}

@app.post("/api/campanas/{cid}/enviar", dependencies=[Depends(auth)])
async def enviar_campana(cid: int):
    """Envía la campaña a través de n8n que gestiona el envío por WhatsApp."""
    with db() as conn:
        camp = conn.execute("SELECT * FROM campanas WHERE id=?", (cid,)).fetchone()
        if not camp:
            raise HTTPException(404)
        if camp["estado"] == "enviada":
            raise HTTPException(400, "Esta campaña ya fue enviada")
        webhook = conn.execute("SELECT valor FROM config WHERE clave='n8n_webhook'").fetchone()
        webhook_url = webhook["valor"] if webhook else N8N_WEBHOOK
        clientes = _get_segmento(conn, camp["segmento"])

    if not webhook_url:
        raise HTTPException(400, "Configura primero la URL del webhook de n8n")

    enviados = 0
    async with httpx.AsyncClient(timeout=10) as client:
        for c in clientes:
            tel = c["telefono"]
            if not tel:
                continue
            msg = _personalizar(camp["mensaje"], dict(c))
            try:
                await client.post(webhook_url, json={"telefono": tel, "mensaje": msg})
                enviados += 1
            except Exception as e:
                logger.warning(f"Error enviando a {tel}: {e}")

    with db() as conn:
        conn.execute(
            "UPDATE campanas SET estado='enviada', enviados=? WHERE id=?",
            (enviados, cid)
        )
        conn.commit()

    logger.info(f"Campaña #{cid} enviada a {enviados} clientes")
    return {"ok": True, "enviados": enviados}


@app.put("/api/config", dependencies=[Depends(auth)])
def actualizar_config(data: dict):
    with db() as conn:
        for k, v in data.items():
            conn.execute("INSERT OR REPLACE INTO config (clave,valor) VALUES (?,?)", (k, str(v)))
        conn.commit()
    return {"ok": True}

@app.get("/api/config", dependencies=[Depends(auth)])
def obtener_config():
    with db() as conn:
        rows = conn.execute("SELECT * FROM config").fetchall()
    return {r["clave"]: r["valor"] for r in rows}


# ── Admin UI & Static ─────────────────────────────────────────
@app.get("/admin")
def admin_ui():
    return FileResponse("static/admin.html")

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root():
    return {"service": "Restaurante CRM", "status": "ok"}
