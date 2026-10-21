from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class ConsentInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: str = Field(min_length=1, max_length=100)
    subject_name: str = Field(min_length=3, max_length=310)
    service: StrictBool
    analytics: StrictBool = False

    @field_validator('subject_name', mode='before')
    @classmethod
    def normalize_name(cls, value):
        return ' '.join(value.split()) if isinstance(value, str) else value

    @field_validator('subject_name')
    @classmethod
    def full_name(cls, value: str):
        if len(value.split()) < 2 or any(ord(char) < 32 for char in value):
            raise ValueError('Укажите фамилию, имя и отчество, если оно есть в документе')
        return value

    @field_validator('service')
    @classmethod
    def require_service(cls, value: bool):
        if value is not True:
            raise ValueError('Для аккаунта и заказов необходимо согласие на обработку данных')
        return value
