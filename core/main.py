from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Header, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, AsyncIterator
import sqlite3, json, os, logging, asyncio, shutil, uuid
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────
ADMIN_PASS  = os.getenv("ADMIN_PASS", "admin1234")
DB_PATH     = "core.db"
UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)
# ──────────────────────────────────────────────────────────────


# ── SSE broadcaster ───────────────────────────────────────────
_clients: list[asyncio.Queue] = []

async def _broadcast(event_type: str, data: dict):
    payload = json.dumps({"type": event_type, "data": data}, ensure_ascii=False)
    for q in list(_clients):
        await q.put(payload)

async def _stream(q: asyncio.Queue) -> AsyncIterator[str]:
    try:
        while True:
            yield f"data: {await q.get()}\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        if q in _clients:
            _clients.remove(q)
# ──────────────────────────────────────────────────────────────


# ── Database ──────────────────────────────────────────────────
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS info (
                clave TEXT PRIMARY KEY,
                valor TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS categorias (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                icono  TEXT DEFAULT '🍽️',
                orden  INTEGER DEFAULT 0,
                activa INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS platos (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                categoria_id INTEGER REFERENCES categorias(id) ON DELETE SET NULL,
                nombre       TEXT NOT NULL,
                descripcion  TEXT DEFAULT '',
                precio       REAL NOT NULL,
                foto_url     TEXT DEFAULT '',
                disponible   INTEGER DEFAULT 1,
                es_especial  INTEGER DEFAULT 0,
                orden        INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS horarios (
                dia      TEXT PRIMARY KEY,
                abierto  INTEGER DEFAULT 1,
                apertura TEXT DEFAULT '13:00',
                cierre   TEXT DEFAULT '23:00'
            );
        """)
        defaults = {
            "nombre": "[NOMBRE_RESTAURANTE]",
            "eslogan": "[ESLOGAN]",
            "direccion": "[DIRECCIÓN]",
            "telefono": "[TELÉFONO]",
            "color": "#FF6B35",
            "whatsapp": "",
        }
        for k, v in defaults.items():
            conn.execute("INSERT OR IGNORE INTO info (clave, valor) VALUES (?,?)", (k, v))
        for dia in ["lunes","martes","miercoles","jueves","viernes","sabado","domingo"]:
            conn.execute("INSERT OR IGNORE INTO horarios (dia) VALUES (?)", (dia,))
        conn.commit()

init_db()
# ──────────────────────────────────────────────────────────────


# ── Auth ──────────────────────────────────────────────────────
def auth(x_admin_pass: str = Header(default=None)):
    if x_admin_pass != ADMIN_PASS:
        raise HTTPException(status_code=401, detail="No autorizado")
# ──────────────────────────────────────────────────────────────


app = FastAPI(title="Restaurante Core")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


# ── Public endpoints (todos los servicios los consumen) ───────

@app.get("/api/menu")
def api_menu():
    with db() as conn:
        cats = conn.execute(
            "SELECT * FROM categorias WHERE activa=1 ORDER BY orden, id"
        ).fetchall()
        result = []
        for cat in cats:
            platos = conn.execute(
                "SELECT * FROM platos WHERE categoria_id=? ORDER BY orden, id",
                (cat["id"],)
            ).fetchall()
            result.append({
                **dict(cat),
                "platos": [dict(p) for p in platos]
            })
    return result


@app.get("/api/info")
def api_info():
    with db() as conn:
        info = {r["clave"]: r["valor"] for r in conn.execute("SELECT * FROM info").fetchall()}
        info["horarios"] = [dict(h) for h in conn.execute(
            "SELECT * FROM horarios ORDER BY rowid"
        ).fetchall()]
    return info


@app.get("/api/stock")
def api_stock():
    with db() as conn:
        return [dict(p) for p in conn.execute(
            "SELECT id, nombre, disponible FROM platos"
        ).fetchall()]


@app.get("/api/events")
async def api_events():
    q: asyncio.Queue = asyncio.Queue()
    _clients.append(q)
    return StreamingResponse(
        _stream(q),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


# ── Admin endpoints (requieren autenticación) ─────────────────

class PlatoIn(BaseModel):
    categoria_id: Optional[int] = None
    nombre: str
    descripcion: Optional[str] = ""
    precio: float
    foto_url: Optional[str] = ""
    disponible: Optional[bool] = True
    es_especial: Optional[bool] = False
    orden: Optional[int] = 0

class PlatoUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    precio: Optional[float] = None
    foto_url: Optional[str] = None
    disponible: Optional[bool] = None
    es_especial: Optional[bool] = None
    categoria_id: Optional[int] = None
    orden: Optional[int] = None

class CategoriaIn(BaseModel):
    nombre: str
    icono: Optional[str] = "🍽️"
    orden: Optional[int] = 0


@app.post("/api/platos", dependencies=[Depends(auth)])
async def crear_plato(p: PlatoIn):
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO platos (categoria_id,nombre,descripcion,precio,foto_url,disponible,es_especial,orden) VALUES (?,?,?,?,?,?,?,?)",
            (p.categoria_id, p.nombre, p.descripcion, p.precio, p.foto_url,
             int(p.disponible), int(p.es_especial), p.orden)
        )
        conn.commit()
        plato = dict(conn.execute("SELECT * FROM platos WHERE id=?", (cur.lastrowid,)).fetchone())
    await _broadcast("plato_creado", plato)
    return plato


@app.put("/api/platos/{pid}", dependencies=[Depends(auth)])
async def actualizar_plato(pid: int, p: PlatoUpdate):
    with db() as conn:
        if not conn.execute("SELECT id FROM platos WHERE id=?", (pid,)).fetchone():
            raise HTTPException(404, "Plato no encontrado")
        fields = {k: v for k, v in p.model_dump().items() if v is not None}
        if fields:
            sets = ", ".join(f"{k}=?" for k in fields)
            conn.execute(f"UPDATE platos SET {sets} WHERE id=?", [*fields.values(), pid])
            conn.commit()
        plato = dict(conn.execute("SELECT * FROM platos WHERE id=?", (pid,)).fetchone())
    await _broadcast("plato_actualizado", plato)
    return plato


@app.delete("/api/platos/{pid}", dependencies=[Depends(auth)])
async def eliminar_plato(pid: int):
    with db() as conn:
        conn.execute("DELETE FROM platos WHERE id=?", (pid,))
        conn.commit()
    await _broadcast("plato_eliminado", {"id": pid})
    return {"ok": True}


@app.post("/api/categorias", dependencies=[Depends(auth)])
async def crear_categoria(c: CategoriaIn):
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO categorias (nombre,icono,orden) VALUES (?,?,?)",
            (c.nombre, c.icono, c.orden)
        )
        conn.commit()
        cat = dict(conn.execute("SELECT * FROM categorias WHERE id=?", (cur.lastrowid,)).fetchone())
    await _broadcast("categoria_creada", cat)
    return cat


@app.delete("/api/categorias/{cid}", dependencies=[Depends(auth)])
async def eliminar_categoria(cid: int):
    with db() as conn:
        conn.execute("DELETE FROM categorias WHERE id=?", (cid,))
        conn.commit()
    await _broadcast("categoria_eliminada", {"id": cid})
    return {"ok": True}


@app.put("/api/info", dependencies=[Depends(auth)])
async def actualizar_info(data: dict):
    with db() as conn:
        for k, v in data.items():
            conn.execute("INSERT OR REPLACE INTO info (clave,valor) VALUES (?,?)", (k, str(v)))
        conn.commit()
    await _broadcast("info_actualizada", data)
    return {"ok": True}


@app.put("/api/horarios", dependencies=[Depends(auth)])
async def actualizar_horarios(horarios: list = Body(...)):
    with db() as conn:
        for h in horarios:
            conn.execute(
                "UPDATE horarios SET abierto=?,apertura=?,cierre=? WHERE dia=?",
                (h.get("abierto", 1), h.get("apertura","13:00"), h.get("cierre","23:00"), h["dia"])
            )
        conn.commit()
    await _broadcast("horarios_actualizados", {"horarios": horarios})
    return {"ok": True}


@app.post("/api/upload", dependencies=[Depends(auth)])
async def upload_foto(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        raise HTTPException(400, "Solo JPG, PNG o WEBP")
    filename = f"{uuid.uuid4().hex}{ext}"
    with (UPLOADS_DIR / filename).open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"url": f"/uploads/{filename}"}


# ── Admin UI & Static ─────────────────────────────────────────
@app.get("/admin")
def admin_ui():
    return FileResponse("static/admin.html")

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root():
    return {"service": "Restaurante Core", "status": "ok"}
