from sqlalchemy import String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from .db import Base

class Phrase(Base):
    __tablename__ = "phrases"

    phrase_id: Mapped[str] = mapped_column(String(10), primary_key = True) # "p001"
    hanzi: Mapped[str] = mapped_column(String(64), nullable = False) # 汉字
    pinyin: Mapped[str] = mapped_column(String(128), nullable = False) # pinyin with tone marks

    attempts = relationship("Attempt", back_populates = "phrase") # Phrase -> Attempt(s)

class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key = True, autoincrement = True) # attempt id
    phrase_id: Mapped[str] = mapped_column(String(10), ForeignKey("phrases.phrase_id"), nullable = False) # link to phrase

    created_at: Mapped[datetime] = mapped_column(DateTime, default = datetime.utcnow) # timestam

    file_url: Mapped[str] = mapped_column(Text, nullable = False) # uploaded audio URL
    score: Mapped[int] = mapped_column(Integer, nullable = True) # overall score (nullable if not compared yet)

    syllables_json: Mapped[str] = mapped_column(Text, default = "[]") # store per-syllable scores as JSON string
    plot_url: Mapped[str] = mapped_column(Text, default = "") # plot.png URL

    phrase = relationship("Phrase", back_populates = "attempts") # Attempt -> Phrase