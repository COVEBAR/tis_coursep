from sqlalchemy import Column, Integer, String, Text, Date, Boolean, Float, ForeignKey, DECIMAL, SmallInteger, \
    CheckConstraint
from sqlalchemy.schema import UniqueConstraint
import enum
from sqlalchemy.orm import relationship, DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

url_db = 'postgresql+asyncpg://postgres:p0S7S0m3Sh17@localhost:5432/postgres'

engine = create_async_engine(url_db, echo=True)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase): pass


# enum тип удобств
class ConvType(enum.Enum):
    FOOD = 'Питание'
    ENTERTAINMENT = 'Развлечение'
    LANGUAGE = 'Язык'
    OTHER = 'Прочее'


# Отели
class Hotel(Base):
    __tablename__ = 'hotels'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    city = Column(String, nullable=False, index=True)
    address = Column(String, nullable=False)
    phone_num = Column(String, nullable=False)
    email = Column(String(255))
    latitude = Column(DECIMAL(8, 6), nullable=False)
    longitude = Column(DECIMAL(9, 6), nullable=False)
    animals = Column(Boolean, default=False)

    __table_args__ = (
        CheckConstraint('latitude <= 90 AND latitude >= -90', name='latitude_size'),
        CheckConstraint('longitude <= 180 AND longitude >= -180', name='longitude_size'))

    rooms = relationship("Room", back_populates="hotel", cascade="all, delete-orphan")
    hotels_conveniences = relationship("HotelConvenience", back_populates="hotel", cascade="all, delete-orphan")
    hotel_photos = relationship("HotelPhoto", back_populates="hotel", cascade="all, delete-orphan")


# Номера
class Room(Base):
    __tablename__ = 'rooms'

    id = Column(Integer, primary_key=True, autoincrement=True)
    id_hotel = Column(Integer, ForeignKey('hotels.id', ondelete='CASCADE'), nullable=False)
    room_num = Column(String(20), nullable=False)
    capacity = Column(SmallInteger, default=2)
    num_of_rooms = Column(SmallInteger)
    price_per_night = Column(Float, nullable=False)
    has_wifi = Column(Boolean, default=False)
    has_tv = Column(Boolean, default=False)
    has_ac = Column(Boolean, default=False)
    has_minibar = Column(Boolean, default=False)
    is_smoking_allowed = Column(Boolean, default=False)

    hotel = relationship("Hotel", back_populates="rooms")
    bookings = relationship("Booking", back_populates="room", cascade="all, delete-orphan")


# Удобства
class Convenience(Base):
    __tablename__ = 'conveniences'

    name = Column(String, primary_key=True)
    conv_type = Column(PgEnum(ConvType), name='convience_type_enum')

    # Уникальность имени
    __table_args__ = (
        UniqueConstraint('name', name='uix_convenience_name'),
    )

    hotels_conveniences = relationship("HotelConvenience", back_populates="convenience", cascade="all, delete-orphan")


# Отели - Удобства
class HotelConvenience(Base):
    __tablename__ = 'hotels_conveniences'

    id_hotel = Column(Integer, ForeignKey('hotels.id', ondelete='CASCADE'), primary_key=True)
    id_convenience = Column(String, ForeignKey('conveniences.name', ondelete='CASCADE'), primary_key=True)

    hotel = relationship("Hotel", back_populates="hotels_conveniences")
    convenience = relationship("Convenience", back_populates="hotels_conveniences")


# Пользователи
class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    phone = Column(String(20))

    __table_args__ = (
        # Проверка формата телефона
        CheckConstraint(
            "phone IS NULL OR phone ~ '^\\+[0-9]{1,3} [0-9]{3} [0-9]{3} [0-9]{4}$'",
            name='check_phone_format'
        ),
        # Проверка длины email
        CheckConstraint(
            "LENGTH(email) < 320",
            name='check_email_length'
        ),
        # Проверка длины пароля
        CheckConstraint(
            "LENGTH(password_hash) > 8",
            name='check_password_length'
        ),
        # Проверка имени на отсутствие цифр
        CheckConstraint(
            "first_name !~ '[0-9]'",
            name='check_first_name_no_digits'
        ),
        # Проверка фамилии на отсутствие цифр
        CheckConstraint(
            "last_name !~ '[0-9]'",
            name='check_last_name_no_digits'
        ),
    )

    bookings = relationship("Booking", back_populates="user", cascade="all, delete-orphan")


# Бронь
class Booking(Base):
    __tablename__ = 'books'  # Оставляем оригинальное имя таблицы

    id = Column(Integer, primary_key=True, autoincrement=True)
    id_room = Column(Integer, ForeignKey('rooms.id', ondelete='CASCADE'), nullable=False)
    booker_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    check_in = Column(Date, nullable=False)
    check_out = Column(Date, nullable=False)
    guests = Column(SmallInteger, nullable=False)
    animals = Column(Boolean, default=False)
    special_reqs = Column(Text)

    room = relationship("Room", back_populates="bookings")
    user = relationship("User", back_populates="bookings")


# Фото отеля
class HotelPhoto(Base):
    __tablename__ = 'hotels_photos'

    id = Column(Integer, primary_key=True, autoincrement=True)
    id_hotel = Column(Integer, ForeignKey('hotels.id', ondelete='CASCADE'), nullable=False)
    photo_url = Column(String(255), nullable=False)  # Исправлено с room_num на photo_url

    hotel = relationship("Hotel", back_populates="hotel_photos")


async def init_base():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)