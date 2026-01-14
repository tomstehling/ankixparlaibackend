import os
import json
from pathlib import Path
from dotenv import load_dotenv

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    Float,
    String,
    Text,
    Boolean,
    Enum,
    ForeignKey,
    TIMESTAMP,
    Table,
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.sql import func
import enum

# --- 1. SETUP AND CONFIGURATION ---

# Load environment variables from .env file
load_dotenv()
DATABASE_URL = os.getenv("SYNCHRONOUS_SUPABASE_STRING")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set.")

# Define base for ORM models
Base = declarative_base()

# --- 2. ORM MODEL DEFINITIONS (Must match your Alembic schema) ---


# Define Enum types to match the database
class CefrLevelEnum(enum.Enum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"


class HackTypeEnum(enum.Enum):
    RULE = "RULE"
    MNEMONIC = "MNEMONIC"
    CONSTRUCTION = "CONSTRUCTION"
    PATTERN = "PATTERN"
    DISTINCTION = "DISTINCTION"
    CONNECTOR = "CONNECTOR"


class HackTagRelationshipEnum(enum.Enum):
    TEACHES = "TEACHES"
    REQUIRES = "REQUIRES"
    REMEDIATES = "REMEDIATES"
    CO_REQUISITE = "CO_REQUISITE"


class TagRelationshipTypeEnum(enum.Enum):
    PREREQUISITE = "PREREQUISITE"
    DEPENDENCY = "DEPENDENCY"
    ANALOGY = "ANALOGY"
    REMEDIATION = "REMEDIATION"
    COREQUISITE = "COREQUISITE"
    IS_PARENT_OF = "IS_PARENT_OF"


# Association table for Tag <-> VerbLemma (many-to-many)
tag_archetype_lemmas_association = Table(
    "tag_archetype_lemmas",
    Base.metadata,
    Column(
        "tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "lemma_id",
        Integer,
        ForeignKey("verb_lemmas.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Tag(Base):
    __tablename__ = "tags"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    category = Column(String(50), nullable=False)
    subcategory = Column(String(50), nullable=False)
    logic_group = Column(String(50))
    cefr_level = Column(Enum(CefrLevelEnum), nullable=False)
    description = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    archetype_lemmas = relationship(
        "VerbLemma",
        secondary=tag_archetype_lemmas_association,
        back_populates="archetype_for_tags",
    )


class LearningHack(Base):
    __tablename__ = "learning_hacks"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    type = Column(Enum(HackTypeEnum), nullable=False)
    cefr_level = Column(Enum(CefrLevelEnum), nullable=False)
    short_description = Column(Text, nullable=False)
    long_description = Column(Text)
    example_front = Column(Text, nullable=False)
    example_back = Column(Text, nullable=False)


class VerbLemma(Base):
    __tablename__ = "verb_lemmas"
    id = Column(Integer, primary_key=True)
    lemma = Column(String(50), unique=True, nullable=False)
    frequent_forms = relationship(
        "FrequentVerbForm", back_populates="lemma", cascade="all, delete-orphan"
    )
    archetype_for_tags = relationship(
        "Tag",
        secondary=tag_archetype_lemmas_association,
        back_populates="archetype_lemmas",
    )


class FrequentVerbForm(Base):
    __tablename__ = "frequent_verb_forms"
    id = Column(Integer, primary_key=True)
    lemma_id = Column(
        Integer, ForeignKey("verb_lemmas.id", ondelete="CASCADE"), nullable=False
    )
    rank = Column(Integer, nullable=False)
    form = Column(String(50), nullable=False)
    tense = Column(String(50))
    person = Column(String(50))
    example = Column(Text)
    is_survival_essential = Column(Boolean, nullable=False, default=False)
    usage_notes = Column(Text)
    lemma = relationship("VerbLemma", back_populates="frequent_forms")


class HackToTagRelationship(Base):
    __tablename__ = "hack_to_tag_relationships"
    hack_id = Column(
        Integer, ForeignKey("learning_hacks.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id = Column(
        Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    relationship_type = Column(Enum(HackTagRelationshipEnum), primary_key=True)


class TagRelationship(Base):
    __tablename__ = "tag_relationships"
    source_tag_id = Column(
        Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    target_tag_id = Column(
        Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    relationship_type = Column(Enum(TagRelationshipTypeEnum), primary_key=True)
    weight = Column(Float, nullable=False, default=1.0)


# --- 3. SEEDING LOGIC ---


def seed_data():
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Define paths to data files
    DATA_DIR = Path(__file__).parent / "database/json-work/intelligent_engine_data"
    TAGS_FILE = DATA_DIR / "tags.json"
    HACKS_FILE = DATA_DIR / "learning_hacks.json"
    VERBS_FILE = DATA_DIR / "verbs.json"
    TAG_REL_FILE = DATA_DIR / "tag_relationships.json"
    TAG_HACK_REL_FILE = DATA_DIR / "tag_hack_relationships.json"
    TAG_LEMMA_REL_FILE = DATA_DIR / "tag_lemma_relationships.json"

    try:
        # --- Seed Tags ---
        print("Seeding tags...")
        with open(TAGS_FILE, "r") as f:
            for item in json.load(f):
                if not session.query(Tag).filter_by(name=item["name"]).first():
                    session.add(Tag(**item))
        session.commit()
        print("Tags seeded.")

        # --- Seed Learning Hacks ---
        print("Seeding learning hacks...")
        with open(HACKS_FILE, "r") as f:
            for item in json.load(f):
                if not session.query(LearningHack).filter_by(name=item["name"]).first():
                    if "type" in item and isinstance(item["type"], str):
                        item["type"] = item["type"].upper()  # Standardize to uppercase
                    session.add(LearningHack(**item))
        session.commit()
        print("Learning hacks seeded.")

        # --- Seed Verbs (Lemmas and Forms) ---
        print("Seeding verbs...")
        with open(VERBS_FILE, "r") as f:
            for item in json.load(f):
                if not session.query(VerbLemma).filter_by(lemma=item["lemma"]).first():
                    lemma_obj = VerbLemma(lemma=item["lemma"])
                    for form_data in item["frequent_forms"]:
                        lemma_obj.frequent_forms.append(FrequentVerbForm(**form_data))
                    session.add(lemma_obj)
        session.commit()
        print("Verbs seeded.")

        # --- Build Caches for Faster Relationship Lookups ---
        print("Building caches for relationship seeding...")
        all_tags = {tag.name: tag for tag in session.query(Tag).all()}
        all_hacks = {hack.name: hack for hack in session.query(LearningHack).all()}
        all_lemmas = {lemma.lemma: lemma for lemma in session.query(VerbLemma).all()}
        print("Caches built.")

        print("Seeding tag-to-tag relationships...")
        with open(TAG_REL_FILE, "r") as f:
            for item in json.load(f):
                # Using IDs directly from the JSON file
                src_id = item["source_tag_id"]
                tgt_id = item["target_tag_id"]
                rel_type = item["relationship_type"].upper()

                # Check if the relationship already exists
                exists = (
                    session.query(TagRelationship)
                    .filter_by(
                        source_tag_id=src_id,
                        target_tag_id=tgt_id,
                        relationship_type=rel_type,
                    )
                    .first()
                )

                if not exists:
                    # Create a dictionary of data to insert, removing keys that aren't columns
                    rel_data = {
                        "source_tag_id": src_id,
                        "target_tag_id": tgt_id,
                        "relationship_type": rel_type,
                        "weight": item.get(
                            "weight", 1.0
                        ),  # Use provided weight, or default to 1.0
                    }
                    session.add(TagRelationship(**rel_data))
        session.commit()
        print("Tag-to-tag relationships seeded.")
        # --- Seed Hack-to-Tag Relationships ---
        print("Seeding hack-to-tag relationships...")
        with open(TAG_HACK_REL_FILE, "r") as f:
            for item in json.load(f):
                tag = all_tags.get(item["name_tag"])
                hack = all_hacks.get(item["name_hack"])
                rel_type = item["relationship_type"].upper()
                if tag and hack:
                    if (
                        not session.query(HackToTagRelationship)
                        .filter_by(
                            hack_id=hack.id, tag_id=tag.id, relationship_type=rel_type
                        )
                        .first()
                    ):
                        session.add(
                            HackToTagRelationship(
                                hack_id=hack.id,
                                tag_id=tag.id,
                                relationship_type=rel_type,
                            )
                        )
        session.commit()
        print("Hack-to-tag relationships seeded.")

        # --- Seed Tag-to-Lemma Relationships ---
        print("Seeding tag-to-lemma relationships...")
        with open(TAG_LEMMA_REL_FILE, "r") as f:
            for tag_name, lemma_name in json.load(f):
                tag = all_tags.get(tag_name)
                lemma = all_lemmas.get(lemma_name)
                if tag and lemma and lemma not in tag.archetype_lemmas:
                    tag.archetype_lemmas.append(lemma)
        session.commit()
        print("Tag-to-lemma relationships seeded.")

    except Exception as e:
        print(f"\nAN ERROR OCCURRED: {e}\n")
        session.rollback()
        print("Transaction has been rolled back.")
    finally:
        session.close()
        print("Seeding process finished. Session closed.")


if __name__ == "__main__":
    seed_data()
