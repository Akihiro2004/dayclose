"""Reminder rules and transactional local storage. No GUI or shutdown side effects."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3

STATUSES = ("Active", "Paused", "Completed")


def minute(value: str) -> int:
    if len(value) != 5 or value[2] != ":" or not (value[:2] + value[3:]).isascii() or not (value[:2] + value[3:]).isdigit():
        raise ValueError("Use 24-hour time, for example 09:00 or 22:30.")
    hour, minutes = int(value[:2]), int(value[3:])
    if hour > 23 or minutes > 59:
        raise ValueError("Hours must be 00–23 and minutes must be 00–59.")
    return hour * 60 + minutes


@dataclass
class Reminder:
    title: str
    notes: str = ""
    status: str = "Active"
    start: str = "18:00"
    end: str = "23:00"
    all_day: bool = True
    id: int | None = None

    def validate(self):
        self.title = self.title.strip()
        if not self.title or len(self.title) > 200:
            raise ValueError("Enter a title between 1 and 200 characters.")
        if len(self.notes) > 20000:
            raise ValueError("Keep notes under 20,000 characters.")
        if self.status not in STATUSES:
            raise ValueError("Choose Active, Paused, or Completed.")
        begin, end = minute(self.start), minute(self.end)
        if not self.all_day and begin == end:
            raise ValueError("Start and end must differ. Use All day for a full day.")

    def due(self, now: datetime) -> bool:
        if self.status != "Active":
            return False
        if self.all_day:
            return True
        current = now.hour * 60 + now.minute
        begin, end = minute(self.start), minute(self.end)
        return begin <= current < end if begin < end else current >= begin or current < end

    @property
    def schedule(self):
        if self.all_day:
            return "All day"
        return f"{self.start} – {self.end}" + (" (overnight)" if self.start > self.end else "")


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY, title TEXT NOT NULL, notes TEXT NOT NULL,
            status TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL,
            all_day INTEGER NOT NULL)""")
        self.db.commit()

    def list(self):
        items = [Reminder(**dict(row)) for row in self.db.execute("SELECT * FROM reminders ORDER BY id DESC")]
        for item in items:
            item.validate()
        return items

    def save(self, item: Reminder):
        item.validate()
        values = (item.title, item.notes, item.status, item.start, item.end, int(item.all_day))
        with self.db:
            if item.id is None:
                cursor = self.db.execute("INSERT INTO reminders (title,notes,status,start,end,all_day) VALUES (?,?,?,?,?,?)", values)
                item.id = cursor.lastrowid
            else:
                cursor = self.db.execute("UPDATE reminders SET title=?,notes=?,status=?,start=?,end=?,all_day=? WHERE id=?", (*values, item.id))
                if cursor.rowcount != 1:
                    raise ValueError("This reminder was deleted in another window. Refresh and try again.")

    def delete(self, item_id: int):
        with self.db:
            self.db.execute("DELETE FROM reminders WHERE id=?", (item_id,))

    def close(self):
        self.db.close()

    def backup(self, destination: Path):
        if destination.resolve() == self.path.resolve():
            raise ValueError('Choose a different file. You cannot replace the live reminder database.')
        target = sqlite3.connect(destination)
        try:
            self.db.backup(target)
        finally:
            target.close()
