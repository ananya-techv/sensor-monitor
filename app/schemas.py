from datetime import datetime

from pydantic import BaseModel, Field


class Reading(BaseModel):
    """What a valid reading looks like. Anything else is rejected with HTTP 422."""

    sensor_id: str = Field(min_length=1, max_length=50)
    timestamp: datetime
    value: float = Field(allow_inf_nan=False)
