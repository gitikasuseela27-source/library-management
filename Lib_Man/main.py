"""
main.py - Tkinter GUI for the Library Management System.
Run:  python main.py        (default login: admin / admin123)
The screens auto-refresh from the database every few seconds, so changes
made by another running instance appear in near real time.
"""
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date

from database import LibraryDB, LOAN_DAYS, FINE_PER_DAY

REFRESH_MS = 3000


def make_tree(parent, columns, widths):
    frame = ttk.Frame(parent)
    tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
    for col, w in zip(columns, widths):
        tree.heading(col, text=col)
        tree.column(col, width=w, anchor="w")
    sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    return frame, tree


def fill(tree, rows):
    """Refresh a tree while keeping the current selection."""
    sel = tree.selection()
    keep = tree.item(sel[0], "values")[0] if sel else None
    tree.delete(*tree.get_children())
    for r in rows:
        iid = tree.insert("", "end", values=tuple(r))
        if keep is not None and str(r[0]) == str(keep):
            tree.selection_set(iid)
    return tree


class LoginWindow(tk.Tk):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.title("Library Management System - Login")
        self.geometry("340x230")
        self.resizable(False, False)
        f = ttk.Frame(self, padding=20)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Library Login", font=("Segoe UI", 16, "bold")).grid(columnspan=2, pady=(0, 15))
        ttk.Label(f, text="Username").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Label(f, text="Password").grid(row=2, column=0, sticky="w", pady=4)
        self.user = ttk.Entry(f, width=24)
        self.pw = ttk.Entry(f, width=24, show="*")
        self.user.grid(row=1, column=1)
        self.pw.grid(row=2, column=1)
        self.user.insert(0, "admin")
        ttk.Button(f, text="Login", command=self.try_login).grid(columnspan=2, pady=18)
        self.bind("<Return>", lambda e: self.try_login())
        self.pw.focus()
        self.ok = False

    def try_login(self):
        if self.db.login(self.user.get().strip(), self.pw.get()):
            self.ok = True
            self.destroy()
        else:
            messagebox.showerror("Login failed", "Invalid username or password.", parent=self)


class App(tk.Tk):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.title("Library Management System")
        self.geometry("1000x620")
        ttk.Style(self).theme_use("clam")

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.tabs = [DashboardTab(nb, db), BooksTab(nb, db), MembersTab(nb, db),
                     CirculationTab(nb, db), HistoryTab(nb, db)]
        for tab, name in zip(self.tabs, ["Dashboard", "Books", "Members", "Issue / Return", "History"]):
            nb.add(tab, text=name)
        self.status = ttk.Label(self, anchor="w", relief="sunken")
        self.status.pack(fill="x", side="bottom")
        self.refresh_all()

    def refresh_all(self):
        for t in self.tabs:
            t.refresh()
        self.status.config(text=f"  Live data from database - last refresh "
                                f"{date.today().isoformat()}  |  Loan period {LOAN_DAYS} days, "
                                f"fine Rs.{FINE_PER_DAY}/day")
        self.after(REFRESH_MS, self.refresh_all)   # real-time polling


