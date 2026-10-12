import uuid

from pydantic import EmailStr

from app.schemas.common import InputModel, OutputModel, UpdateModel, text_field

Name = text_field(200)
Phone = text_field(50)
JobTitle = text_field(150)


class ContactCreate(InputModel):
    name: Name
    company_id: uuid.UUID
    email: EmailStr
    phone: Phone
    job_title: JobTitle


class ContactUpdate(UpdateModel):
    name: Name | None = None
    company_id: uuid.UUID | None = None
    email: EmailStr | None = None
    phone: Phone | None = None
    job_title: JobTitle | None = None


class ContactRead(OutputModel):
    name: str
    company_id: uuid.UUID
    email: str
    phone: str
    job_title: str
