from pydantic import EmailStr

from app.models.enums import CompanyStatus
from app.schemas.common import InputModel, OutputModel, UpdateModel, text_field

Name = text_field(200)
Industry = text_field(100)
Phone = text_field(50)
Location = text_field(200)


class CompanyCreate(InputModel):
    name: Name
    industry: Industry
    email: EmailStr
    phone: Phone
    location: Location
    status: CompanyStatus = CompanyStatus.PROSPECT


class CompanyUpdate(UpdateModel):
    name: Name | None = None
    industry: Industry | None = None
    email: EmailStr | None = None
    phone: Phone | None = None
    location: Location | None = None
    status: CompanyStatus | None = None


class CompanyRead(OutputModel):
    name: str
    industry: str
    email: str
    phone: str
    location: str
    status: CompanyStatus
