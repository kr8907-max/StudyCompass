"""
Study Compass - Pomodoro Timer, Task Manager and Study Analytics (Tkinter)

Run:  python study_compass.py        (Python 3.8+, no extra libraries needed)

The project is split into three parts so a team of 3 can each own one:
  Member 1 -> TimerTab      (focus/break timer, daily goal, subjects)
  Member 2 -> TasksTab      (task checklist)  + RemindersTab (Notion-style reminders)
  Member 3 -> AnalyticsTab  (charts, most/least studied subject) + HistoryTab (session log)
Shared: Store (saves data to study_data.json) and App (window, menu, tabs).
"""
import json
import os
import time
import tkinter as tk
from datetime import datetime, timedelta
from random import choice, randint
from tkinter import messagebox, ttk

APP_TITLE = "Study Compass"
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "study_data.json")

BG, CARD, INK, MUTE, LINE = "#eef2f6", "#ffffff", "#14233a", "#5d6b7e", "#d5dde4"
ACC, BREAK = "#2f5bea", "#0e9f8e"
SUBJECT_COLORS = ["#2f5bea", "#0e9f8e", "#d9822b", "#a23fb8", "#c8374e", "#5f8a1d", "#3e7cb1", "#8a6d1f"]

DEFAULT = {
    "subjects": ["Mathematics", "Physics", "Literature", "Programming"],
    "sessions": [],          # {"ts": ISO time, "min": int, "subject": str}
    "tasks": [],             # {"text": str, "subject": str, "done": bool}
    "reminders": [],         # Notion-style pages: title, due, priority, status, subject, notes
    "goal": 120,             # daily goal in minutes
    "cfg": {"focus": 25, "short": 5, "long": 15},
}


# ----------------------------------------------------------------- data layer
class Store:
    """Loads, saves and answers questions about the study data."""

    def __init__(self):
        self.d = json.loads(json.dumps(DEFAULT))
        try:
            with open(DATA_FILE, encoding="utf-8") as f:
                self.d.update(json.load(f))
        except (OSError, ValueError):
            pass

    def save(self):
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.d, f, indent=2)
        except OSError:
            pass

    def color(self, subject):
        subs = self.d["subjects"]
        i = subs.index(subject) if subject in subs else 0
        return SUBJECT_COLORS[i % len(SUBJECT_COLORS)]

    def add_session(self, minutes, subject, when=None):
        when = when or datetime.now()
        self.d["sessions"].append({"ts": when.isoformat(timespec="seconds"), "min": int(minutes), "subject": subject})
        self.save()

    def today_minutes(self):
        today = datetime.now().date()
        return sum(s["min"] for s in self.d["sessions"] if datetime.fromisoformat(s["ts"]).date() == today)

    def minutes_by_subject(self, days):
        """days = 7 / 30, or 0 for all time. Subjects with no time show 0."""
        cutoff = datetime.now() - timedelta(days=days) if days else None
        totals = {name: 0 for name in self.d["subjects"]}
        for s in self.d["sessions"]:
            if cutoff is None or datetime.fromisoformat(s["ts"]) >= cutoff:
                totals[s["subject"]] = totals.get(s["subject"], 0) + s["min"]
        return totals

    def last_days(self, n=7):
        """List of (date, {subject: minutes}) for the last n days, oldest first."""
        today = datetime.now().date()
        days = [today - timedelta(days=i) for i in range(n - 1, -1, -1)]
        out = {day: {} for day in days}
        for s in self.d["sessions"]:
            day = datetime.fromisoformat(s["ts"]).date()
            if day in out:
                out[day][s["subject"]] = out[day].get(s["subject"], 0) + s["min"]
        return [(day, out[day]) for day in days]

    def streak(self):
        days = {datetime.fromisoformat(s["ts"]).date() for s in self.d["sessions"]}
        day, n = datetime.now().date(), 0
        if day not in days:
            day -= timedelta(days=1)
        while day in days:
            n += 1
            day -= timedelta(days=1)
        return n