# ------------------------------------------------------------------ Dashboard
class DashboardTab(ttk.Frame):
    def __init__(self, parent, db):
        super().__init__(parent, padding=20)
        self.db = db
        ttk.Label(self, text="Library Overview", font=("Segoe UI", 18, "bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 15))
        self.cards = {}
        for i, key in enumerate(db.stats()):
            card = ttk.LabelFrame(self, text=key, padding=15)
            card.grid(row=1 + i // 4, column=i % 4, padx=8, pady=8, sticky="nsew")
            lbl = ttk.Label(card, text="0", font=("Segoe UI", 22, "bold"), width=8)
            lbl.pack()
            self.cards[key] = lbl

    def refresh(self):
        for k, v in self.db.stats().items():
            self.cards[k].config(text=str(v))


# ------------------------------------------------------------------ Books
class BooksTab(ttk.Frame):
    FIELDS = ["Title", "Author", "Category", "ISBN", "Copies"]

    def __init__(self, parent, db):
        super().__init__(parent, padding=10)
        self.db = db
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="Search:").pack(side="left")
        self.search = tk.StringVar()
        e = ttk.Entry(top, textvariable=self.search, width=40)
        e.pack(side="left", padx=6)
        e.bind("<KeyRelease>", lambda ev: self.refresh())

        frame, self.tree = make_tree(self, ("ID", "Title", "Author", "Category", "ISBN", "Total", "Available"),
                                     (50, 280, 180, 120, 120, 60, 80))
        frame.pack(fill="both", expand=True, pady=8)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        form = ttk.LabelFrame(self, text="Book details", padding=10)
        form.pack(fill="x")
        self.vars = {f: tk.StringVar() for f in self.FIELDS}
        for i, f in enumerate(self.FIELDS):
            ttk.Label(form, text=f).grid(row=0, column=i, sticky="w", padx=4)
            ttk.Entry(form, textvariable=self.vars[f], width=22 if f != "Copies" else 8).grid(
                row=1, column=i, padx=4)
        btns = ttk.Frame(form)
        btns.grid(row=2, column=0, columnspan=5, pady=(10, 0), sticky="w")
        for text, cmd in [("Add", self.add), ("Update", self.update), ("Delete", self.delete),
                          ("Clear", self.clear)]:
            ttk.Button(btns, text=text, command=cmd).pack(side="left", padx=4)

    def refresh(self):
        fill(self.tree, [tuple(r) for r in self.db.list_books(self.search.get().strip())])

    def selected_id(self):
        sel = self.tree.selection()
        return int(self.tree.item(sel[0], "values")[0]) if sel else None

    def on_select(self, _):
        sel = self.tree.selection()
        if not sel:
            return
        v = self.tree.item(sel[0], "values")
        for f, val in zip(self.FIELDS, (v[1], v[2], v[3], v[4], v[5])):
            self.vars[f].set(val)

    def read_form(self):
        t, a = self.vars["Title"].get().strip(), self.vars["Author"].get().strip()
        if not t or not a:
            raise ValueError("Title and Author are required.")
        try:
            n = int(self.vars["Copies"].get())
            if n < 0:
                raise ValueError
        except ValueError:
            raise ValueError("Copies must be a non-negative number.")
        return t, a, self.vars["Category"].get().strip(), self.vars["ISBN"].get().strip(), n

    def guard(self, fn):
        try:
            fn()
            self.refresh()
        except sqlite3.IntegrityError as e:
            messagebox.showerror("Not allowed", f"Database constraint: {e}\n(Duplicate ISBN, or the "
                                                "book has transaction history.)")
        except ValueError as e:
            messagebox.showerror("Error", str(e))

    def add(self):
        self.guard(lambda: (self.db.add_book(*self.read_form()), self.clear()))

    def update(self):
        bid = self.selected_id()
        if bid is None:
            return messagebox.showinfo("Select", "Select a book first.")
        self.guard(lambda: self.db.update_book(bid, *self.read_form()))

    def delete(self):
        bid = self.selected_id()
        if bid is None:
            return messagebox.showinfo("Select", "Select a book first.")
        if messagebox.askyesno("Confirm", "Delete this book?"):
            self.guard(lambda: (self.db.delete_book(bid), self.clear()))

    def clear(self):
        for v in self.vars.values():
            v.set("")


# ------------------------------------------------------------------ Members
class MembersTab(ttk.Frame):
    FIELDS = ["Name", "Email", "Phone"]

    def __init__(self, parent, db):
        super().__init__(parent, padding=10)
        self.db = db
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="Search:").pack(side="left")
        self.search = tk.StringVar()
        e = ttk.Entry(top, textvariable=self.search, width=40)
        e.pack(side="left", padx=6)
        e.bind("<KeyRelease>", lambda ev: self.refresh())

        frame, self.tree = make_tree(self, ("ID", "Name", "Email", "Phone", "Joined"),
                                     (50, 220, 230, 130, 110))
        frame.pack(fill="both", expand=True, pady=8)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        form = ttk.LabelFrame(self, text="Member details", padding=10)
        form.pack(fill="x")
        self.vars = {f: tk.StringVar() for f in self.FIELDS}
        for i, f in enumerate(self.FIELDS):
            ttk.Label(form, text=f).grid(row=0, column=i, sticky="w", padx=4)
            ttk.Entry(form, textvariable=self.vars[f], width=28).grid(row=1, column=i, padx=4)
        btns = ttk.Frame(form)
        btns.grid(row=2, column=0, columnspan=3, pady=(10, 0), sticky="w")
        for text, cmd in [("Add", self.add), ("Update", self.update), ("Delete", self.delete),
                          ("Clear", self.clear)]:
            ttk.Button(btns, text=text, command=cmd).pack(side="left", padx=4)

    def refresh(self):
        fill(self.tree, [tuple(r) for r in self.db.list_members(self.search.get().strip())])

    def selected_id(self):
        sel = self.tree.selection()
        return int(self.tree.item(sel[0], "values")[0]) if sel else None

    def on_select(self, _):
        sel = self.tree.selection()
        if sel:
            v = self.tree.item(sel[0], "values")
            for f, val in zip(self.FIELDS, v[1:4]):
                self.vars[f].set(val)

    def read_form(self):
        name = self.vars["Name"].get().strip()
        if not name:
            raise ValueError("Name is required.")
        phone = self.vars["Phone"].get().strip()
        if phone and not phone.isdigit():
            raise ValueError("Phone must contain digits only.")
        return name, self.vars["Email"].get().strip(), phone

    def guard(self, fn):
        try:
            fn()
            self.refresh()
        except sqlite3.IntegrityError as e:
            messagebox.showerror("Not allowed", f"Database constraint: {e}\n(Duplicate email, or the "
                                                "member has transaction history.)")
        except ValueError as e:
            messagebox.showerror("Error", str(e))

    def add(self):
        self.guard(lambda: (self.db.add_member(*self.read_form()), self.clear()))

    def update(self):
        mid = self.selected_id()
        if mid is None:
            return messagebox.showinfo("Select", "Select a member first.")
        self.guard(lambda: self.db.update_member(mid, *self.read_form()))

    def delete(self):
        mid = self.selected_id()
        if mid is None:
            return messagebox.showinfo("Select", "Select a member first.")
        if messagebox.askyesno("Confirm", "Delete this member?"):
            self.guard(lambda: (self.db.delete_member(mid), self.clear()))

    def clear(self):
        for v in self.vars.values():
            v.set("")


# ------------------------------------------------------------------ Issue / Return
class CirculationTab(ttk.Frame):
    def __init__(self, parent, db):
        super().__init__(parent, padding=10)
        self.db = db
        issue = ttk.LabelFrame(self, text="Issue a book", padding=10)
        issue.pack(fill="x")
        self.book_id, self.member_id = tk.StringVar(), tk.StringVar()
        ttk.Label(issue, text="Book ID").grid(row=0, column=0, padx=4)
        ttk.Entry(issue, textvariable=self.book_id, width=10).grid(row=0, column=1, padx=4)
        ttk.Label(issue, text="Member ID").grid(row=0, column=2, padx=4)
        ttk.Entry(issue, textvariable=self.member_id, width=10).grid(row=0, column=3, padx=4)
        ttk.Button(issue, text="Issue Book", command=self.issue).grid(row=0, column=4, padx=10)

        ret = ttk.LabelFrame(self, text="Return a book (select a loan below)", padding=10)
        ret.pack(fill="x", pady=8)
        ttk.Button(ret, text="Return Selected Book", command=self.return_book).pack(side="left")

        ttk.Label(self, text="Books currently on loan (red = overdue)").pack(anchor="w")
        frame, self.tree = make_tree(self, ("Txn", "Book", "Member", "Issued", "Due", "Days late"),
                                     (50, 300, 180, 100, 100, 80))
        frame.pack(fill="both", expand=True)
        self.tree.tag_configure("late", foreground="#c0392b")

    def refresh(self):
        sel = self.tree.selection()
        keep = self.tree.item(sel[0], "values")[0] if sel else None
        self.tree.delete(*self.tree.get_children())
        today = date.today()
        for r in self.db.list_transactions("Issued"):
            late = max(0, (today - date.fromisoformat(r["due_date"])).days)
            iid = self.tree.insert("", "end", tags=("late",) if late else (),
                                   values=(r["txn_id"], r["title"], r["name"], r["issue_date"],
                                           r["due_date"], late))
            if keep is not None and str(r["txn_id"]) == str(keep):
                self.tree.selection_set(iid)

    def issue(self):
        try:
            title, name, due = self.db.issue_book(int(self.book_id.get()), int(self.member_id.get()))
        except ValueError as e:
            msg = str(e) if "invalid literal" not in str(e) else "Enter numeric Book ID and Member ID."
            return messagebox.showerror("Cannot issue", msg)
        messagebox.showinfo("Issued", f"'{title}' issued to {name}.\nDue date: {due}")
        self.book_id.set("")
        self.member_id.set("")
        self.refresh()

    def return_book(self):
        sel = self.tree.selection()
        if not sel:
            return messagebox.showinfo("Select", "Select a loan to return.")
        txn = int(self.tree.item(sel[0], "values")[0])
        try:
            fine = self.db.return_book(txn)
        except ValueError as e:
            return messagebox.showerror("Error", str(e))
        msg = "Book returned successfully."
        if fine:
            msg += f"\nOverdue fine to collect: Rs. {fine}"
        messagebox.showinfo("Returned", msg)
        self.refresh()


# ------------------------------------------------------------------ History
class HistoryTab(ttk.Frame):
    def __init__(self, parent, db):
        super().__init__(parent, padding=10)
        self.db = db
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="Show:").pack(side="left")
        self.status = tk.StringVar(value="All")
        cb = ttk.Combobox(top, textvariable=self.status, state="readonly", width=12,
                          values=["All", "Issued", "Overdue", "Returned"])
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        frame, self.tree = make_tree(self, ("Txn", "Book", "Member", "Issued", "Due", "Returned", "Fine (Rs.)"),
                                     (50, 280, 160, 100, 100, 100, 80))
        frame.pack(fill="both", expand=True, pady=8)

    def refresh(self):
        fill(self.tree, [(r["txn_id"], r["title"], r["name"], r["issue_date"], r["due_date"],
                          r["return_date"] or "-", r["fine"]) for r in self.db.list_transactions(self.status.get())])


if __name__ == "__main__":
    db = LibraryDB()
    login = LoginWindow(db)
    login.mainloop()
    if login.ok:
        App(db).mainloop()
