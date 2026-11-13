"""Catalog search, reviews, and manager book operations."""

from datetime import datetime, timezone
from decimal import Decimal
import re

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, current_app, g, request
from pymongo import ReturnDocument

from service import ApiError, json_object, require_auth, utc_timestamp


catalog = Blueprint("catalog", __name__)
MAX_QUANTITY = 2_147_483_647
MAX_AMOUNT = Decimal("99999999.99")
CENT = Decimal("0.01")


def books_collection():
    return current_app.extensions["books"]


def book_object_id(value):
    if not isinstance(value, str):
        raise ApiError(400, "book_id must be a MongoDB ObjectId")
    try:
        return ObjectId(value)
    except InvalidId as error:
        raise ApiError(400, "book_id must be a MongoDB ObjectId") from error


def price_amount(value, field):
    if type(value) not in (int, float):
        raise ApiError(400, f"{field} must be a numeric price")
    price = Decimal(str(value))
    if not price.is_finite() or not 0 <= price <= MAX_AMOUNT or price != price.quantize(CENT):
        raise ApiError(400, f"{field} must be a nonnegative price with at most two decimal places")
    return price.quantize(CENT)


def average_rating(reviews):
    if not reviews:
        return 0.0
    return round(sum(review["rating"] for review in reviews) / len(reviews), 2)


def serialize_book(book):
    reviews = book.get("reviews", [])
    return {
        "id": str(book["_id"]),
        "title": book["title"],
        "author": book["author"],
        "buy_price": book["buy_price"],
        "rent_price": book["rent_price"],
        "available_copies": book["available_copies"],
        "avg_rating": average_rating(reviews),
        "review_count": len(reviews),
        "reviews": reviews,
    }


def book_fields(payload):
    fields = {}
    for name in ("title", "author"):
        value = payload.get(name)
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 255:
            raise ApiError(400, f"{name} must contain 1–255 characters")
        fields[name] = value.strip()
    for name in ("buy_price", "rent_price"):
        fields[name] = float(price_amount(payload.get(name), name))
    copies = payload.get("available_copies")
    if type(copies) is not int or not 0 <= copies <= MAX_QUANTITY:
        raise ApiError(400, "available_copies must be a nonnegative integer in range")
    fields["available_copies"] = copies
    return fields


@catalog.get("/api/books")
@require_auth()
def search_books():
    keyword = request.args.get("q", "").strip()
    query = {}
    if keyword:
        match = {"$regex": re.escape(keyword), "$options": "i"}
        query = {"$or": [{"title": match}, {"author": match}]}
    books = books_collection().find(query).sort([("title", 1), ("_id", 1)])
    return {"books": [serialize_book(book) for book in books]}


@catalog.post("/api/books/<book_id>/reviews")
@require_auth(role="CUSTOMER")
def add_review(book_id):
    book_id = book_object_id(book_id)
    payload = json_object()
    rating = payload.get("rating")
    comment = payload.get("comment")
    if type(rating) is not int or not 1 <= rating <= 5:
        raise ApiError(400, "rating must be an integer from 1 to 5")
    if not isinstance(comment, str) or not comment.strip():
        raise ApiError(400, "comment must be a nonempty string")

    review = {
        "user_id": g.user["user_id"],
        "username": g.user["username"],
        "rating": rating,
        "comment": comment.strip(),
        "created_at": utc_timestamp(datetime.now(timezone.utc)),
    }
    book = books_collection().find_one_and_update(
        {"_id": book_id},
        {"$push": {"reviews": review}},
        projection={"reviews": 1},
        return_document=ReturnDocument.AFTER,
    )
    if book is None:
        raise ApiError(404, "Book not found")
    return {"message": "Review added", "avg_rating": average_rating(book["reviews"])}, 201


@catalog.post("/api/manager/books")
@require_auth(role="MANAGER")
def add_book():
    book = {**book_fields(json_object()), "reviews": []}
    book["_id"] = books_collection().insert_one(book).inserted_id
    return serialize_book(book), 201


@catalog.put("/api/manager/books/<book_id>")
@require_auth(role="MANAGER")
def update_book(book_id):
    book_id = book_object_id(book_id)
    fields = book_fields(json_object())
    with current_app.extensions["inventory_lock"]:
        book = books_collection().find_one_and_update(
            {"_id": book_id}, {"$set": fields}, return_document=ReturnDocument.AFTER
        )
    if book is None:
        raise ApiError(404, "Book not found")
    return serialize_book(book)
