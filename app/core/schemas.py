"""Shared transport schemas used across API modules."""
from pydantic import BaseModel, ConfigDict


class ValidationIssue(BaseModel):
    type: str
    loc: list[str | int]
    msg: str


class ErrorResponse(BaseModel):
    """Standard API error shown in Swagger/OpenAPI documentation."""

    model_config = ConfigDict(
        json_schema_extra={
            'examples': [
                {'detail': 'Описание ошибки'}
            ]
        }
    )

    detail: str | list[ValidationIssue]
