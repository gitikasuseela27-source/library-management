# Library Management System
**Design and development of a real-time, database-driven application with GUI integration**

## Run
```
python main.py
```

## Database design
```
users(username PK, password_hash, role)
books(book_id PK, title, author, category, isbn UNIQUE, total_copies, available_copies)
members(member_id PK, name, email UNIQUE, phone, joined_date)
transactions(txn_id PK, book_id FK→books, member_id FK→members,
             issue_date, due_date, return_date, fine)
```
Relationships: one member → many transactions; one book → many transactions
(books ↔ members is many-to-many, resolved by `transactions`).

**Triggers** (real-time consistency inside the DB):
- `trg_issue` – inserting a transaction decrements `available_copies`.
- `trg_return` – setting `return_date` increments `available_copies`.

**Constraints:** `CHECK (0 <= available_copies <= total_copies)`, UNIQUE ISBN/email,
foreign keys (a book/member with history cannot be deleted).

## Features
- Login with SHA-256 hashed password
- Dashboard: titles, copies, available, members, issued, overdue, fines collected
- Books and Members: add / update / delete / live search
- Issue & Return: max 3 books per member, 14-day loan, fine Rs. 2/day after due date
- History with filters (All / Issued / Overdue / Returned); overdue loans shown in red
- **Real-time:** every screen re-queries the database every 3 seconds, so changes made by
  another instance of the app (same `library.db`) appear automatically

## Business rules (edit at top of `database.py`)
`LOAN_DAYS = 14`, `FINE_PER_DAY = 2`, `MAX_LOANS = 3`

## Possible extensions
Book reservation, barcode/ISBN scan, email reminders for overdue books, MySQL/PostgreSQL
backend for true multi-user access, role-based access (admin vs librarian).
