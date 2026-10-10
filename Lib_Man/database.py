"""
database.py - Data layer for the Library Management System (SQLite).
All business rules (loan limit, fine calculation) live here, and the
stock counts are kept consistent by DATABASE TRIGGERS, so any client
that touches the DB sees correct, real-time data.
"""
import sqlite3
import hashlib
from datetime import date, timedelta

DB_FILE = "library.db"
LOAN_DAYS = 14          # days a book can be kept
FINE_PER_DAY = 2        # fine in Rs. per overdue day
MAX_LOANS = 3           # max books a member can hold at once

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'librarian'
);

CREATE TABLE IF NOT EXISTS books (
    book_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title            TEXT NOT NULL,
    author           TEXT NOT NULL,
    category         TEXT,
    isbn             TEXT UNIQUE,
    total_copies     INTEGER NOT NULL CHECK (total_copies >= 0),
    available_copies INTEGER NOT NULL,
    CHECK (available_copies >= 0 AND available_copies <= total_copies)
);

CREATE TABLE IF NOT EXISTS members (
    member_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    email       TEXT UNIQUE,
    phone       TEXT,
    joined_date TEXT NOT NULL DEFAULT (date('now'))
);

CREATE TABLE IF NOT EXISTS transactions (
    txn_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id     INTEGER NOT NULL REFERENCES books(book_id),
    member_id   INTEGER NOT NULL REFERENCES members(member_id),
    issue_date  TEXT NOT NULL,
    due_date    TEXT NOT NULL,
    return_date TEXT,
    fine        INTEGER NOT NULL DEFAULT 0
);

-- Issuing a book reduces available stock automatically
CREATE TRIGGER IF NOT EXISTS trg_issue
AFTER INSERT ON transactions
BEGIN
    UPDATE books SET available_copies = available_copies - 1
    WHERE book_id = NEW.book_id;
END;

-- Returning a book restores stock automatically
CREATE TRIGGER IF NOT EXISTS trg_return
AFTER UPDATE OF return_date ON transactions
WHEN OLD.return_date IS NULL AND NEW.return_date IS NOT NULL
BEGIN
    UPDATE books SET available_copies = available_copies + 1
    WHERE book_id = NEW.book_id;
