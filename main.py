from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload, joinedload

from typing import List, Optional
from datetime import date, timedelta
import jwt
from starlette.responses import Response

import models.models as models
import schemas.schemas as schemas
from funcs.auth import create_access_token, config
from funcs.hash import get_password_hash, verify_password
from funcs.rooms import check_room_capacity, check_room_availability

app = FastAPI(title="Hotel Booking API", version="1.0.0")


async def get_db() -> AsyncSession:
    async with models.AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# Проверка авторизации
async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
        db: AsyncSession = Depends(get_db)
) -> models.User:
    try:
        token = credentials.credentials

        # Декодировка токена
        try:
            payload = jwt.decode(
                token,
                config.JWT_SECRET_KEY,
                algorithms=["HS256"],
                options={"verify_exp": True}
            )
            user_id = payload.get("sub")

            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token: no subject"
                )

            user_id = int(user_id)

        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired"
            )
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}"
            )

        result = await db.execute(
            select(models.User).where(models.User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )

        return user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}"
        )


# 1. Бронирование
@app.post("/bookings", response_model=schemas.BookingResponse, status_code=status.HTTP_201_CREATED)
async def create_booking(
        booking_data: schemas.BookingBase,
        current_user: models.User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    # Проверка существования комнаты
    result = await db.execute(
        select(models.Room).where(models.Room.id == booking_data.id_room)
    )
    room = result.scalar_one_or_none()

    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found"
        )

    # Проверка доступности комнаты
    if not await check_room_availability(db, booking_data.id_room, booking_data.check_in, booking_data.check_out):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Room is not available for the selected dates"
        )

    # Проверка вместимости
    if not await check_room_capacity(db, booking_data.id_room, booking_data.guests):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Room capacity is {room.capacity}, but {booking_data.guests} guests requested"
        )

    # Проверка животных
    if booking_data.animals:
        result = await db.execute(
            select(models.Hotel.animals).join(
                models.Room, models.Room.id_hotel == models.Hotel.id
            ).where(models.Room.id == booking_data.id_room)
        )
        hotel_allows_animals = result.scalar_one_or_none()

        if not hotel_allows_animals:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Hotel does not allow animals"
            )

    # Создание брони
    booking = models.Booking(
        id_room=booking_data.id_room,
        booker_id=current_user.id,
        check_in=booking_data.check_in,
        check_out=booking_data.check_out,
        guests=booking_data.guests,
        animals=booking_data.animals,
        special_reqs=booking_data.special_reqs
    )

    db.add(booking)
    await db.commit()
    await db.refresh(booking)

    result = await db.execute(
        select(models.Booking)
        .options(joinedload(models.Booking.room), joinedload(models.Booking.user))
        .where(models.Booking.id == booking.id)
    )
    booking_with_relations = result.scalar_one()

    return booking_with_relations


# 2. Поиск отеля
@app.get("/hotels/search", response_model=List[schemas.HotelResponse])
async def search_hotels(
        city: str,
        check_in: date,
        check_out: date,
        guests: int,
        animals: bool = False,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        has_wifi: bool = False,
        has_tv: bool = False,
        has_ac: bool = False,
        has_minibar: bool = False,
        conveniences: Optional[str] = None,
        db: AsyncSession = Depends(get_db)
):
    # Въезд не раньше текущей даты
    if check_in < date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Check-in date cannot be earlier than today"
        )

    # Выезд позже въезда
    if check_out <= check_in:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Check-out date must be later than check-in date"
        )

    query = select(models.Hotel).options(
        selectinload(models.Hotel.rooms),
        selectinload(models.Hotel.hotels_conveniences).selectinload(models.HotelConvenience.convenience),
        selectinload(models.Hotel.hotel_photos)
    )

    # Фильтры
    filters = []

    filters.append(models.Hotel.city.ilike(f"%{city}%"))

    if animals == True:
        filters.append(models.Hotel.animals == animals)

    # Фильтры для комнат
    room_filters = []

    subquery = select(models.Booking.id_room).where(
        and_(
            models.Booking.check_out > check_in,
            models.Booking.check_in < check_out
        )
    ).subquery()

    room_filters.append(~models.Room.id.in_(select(subquery)))

    room_filters.append(models.Room.capacity >= guests)

    if min_price:
        room_filters.append(models.Room.price_per_night >= min_price)
    if max_price:
        room_filters.append(models.Room.price_per_night <= max_price)
    if has_wifi == True:
        room_filters.append(models.Room.has_wifi == has_wifi)
    if has_tv == True:
        room_filters.append(models.Room.has_tv == has_tv)
    if has_ac == True:
        room_filters.append(models.Room.has_ac == has_ac)
    if has_minibar == True:
        room_filters.append(models.Room.has_minibar == has_minibar)

    # Фильтры по удобствам
    if conveniences:
        convenience_list = [c.strip() for c in conveniences.split(',') if c.strip()]
        if convenience_list:
            convenience_filters = []
            for conv_name in convenience_list:
                subquery = select(models.HotelConvenience.id_hotel).where(
                    models.HotelConvenience.id_convenience == conv_name
                )
                convenience_filters.append(models.Hotel.id.in_(subquery))

            if convenience_filters:
                filters.append(and_(*convenience_filters))

    if room_filters:
        room_subquery = select(models.Room.id_hotel).where(and_(*room_filters)).distinct()
        filters.append(models.Hotel.id.in_(room_subquery))

    query = query.where(and_(*filters))

    result = await db.execute(query)
    hotels = result.scalars().all()

    # Фильтр комнат
    for hotel in hotels:
        if check_in and check_out and guests:
            available_rooms = []
            for room in hotel.rooms:
                is_available = await check_room_availability(db, room.id, check_in, check_out)
                if is_available and room.capacity >= guests:
                    available_rooms.append(room)
            hotel.rooms = available_rooms

    return hotels