# ------------------------------------------------------------- member 1: timer
class TimerTab(ttk.Frame):
    MODES = {"focus": "Focus", "short": "Short break", "long": "Long break"}

    def __init__(self, parent, store, on_change):
        super().__init__(parent, padding=16)
        self.store, self.on_change = store, on_change
        self.mode, self.running, self.cycle, self.after_id = "focus", False, 0, None
        self.mode_var = tk.StringVar(value="focus")
        self.subject_var = tk.StringVar(value=store.d["subjects"][0])
        self.cfg_vars = {k: tk.StringVar(value=str(v)) for k, v in store.d["cfg"].items()}

        left = ttk.Frame(self)
        left.pack(side="left", fill="both", expand=True)
        right = ttk.Frame(self, padding=(24, 0, 0, 0))
        right.pack(side="right", fill="y")

        # mode buttons (radio buttons styled as a toggle bar)
        bar = ttk.Frame(left)
        bar.pack(pady=(0, 8))
        for key, label in self.MODES.items():
            ttk.Radiobutton(bar, text=label, value=key, variable=self.mode_var, style="Toolbutton",
                            command=lambda k=key: self.set_mode(k)).pack(side="left", padx=3)

        # ring + time
        self.canvas = tk.Canvas(left, width=270, height=270, bg=BG, highlightthickness=0)
        self.canvas.pack()
        self.canvas.create_oval(20, 20, 250, 250, outline=LINE, width=14)
        self.arc = self.canvas.create_arc(20, 20, 250, 250, start=90, extent=-359.9, style="arc", outline=ACC, width=14)
        self.time_text = self.canvas.create_text(135, 125, text="25:00", font=("Segoe UI", 44, "bold"), fill=INK)
        self.mode_text = self.canvas.create_text(135, 172, text="Focus", font=("Segoe UI", 13), fill=MUTE)

        btns = ttk.Frame(left)
        btns.pack(pady=10)
        self.start_btn = ttk.Button(btns, text="Start focus", style="Accent.TButton", command=self.toggle)
        self.start_btn.pack(side="left", padx=4)
        ttk.Button(btns, text="Finish and log", command=self.finish_early).pack(side="left", padx=4)
        ttk.Button(btns, text="Reset", command=lambda: self.set_mode(self.mode)).pack(side="left", padx=4)
        ttk.Label(left, text="Tip: press Space to start or pause", style="Muted.TLabel").pack()

        # right column: subject, durations, daily goal
        ttk.Label(right, text="Studying", style="H.TLabel").pack(anchor="w")
        self.combo = ttk.Combobox(right, textvariable=self.subject_var, values=store.d["subjects"], state="readonly", width=22)
        self.combo.pack(anchor="w", pady=(2, 6))
        row = ttk.Frame(right)
        row.pack(anchor="w", pady=(0, 14))
        self.new_subject = ttk.Entry(row, width=15)
        self.new_subject.pack(side="left")
        self.new_subject.bind("<Return>", lambda e: self.add_subject())
        ttk.Button(row, text="Add subject", command=self.add_subject).pack(side="left", padx=4)

        ttk.Label(right, text="Minutes", style="H.TLabel").pack(anchor="w")
        for key, label in (("focus", "Focus"), ("short", "Short break"), ("long", "Long break")):
            r = ttk.Frame(right)
            r.pack(anchor="w", pady=2)
            ttk.Label(r, text=label, width=11).pack(side="left")
            ttk.Spinbox(r, from_=1, to=120, width=5, textvariable=self.cfg_vars[key], command=self.on_cfg).pack(side="left")

        ttk.Label(right, text="Today's goal", style="H.TLabel").pack(anchor="w", pady=(18, 0))
        self.goal_var = tk.StringVar(value=str(store.d["goal"]))
        g = ttk.Frame(right)
        g.pack(anchor="w", pady=2)
        ttk.Spinbox(g, from_=10, to=600, increment=10, width=6, textvariable=self.goal_var, command=self.on_goal).pack(side="left")
        ttk.Label(g, text="minutes").pack(side="left", padx=4)
        self.goal_bar = ttk.Progressbar(right, length=210, maximum=100, style="Goal.Horizontal.TProgressbar")
        self.goal_bar.pack(anchor="w", pady=4)
        self.goal_label = ttk.Label(right, text="", style="Muted.TLabel")
        self.goal_label.pack(anchor="w")
        self.streak_label = ttk.Label(right, text="", style="Muted.TLabel")
        self.streak_label.pack(anchor="w", pady=(8, 0))

        self.combo.bind("<<ComboboxSelected>>", lambda e: None)
        self.set_mode("focus")
        self.refresh_goal()

    # --- helpers
    @property
    def subject(self):
        return self.subject_var.get()

    def reload_subjects(self):
        self.combo["values"] = self.store.d["subjects"]

    def minutes_for(self, mode):
        try:
            return max(1, min(120, int(self.cfg_vars[mode].get())))
        except ValueError:
            return self.store.d["cfg"][mode]

    # --- events
    def add_subject(self):
        name = self.new_subject.get().strip()
        if not name:
            return
        if name not in self.store.d["subjects"]:
            self.store.d["subjects"].append(name)
            self.store.save()
        self.reload_subjects()
        self.subject_var.set(name)
        self.new_subject.delete(0, "end")
        self.on_change()

    def on_cfg(self):
        for k in self.cfg_vars:
            self.store.d["cfg"][k] = self.minutes_for(k)
        self.store.save()
        if not self.running:
            self.set_mode(self.mode)

    def on_goal(self):
        try:
            self.store.d["goal"] = max(10, int(self.goal_var.get()))
        except ValueError:
            pass
        self.store.save()
        self.on_change()

    # --- timer logic: remember WHEN it ends, so it never drifts
    def set_mode(self, mode):
        self.stop_loop()
        self.mode, self.running = mode, False
        self.mode_var.set(mode)
        self.total = self.minutes_for(mode) * 60
        self.remain = self.total
        self.draw()

    def stop_loop(self):
        if self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None

    def toggle(self):
        if self.running:
            self.running = False
            self.stop_loop()
        else:
            self.running = True
            self.end_at = time.time() + self.remain
            self.tick()
        self.draw()

    def tick(self):
        if not self.running:
            return
        self.remain = max(0, round(self.end_at - time.time()))
        if self.remain == 0:
            self.complete()
            return
        self.draw()
        self.after_id = self.after(250, self.tick)

    def complete(self):
        self.running = False
        self.bell()
        if self.mode == "focus":
            self.store.add_session(self.total // 60, self.subject)
            self.cycle += 1
            nxt = "long" if self.cycle % 4 == 0 else "short"
            self.set_mode(nxt)
            self.on_change()
            messagebox.showinfo(APP_TITLE, "Focus session complete! Time for a break.")
        else:
            self.set_mode("focus")
            messagebox.showinfo(APP_TITLE, "Break over. Ready to focus?")

    def finish_early(self):
        if self.mode != "focus":
            return
        minutes = (self.total - self.remain) // 60
        if minutes < 1:
            messagebox.showwarning(APP_TITLE, "Focus for at least one minute before logging a session.")
            return
        self.store.add_session(minutes, self.subject)
        self.set_mode("focus")
        self.on_change()

    def draw(self):
        m, s = divmod(self.remain, 60)
        text = f"{m:02d}:{s:02d}"
        self.canvas.itemconfigure(self.time_text, text=text)
        self.canvas.itemconfigure(self.mode_text, text=self.MODES[self.mode])
        frac = self.remain / self.total if self.total else 0
        self.canvas.itemconfigure(self.arc, extent=-max(0.1, min(359.9, 360 * frac)),
                                  outline=ACC if self.mode == "focus" else BREAK)
        if self.running:
            self.start_btn.configure(text="Pause")
        else:
            self.start_btn.configure(text="Resume" if self.remain < self.total else
                                     "Start focus" if self.mode == "focus" else "Start break")
        self.winfo_toplevel().title(f"{text} - {APP_TITLE}" if self.running else APP_TITLE)

    def refresh_goal(self):
        done, goal = self.store.today_minutes(), self.store.d["goal"]
        self.goal_bar["value"] = min(100, done * 100 / goal)
        self.goal_label.configure(text=f"{done} of {goal} min done" + ("  - goal reached!" if done >= goal else ""))
        n = self.store.streak()
        self.streak_label.configure(text=f"{n}-day study streak" if n else "Finish a session to start a streak")


# -------------------------------------------------------------- member 2: tasks
class TasksTab(ttk.Frame):
    def __init__(self, parent, store, get_subject):
        super().__init__(parent, padding=16)
        self.store, self.get_subject = store, get_subject

        top = ttk.Frame(self)
        top.pack(fill="x")
        self.entry = ttk.Entry(top)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.add())
        ttk.Button(top, text="Add task", style="Accent.TButton", command=self.add).pack(side="left", padx=(8, 0))

        self.tree = ttk.Treeview(self, columns=("done", "task", "subject"), show="headings", height=14, selectmode="browse")
        for col, title, w in (("done", "Done", 60), ("task", "Task", 420), ("subject", "Subject", 150)):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=w, anchor="center" if col == "done" else "w")
        self.tree.tag_configure("done", foreground="#9aa5b4")
        self.tree.pack(fill="both", expand=True, pady=10)
        self.tree.bind("<Double-1>", self.toggle_clicked)   # double-click = tick / untick
        self.tree.bind("<Delete>", lambda e: self.delete())

        bottom = ttk.Frame(self)
        bottom.pack(fill="x")
        self.count = ttk.Label(bottom, text="", style="Muted.TLabel")
        self.count.pack(side="left")
        ttk.Button(bottom, text="Clear completed", command=self.clear_done).pack(side="right")
        ttk.Button(bottom, text="Delete selected", command=self.delete).pack(side="right", padx=6)
        ttk.Button(bottom, text="Tick / untick", command=self.toggle_selected).pack(side="right")
        self.refresh()

    def add(self):
        text = self.entry.get().strip()
        if not text:
            messagebox.showwarning(APP_TITLE, "Type a task first.")
            return
        self.store.d["tasks"].insert(0, {"text": text, "subject": self.get_subject(), "done": False})
        self.store.save()
        self.entry.delete(0, "end")
        self.refresh()

    def toggle_clicked(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.flip(int(row))

    def toggle_selected(self):
        sel = self.tree.selection()
        if sel:
            self.flip(int(sel[0]))

    def flip(self, i):
        t = self.store.d["tasks"][i]
        t["done"] = not t["done"]
        self.store.save()
        self.refresh()

    def delete(self):
        sel = self.tree.selection()
        if sel:
            del self.store.d["tasks"][int(sel[0])]
            self.store.save()
            self.refresh()

    def clear_done(self):
        self.store.d["tasks"] = [t for t in self.store.d["tasks"] if not t["done"]]
        self.store.save()
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for i, t in enumerate(self.store.d["tasks"]):
            self.tree.insert("", "end", iid=str(i), values=("[x]" if t["done"] else "[ ]", t["text"], t["subject"]),
                             tags=("done",) if t["done"] else ())
        done = sum(t["done"] for t in self.store.d["tasks"])
        self.count.configure(text=f"{done} of {len(self.store.d['tasks'])} tasks done. Double-click a task to tick it.")


class HistoryTab(ttk.Frame):
    def __init__(self, parent, store, on_change):
        super().__init__(parent, padding=16)
        self.store, self.on_change = store, on_change
        self.tree = ttk.Treeview(self, columns=("date", "time", "subject", "min"), show="headings", height=16)
        for col, title, w in (("date", "Date", 130), ("time", "Time", 90), ("subject", "Subject", 220), ("min", "Minutes", 90)):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True)
        ttk.Button(self, text="Delete selected session", command=self.delete).pack(anchor="e", pady=8)
        self.refresh()

    def delete(self):
        sel = self.tree.selection()
        if sel and messagebox.askyesno(APP_TITLE, "Delete this session?"):
            del self.store.d["sessions"][int(sel[0])]
            self.store.save()
            self.on_change()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for i in range(len(self.store.d["sessions"]) - 1, -1, -1):   # newest first
            s = self.store.d["sessions"][i]
            t = datetime.fromisoformat(s["ts"])
            self.tree.insert("", "end", iid=str(i), values=(t.strftime("%d %b %Y"), t.strftime("%H:%M"), s["subject"], s["min"]))


