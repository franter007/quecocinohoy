from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

MEAL_TYPES = ("desayuno", "almuerzo", "cena", "lonchera", "refresco")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120), default="")
    role: Mapped[str] = mapped_column(String(40), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(80), index=True, default="")
    ip_address: Mapped[str] = mapped_column(String(64), index=True, default="")
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class AppSetting(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    value: Mapped[str] = mapped_column(String(255), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Dish(Base):
    __tablename__ = "dishes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    meal_type: Mapped[str] = mapped_column(String(20), index=True)
    ingredients: Mapped[str] = mapped_column(Text)
    cost_per_serving: Mapped[float] = mapped_column(Float)
    calories: Mapped[int] = mapped_column(Integer)
    protein_g: Mapped[float] = mapped_column(Float, default=0)
    carbs_g: Mapped[float] = mapped_column(Float, default=0)
    fat_g: Mapped[float] = mapped_column(Float, default=0)
    fiber_g: Mapped[float] = mapped_column(Float, default=0)
    sugar_g: Mapped[float] = mapped_column(Float, default=0)
    sodium_mg: Mapped[float] = mapped_column(Float, default=0)
    benefits: Mapped[str] = mapped_column(Text, default="")
    warnings: Mapped[str] = mapped_column(Text, default="")
    is_healthy: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    menu_items: Mapped[list["WeeklyMenuItem"]] = relationship(back_populates="dish", cascade="all,delete")


class WeeklyMenu(Base):
    __tablename__ = "weekly_menus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    week_start: Mapped[date] = mapped_column(Date, unique=True, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list["WeeklyMenuItem"]] = relationship(
        back_populates="weekly_menu", cascade="all,delete-orphan", order_by="WeeklyMenuItem.day_of_week"
    )


class WeeklyMenuItem(Base):
    __tablename__ = "weekly_menu_items"
    __table_args__ = (UniqueConstraint("weekly_menu_id", "day_of_week", "meal_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    weekly_menu_id: Mapped[int] = mapped_column(ForeignKey("weekly_menus.id", ondelete="CASCADE"))
    day_of_week: Mapped[int] = mapped_column(Integer, index=True)
    meal_type: Mapped[str] = mapped_column(String(20), index=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"))
    estimated_cost: Mapped[float] = mapped_column(Float, default=0)
    nutrition_assessment: Mapped[str] = mapped_column(Text, default="")

    weekly_menu: Mapped["WeeklyMenu"] = relationship(back_populates="items")
    dish: Mapped["Dish"] = relationship(back_populates="menu_items")