# 3. Просмотр отеля
@app.get("/hotels/{hotel_id}", response_model=schemas.HotelResponse)
async def get_hotel(
        hotel_id: int,
        check_in: Optional[date] = Query(None),
        check_out: Optional[date] = Query(None),
        guests: Optional[int] = Query(None),
        animals: Optional[bool] = Query(None),
        db: AsyncSession = Depends(get_db)
):
    # Проверка дат, если они переданы
    if check_in:
        if check_in < date.today():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Check-in date cannot be earlier than today"
            )

        if check_out:
            if check_out <= check_in:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Check-out date must be later than check-in date"
                )

    query = select(models.Hotel).options(
        selectinload(models.Hotel.rooms),
        selectinload(models.Hotel.hotels_conveniences).selectinload(
            models.HotelConvenience.convenience
        ),
        selectinload(models.Hotel.hotel_photos)
    ).where(models.Hotel.id == hotel_id)

    result = await db.execute(query)
    hotel = result.scalar_one_or_none()

    if not hotel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hotel not found"
        )

    # Фильтрация комнат по параметрам
    if check_in and check_out and guests:
        available_rooms = []
        for room in hotel.rooms:
            # Проверка доступности комнаты
            is_available = await check_room_availability(db, room.id, check_in, check_out)
            if (is_available and
                    room.capacity >= guests and
                    (animals is None or hotel.animals == animals)):
                available_rooms.append(room)

        hotel.rooms = available_rooms

    return hotel


# 4. Просмотр броней
@app.get("/bookings/my", response_model=List[schemas.BookingResponse])
async def get_my_bookings(
        current_user: models.User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(models.Booking)
        .options(joinedload(models.Booking.room), joinedload(models.Booking.user))
        .where(models.Booking.booker_id == current_user.id)
        .order_by(models.Booking.check_in)
    )
    bookings = result.scalars().all()
    return bookings


# 5. Отмена брони
@app.delete("/bookings/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_booking(
        booking_id: int,
        current_user: models.User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(models.Booking).where(
            and_(
                models.Booking.id == booking_id,
                models.Booking.booker_id == current_user.id
            )
        )
    )
    booking = result.scalar_one_or_none()

    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found or you don't have permission to cancel it"
        )

    # Проверка возможности отмены брони
    if booking.check_in - date.today() < timedelta(days=1):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cancellation is only possible at least 1 day before check-in"
        )

    await db.delete(booking)
    await db.commit()


# 6. Изменение брони
@app.put("/bookings/{booking_id}", response_model=schemas.BookingResponse)
async def update_booking(
        booking_id: int,
        booking_update: schemas.BookingUpdate,
        current_user: models.User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(models.Booking).where(
            and_(
                models.Booking.id == booking_id,
                models.Booking.booker_id == current_user.id
            )
        )
    )
    booking = result.scalar_one_or_none()

    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found or you don't have permission to modify it"
        )

    # Проверка возможности изменения
    if booking.check_in - date.today() < timedelta(days=2):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Modification is only possible at least 48 hours before check-in"
        )

    update_data = booking_update.model_dump(exclude_unset=True)

    # Проверка доступности
    if 'id_room' in update_data or 'check_in' in update_data or 'check_out' in update_data:
        room_id = update_data.get('id_room', booking.id_room)
        check_in = update_data.get('check_in', booking.check_in)
        check_out = update_data.get('check_out', booking.check_out)

        is_available = await check_room_availability(
            db, room_id, check_in, check_out, exclude_booking_id=booking_id
        )

        if not is_available:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Room is not available for the selected dates"
            )

    for field, value in update_data.items():
        setattr(booking, field, value)

    await db.commit()
    await db.refresh(booking)

    result = await db.execute(
        select(models.Booking)
        .options(joinedload(models.Booking.room), joinedload(models.Booking.user))
        .where(models.Booking.id == booking.id)
    )
    booking_with_relations = result.scalar_one()

    return booking_with_relations


# 7. Регистрация
@app.post("/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
        user_data: schemas.UserBase,
        db: AsyncSession = Depends(get_db)
):
    # Проверка существования пользователя
    result = await db.execute(
        select(models.User).where(models.User.email == user_data.email)
    )
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
        )

    # Создание нового пользователя
    user = models.User(
        email=user_data.email,
        password_hash=get_password_hash(user_data.password),
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        phone=user_data.phone
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    return user


# 8. Авторизация
@app.post("/login")
async def login(
        email: str,
        password: str,
        response: Response,
        db: AsyncSession = Depends(get_db)
):
    # Поиск пользователя
    result = await db.execute(
        select(models.User).where(models.User.email == email)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # Создание токена
    token = create_access_token(user.id)
    response.set_cookie(config.JWT_ACCESS_COOKIE_NAME, token)
    return {"access_token": token,
            "user_id": user.id}


# Инициализация БД
@app.on_event("startup")
async def startup_event():
    await models.init_base()


# Запуск приложения
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", port=1121, reload=True)