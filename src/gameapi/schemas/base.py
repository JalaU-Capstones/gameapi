from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict
from pydantic.alias_generators import to_camel

ObjectIdStr = Annotated[str, BeforeValidator(lambda value: str(value))]


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        str_strip_whitespace=True,
    )
