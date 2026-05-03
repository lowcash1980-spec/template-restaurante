from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Header, Body, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from typing import Optional, AsyncIterator
import sqlite3, json, os, logging, asyncio, shutil, uuid, hmac, time
from collections import defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────
ADMIN_PASS       = os.getenv("ADMIN_PASS", "admin1234")
DB_PATH          = "core.db"
UPLOADS_DIR      = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)
MAX_UPLOAD_BYTES = 5 * 1024 * 1024          # 5 MB
ALLOWED_ORIGINS  = os.getenv("ALLOWED_ORIGINS", "*").split(",")
# ──────────────────────────────────────────────────────────────


# ── Seguridad: cabeceras HTTP ─────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"]  = "nosniff"
        response.headers["X-Frame-Options"]         = "DENY"
        response.headers["X-XSS-Protection"]        = "1; mode=block"
        response.headers["Referrer-Policy"]         = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"]      = "camera=(), microphone=(), geolocation=()"
        return response
# ──────────────────────────────────────────────────────────────


# ── Seguridad: anti-fuerza bruta ──────────────────────────────
_failed: dict[str, list[float]] = defaultdict(list)
MAX_ATTEMPTS   = 5
LOCKOUT_SECS   = 300  # 5 minutos

def _is_locked(ip: str) -> bool:
    now = time.time()
    _failed[ip] = [t for t in _failed[ip] if now - t < LOCKOUT_SECS]
    return len(_failed[ip]) >= MAX_ATTEMPTS

def _record_fail(ip: str):
    _failed[ip].append(time.time())
# ──────────────────────────────────────────────────────────────


# ── Seguridad: rate limiting simple ───────────────────────────
_rl: dict[str, list[float]] = defaultdict(list)

def _rate_exceeded(ip: str, limit: int = 120, window: int = 60) -> bool:
    now = time.time()
    _rl[ip] = [t for t in _rl[ip] if now - t < window]
    if len(_rl[ip]) >= limit:
        return True
    _rl[ip].append(now)
    return False
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
            CREATE TABLE IF NOT EXISTS fuera_carta (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre      TEXT NOT NULL,
                descripcion TEXT DEFAULT '',
                precio      REAL NOT NULL,
                unidades    INTEGER DEFAULT 0,
                activo      INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS mesas (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                numero     INTEGER NOT NULL UNIQUE,
                capacidad  INTEGER NOT NULL CHECK(capacidad >= 2),
                forma      TEXT    NOT NULL DEFAULT 'cuadrada',
                x          INTEGER NOT NULL DEFAULT 40,
                y          INTEGER NOT NULL DEFAULT 40,
                w          INTEGER NOT NULL DEFAULT 80,
                h          INTEGER NOT NULL DEFAULT 80,
                zona       TEXT    NOT NULL DEFAULT 'Salón',
                rotacion   INTEGER NOT NULL DEFAULT 0,
                activa     INTEGER NOT NULL DEFAULT 1,
                created_at TEXT    DEFAULT (datetime('now'))
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
def auth(request: Request, x_admin_pass: str = Header(default=None)):
    ip = request.client.host if request.client else "unknown"
    if _is_locked(ip):
        raise HTTPException(status_code=429, detail="Demasiados intentos fallidos. Espera 5 minutos.")
    if not hmac.compare_digest(str(x_admin_pass or ""), ADMIN_PASS):
        _record_fail(ip)
        raise HTTPException(status_code=401, detail="No autorizado")
# ──────────────────────────────────────────────────────────────


app = FastAPI(title="Restaurante Core", docs_url=None, redoc_url=None)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-Admin-Pass"],
)


# ── Rate limiting middleware ───────────────────────────────────
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"
    if _rate_exceeded(ip):
        return JSONResponse(status_code=429, content={"detail": "Demasiadas peticiones. Intenta más tarde."})
    return await call_next(request)
# ──────────────────────────────────────────────────────────────


# ── Public endpoints ──────────────────────────────────────────

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
            result.append({**dict(cat), "platos": [dict(p) for p in platos]})
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


@app.get("/api/fuera-carta")
def api_fuera_carta():
    with db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM fuera_carta WHERE activo=1 ORDER BY id"
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


# ── Admin endpoints ───────────────────────────────────────────

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

class FueraCartaIn(BaseModel):
    nombre: str
    descripcion: Optional[str] = ""
    precio: float
    unidades: Optional[int] = 0
    activo: Optional[bool] = True

class FueraCartaUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    precio: Optional[float] = None
    unidades: Optional[int] = None
    activo: Optional[bool] = None


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


@app.get("/api/fuera-carta/all", dependencies=[Depends(auth)])
def api_fuera_carta_all():
    with db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM fuera_carta ORDER BY id"
        ).fetchall()]


