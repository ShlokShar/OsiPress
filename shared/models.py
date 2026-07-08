
from collections import defaultdict

from sqlalchemy import ForeignKey, ARRAY, String
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


def get_headlines_by_country():
    with SessionLocal() as session:
        results = (
            session.query(Countries.name, Sources.name, Articles)
            .join(Sources, Sources.country_id == Countries.id)
            .join(Articles, Articles.source_id == Sources.id)
            .all()
        )

        output = defaultdict(lambda: defaultdict(list))
        for country_name, source_name, article in results:
            output[country_name][source_name].append(article.to_dict())

    return output