END;
"""


def hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


class LibraryDB:
    def __init__(self, path: str = DB_FILE):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._seed()

    # ------------------------------------------------------------ setup
    def _seed(self):
        c = self.conn
        if not c.execute("SELECT 1 FROM users").fetchone():
            c.execute("INSERT INTO users VALUES (?,?,?)",
                      ("admin", hash_pw("admin123"), "admin"))
        if not c.execute("SELECT 1 FROM books").fetchone():
            books = [
                ("Database System Concepts", "Silberschatz, Korth", "Computer Science", "9780078022159", 3),
                ("Fundamentals of Database Systems", "Elmasri, Navathe", "Computer Science", "9780133970777", 2),
                ("Python Crash Course", "Eric Matthes", "Programming", "9781593279288", 4),
                ("Introduction to Algorithms", "Cormen et al.", "Computer Science", "9780262033848", 2),
                ("Wings of Fire", "A.P.J. Abdul Kalam", "Biography", "9788173711466", 5),
            ]
            for t, a, cat, isbn, n in books:
                c.execute("INSERT INTO books(title,author,category,isbn,total_copies,available_copies) "
                          "VALUES (?,?,?,?,?,?)", (t, a, cat, isbn, n, n))
        if not c.execute("SELECT 1 FROM members").fetchone():
            c.execute("INSERT INTO members(name,email,phone) VALUES ('Arun Kumar','arun@example.com','9876543210')")
            c.execute("INSERT INTO members(name,email,phone) VALUES ('Priya S','priya@example.com','9123456780')")
        c.commit()

    # ------------------------------------------------------------ auth
    def login(self, username, password) -> bool:
        row = self.conn.execute("SELECT password_hash FROM users WHERE username=?",
                                (username,)).fetchone()
        return bool(row and row["password_hash"] == hash_pw(password))

    # ------------------------------------------------------------ books
    def list_books(self, term=""):
        like = f"%{term}%"
        return self.conn.execute(
            "SELECT * FROM books WHERE title LIKE ? OR author LIKE ? OR category LIKE ? "
            "OR isbn LIKE ? OR CAST(book_id AS TEXT)=? ORDER BY book_id",
            (like, like, like, like, term)).fetchall()

    def add_book(self, title, author, category, isbn, copies):
        with self.conn:
            self.conn.execute(
                "INSERT INTO books(title,author,category,isbn,total_copies,available_copies) "
                "VALUES (?,?,?,?,?,?)", (title, author, category, isbn or None, copies, copies))

    def update_book(self, book_id, title, author, category, isbn, copies):
        row = self.conn.execute("SELECT total_copies, available_copies FROM books WHERE book_id=?",
                                (book_id,)).fetchone()
        if not row:
            raise ValueError("Book not found.")
        issued = row["total_copies"] - row["available_copies"]
        if copies < issued:
            raise ValueError(f"{issued} copies are currently issued; total cannot be below that.")
        with self.conn:
            self.conn.execute(
                "UPDATE books SET title=?, author=?, category=?, isbn=?, total_copies=?, "
                "available_copies=? WHERE book_id=?",
                (title, author, category, isbn or None, copies, copies - issued, book_id))

    def delete_book(self, book_id):
        with self.conn:
            self.conn.execute("DELETE FROM books WHERE book_id=?", (book_id,))

    # ------------------------------------------------------------ members
    def list_members(self, term=""):
        like = f"%{term}%"
        return self.conn.execute(
            "SELECT * FROM members WHERE name LIKE ? OR email LIKE ? OR phone LIKE ? "
            "OR CAST(member_id AS TEXT)=? ORDER BY member_id", (like, like, like, term)).fetchall()

    def add_member(self, name, email, phone):
        with self.conn:
            self.conn.execute("INSERT INTO members(name,email,phone) VALUES (?,?,?)",
                              (name, email or None, phone))

    def update_member(self, member_id, name, email, phone):
        with self.conn:
            self.conn.execute("UPDATE members SET name=?, email=?, phone=? WHERE member_id=?",
                              (name, email or None, phone, member_id))

    def delete_member(self, member_id):
        with self.conn:
            self.conn.execute("DELETE FROM members WHERE member_id=?", (member_id,))

    # ------------------------------------------------------------ circulation
    def issue_book(self, book_id, member_id):
        c = self.conn
        book = c.execute("SELECT title, available_copies FROM books WHERE book_id=?",
                         (book_id,)).fetchone()
        member = c.execute("SELECT name FROM members WHERE member_id=?", (member_id,)).fetchone()
        if not book:
            raise ValueError("Book ID not found.")
        if not member:
            raise ValueError("Member ID not found.")
        if book["available_copies"] <= 0:
            raise ValueError(f"No copies of '{book['title']}' are available.")
        active = c.execute("SELECT COUNT(*) FROM transactions WHERE member_id=? AND return_date IS NULL",
                           (member_id,)).fetchone()[0]
        if active >= MAX_LOANS:
            raise ValueError(f"{member['name']} already has {MAX_LOANS} books issued.")
        if c.execute("SELECT 1 FROM transactions WHERE member_id=? AND book_id=? AND return_date IS NULL",
                     (member_id, book_id)).fetchone():
            raise ValueError("This member already has this book.")
        today = date.today()
        with c:
            c.execute("INSERT INTO transactions(book_id,member_id,issue_date,due_date) VALUES (?,?,?,?)",
                      (book_id, member_id, today.isoformat(),
                       (today + timedelta(days=LOAN_DAYS)).isoformat()))
        return book["title"], member["name"], today + timedelta(days=LOAN_DAYS)

    def return_book(self, txn_id):
        c = self.conn
        t = c.execute("SELECT * FROM transactions WHERE txn_id=?", (txn_id,)).fetchone()
        if not t:
            raise ValueError("Transaction not found.")
        if t["return_date"]:
            raise ValueError("This book was already returned.")
        late = (date.today() - date.fromisoformat(t["due_date"])).days
        fine = max(0, late) * FINE_PER_DAY
        with c:
            c.execute("UPDATE transactions SET return_date=?, fine=? WHERE txn_id=?",
                      (date.today().isoformat(), fine, txn_id))
        return fine

    def list_transactions(self, status="All"):
        q = ("SELECT t.txn_id, b.title, m.name, t.issue_date, t.due_date, t.return_date, t.fine, "
             "t.book_id, t.member_id FROM transactions t "
             "JOIN books b ON b.book_id=t.book_id JOIN members m ON m.member_id=t.member_id ")
        today = date.today().isoformat()
        args = ()
        if status == "Issued":
            q += "WHERE t.return_date IS NULL "
        elif status == "Overdue":
            q += "WHERE t.return_date IS NULL AND t.due_date < ? "
            args = (today,)
        elif status == "Returned":
            q += "WHERE t.return_date IS NOT NULL "
        q += "ORDER BY t.txn_id DESC"
        return self.conn.execute(q, args).fetchall()

    # ------------------------------------------------------------ stats
    def stats(self):
        c = self.conn
        today = date.today().isoformat()
        one = lambda q, a=(): c.execute(q, a).fetchone()[0]
        return {
            "Book titles": one("SELECT COUNT(*) FROM books"),
            "Total copies": one("SELECT COALESCE(SUM(total_copies),0) FROM books"),
            "Available copies": one("SELECT COALESCE(SUM(available_copies),0) FROM books"),
            "Members": one("SELECT COUNT(*) FROM members"),
            "Currently issued": one("SELECT COUNT(*) FROM transactions WHERE return_date IS NULL"),
            "Overdue": one("SELECT COUNT(*) FROM transactions WHERE return_date IS NULL AND due_date < ?",
                           (today,)),
            "Fines collected (Rs.)": one("SELECT COALESCE(SUM(fine),0) FROM transactions"),
        }