@app.post("/api/fuera-carta", dependencies=[Depends(auth)])
async def crear_fuera_carta(f: FueraCartaIn):
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO fuera_carta (nombre,descripcion,precio,unidades,activo) VALUES (?,?,?,?,?)",
            (f.nombre, f.descripcion, f.precio, f.unidades, int(f.activo))
        )
        conn.commit()
        item = dict(conn.execute("SELECT * FROM fuera_carta WHERE id=?", (cur.lastrowid,)).fetchone())
    await _broadcast("fuera_carta_creado", item)
    return item


@app.put("/api/fuera-carta/{fid}", dependencies=[Depends(auth)])
async def actualizar_fuera_carta(fid: int, f: FueraCartaUpdate):
    with db() as conn:
        if not conn.execute("SELECT id FROM fuera_carta WHERE id=?", (fid,)).fetchone():
            raise HTTPException(404, "Plato no encontrado")
        fields = {k: v for k, v in f.model_dump().items() if v is not None}
        if "activo" in fields:
            fields["activo"] = int(fields["activo"])
        if fields:
            sets = ", ".join(f"{k}=?" for k in fields)
            conn.execute(f"UPDATE fuera_carta SET {sets} WHERE id=?", [*fields.values(), fid])
            conn.commit()
        item = dict(conn.execute("SELECT * FROM fuera_carta WHERE id=?", (fid,)).fetchone())
    await _broadcast("fuera_carta_actualizado", item)
    return item


@app.delete("/api/fuera-carta/{fid}", dependencies=[Depends(auth)])
async def eliminar_fuera_carta(fid: int):
    with db() as conn:
        conn.execute("DELETE FROM fuera_carta WHERE id=?", (fid,))
        conn.commit()
    await _broadcast("fuera_carta_eliminado", {"id": fid})
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
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Imagen demasiado grande. Máximo 5 MB.")
    filename = f"{uuid.uuid4().hex}{ext}"
    (UPLOADS_DIR / filename).write_bytes(content)
    return {"url": f"/uploads/{filename}"}


# ── Distribución del local (mesas) ────────────────────────────

class MesaIn(BaseModel):
    numero: int
    capacidad: int
    forma: Optional[str] = "cuadrada"      # cuadrada | redonda | rectangular
    x: Optional[int] = 40
    y: Optional[int] = 40
    w: Optional[int] = 80
    h: Optional[int] = 80
    zona: Optional[str] = "Salón"
    rotacion: Optional[int] = 0

class MesaUpdate(BaseModel):
    numero: Optional[int] = None
    capacidad: Optional[int] = None
    forma: Optional[str] = None
    x: Optional[int] = None
    y: Optional[int] = None
    w: Optional[int] = None
    h: Optional[int] = None
    zona: Optional[str] = None
    rotacion: Optional[int] = None
    activa: Optional[int] = None

def _row_to_mesa(r):
    return {
        "id": r["id"], "numero": r["numero"], "capacidad": r["capacidad"],
        "forma": r["forma"], "x": r["x"], "y": r["y"],
        "w": r["w"], "h": r["h"], "zona": r["zona"],
        "rotacion": r["rotacion"], "activa": bool(r["activa"]),
    }

@app.get("/api/mesas")
def api_mesas_list(zona: Optional[str] = None, incluir_inactivas: bool = False):
    """Lista todas las mesas activas. Opcional filtrar por zona."""
    with db() as conn:
        sql = "SELECT * FROM mesas WHERE 1=1"
        params = []
        if not incluir_inactivas:
            sql += " AND activa=1"
        if zona:
            sql += " AND zona=?"
            params.append(zona)
        sql += " ORDER BY zona, numero"
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_mesa(r) for r in rows]

@app.get("/api/mesas/{mesa_id}")
def api_mesa_get(mesa_id: int):
    with db() as conn:
        r = conn.execute("SELECT * FROM mesas WHERE id=?", (mesa_id,)).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Mesa no encontrada")
    return _row_to_mesa(r)

