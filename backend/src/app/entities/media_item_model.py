from pydantic import BaseModel, Field
from typing import Literal

class MediaItem(BaseModel):
    title: str = Field(..., description="Title of the audiovisual work")
    director: str | None = Field(None, description="Primary director (if known)")
    cast: list[str] = Field(default_factory=list, description="List of cast members")
    genre: list[str] = Field(default_factory=list, description="List of genres")
    description: str | None = Field(None, description="Short synopsis or description")
    duration_min: int | None = Field(
        None, description="Duration in minutes, if applicable"
    )
    type: Literal["Movie", "TV Show"] | str = Field(..., description="Type of work")

    class Config:
        extra = "ignore"

    def duration_category(self) -> str | None:
        """Classify the media item by duration."""
        if self.duration_min is None:
            return None
        if self.duration_min <= 90:
            return "short"
        elif self.duration_min <= 120:
            return "Medium"
        else:
            return "Long"

    def __str__(self):
        parts = [f"Title: {self.title}."]
        if self.director:
            parts.append(f"Director: {self.director}.")
        if self.cast:
            parts.append(f"Cast: {', '.join(self.cast)}.")
        if self.genre:
            parts.append(f"Genre: {', '.join(self.genre)}.")
        if self.description:
            parts.append(f"Synopsis: {self.description}")
        if self.duration_category():
            parts.append(f"Duration: {self.duration_category()}.")
        return " ".join(parts).strip()
