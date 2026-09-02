from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    mechanic = "mechanic"
    accountant = "accountant"


class AppLocale(str, enum.Enum):
    ru = "ru"
    en = "en"
    ka = "ka"


class OrderStatus(str, enum.Enum):
    in_progress = "in_progress"
    waiting_part = "waiting_part"
    ready = "ready"
    issued = "issued"


class CashEntryKind(str, enum.Enum):
    expense = "expense"
    collection = "collection"


class CollectionSubtype(str, enum.Enum):
    bank = "bank"
    advance = "advance"
    salary = "salary"


class LineType(str, enum.Enum):
    work = "work"
    part = "part"
    expense = "expense"
    warranty = "warranty"
    diagnostic = "diagnostic"


class PaymentType(str, enum.Enum):
    cash = "Cash"
    card = "Card"
    warranty = "garanty"
    expense = "rasxod"
    transfer = "perechisleniye"


class ServiceCenter(Base):
    __tablename__ = "service_centers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    city: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    users: Mapped[list[User]] = relationship(back_populates="service_center")
    orders: Mapped[list[ServiceOrder]] = relationship(back_populates="service_center")
    cash_entries: Mapped[list[CashEntry]] = relationship(back_populates="service_center")
    cash_openings: Mapped[list[CashOpening]] = relationship(back_populates="service_center")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    login: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    service_center_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("service_centers.id"), nullable=True
    )
    locale: Mapped[str] = mapped_column(String(8), nullable=False, default=AppLocale.ru.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    service_center: Mapped[Optional[ServiceCenter]] = relationship(back_populates="users")
    orders: Mapped[list[ServiceOrder]] = relationship(back_populates="assignee")
    cash_entries: Mapped[list[CashEntry]] = relationship(back_populates="created_by")


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    orders: Mapped[list[ServiceOrder]] = relationship(back_populates="client")
    machine_links: Mapped[list[ClientMachine]] = relationship(back_populates="client")


class Machine(Base):
    __tablename__ = "machines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    serial_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    erp_goods_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    needs_serial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    orders: Mapped[list[ServiceOrder]] = relationship(back_populates="machine")
    client_links: Mapped[list[ClientMachine]] = relationship(back_populates="machine")


class ClientMachine(Base):
    __tablename__ = "client_machines"
    __table_args__ = (UniqueConstraint("client_id", "machine_id", name="uq_client_machine"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    client: Mapped[Client] = relationship(back_populates="machine_links")
    machine: Mapped[Machine] = relationship(back_populates="client_links")


class IssueReason(Base):
    __tablename__ = "issue_reasons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    orders: Mapped[list[ServiceOrder]] = relationship(back_populates="issue_reason")


class ServiceOrder(Base):
    __tablename__ = "service_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    assignee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    service_center_id: Mapped[int] = mapped_column(ForeignKey("service_centers.id"), nullable=False)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"), nullable=False)
    client_id: Mapped[Optional[int]] = mapped_column(ForeignKey("clients.id"), nullable=True)
    issue_reason_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("issue_reasons.id"), nullable=True
    )
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=OrderStatus.in_progress,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    assignee: Mapped[User] = relationship(back_populates="orders")
    service_center: Mapped[ServiceCenter] = relationship(back_populates="orders")
    machine: Mapped[Machine] = relationship(back_populates="orders")
    client: Mapped[Optional[Client]] = relationship(back_populates="orders")
    issue_reason: Mapped[Optional[IssueReason]] = relationship(back_populates="orders")
    lines: Mapped[list[OrderLine]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderLine.id"
    )

    @property
    def total_amount(self) -> Decimal:
        total = Decimal("0")
        for line in self.lines:
            total += (line.amount_work or Decimal("0")) + (line.amount_parts or Decimal("0"))
        return total


class OrderLine(Base):
    __tablename__ = "order_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("service_orders.id"), nullable=False)
    line_type: Mapped[LineType] = mapped_column(
        Enum(LineType, name="line_type", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    part_code: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    payment_type: Mapped[PaymentType] = mapped_column(
        Enum(PaymentType, name="payment_type", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=PaymentType.cash,
    )
    amount_work: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    amount_parts: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    order: Mapped[ServiceOrder] = relationship(back_populates="lines")


class ErpGoodsCache(Base):
    __tablename__ = "erp_goods_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    erp_goods_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="machine")  # machine|part
    group_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ErpSyncState(Base):
    __tablename__ = "erp_sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)  # machines|parts
    last_max_goods_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_stats: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sync_in_progress: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CashEntry(Base):
    __tablename__ = "cash_entries"
    __table_args__ = (
        UniqueConstraint(
            "service_center_id",
            "entry_date",
            "kind",
            "amount",
            "description",
            name="uq_cash_entry_dedupe",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    service_center_id: Mapped[int] = mapped_column(ForeignKey("service_centers.id"), nullable=False)
    kind: Mapped[CashEntryKind] = mapped_column(
        Enum(CashEntryKind, name="cash_entry_kind", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    subtype: Mapped[Optional[CollectionSubtype]] = mapped_column(
        Enum(
            CollectionSubtype,
            name="collection_subtype",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    service_center: Mapped[ServiceCenter] = relationship(back_populates="cash_entries")
    created_by: Mapped[Optional[User]] = relationship(back_populates="cash_entries")


class CashOpening(Base):
    __tablename__ = "cash_openings"
    __table_args__ = (
        UniqueConstraint("service_center_id", "as_of_date", name="uq_cash_opening_center_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_center_id: Mapped[int] = mapped_column(ForeignKey("service_centers.id"), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    service_center: Mapped[ServiceCenter] = relationship(back_populates="cash_openings")
