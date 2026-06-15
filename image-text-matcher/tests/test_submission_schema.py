from __future__ import annotations

import pytest

from app.schemas.submission import SubmissionCreate


def test_submission_schema_rejects_empty_images() -> None:
    with pytest.raises(ValueError, match="images must include a path"):
        SubmissionCreate(
            brand="Brand",
            classType="Wine",
            address="123 Main",
            netContents="750ml",
            alcohol="12%",
            warning="warning",
            category="category",
            images="   ",
        )


def test_submission_schema_accepts_camel_case_aliases() -> None:
    model = SubmissionCreate(
        brand="Brand",
        classType="Wine",
        address="123 Main",
        netContents="750ml",
        alcohol="12%",
        warning="warning",
        category="category",
        images="/data/images/one.png",
    )

    assert model.class_type == "Wine"
    assert model.net_contents == "750ml"


def test_submission_schema_allows_optional_alcohol_and_wine_appellation() -> None:
    model = SubmissionCreate(
        brand="Brand",
        classType="Wine",
        address="123 Main",
        netContents="750ml",
        warning="warning",
        category="Wine",
        images="/data/images/one.png",
    )

    assert model.alcohol is None
    assert model.appellation is None


def test_submission_schema_normalizes_blank_optional_fields() -> None:
    model = SubmissionCreate(
        brand="Brand",
        classType="Wine",
        address="123 Main",
        netContents="750ml",
        alcohol="12%",
        origin="  ",
        appellation="Bordeaux",
        warning="warning",
        category="Wine",
        images="/data/images/one.png",
    )

    assert model.origin is None


def test_submission_schema_normalizes_blank_alcohol() -> None:
    model = SubmissionCreate(
        brand="Brand",
        classType="Wine",
        address="123 Main",
        netContents="750ml",
        alcohol="  ",
        warning="warning",
        category="Wine",
        images="/data/images/one.png",
    )

    assert model.alcohol is None
