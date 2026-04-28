import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy import Column, String, Text, DateTime, Integer, Boolean
from datetime import datetime, timedelta

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./sara.db")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Conversacion(Base):
    __tablename__ = "conversaciones"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telefono = Column(String(50), index=True)
    rol = Column(String(20))
    contenido = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)


class Reserva(Base):
    __tablename__ = "reservas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(200))
    telefono = Column(String(50), index=True)
    fecha_texto = Column(String(100))
    hora_texto = Column(String(20))
    personas = Column(Integer)
    notas = Column(Text, default="")
    fecha_datetime = Column(DateTime, nullable=True)
    recordatorio_enviado = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def guardar_mensaje(telefono: str, rol: str, contenido: str):
    async with AsyncSessionLocal() as session:
        msg = Conversacion(telefono=telefono, rol=rol, contenido=contenido)
        session.add(msg)
        await session.commit()


async def obtener_historial(telefono: str, limite: int = 10) -> list[dict]:
    from sqlalchemy import select, desc
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Conversacion)
            .where(Conversacion.telefono == telefono)
            .order_by(desc(Conversacion.timestamp))
            .limit(limite)
        )
        mensajes = result.scalars().all()
        return [{"role": m.rol, "content": m.contenido} for m in reversed(mensajes)]


async def guardar_reserva(
    nombre: str,
    telefono: str,
    fecha_texto: str,
    hora_texto: str,
    personas: int,
    notas: str,
    fecha_datetime: datetime | None,
):
    async with AsyncSessionLocal() as session:
        reserva = Reserva(
            nombre=nombre,
            telefono=telefono,
            fecha_texto=fecha_texto,
            hora_texto=hora_texto,
            personas=personas,
            notas=notas,
            fecha_datetime=fecha_datetime,
        )
        session.add(reserva)
        await session.commit()


async def obtener_reservas_para_recordatorio() -> list[Reserva]:
    """Devuelve reservas cuya fecha_datetime está entre 23h y 25h desde ahora y sin recordatorio enviado."""
    from sqlalchemy import select
    ahora = datetime.utcnow()
    ventana_inicio = ahora + timedelta(hours=23)
    ventana_fin = ahora + timedelta(hours=25)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Reserva).where(
                Reserva.fecha_datetime >= ventana_inicio,
                Reserva.fecha_datetime <= ventana_fin,
                Reserva.recordatorio_enviado == False,
            )
        )
        return result.scalars().all()


async def obtener_perfil_cliente(telefono: str) -> dict | None:
    """Devuelve nombre y teléfono del cliente si ya reservó antes."""
    from sqlalchemy import select, desc
    telefono_limpio = telefono.lstrip("+").lstrip("34")
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Reserva)
            .where(Reserva.telefono.contains(telefono_limpio))
            .order_by(desc(Reserva.created_at))
            .limit(1)
        )
        reserva = result.scalar_one_or_none()
        if reserva:
            return {"nombre": reserva.nombre, "telefono": reserva.telefono}
        return None


async def marcar_recordatorio_enviado(reserva_id: int):
    from sqlalchemy import select
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Reserva).where(Reserva.id == reserva_id))
        reserva = result.scalar_one_or_none()
        if reserva:
            reserva.recordatorio_enviado = True
            await session.commit()
