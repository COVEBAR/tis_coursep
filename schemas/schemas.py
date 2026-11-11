from datetime import date
from decimal import Decimal
from typing import List, Optional, Any
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from enum import Enum

class ConvType(str, Enum):
    FOOD = 'Питание'
    ENTERTAINMENT = 'Развлечение'
    LANGUAGE = 'Язык'
    OTHER = 'Прочее'

# Convenience
class ConvenienceBase(BaseModel):
    name: str
    conv_type: ConvType

class ConvenienceResponse(ConvenienceBase):
    model_config = ConfigDict(from_attributes=True)

# Hotel
class HotelBase(BaseModel):
    name: str
    description: str | None
    city: str
    address: str
    phone_num: str
    email: EmailStr | None
    latitude: Decimal = Field(..., ge=-90, le=90)
    longitude: Decimal = Field(..., ge=-180, le=180)
    animals: bool = False

class HotelUpdate(BaseModel):
    name: str | None
    description: str | None
    city: str | None
    address: str | None
    phone_num: str | None
    email: str | None
    latitude: Decimal | None = Field(ge=-90, le=90)
    longitude: Decimal | None = Field(ge=-180, le=180)
    animals: bool = False

class HotelResponse(HotelBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    rooms: List["RoomResponse"] = []
    hotels_conveniences: List["HotelConvenienceResponse"] = []
    hotel_photos: List["HotelPhotoResponse"] = []


# Room
class RoomBase(BaseModel):
    id_hotel: int
    room_num: str = Field(..., max_length=20)
    capacity: int = Field(2, ge=1)
    num_of_rooms: int | None = Field(ge=1)
    price_per_night: float = Field(..., gt=0)
    has_wifi: bool = False
    has_tv: bool = False
    has_ac: bool = False
    has_minibar: bool = False
    is_smoking_allowed: bool = False

class RoomUpdate(BaseModel):
    id_hotel: int | None
    room_num: str | None = Field(max_length=20)
    capacity: int | None = Field(ge=1)
    num_of_rooms: int | None = Field(ge=1)
    price_per_night: float | None = Field(gt=0)
    has_wifi: bool | None
    has_tv: bool | None
    has_ac: bool | None
    has_minibar: bool | None
    is_smoking_allowed: bool | None

class RoomResponse(RoomBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# HotelConvenience
class HotelConvenienceBase(BaseModel):
    id_hotel: int
    id_convenience: str

class HotelConvenienceResponse(HotelConvenienceBase):
    model_config = ConfigDict(from_attributes=True)
    convenience: Optional[ConvenienceResponse] = None

# HotelSearchParams
class HotelSearchParams(BaseModel):
    city: str | None
    check_in: date | None
    check_out: date | None
    guests: int | None
    animals: bool | None
    min_price: float | None
    max_price: float | None
    has_wifi: bool | None
    has_tv: bool | None
    has_ac: bool | None
    has_minibar: bool | None
    conveniences: List[str] | None


# User
class UserBase(BaseModel):
    email: EmailStr = Field(..., max_length=319)
    first_name: str = Field(..., max_length=100)
    last_name: str = Field(..., max_length=100)
    phone: str | None
    password: str = Field(..., min_length=9)

    @field_validator('password')
    @classmethod
    def validate_password_length(cls, v: str) -> str:
        if len(v) <= 8:
            raise ValueError('Password must be longer than 8 characters')
        return v

    @field_validator('first_name', 'last_name')
    @classmethod
    def validate_name_no_digits(cls, v: str) -> str:
        if any(char.isdigit() for char in v):
            raise ValueError('First and last name must not contain digits')
        return v

    @field_validator('phone')
    @classmethod
    def validate_phone_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        import re
        pattern = r'^\+\d{1,3} \d{3} \d{3} \d{4}$'
        if not re.match(pattern, v):
            raise ValueError('Phone must be in format: +XXX XXX XXX XXXX')
        return v

class UserUpdate(BaseModel):
    email: EmailStr | None = Field(None, max_length=319)
    first_name: str | None = Field(None, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    phone: str | None = None
    password: str | None = Field(None, min_length=9)

    @field_validator('first_name', 'last_name')
    @classmethod
    def validate_name_no_digits(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if any(char.isdigit() for char in v):
            raise ValueError('Имя и фамилия не должны содержать цифры')
        return v

    @field_validator('phone')
    @classmethod
    def validate_phone_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        import re
        pattern = r'^\+\d{1,3} \d{3} \d{3} \d{4}$'
        if not re.match(pattern, v):
            raise ValueError('Phone must be in format: +XXX XXX XXX XXXX')
        return v

    @field_validator('password')
    @classmethod
    def validate_password_length(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if len(v) <= 8:
            raise ValueError('Password must be longer than 8 characters')
        return v

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    first_name: str
    last_name: str
    phone: str | None

# Booking
class BookingBase(BaseModel):
    id_room: int
    booker_id: int
    check_in: date
    check_out: date
    guests: int = Field(..., ge=1)
    animals: bool = False
    special_reqs: str | None = None

    @field_validator('check_out')
    @classmethod
    def validate_check_out_after_check_in(cls, v: date, info: Any) -> date:
        if 'check_in' in info.data and v <= info.data['check_in']:
            raise ValueError('Check-out date must be later than check-in date')
        return v

class BookingUpdate(BaseModel):
    id_room: int | None = None
    check_in: date | None = None
    check_out: date | None = None
    guests: int | None = Field(None, ge=1)
    animals: bool | None = None
    special_reqs: str | None = None

    @field_validator('check_out')
    @classmethod
    def validate_check_out_after_check_in(cls, v: date | None, info: Any) -> date | None:
        if v is not None and 'check_in' in info.data and info.data['check_in'] is not None:
            if v <= info.data['check_in']:
                raise ValueError('Check-out date must be later than check-in date')
        return v

class BookingResponse(BookingBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    room: Optional[RoomResponse] = None
    user: Optional[UserResponse] = None

# HotelPhoto
class HotelPhotoBase(BaseModel):
    id_hotel: int
    photo_url: str = Field(..., max_length=255)

class HotelPhotoResponse(HotelPhotoBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


HotelResponse.model_rebuild()
RoomResponse.model_rebuild()
HotelConvenienceResponse.model_rebuild()
BookingResponse.model_rebuild()