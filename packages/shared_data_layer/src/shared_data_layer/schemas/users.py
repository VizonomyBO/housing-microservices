from datetime import datetime
from typing import Optional
from uuid import UUID

from .common import ORMBaseSchema


class UserRead(ORMBaseSchema):
    id: UUID
    email: str
    full_name: Optional[str] = None
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime
