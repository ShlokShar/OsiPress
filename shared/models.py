
from collections import defaultdict
from datetime import (
    date,
    datetime,
    timedelta,
    timezone
)
from typing import Optional

from sqlalchemy import (
    ForeignKey,
    ARRAY,
    String,
    DateTime,
    func
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from shared.database import Base, SessionLocal


class Countries(Base):
    __tablename__ = 'countries'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()

    @classmethod
    def get_country(cls, name: str = "", id: int = -1) -> Mapped[str]:
        with SessionLocal() as session:
            if id > 0:
                return session.query(cls).filter(cls.id == id).first()
            return session.query(cls).filter(cls.name == name).first()


class Sources(Base):
    __tablename__ = 'sources'

    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(ForeignKey('countries.id'))
    name: Mapped[str] = mapped_column()
    link: Mapped[str] = mapped_column()
    political_leaning: Mapped[str] = mapped_column()

    @classmethod
    def get_source(cls, country_id: int, source_id: int) -> Mapped[int]:
        with SessionLocal() as session:
            if source_id:
                return session.query(cls).filter(cls.id == source_id).first()
            return session.query(cls).filter(cls.country_id == country_id).first()

    @classmethod
    def get_source_by_name(cls, country_id: int, name: str):
        with SessionLocal() as session:
            return session.query(cls).filter(
                cls.country_id == country_id, cls.name == name
            ).first()


class Articles(Base):
    __tablename__ = 'articles'

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey('sources.id'))
    headline: Mapped[str] = mapped_column()
    translated_headline: Mapped[str] = mapped_column()
    link: Mapped[str] = mapped_column()
    summary: Mapped[str] = mapped_column()
    references_original: Mapped[list[str]] = mapped_column(ARRAY(String))
    references_translated: Mapped[list[str]] = mapped_column(ARRAY(String))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "source_id": self.source_id,
            "headline": self.headline,
            "translated_headline": self.translated_headline,
            "link": self.link,
            "summary": self.summary,
            "references_original": self.references_original,
            "references_translated": self.references_translated,
        }

    @staticmethod
    def add_article(article):
        with SessionLocal() as session:
            session.add(article)
            session.commit()


def get_headlines_by_country(target_date: Optional[date] = None):
    if target_date is None:
        target_date = datetime.now(timezone.utc).date()

    start = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    with SessionLocal() as session:
        latest_per_source = (
            session.query(
                Articles.source_id,
                func.max(Articles.captured_at).label("latest_captured_at")
            )
            .filter(Articles.captured_at >= start, Articles.captured_at < end)
            .group_by(Articles.source_id)
            .subquery()
        )

        results = (
            session.query(Countries.name, Sources.name, Sources.political_leaning, Articles)
            .join(Sources, Sources.country_id == Countries.id)
            .join(Articles, Articles.source_id == Sources.id)
            .join(
                latest_per_source,
                (Articles.source_id == latest_per_source.c.source_id)
                & (Articles.captured_at == latest_per_source.c.latest_captured_at)
            )
            .all()
        )

        output = defaultdict(dict)
        for country_name, source_name, political_leaning, article in results:
            if source_name not in output[country_name]:
                output[country_name][source_name] = {
                    "political_leaning": political_leaning,
                    "articles": [],
                }
            output[country_name][source_name]["articles"].append(article.to_dict())

    return output