@app.get("/api/aforo")
def api_aforo():
    """Aforo total y por zona (suma de capacidades)."""
    with db() as conn:
        rows = conn.execute(
            "SELECT zona, SUM(capacidad) AS cap, COUNT(*) AS n "
            "FROM mesas WHERE activa=1 GROUP BY zona"
        ).fetchall()
    por_zona = [{"zona": r["zona"], "capacidad": r["cap"] or 0, "mesas": r["n"]} for r in rows]
    total_cap = sum(z["capacidad"] for z in por_zona)
    total_mesas = sum(z["mesas"] for z in por_zona)
    return {"total_capacidad": total_cap, "total_mesas": total_mesas, "por_zona": por_zona}

@app.get("/api/zonas")
def api_zonas():
    """Lista distinta de zonas usadas."""
    with db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT zona FROM mesas WHERE activa=1 ORDER BY zona"
        ).fetchall()
    zonas = [r["zona"] for r in rows]
    if not zonas:
        zonas = ["Salón"]
    return zonas

@app.post("/api/mesas", dependencies=[Depends(auth)])
async def api_mesa_crear(m: MesaIn):
    if m.capacidad < 2:
        raise HTTPException(status_code=400, detail="La capacidad mínima es 2 personas")
    if m.forma not in ("cuadrada", "redonda", "rectangular"):
        raise HTTPException(status_code=400, detail="Forma debe ser: cuadrada, redonda o rectangular")
    with db() as conn:
        existe = conn.execute("SELECT 1 FROM mesas WHERE numero=? AND activa=1", (m.numero,)).fetchone()
        if existe:
            raise HTTPException(status_code=409, detail=f"Ya existe una mesa #{m.numero} activa")
        cursor = conn.execute(
            """INSERT INTO mesas (numero, capacidad, forma, x, y, w, h, zona, rotacion)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (m.numero, m.capacidad, m.forma, m.x, m.y, m.w, m.h, m.zona, m.rotacion)
        )
        conn.commit()
        new_id = cursor.lastrowid
    await _broadcast("mesa_creada", {"id": new_id})
    return {"ok": True, "id": new_id}

@app.put("/api/mesas/{mesa_id}", dependencies=[Depends(auth)])
async def api_mesa_actualizar(mesa_id: int, m: MesaUpdate):
    fields, values = [], []
    for k in ("numero","capacidad","forma","x","y","w","h","zona","rotacion","activa"):
        v = getattr(m, k)
        if v is not None:
            if k == "capacidad" and v < 2:
                raise HTTPException(status_code=400, detail="Capacidad mínima 2")
            if k == "forma" and v not in ("cuadrada","redonda","rectangular"):
                raise HTTPException(status_code=400, detail="Forma inválida")
            fields.append(f"{k}=?")
            values.append(v)
    if not fields:
        return {"ok": True, "noop": True}
    values.append(mesa_id)
    with db() as conn:
        c = conn.execute(f"UPDATE mesas SET {', '.join(fields)} WHERE id=?", values)
        conn.commit()
        if c.rowcount == 0:
            raise HTTPException(status_code=404, detail="Mesa no encontrada")
    await _broadcast("mesa_actualizada", {"id": mesa_id})
    return {"ok": True}

@app.delete("/api/mesas/{mesa_id}", dependencies=[Depends(auth)])
async def api_mesa_eliminar(mesa_id: int, hard: bool = False):
    """Por defecto soft delete (activa=0). Pasar ?hard=true para borrar permanente."""
    with db() as conn:
        if hard:
            c = conn.execute("DELETE FROM mesas WHERE id=?", (mesa_id,))
        else:
            c = conn.execute("UPDATE mesas SET activa=0 WHERE id=?", (mesa_id,))
        conn.commit()
        if c.rowcount == 0:
            raise HTTPException(status_code=404, detail="Mesa no encontrada")
    await _broadcast("mesa_eliminada", {"id": mesa_id})
    return {"ok": True}


# ── Admin UI & Static ─────────────────────────────────────────
@app.get("/admin")
def admin_ui():
    return FileResponse("static/admin.html")

@app.get("/admin/cocina")
def admin_cocina():
    """Panel cocina: vista en tiempo real de pedidos pendientes/en preparacion/terminados."""
    return FileResponse("static/cocina.html")

@app.get("/admin/distribucion")
def admin_distribucion():
    """Editor del plano del local: añadir/mover/eliminar mesas, organizar por zonas."""
    return FileResponse("static/distribucion.html")

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root():
    return {"service": "Restaurante Core", "status": "ok"}
