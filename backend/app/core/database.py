from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings
from app.models.game import Base
from pathlib import Path


engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Create tables and data directories at startup."""
    db_path = Path("./data/runtime/pax_venture.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    players_dir = settings.DATA_DIR / "players"
    players_dir.mkdir(parents=True, exist_ok=True)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
