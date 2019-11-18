import os
import requests
from werkzeug.security import generate_password_hash, check_password_hash

from flask import Flask, flash, session, render_template, request, redirect, url_for, escape, jsonify
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.exc import IntegrityError


app = Flask(__name__)

# check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

# keep track of user information
def user_info():
    user = {}
    user["id"] = str(escape(session.get("id", None)))
    user["username"] = str(escape(session.get("username", None)))
    user["first_name"] = str(escape(session.get("first_name", None))).capitalize()
    return user

# homepage
@app.route("/")
def index():
    user = user_info()
    return render_template("index.html")

# registration page
@app.route("/register", methods=["POST","GET"])
def register():
    error_message = None
    if request.method == "GET":
        return render_template("register.html", error_message= error_message)

    else:
        username = request.form.get("username")
        password = request.form.get("password")
        password2 = request.form.get("password2")
        first_name = request.form.get("first_name")

        # ensure proper usage
        if password != password2 or password is None or password2 is None:
            error_message = "Passwords don't match. Please try again."
            return render_template("register.html", error_message=error_message)

        user = db.execute("SELECT * FROM users WHERE username= :username", {"username": username}).fetchone()
        if user:
            error_message = "Username already taken."
            return render_template("register.html", error_message=error_message)

        try:
            db.execute("INSERT INTO users (username, password, first_name) VALUES (:username, :password, :first_name)",
                   {"username": username, "password": generate_password_hash(password), "first_name": first_name})
        except IntegrityError:
            return render_template("error.html", error_message="Something went wrong, please try again.")

        db.commit()
        session["logged_in"] = True
        session["first_name"] = first_name
    return render_template("index.html")

# login
@app.route("/login", methods=["POST", "GET"])
def login():
    user = None
    error_message = None

    if request.method == "GET":
        if session.get("logged_in"):
            return redirect(url_for("index"))
        else:
            return render_template("login.html")

    if request.method == "POST":
        try:
            username = request.form.get("username")
            password = request.form.get("password")
            user = db.execute("SELECT * FROM users WHERE username= :username", {"username": username}).fetchone()
            check_password = check_password_hash(user["password"], password)
            if check_password:
                session["logged_in"] = True
                session["id"] = user[0]
                session["username"] = user[1]
                session["first_name"] = user[3]
                return redirect(url_for("index"))
        except:
            error_message = "Invalid username or password."
    return render_template("login.html", user=user, error_message=error_message)

# logout
@app.route("/logout")
def logout():
    session.clear()
    session["logged_in"] = False
    return redirect(url_for("login"))


# search results
@app.route("/search", methods=["POST"])
def search():
    query = request.form.get("searchbox")
    query = "%" + query.lower() + "%"
    results = db.execute("SELECT * FROM books WHERE lower(title) LIKE :q OR isbn LIKE :q OR lower(author) LIKE :q", {"q": query}).fetchall()
    return render_template("search.html", results=results)


# individual book pages
@app.route("/<string:isbn>", methods=["GET", "POST"])
def info(isbn):
    user = user_info()
    if request.method == "POST":
        comment = request.form.get("comment")
        my_rating = request.form.get("rating")
        book = db.execute("INSERT INTO reviews (isbn, review, rating, username) VALUES (:a, :b, :c, :d)", {"a": isbn, "b": comment, "c": my_rating, "d": user["username"]})
        db.commit()

    book = db.execute("SELECT * FROM books WHERE isbn = :q", {"q": isbn}).fetchone()
    reviews = db.execute("SELECT * FROM reviews WHERE isbn = :isbn", {"isbn": isbn}).fetchall()
    res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": "TingtldrKhBrZBDizSXh3g", "isbns": isbn})
    data = res.json()
    goodreads_rating = (data["books"][0]["average_rating"])
    ratings_total = (data["books"][0]["work_ratings_count"])

    username_reviews = []
    for review in reviews:
        username_reviews += review.username

    return render_template("info.html", book_info=book, rating=goodreads_rating, reviews=reviews, ratings_total=ratings_total, username=user["username"], username_reviews=username_reviews)


# API access: JSON response
@app.route("/api/<string:isbn>")
def api(isbn):
    book = db.execute("SELECT * FROM books WHERE isbn = :q", {"q": isbn}).fetchone()

    if book is None:
        return render_template("error.html", error_message="404: invalid ISBN.")

    reviews = db.execute("SELECT * FROM reviews WHERE isbn = :isbn", {"isbn": isbn}).fetchall()
    res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": "TingtldrKhBrZBDizSXh3g", "isbns": isbn})
    data = res.json()["books"][0]

    return jsonify({
        "title": book.title,
        "author": book.author,
        "isbn": book.isbn,
        "review_count": data["reviews_count"],
        "average_rating": data["average_rating"]
    })
