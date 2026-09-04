from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from app.models import AccountType, ApplicationStatus
from app.validators import require_non_blank, validate_date_of_birth, validate_phone


class ApplicationCreate(BaseModel):
    full_name: str
    date_of_birth: date
    id_number: str
    address: str
    email: EmailStr
    phone: str
    account_type: AccountType

    @field_validator("full_name")
    @classmethod
    def _full_name_not_blank(cls, v: str) -> str:
        return require_non_blank(v, "Full name")

    @field_validator("id_number")
    @classmethod
    def _id_number_not_blank(cls, v: str) -> str:
        return require_non_blank(v, "ID number")

    @field_validator("address")
    @classmethod
    def _address_not_blank(cls, v: str) -> str:
        return require_non_blank(v, "Address")

    @field_validator("date_of_birth")
    @classmethod
    def _dob_not_future(cls, v: date) -> date:
        return validate_date_of_birth(v)

    @field_validator("phone")
    @classmethod
    def _phone_valid(cls, v: str) -> str:
        return validate_phone(v)


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reference_id: str
    status: ApplicationStatus
    submitted_at: datetime
    full_name: str
    date_of_birth: date
    id_number: str
    address: str
    email: str
    phone: str
    account_type: AccountType


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime
    preview_url: str
