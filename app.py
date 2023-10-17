import os
import datetime

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Generate portfolio of user's current holdings
    portfolio = db.execute("SELECT symbol, SUM(CASE WHEN type = 'buy' THEN shares ELSE -shares END) AS total_shares FROM transactions WHERE id = ? GROUP BY symbol", session["user_id"])

    # Add each stock's current price to the dictionary.
    running_total = 0
    for row in portfolio:
        running_total += lookup(row['symbol'])['price'] * row['total_shares']
        row['symbol'] = row['symbol'].upper()
        row['price'] = usd(lookup(row['symbol'])['price'])
        row["TOTAL"] = usd(lookup(row['symbol'])['price'] * row['total_shares'])

    # Add the user's current cash and calculate a total portfolio value
    user = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
    user[0]["TOTAL"] = usd(user[0]['cash'] + running_total)
    user[0]["cash"] = usd(user[0]['cash'])
    return render_template("index.html", portfolio=portfolio, user=user)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")
    else:
        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))
        if not type(shares) == int or shares < 1:
            return apology("Invalid share count")
        stock_info = lookup(symbol)
        if not stock_info:
            return apology("Invalid Symbol")

        # Get the user's info from the database
        user = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
        transaction_cost = stock_info["price"] * shares
        if user[0]["cash"] < transaction_cost:
            return apology("Cannot Afford Purchase")
        timestamp = datetime.datetime.now().replace(microsecond=0)

        # Conduct the purchase
        db.execute("INSERT INTO transactions (symbol, price, shares, cost, type, id, timestamp) VALUES(?, ?, ?, ?, ?, ?, ?)", symbol, stock_info["price"], shares, transaction_cost, "buy", session["user_id"], timestamp)

        # Update user's cash balance
        new_balance = user[0]["cash"] - transaction_cost
        db.execute("UPDATE users SET cash = ? WHERE id = ?", new_balance, session["user_id"])
        return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = db.execute("SELECT * FROM transactions WHERE id = ?", session["user_id"])
    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")
    else:
        symbol = request.form.get("symbol")
        stock_info = lookup(symbol)
        if not stock_info:
            return apology("Stock not found.")
        return render_template("quoted.html", stock=stock_info)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    else:
        # Check if username is taken
        if len(db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))) != 0:
            return apology("Username already registered.")

        # Register new user
        if request.form.get("username") and request.form.get("password") and request.form.get("confirmation") and request.form.get("password") == request.form.get("confirmation"):
            username = request.form.get("username")
            hashed_password = generate_password_hash(request.form.get("password"))
            db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", username, hashed_password)
            return redirect("/")
        else:
            return apology("Invalid registration information.")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    portfolio = db.execute("SELECT symbol, SUM(CASE WHEN type = 'buy' THEN shares ELSE -shares END) AS total_shares FROM transactions WHERE id = ? GROUP BY symbol", session["user_id"])
    if request.method == "GET":
        return render_template('/sell.html', portfolio=portfolio)
    else:
        symbol = request.form.get('symbol')
        shares = int(request.form.get('shares'))
        if not symbol:
            return apology("Please enter a symbol")

        # Make sure user has enough shares to sell
        for stock in portfolio:
            if stock['symbol'] == symbol:
                if stock["total_shares"] < shares:
                    return apology("Insufficent Stock")

        # Insert transaction into database
        stock_info = lookup(symbol)
        transaction_cost = stock_info["price"] * shares
        timestamp = datetime.datetime.now().replace(microsecond=0)
        db.execute("INSERT INTO transactions (symbol, price, shares, cost, type, id, timestamp) VALUES(?, ?, ?, ?, ?, ?, ?)", symbol, stock_info["price"], shares, transaction_cost, "sell", session["user_id"], timestamp)\

        # Reflect transaction on user's cash balance
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", transaction_cost, session["user_id"])
        return redirect("/")
