import os
import re
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from .config import AFFAIR_STATUS_CHOICES, STATUS_CHOICES

_STATUS_VALUES = [v for v, _ in STATUS_CHOICES]
_AFFAIR_STATUS_VALUES = [v for v, _ in AFFAIR_STATUS_CHOICES]


def _coerce_optional_int(v):
    if v in (None, "", "None"):
        return None
    return int(v)


def _coerce_optional_float(v):
    if v in (None, "", "None"):
        return None
    return float(v)


class LandBase(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    location: str = Field(min_length=2, max_length=160)
    area: float = Field(gt=0, description="Area in square meters")
    price: float = Field(ge=0, description="Price in the local currency")
    owner_name: str = Field(min_length=2, max_length=120)
    description: Optional[str] = Field(default=None, max_length=2000)
    status: str = Field(default="Open")
    seller_id: Optional[int] = None

    @field_validator("title", "location", "owner_name")
    @classmethod
    def strip_strings(cls, v: str) -> str:
        return v.strip()

    @field_validator("seller_id", mode="before")
    @classmethod
    def coerce_seller_id(cls, v):
        return _coerce_optional_int(v)

    @field_validator("status")
    @classmethod
    def status_allowed(cls, v: str) -> str:
        v = (v or "").strip()
        if v not in _STATUS_VALUES:
            raise ValueError(
                f"status must be one of {', '.join(_STATUS_VALUES)}"
            )
        return v


class AffairBase(BaseModel):
    seller_id: Optional[int] = None
    land_id: Optional[int] = None
    buyer_id: Optional[int] = None
    status: str = Field(default="Open")
    agreed_price: Optional[float] = None
    deposit: Optional[float] = None
    commission: Optional[float] = None
    closing_date: Optional[str] = Field(default=None, max_length=20)
    notes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("seller_id", "land_id", "buyer_id", mode="before")
    @classmethod
    def coerce_ids(cls, v):
        return _coerce_optional_int(v)

    @field_validator("agreed_price", "deposit", "commission", mode="before")
    @classmethod
    def coerce_floats(cls, v):
        return _coerce_optional_float(v)

    @field_validator("status")
    @classmethod
    def status_allowed(cls, v: str) -> str:
        v = (v or "").strip()
        if v not in _AFFAIR_STATUS_VALUES:
            raise ValueError(
                f"status must be one of {', '.join(_AFFAIR_STATUS_VALUES)}"
            )
        return v


class AffairCreate(AffairBase):
    """Payload for creating an affair (validated with Pydantic)."""


class AffairUpdate(AffairBase):
    """Payload for updating an affair (validated with Pydantic)."""


class LandCreate(LandBase):
    """Payload for creating a new land (validated with Pydantic)."""


class LandUpdate(LandBase):
    """Payload for updating an existing land (validated with Pydantic)."""


class PartyBase(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: Optional[str] = Field(default=None, max_length=160)
    phone: str = Field(min_length=5, max_length=30)
    address: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("full_name", "phone")
    @classmethod
    def strip_strings(cls, v: str) -> str:
        return v.strip()

    @field_validator("email")
    @classmethod
    def email_valid(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("invalid email address")
        return v


class PartyCreate(PartyBase):
    """Payload for creating a customer or seller."""


class PartyUpdate(PartyBase):
    """Payload for updating a customer or seller."""


# Allowed media extensions (enforced both here and in the upload handler).
ALLOWED_PHOTO_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALLOWED_VIDEO_EXT = {".mp4", ".webm", ".ogg", ".mov", ".avi"}


def validate_media_files(files: List, allowed_ext: set, kind: str) -> List[str]:
    """Validate uploaded FileStorage objects.

    Returns a list of human readable error messages (empty when all OK).
    """
    errors: List[str] = []
    for f in files:
        if not f or not getattr(f, "filename", ""):
            continue
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in allowed_ext:
            errors.append(f"{kind} '{f.filename}' has an unsupported format")
    return errors
