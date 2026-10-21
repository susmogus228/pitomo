"""Public review and discussion response schemas."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReviewCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    order_id: int = Field(gt=0, le=2147483647)
    rating: int = Field(ge=1, le=5)
    body: str = Field(min_length=10, max_length=2000)


class ReviewUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    rating: int | None = Field(default=None, ge=1, le=5)
    body: str | None = Field(default=None, min_length=10, max_length=2000)


class ReplyCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    body: str = Field(min_length=1, max_length=2000)
    parent_reply_id: int | None = Field(default=None, gt=0, le=2147483647)
    official: bool = False


class ReplyUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    body: str = Field(min_length=1, max_length=2000)


class PhotoResponse(BaseModel):
    id: int
    url: str


class ReplyResponse(BaseModel):
    id: int
    parent_reply_id: int | None
    author_id: int
    author_name: str
    body: str
    created_at: datetime
    updated_at: datetime
    edited_at: datetime | None = None
    is_edited: bool = False
    is_official: bool
    is_pinned: bool
    is_deleted: bool
    photos: list[PhotoResponse]


class ReviewResponse(BaseModel):
    id: int
    rating: int
    body: str
    created_at: datetime
    updated_at: datetime
    edited_at: datetime | None = None
    is_edited: bool = False
    verified_purchase: bool = False
    is_hidden: bool = False
    author_id: int
    author_name: str
    is_deleted: bool
    photos: list[PhotoResponse]
    replies: list[ReplyResponse]


class ReviewPage(BaseModel):
    items: list[ReviewResponse]
    total: int
    average_rating: float | None
    summary_total: int = 0
    rating_distribution: dict[str, int] = Field(default_factory=dict)