# ------------------------------------------------- member 2: notion-style reminders
PRIORITIES = ("High", "Medium", "Low")
STATUSES = ("To do", "In progress", "Done")
DUE_FMT = "%Y-%m-%d %H:%M"


class RemindersTab(ttk.Frame):
    """A small Notion-style database. Every reminder is a 'page' with properties
    (due, priority, status, subject) and free-text notes. Switch between a Table
    view and a Board view, filter the list, and edit the selected page on the right."""

    def __init__(self, parent, store):
        super().__init__(parent, padding=16)
        self.store = store
        self.current = None
        self.loading = False
        self.filter_var = tk.StringVar(value="All")
        self.view_var = tk.StringVar(value="Table")
        self.f = {k: tk.StringVar() for k in ("title", "date", "time", "priority", "status", "subject")}

        top = ttk.Frame(self)
        top.pack(fill="x")
        self.quick = ttk.Entry(top)
        self.quick.pack(side="left", fill="x", expand=True)
        self.quick.bind("<Return>", lambda e: self.quick_add())
        ttk.Button(top, text="Add reminder", style="Accent.TButton", command=self.quick_add).pack(side="left", padx=(8, 0))

        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(10, 6))
        for name in ("All", "Today", "Overdue", "Done"):
            ttk.Radiobutton(bar, text=name, value=name, variable=self.filter_var, style="Toolbutton",
                            command=self.refresh).pack(side="left", padx=2)
        self.summary = ttk.Label(bar, text="", style="Muted.TLabel")
        self.summary.pack(side="left", padx=12)
        for name in ("Board", "Table"):
            ttk.Radiobutton(bar, text=name + " view", value=name, variable=self.view_var, style="Toolbutton",
                            command=self.switch_view).pack(side="right", padx=2)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.list_area = ttk.Frame(body)
        self.list_area.pack(side="left", fill="both", expand=True)
        detail = ttk.Frame(body, padding=(16, 0, 0, 0))
        detail.pack(side="right", fill="y")

        # table view
        self.tree = ttk.Treeview(self.list_area, columns=("title", "due", "priority", "status", "subject"),
                                 show="headings", height=14, selectmode="browse")
        for col, title, w in (("title", "Title", 200), ("due", "Due", 105), ("priority", "Priority", 70),
                              ("status", "Status", 85), ("subject", "Subject", 95)):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=w, anchor="w")
        self.tree.tag_configure("done", foreground="#9aa5b4")
        self.tree.tag_configure("overdue", foreground="#c8374e")
        self.tree.bind("<<TreeviewSelect>>", self.on_select_tree)
        self.tree.bind("<Delete>", lambda e: self.delete())
        self.tree.pack(fill="both", expand=True)

        # board view (three columns like a Notion board)
        self.board = ttk.Frame(self.list_area)
        self.board.rowconfigure(0, weight=1)
        self.lists, self.board_ids = {}, {st: [] for st in STATUSES}
        for i, st in enumerate(STATUSES):
            col = ttk.Frame(self.board)
            col.grid(row=0, column=i, sticky="nsew", padx=4)
            self.board.columnconfigure(i, weight=1, uniform="col")
            ttk.Label(col, text=st, style="H.TLabel").pack(anchor="w")
            lb = tk.Listbox(col, height=14, width=18, exportselection=False, activestyle="none", bd=0,
                            highlightthickness=1, highlightbackground=LINE, font=("Segoe UI", 10),
                            selectbackground="#dfe7fd", selectforeground=INK)
            lb.pack(fill="both", expand=True)
            lb.bind("<<ListboxSelect>>", lambda e, s=st: self.on_select_board(s))
            self.lists[st] = lb

        # detail "page"
        ttk.Label(detail, text="Reminder page", style="H.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self.widgets = {}
        for i, (label, key) in enumerate((("Title", "title"), ("Due date", "date"), ("Time", "time"),
                                          ("Priority", "priority"), ("Status", "status"), ("Subject", "subject")), start=1):
            ttk.Label(detail, text=label).grid(row=i, column=0, sticky="w", pady=3)
            if key == "priority":
                w = ttk.Combobox(detail, textvariable=self.f[key], values=PRIORITIES, state="readonly", width=19)
            elif key == "status":
                w = ttk.Combobox(detail, textvariable=self.f[key], values=STATUSES, state="readonly", width=19)
            elif key == "subject":
                w = ttk.Combobox(detail, textvariable=self.f[key], values=[""] + store.d["subjects"], state="readonly", width=19)
            else:
                w = ttk.Entry(detail, textvariable=self.f[key], width=22)
                w.bind("<Return>", lambda e: self.save())
            w.grid(row=i, column=1, sticky="w", pady=3, padx=(8, 0))
            self.widgets[key] = w
        quick = ttk.Frame(detail)
        quick.grid(row=7, column=0, columnspan=2, sticky="w", pady=(2, 0))
        for text, kind in (("Today", "today"), ("Tomorrow", "tomorrow"), ("In 1 hour", "hour")):
            ttk.Button(quick, text=text, command=lambda k=kind: self.set_due(k)).pack(side="left", padx=(0, 4))
        ttk.Label(detail, text="Date YYYY-MM-DD, time HH:MM (24-hour)", style="Muted.TLabel").grid(
            row=8, column=0, columnspan=2, sticky="w", pady=(2, 6))
        ttk.Label(detail, text="Notes").grid(row=9, column=0, sticky="w")
        self.notes = tk.Text(detail, width=32, height=6, wrap="word", font=("Segoe UI", 10), bd=1, relief="solid",
                             highlightthickness=0)
        self.notes.grid(row=10, column=0, columnspan=2, sticky="we", pady=(2, 8))
        row = ttk.Frame(detail)
        row.grid(row=11, column=0, columnspan=2, sticky="w")
        ttk.Button(row, text="Save changes", style="Accent.TButton", command=self.save).pack(side="left", padx=(0, 4))
        ttk.Button(row, text="Delete", command=self.delete).pack(side="left")
        row2 = ttk.Frame(detail)
        row2.grid(row=12, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Button(row2, text="< Move back", command=lambda: self.move(-1)).pack(side="left", padx=(0, 4))
        ttk.Button(row2, text="Move on >", command=lambda: self.move(1)).pack(side="left")
        self.refresh()

    # --- helpers
    def items(self):
        return self.store.d["reminders"]

    def get(self, rid):
        return next((r for r in self.items() if r["id"] == rid), None)

    @staticmethod
    def due_dt(r):
        try:
            return datetime.strptime(r["due"], DUE_FMT)
        except (ValueError, KeyError):
            return None

    def overdue(self, r):
        d = self.due_dt(r)
        return bool(d and d < datetime.now() and r["status"] != "Done")

    def show_due(self, r):
        d = self.due_dt(r)
        return d.strftime("%d %b, %H:%M") if d else "-"

    def visible(self):
        mode, today, out = self.filter_var.get(), datetime.now().date(), []
        for r in self.items():
            d = self.due_dt(r)
            if mode == "Today" and not (d and d.date() == today and r["status"] != "Done"):
                continue
            if mode == "Overdue" and not self.overdue(r):
                continue
            if mode == "Done" and r["status"] != "Done":
                continue
            out.append(r)
        rank = {p: i for i, p in enumerate(PRIORITIES)}
        out.sort(key=lambda r: (r["status"] == "Done", self.due_dt(r) is None, self.due_dt(r) or datetime.max,
                                rank.get(r["priority"], 1)))
        return out

    # --- events
    def switch_view(self):
        if self.view_var.get() == "Table":
            self.board.pack_forget()
            self.tree.pack(fill="both", expand=True)
        else:
            self.tree.pack_forget()
            self.board.pack(fill="both", expand=True)

    def on_select_tree(self, event):
        sel = self.tree.selection()
        if sel and not self.loading:
            self.load(int(sel[0]))

    def on_select_board(self, status):
        sel = self.lists[status].curselection()
        if sel:
            self.load(self.board_ids[status][sel[0]])

    def quick_add(self):
        title = self.quick.get().strip()
        if not title:
            messagebox.showwarning(APP_TITLE, "Type a reminder title first.")
            return
        rid = max([r["id"] for r in self.items()] + [0]) + 1
        self.items().append({"id": rid, "title": title, "due": "", "priority": "Medium", "status": "To do",
                             "subject": "", "notes": "", "notified": False})
        self.store.save()
        self.quick.delete(0, "end")
        self.filter_var.set("All")
        self.load(rid)
        self.refresh()

    def load(self, rid):
        r = self.get(rid)
        if not r:
            return
        self.current, d = rid, self.due_dt(r)
        self.f["title"].set(r["title"])
        self.f["date"].set(d.strftime("%Y-%m-%d") if d else "")
        self.f["time"].set(d.strftime("%H:%M") if d else "")
        self.f["priority"].set(r["priority"])
        self.f["status"].set(r["status"])
        self.f["subject"].set(r["subject"])
        self.notes.delete("1.0", "end")
        self.notes.insert("1.0", r["notes"])

    def set_due(self, kind):
        now = datetime.now()
        if kind == "today":
            d = now.replace(hour=18, minute=0)
        elif kind == "tomorrow":
            d = (now + timedelta(days=1)).replace(hour=9, minute=0)
        else:
            d = now + timedelta(hours=1)
        self.f["date"].set(d.strftime("%Y-%m-%d"))
        self.f["time"].set(d.strftime("%H:%M"))

    def save(self):
        r = self.get(self.current)
        if not r:
            messagebox.showinfo(APP_TITLE, "Pick a reminder from the list, or add a new one first.")
            return
        title = self.f["title"].get().strip()
        if not title:
            messagebox.showwarning(APP_TITLE, "A reminder needs a title.")
            return
        date, clock, due = self.f["date"].get().strip(), self.f["time"].get().strip() or "09:00", ""
        if date:
            try:
                due = datetime.strptime(f"{date} {clock}", DUE_FMT).strftime(DUE_FMT)
            except ValueError:
                messagebox.showwarning(APP_TITLE, "Use the date as YYYY-MM-DD and the time as HH:MM (24-hour).")
                return
        if due != r["due"]:
            r["notified"] = False      # new time -> remind again
        r.update(title=title, due=due, priority=self.f["priority"].get() or "Medium",
                 status=self.f["status"].get() or "To do", subject=self.f["subject"].get(),
                 notes=self.notes.get("1.0", "end").strip())
        self.store.save()
        self.refresh()

    def move(self, step):
        r = self.get(self.current)
        if not r:
            return
        i = max(0, min(len(STATUSES) - 1, STATUSES.index(r["status"]) + step))
        r["status"] = STATUSES[i]
        self.f["status"].set(r["status"])
        self.store.save()
        self.refresh()

    def delete(self):
        r = self.get(self.current)
        if r and messagebox.askyesno(APP_TITLE, f"Delete '{r['title']}'?"):
            self.items().remove(r)
            self.current = None
            for k in self.f:
                self.f[k].set("")
            self.notes.delete("1.0", "end")
            self.store.save()
            self.refresh()

    def refresh(self):
        self.widgets["subject"]["values"] = [""] + self.store.d["subjects"]
        self.loading = True
        self.tree.delete(*self.tree.get_children())
        for st in STATUSES:
            self.lists[st].delete(0, "end")
            self.board_ids[st] = []
        shown = self.visible()
        for r in shown:
            tags = ("done",) if r["status"] == "Done" else ("overdue",) if self.overdue(r) else ()
            self.tree.insert("", "end", iid=str(r["id"]), tags=tags,
                             values=(r["title"], self.show_due(r), r["priority"], r["status"], r["subject"] or "-"))
            lb = self.lists[r["status"]]
            lb.insert("end", f"{r['title']}  ({self.show_due(r)})")
            self.board_ids[r["status"]].append(r["id"])
            if self.overdue(r):
                lb.itemconfig("end", foreground="#c8374e")
        if self.current is not None and self.tree.exists(str(self.current)):
            self.tree.selection_set(str(self.current))
        self.loading = False
        late = sum(1 for r in self.items() if self.overdue(r))
        open_n = sum(1 for r in self.items() if r["status"] != "Done")
        self.summary.configure(text=f"{open_n} open, {late} overdue")

    # --- called by the App every few seconds
    def pop_due(self):
        """Returns reminders whose time has arrived (each one only once)."""
        now, due = datetime.now(), []
        for r in self.items():
            d = self.due_dt(r)
            if d and d <= now and r["status"] != "Done" and not r.get("notified"):
                r["notified"] = True
                due.append(r)
        if due:
            self.store.save()
            self.refresh()
        return due

    def add_samples(self):
        now, base = datetime.now(), max([r["id"] for r in self.items()] + [0])
        samples = [("Submit physics lab report", -3, "High", "In progress", "Physics", "Include the graphs from experiment 2."),
                   ("Revise integration formulas", 2, "Medium", "To do", "Mathematics", "Chapter 5 practice set."),
                   ("Finish Tkinter project report", 26, "High", "To do", "Programming", "Add screenshots and team contribution."),
                   ("Read the poetry chapter", 50, "Low", "To do", "Literature", ""),
                   ("Buy a lab notebook", -30, "Low", "Done", "", "")]
        for i, (title, hours, pri, status, subject, notes) in enumerate(samples, start=1):
            due = (now + timedelta(hours=hours)).strftime(DUE_FMT)
            self.items().append({"id": base + i, "title": title, "due": due, "priority": pri, "status": status,
                                 "subject": subject, "notes": notes, "notified": hours < 0})
        self.store.save()
        self.refresh()


# ---------------------------------------------------------- member 3: analytics
class AnalyticsTab(ttk.Frame):
    def __init__(self, parent, store):
        super().__init__(parent, padding=16)
        self.store = store
        self.range_var = tk.IntVar(value=7)

        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="Time by subject", style="H.TLabel").pack(side="left")
        for days, label in ((0, "All time"), (30, "30 days"), (7, "7 days")):
            ttk.Radiobutton(top, text=label, value=days, variable=self.range_var, style="Toolbutton",
                            command=self.refresh).pack(side="right", padx=2)

        self.callouts = ttk.Label(self, text="", font=("Segoe UI", 11, "bold"), foreground=INK)
        self.callouts.pack(anchor="w", pady=(8, 2))
        self.subject_canvas = tk.Canvas(self, width=820, height=150, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        self.subject_canvas.pack(fill="x")

        ttk.Label(self, text="Last 7 days", style="H.TLabel").pack(anchor="w", pady=(14, 2))
        self.week_canvas = tk.Canvas(self, width=820, height=210, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        self.week_canvas.pack(fill="x")
        self.refresh()

    def refresh(self):
        self.draw_subjects()
        self.draw_week()

    def draw_subjects(self):
        c = self.subject_canvas
        c.delete("all")
        totals = self.store.minutes_by_subject(self.range_var.get())
        names = sorted(totals, key=lambda n: totals[n], reverse=True)
        total = sum(totals.values())
        if not total:
            self.callouts.configure(text="No focus time in this range yet.")
            c.create_text(20, 30, anchor="w", fill=MUTE, font=("Segoe UI", 11),
                          text="Finish a focus session or use File > Load sample data.")
            return
        most, least = names[0], names[-1]
        self.callouts.configure(
            text=f"Most studied: {most} ({totals[most]} min)     Least studied: {least} ({totals[least]} min)     Total: {total} min")
        top = totals[most] or 1
        row_h = min(30, 140 // max(1, len(names)))
        for i, n in enumerate(names):
            y = 10 + i * row_h
            c.create_text(10, y + row_h / 2 - 2, anchor="w", text=n, fill=INK, font=("Segoe UI", 10))
            width = 540 * totals[n] / top
            c.create_rectangle(150, y, 150 + max(width, 2), y + row_h - 8, fill=self.store.color(n), outline="")
            tag = "  most" if n == most else "  least" if n == least else ""
            c.create_text(158 + width, y + row_h / 2 - 2, anchor="w", text=f"{totals[n]} min{tag}", fill=MUTE, font=("Segoe UI", 9))
        c.configure(height=max(80, 20 + len(names) * row_h))

    def draw_week(self):
        c = self.week_canvas
        c.delete("all")
        data = self.store.last_days(7)
        goal = self.store.d["goal"]
        peak = max([sum(o.values()) for _, o in data] + [goal])
        left, base, top, bar_w = 40, 180, 20, 56
        gap = (780 - left - 7 * bar_w) / 7
        gy = base - (base - top) * goal / peak
        c.create_line(left, gy, 800, gy, dash=(4, 3), fill=MUTE)
        c.create_text(800, gy - 8, anchor="e", text=f"goal {goal} min", fill=MUTE, font=("Segoe UI", 9))
        c.create_line(left, base, 800, base, fill=LINE)
        for i, (day, per_subject) in enumerate(data):
            x = left + gap / 2 + i * (bar_w + gap)
            y = base
            for name in self.store.d["subjects"]:
                v = per_subject.get(name, 0)
                if v:
                    h = (base - top) * v / peak
                    c.create_rectangle(x, y - h, x + bar_w, y, fill=self.store.color(name), outline="")
                    y -= h
            day_total = sum(per_subject.values())
            if day_total:
                c.create_text(x + bar_w / 2, y - 8, text=str(day_total), fill=INK, font=("Segoe UI", 9, "bold"))
            c.create_text(x + bar_w / 2, base + 14, text=day.strftime("%a"), fill=MUTE, font=("Segoe UI", 9))
        lx = 10
        for name in self.store.d["subjects"]:
            c.create_rectangle(lx, 200, lx + 9, 209, fill=self.store.color(name), outline="")
            c.create_text(lx + 13, 204, anchor="w", text=name, fill=MUTE, font=("Segoe UI", 8))
            lx += 30 + 6 * len(name)


# --------------------------------------------------------------------- main app
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("920x700")
        self.minsize(860, 640)
        self.configure(bg=BG)
        self.store = Store()
        self.apply_style()

        ttk.Label(self, text=APP_TITLE, style="Title.TLabel").pack(anchor="w", padx=20, pady=(14, 0))
        ttk.Label(self, text="Pomodoro timer, tasks and study analytics", style="Muted.TLabel").pack(anchor="w", padx=20)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=14, pady=12)
        self.timer = TimerTab(self.nb, self.store, self.refresh_all)
        self.tasks = TasksTab(self.nb, self.store, lambda: self.timer.subject)
        self.reminders = RemindersTab(self.nb, self.store)
        self.analytics = AnalyticsTab(self.nb, self.store)
        self.history = HistoryTab(self.nb, self.store, self.refresh_all)
        for tab, name in ((self.timer, "Timer"), (self.tasks, "Tasks"), (self.reminders, "Reminders"),
                          (self.analytics, "Analytics"), (self.history, "History")):
            self.nb.add(tab, text=name)

        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=0)
        file_menu.add_command(label="Load sample data", command=self.load_sample)
        file_menu.add_command(label="Clear all data", command=self.clear_all)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menu.add_cascade(label="File", menu=file_menu)
        self.config(menu=menu)

        self.nb.bind("<<NotebookTabChanged>>", lambda e: self.refresh_all())
        self.bind("<space>", self.on_space)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(1500, self.poll_reminders)

    def poll_reminders(self):
        """Every 15 seconds, pop up any reminder whose time has arrived."""
        for r in self.reminders.pop_due():
            self.bell()
            messagebox.showinfo("Reminder", f"{r['title']}\nDue: {self.reminders.show_due(r)}")
        self.after(15000, self.poll_reminders)

    def apply_style(self):
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure(".", background=BG, foreground=INK, font=("Segoe UI", 10))
        st.configure("TFrame", background=BG)
        st.configure("TLabel", background=BG, foreground=INK)
        st.configure("Title.TLabel", font=("Segoe UI", 22, "bold"))
        st.configure("H.TLabel", font=("Segoe UI", 11, "bold"))
        st.configure("Muted.TLabel", foreground=MUTE)
        st.configure("TNotebook", background=BG, borderwidth=0)
        st.configure("TNotebook.Tab", padding=(18, 8), font=("Segoe UI", 10, "bold"))
        st.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", ACC)])
        st.configure("TButton", padding=(12, 6), background=CARD, bordercolor=LINE)
        st.map("TButton", background=[("active", "#e3eafd")])
        st.configure("Accent.TButton", background=ACC, foreground="white", bordercolor=ACC)
        st.map("Accent.TButton", background=[("active", "#1f48c9")])
        st.configure("Toolbutton", padding=(12, 6), background=CARD, bordercolor=LINE)
        st.map("Toolbutton", background=[("selected", "#dfe7fd"), ("active", "#eef2fd")], foreground=[("selected", ACC)])
        st.configure("Goal.Horizontal.TProgressbar", troughcolor=LINE, background=ACC, thickness=12, bordercolor=BG)
        st.configure("Treeview", rowheight=26, background=CARD, fieldbackground=CARD)
        st.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

    def refresh_all(self):
        self.timer.reload_subjects()
        self.timer.refresh_goal()
        self.tasks.refresh()
        self.reminders.refresh()
        self.analytics.refresh()
        self.history.refresh()

    def on_space(self, event):
        if self.focus_get() is not None and self.focus_get().winfo_class() in (
                "TEntry", "TSpinbox", "TCombobox", "Entry", "TButton", "TRadiobutton", "Treeview"):
            return
        self.timer.toggle()

    def load_sample(self):
        for d in range(7):
            for _ in range(randint(1, 4)):
                subject = choice(self.store.d["subjects"][:1] * 3 + self.store.d["subjects"][1:2] * 2 + self.store.d["subjects"])
                when = datetime.now() - timedelta(days=d, hours=randint(0, 10))
                self.store.add_session(choice([25, 25, 30, 45]), subject, when)
        self.store.d["sessions"].sort(key=lambda s: s["ts"])
        self.store.save()
        self.reminders.add_samples()
        self.refresh_all()

    def clear_all(self):
        if messagebox.askyesno(APP_TITLE, "Delete all sessions, tasks and reminders?"):
            self.store.d["sessions"], self.store.d["tasks"], self.store.d["reminders"] = [], [], []
            self.reminders.current = None
            self.store.save()
            self.refresh_all()

    def on_close(self):
        if self.timer.running and not messagebox.askyesno(APP_TITLE, "A timer is running. Quit anyway?"):
            return
        self.store.save()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()