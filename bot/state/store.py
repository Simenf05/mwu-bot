from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # started|success|failed
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (UniqueConstraint("session_date", "strategy_version", name="uq_run_session_strategy"),)


class Weight(Base):
    __tablename__ = "weights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (UniqueConstraint("session_date", "symbol", name="uq_weight_session_symbol"),)


class Price(Base):
    __tablename__ = "prices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    prev_close: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (UniqueConstraint("session_date", "symbol", name="uq_price_session_symbol"),)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)  # buy|sell
    notional: Mapped[float] = mapped_column(Float, nullable=False)
    alpaca_order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


@dataclass(frozen=True)
class Store:
    sqlite_path: str

    def engine(self):
        return create_engine(f"sqlite:///{self.sqlite_path}", future=True)

    def init_db(self) -> None:
        eng = self.engine()
        Base.metadata.create_all(eng)

    def run_success_exists(self, session_date: date, strategy_version: str) -> bool:
        eng = self.engine()
        with Session(eng) as s:
            q = select(Run).where(
                Run.session_date == session_date,
                Run.strategy_version == strategy_version,
                Run.status == "success",
            )
            return s.execute(q).first() is not None

    def start_run(self, session_date: date, strategy_version: str) -> int:
        eng = self.engine()
        with Session(eng) as s:
            run = Run(
                session_date=session_date,
                strategy_version=strategy_version,
                status="started",
                started_at=datetime.utcnow(),
                finished_at=None,
                error=None,
            )
            s.add(run)
            s.commit()
            s.refresh(run)
            return int(run.id)

    def finish_run(self, run_id: int, *, status: str, error: str | None) -> None:
        if status not in {"success", "failed"}:
            raise ValueError("status must be success|failed")
        eng = self.engine()
        with Session(eng) as s:
            run = s.get(Run, run_id)
            if run is None:
                raise ValueError("Unknown run_id")
            run.status = status
            run.finished_at = datetime.utcnow()
            run.error = error
            s.commit()

    def get_latest_weights(self, symbols: list[str]) -> dict[str, float] | None:
        eng = self.engine()
        with Session(eng) as s:
            latest_date = s.execute(select(Weight.session_date).order_by(Weight.session_date.desc()).limit(1)).scalar()
            if latest_date is None:
                return None
            q = select(Weight.symbol, Weight.weight).where(Weight.session_date == latest_date)
            rows = s.execute(q).all()
            out = {str(sym).upper(): float(w) for sym, w in rows}
            return {sym: float(out.get(sym, 0.0)) for sym in symbols}

    def upsert_weights(self, session_date: date, weights: dict[str, float]) -> None:
        eng = self.engine()
        with Session(eng) as s:
            for sym, w in weights.items():
                sym_u = str(sym).upper()
                existing = s.execute(
                    select(Weight).where(Weight.session_date == session_date, Weight.symbol == sym_u)
                ).scalar_one_or_none()
                if existing is None:
                    s.add(Weight(session_date=session_date, symbol=sym_u, weight=float(w)))
                else:
                    existing.weight = float(w)
            s.commit()

    def upsert_prices(self, session_date: date, prices: dict[str, tuple[float, float]]) -> None:
        eng = self.engine()
        with Session(eng) as s:
            for sym, (close, prev_close) in prices.items():
                sym_u = str(sym).upper()
                existing = s.execute(
                    select(Price).where(Price.session_date == session_date, Price.symbol == sym_u)
                ).scalar_one_or_none()
                if existing is None:
                    s.add(Price(session_date=session_date, symbol=sym_u, close=float(close), prev_close=float(prev_close)))
                else:
                    existing.close = float(close)
                    existing.prev_close = float(prev_close)
            s.commit()

    def insert_order(
        self,
        *,
        session_date: date,
        symbol: str,
        side: str,
        notional: float,
        alpaca_order_id: str,
        status: str,
    ) -> None:
        eng = self.engine()
        with Session(eng) as s:
            s.add(
                Order(
                    session_date=session_date,
                    symbol=str(symbol).upper(),
                    side=side,
                    notional=float(notional),
                    alpaca_order_id=str(alpaca_order_id),
                    status=str(status),
                )
            )
            s.commit()

