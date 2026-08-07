"""
db.py — SQLAlchemy engine/session setup สำหรับ Com Sec backend

ตัดสินใจ (2026-08-02, ต่อจาก /debug-mantra ที่สร้าง audio_worker เสร็จ): ใช้ SQLite + SQLAlchemy
ORM สำหรับ Meeting entity (และ Module 3-5 ที่ตามมา: Minutes, Approval workflow, audit trail) —
เลือกแทน sqlite3 ดิบ/JSON file เพราะต้องมี foreign key จริงระหว่างหลาย entity ที่จะโตขึ้นเรื่อยๆ
(ผู้ใช้ตัดสินใจร่วมกับ AI หลังเทียบ tradeoff ทั้ง 3 แบบ)

MVP เท่านั้น: ใช้ `Base.metadata.create_all()` สร้างตารางตรงๆ ตอน startup แทน Alembic migration —
เพียงพอตอนนี้เพราะยังไม่มี production data ใดๆ ต้อง**เพิ่ม Alembic ก่อนขึ้น production จริง** ถ้า
schema เปลี่ยนหลังมีข้อมูลจริงแล้ว (ยังไม่ตัดสินใจ ทิ้งเป็น TODO)
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DB_PATH = os.environ.get(
    "COM_SEC_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "com_sec.db"),
)

# check_same_thread=False: FastAPI ใช้หลาย thread เรียก endpoint เดียวกันได้ (threadpool ของ
# sync def endpoints) — SQLite รองรับ multi-thread access ได้ถ้าไม่ share connection object ข้าม
# thread โดยตรง ซึ่ง sessionmaker ด้านล่างสร้าง session ใหม่ต่อ request อยู่แล้ว (ดู get_db())
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """สร้างตารางถ้ายังไม่มี — เรียกตอน backend startup (ดู main.py)"""
    import models  # noqa: F401 — ต้อง import ให้ SQLAlchemy เห็น model classes ก่อน create_all

    Base.metadata.create_all(bind=engine)
    _migrate_add_missing_columns()


def _migrate_add_missing_columns() -> None:
    """MVP เท่านั้น ไม่มี Alembic (ดู docstring หัวไฟล์) — `create_all()` สร้างตารางใหม่ให้เท่านั้น
    **ไม่เพิ่มคอลัมน์ใหม่ให้ตารางที่มีอยู่แล้ว** (SQLite/SQLAlchemy ทำงานแบบนี้เป็นปกติ) ถ้าเพิ่ม field
    ใหม่ใน models.py ตรงๆแล้วมี DB เก่าอยู่แล้ว (`com_sec.db` มี meeting จริงอยู่แล้ว — เจอกรณีนี้จริง
    2026-08-07 ตอนเพิ่ม `MeetingAgendaItem.label`) query จะ error ทันทีว่าไม่มีคอลัมน์นี้ — เพิ่ม migration
    เบาที่สุดเท่าที่จำเป็น: เช็ค `PRAGMA table_info` ก่อนว่ามีคอลัมน์แล้วหรือยัง (กัน error "duplicate
    column" ถ้ารันซ้ำ/DB สร้างใหม่ที่มีคอลัมน์อยู่แล้วจาก `create_all()`) ถ้ายังไม่มีค่อย `ALTER TABLE
    ... ADD COLUMN` เพิ่มรายการใน `_COLUMN_MIGRATIONS` ทุกครั้งที่เพิ่ม field ใหม่ในอนาคต (nullable
    เท่านั้น — SQLite `ADD COLUMN` ใส่ `NOT NULL` ไม่ได้ถ้าไม่มี default)"""
    _COLUMN_MIGRATIONS = [
        ("meeting_agenda_items", "label", "VARCHAR"),
    ]
    with engine.connect() as conn:
        for table, column, col_type in _COLUMN_MIGRATIONS:
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            if column not in existing:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                conn.commit()


def get_db():
    """FastAPI dependency — เปิด session ใหม่ต่อ request แล้วปิดให้อัตโนมัติเสมอ (แม้ error)"""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
