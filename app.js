(() => {
  "use strict";

  const STORAGE_KEY = "study-compass-web-v1";
  const COLORS = ["#ff5ca8", "#60a5fa", "#fbbf24", "#a3e635", "#d946ef", "#22d3ee", "#fb7185", "#0e9f8e"];
  const MODE_LABELS = { focus: "Focus", short: "Short break", long: "Long break" };
  const DEFAULTS = {
    subjects: ["APP", "DSA", "MATHS", "COA"],
    sessions: [],
    tasks: [],
    reminders: [],
    goal: 120,
    cfg: { focus: 25, short: 5, long: 15 },
    cycle: 0,
    timer: { mode: "focus", remain: 25 * 60, running: false, endsAt: null }
  };

  let state;
  let activePage = "timer";
  let reminderFilter = "All";
  let analyticsRange = 7;
  let toastTimer = null;
  let deferredInstallPrompt = null;

  const $ = selector => document.querySelector(selector);
  const $$ = selector => Array.from(document.querySelectorAll(selector));
  const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[char]);
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const localDateKey = date => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  };
  state = loadState();

  function loadState() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (!saved) return structuredClone(DEFAULTS);
      return normalizeState(JSON.parse(saved));
    } catch (error) {
      console.error("Could not load Study Compass data:", error);
      showStorageWarning("Saved data could not be loaded. The app is using a fresh in-memory copy.");
      return structuredClone(DEFAULTS);
    }
  }

  function normalizeState(value) {
    if (!value || typeof value !== "object") throw new Error("The saved data is not a valid object.");
    const next = { ...structuredClone(DEFAULTS), ...value };
    next.subjects = Array.isArray(value.subjects) && value.subjects.length
      ? [...new Set(value.subjects.filter(item => typeof item === "string" && item.trim()).map(item => item.trim()))]
      : [...DEFAULTS.subjects];
    next.sessions = Array.isArray(value.sessions) ? value.sessions.filter(item =>
      item && typeof item.ts === "string" && Number.isFinite(Number(item.min)) && typeof item.subject === "string"
    ) : [];
    next.tasks = Array.isArray(value.tasks) ? value.tasks.filter(item => item && typeof item.text === "string").map(item => ({
      id: String(item.id || makeId()), text: item.text, subject: typeof item.subject === "string" ? item.subject : "",
      done: Boolean(item.done)
    })) : [];
    next.reminders = Array.isArray(value.reminders) ? value.reminders.filter(item => item && typeof item.title === "string").map(item => ({
      id: String(item.id || makeId()), title: item.title, due: typeof item.due === "string" ? item.due : "",
      priority: ["High", "Medium", "Low"].includes(item.priority) ? item.priority : "Medium",
      status: ["To do", "In progress", "Done"].includes(item.status) ? item.status : "To do",
      subject: typeof item.subject === "string" ? item.subject : "",
      notes: typeof item.notes === "string" ? item.notes : "",
      notifiedAt: typeof item.notifiedAt === "string" ? item.notifiedAt : ""
    })) : [];
    next.goal = clampNumber(next.goal, 120, 10, 600);
    next.cfg = {
      focus: clampNumber(value.cfg?.focus, 25, 1, 120),
      short: clampNumber(value.cfg?.short, 5, 1, 120),
      long: clampNumber(value.cfg?.long, 15, 1, 120)
    };
    next.cycle = Number.isInteger(value.cycle) && value.cycle >= 0 ? value.cycle : 0;
    const mode = ["focus", "short", "long"].includes(value.timer?.mode) ? value.timer.mode : "focus";
    const total = next.cfg[mode] * 60;
    const endsAt = Number(value.timer?.endsAt) || null;
    const remains = Number(value.timer?.remain);
    next.timer = {
      mode,
      remain: endsAt && value.timer?.running ? Math.max(0, Math.min(total, Math.ceil((endsAt - Date.now()) / 1000))) : clampNumber(remains, total, 0, total),
      running: Boolean(value.timer?.running && endsAt && endsAt > Date.now()),
      endsAt: value.timer?.running && endsAt > Date.now() ? endsAt : null
    };
    if (!next.timer.running && next.timer.remain === 0) next.timer.remain = total;
    return next;
  }

  function clampNumber(value, fallback, min, max) {
    const number = Number(value);
    return Number.isFinite(number) ? clamp(Math.round(number), min, max) : fallback;
  }

  function makeId() {
    return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function showStorageWarning(message) {
    const notice = $("#notice");
    if (!notice) return;
    notice.textContent = message;
    notice.classList.remove("hidden");
    notice.classList.add("error");
  }

  function saveState() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
      $("#notice")?.classList.add("hidden");
    } catch (error) {
      console.error("Could not save Study Compass data:", error);
      showStorageWarning("Your browser could not save this change. Check available storage or export a backup.");
    }
  }

  function showToast(message, kind = "") {
    const region = $("#toast-region");
    const toast = document.createElement("div");
    toast.className = `toast ${kind}`.trim();
    toast.textContent = message;
    region.append(toast);
    window.setTimeout(() => toast.remove(), 3600);
  }

  function formatMinutes(minutes) {
    const hours = Math.floor(minutes / 60);
    const rest = minutes % 60;
    if (!hours) return `${rest} min`;
    return rest ? `${hours} hr ${rest} min` : `${hours} hr`;
  }

  function formatDue(due) {
    if (!due) return "No due date";
    const parsed = new Date(due);
    if (Number.isNaN(parsed.getTime())) return "No due date";
    return parsed.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }

  function getDayStreak() {
    const days = new Set(state.sessions.map(session => {
      const date = new Date(session.ts);
      return Number.isNaN(date.getTime()) ? "" : localDateKey(date);
    }).filter(Boolean));
    const day = new Date();
    if (!days.has(localDateKey(day))) day.setDate(day.getDate() - 1);
    let count = 0;
    while (days.has(localDateKey(day))) {
      count += 1;
      day.setDate(day.getDate() - 1);
    }
    return count;
  }

  function totalToday() {
    const today = localDateKey(new Date());
    return state.sessions.reduce((sum, session) => {
      return localDateKey(new Date(session.ts)) === today ? sum + Number(session.min) : sum;
    }, 0);
  }

  function navigate(page) {
    const target = document.getElementById(`page-${page}`);
    if (!target) return;
    activePage = page;
    $$(".page").forEach(section => section.classList.toggle("active", section === target));
    $$(".nav-item[data-page], .mobile-nav-item[data-page]").forEach(button => {
      button.classList.toggle("active", button.dataset.page === page);
    });
    const titles = { timer: "Focus timer", tasks: "My tasks", reminders: "Reminders", analytics: "Analytics", history: "Session history", settings: "Settings & data" };
    $("#page-title").textContent = titles[page] || "Study Compass";
    if (page === "analytics") renderAnalytics();
    if (page === "history") renderHistory();
    if (page === "reminders") renderReminders();
    if (page === "tasks") renderTasks();
    if (page === "timer") renderPreview();
    history.replaceState(null, "", `#${page}`);
  }

  function renderSubjects() {
    const subjectSelect = $("#subject-select");
    const taskSubject = $("#task-subject");
    const reminderSubject = $("#reminder-subject");
    const previous = subjectSelect.value;
    const options = state.subjects.map(subject => `<option value="${escapeHtml(subject)}">${escapeHtml(subject)}</option>`).join("");
    subjectSelect.innerHTML = options;
    taskSubject.innerHTML = `<option value="">No subject</option>${options}`;
    reminderSubject.innerHTML = `<option value="">No subject</option>${options}`;
    subjectSelect.value = state.subjects.includes(previous) ? previous : state.subjects[0];
  }

  function renderHeader() {
    $("#today-label").textContent = new Date().toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" }).toUpperCase();
  }

  function renderStats() {
    const today = totalToday();
    const goal = state.goal;
    const openTasks = state.tasks.filter(task => !task.done).length;
    const streak = getDayStreak();
    $("#stat-today").innerHTML = `${today}<span> min</span>`;
    $("#stat-goal").textContent = `of ${goal} min goal`;
    $("#stat-streak").innerHTML = `${streak}<span> ${streak === 1 ? "day" : "days"}</span>`;
    $("#stat-open").textContent = String(openTasks);
    $("#nav-task-count").textContent = String(openTasks);
    $("#goal-progress-text").textContent = `${today} / ${goal} min`;
    $("#goal-progress-bar").style.width = `${Math.min(100, (today / goal) * 100)}%`;
    $("#routine-streak").textContent = streak ? `${streak}-day study streak. Keep it going!` : "Start a focus session to begin your streak.";
    $("#focus-minutes").value = state.cfg.focus;
    $("#short-minutes").value = state.cfg.short;
    $("#long-minutes").value = state.cfg.long;
    $("#goal-minutes").value = state.goal;
  }

  function timerTotal() {
    return state.cfg[state.timer.mode] * 60;
  }

  function renderTimer() {
    if (state.timer.running && state.timer.endsAt) {
      state.timer.remain = Math.max(0, Math.ceil((state.timer.endsAt - Date.now()) / 1000));
      if (state.timer.remain <= 0) {
        completeTimer();
        return;
      }
    }
    const total = timerTotal();
    const remain = Math.max(0, state.timer.remain);
    const minutes = String(Math.floor(remain / 60)).padStart(2, "0");
    const seconds = String(remain % 60).padStart(2, "0");
    const progress = $("#timer-progress");
    const circumference = 2 * Math.PI * 116;
    $("#timer-display").textContent = `${minutes}:${seconds}`;
    $("#timer-caption").textContent = `${MODE_LABELS[state.timer.mode].toUpperCase()} SESSION`;
    $("#timer-face").classList.toggle("break", state.timer.mode !== "focus");
    progress.style.strokeDasharray = String(circumference);
    progress.style.strokeDashoffset = String(circumference * (1 - remain / total));
    $$(".mode-button").forEach(button => button.classList.toggle("active", button.dataset.mode === state.timer.mode));
    const startButton = $("#timer-start");
    startButton.textContent = state.timer.running ? "Pause" : remain < total
      ? "Resume" : state.timer.mode === "focus" ? "Start focus" : "Start break";
    startButton.classList.toggle("button-primary", state.timer.mode === "focus");
    $("#timer-status").innerHTML = state.timer.running
      ? '<span class="status-dot"></span> Session in progress'
      : '<span class="status-dot"></span> Ready when you are';
    $("#timer-finish").disabled = state.timer.mode !== "focus";
    $("#timer-finish").style.opacity = state.timer.mode !== "focus" ? ".5" : "1";
    document.title = state.timer.running ? `${minutes}:${seconds} · Study Compass` : "Study Compass";
  }

  function setTimerMode(mode) {
    if (!MODE_LABELS[mode]) return;
    state.timer = { mode, remain: state.cfg[mode] * 60, running: false, endsAt: null };
    saveState();
    renderTimer();
  }

  function toggleTimer() {
    if (state.timer.running) {
      state.timer.remain = Math.max(0, Math.ceil((state.timer.endsAt - Date.now()) / 1000));
      state.timer.running = false;
      state.timer.endsAt = null;
    } else {
      if (state.timer.remain <= 0) state.timer.remain = timerTotal();
      state.timer.running = true;
      state.timer.endsAt = Date.now() + state.timer.remain * 1000;
    }
    saveState();
    renderTimer();
  }

  function logFocusSession(minutes) {
    if (minutes < 1) {
      showToast("Focus for at least one minute before logging a session.");
      return false;
    }
    state.sessions.push({ ts: new Date().toISOString(), min: minutes, subject: $("#subject-select").value || state.subjects[0] });
    return true;
  }

  function finishFocusEarly() {
    if (state.timer.mode !== "focus") return;
    const elapsed = Math.floor((timerTotal() - state.timer.remain) / 60);
    if (!logFocusSession(elapsed)) return;
    state.timer = { mode: "focus", remain: state.cfg.focus * 60, running: false, endsAt: null };
    saveState();
    renderAll();
    showToast(`Logged ${formatMinutes(elapsed)} of focus time. Nice work!`, "success");
  }

  function completeTimer() {
    const finishedMode = state.timer.mode;
    if (finishedMode === "focus") {
      logFocusSession(Math.floor(timerTotal() / 60));
      state.cycle += 1;
      const nextMode = state.cycle % 4 === 0 ? "long" : "short";
      state.timer = { mode: nextMode, remain: state.cfg[nextMode] * 60, running: false, endsAt: null };
      showToast("Focus session complete! Take a well-earned break.", "success");
      if ("Notification" in window && Notification.permission === "granted") {
        new Notification("Study Compass", { body: "Focus session complete! Time for a break.", icon: "./icon.svg" });
      }
    } else {
      state.timer = { mode: "focus", remain: state.cfg.focus * 60, running: false, endsAt: null };
      showToast("Break over. Ready to focus?");
    }
    saveState();
    renderAll();
  }

  function renderTasks() {
    const list = $("#task-list");
    const open = state.tasks.filter(task => !task.done).length;
    $("#task-summary").textContent = `${open} to do · ${state.tasks.length - open} completed`;
    $("#clear-done").classList.toggle("hidden", !state.tasks.some(task => task.done));
    if (!state.tasks.length) {
      list.innerHTML = '<div class="empty-state"><span class="empty-icon">✓</span><strong>Your list is a fresh start.</strong>Add a task above and take it one step at a time.</div>';
      return;
    }
    list.innerHTML = state.tasks.map(task => `
      <article class="task-row ${task.done ? "done" : ""}">
        <button class="check-button ${task.done ? "checked" : ""}" data-task-toggle="${escapeHtml(task.id)}" type="button" aria-label="${task.done ? "Mark incomplete" : "Mark complete"}">${task.done ? "✓" : ""}</button>
        <span class="task-text">${escapeHtml(task.text)}</span>
        ${task.subject ? `<span class="subject-tag">${escapeHtml(task.subject)}</span>` : ""}
        <button class="icon-button" data-task-delete="${escapeHtml(task.id)}" type="button" aria-label="Delete task">×</button>
      </article>`).join("");
  }

  function renderPreview() {
    const list = $("#task-preview");
    const tasks = state.tasks.filter(task => !task.done).slice(0, 3);
    if (!tasks.length) {
      list.innerHTML = '<div class="empty-state"><strong>No tasks on your plate.</strong>Add one whenever you’re ready.</div>';
      return;
    }
    list.innerHTML = tasks.map(task => `
      <div class="preview-task">
        <button class="check-button" data-task-toggle="${escapeHtml(task.id)}" type="button" aria-label="Mark complete"></button>
        <span class="task-text">${escapeHtml(task.text)}</span>
        ${task.subject ? `<span class="subject-tag">${escapeHtml(task.subject)}</span>` : ""}
      </div>`).join("");
  }

  function renderReminders() {
    const list = $("#reminder-list");
    let reminders = [...state.reminders];
    if (reminderFilter === "Today") {
      const today = localDateKey(new Date());
      reminders = reminders.filter(item => item.due && item.due.slice(0, 10) === today && item.status !== "Done");
    } else if (reminderFilter === "Overdue") {
      reminders = reminders.filter(isOverdue);
    } else if (reminderFilter === "Done") {
      reminders = reminders.filter(item => item.status === "Done");
    }
    reminders.sort((a, b) => {
      if ((a.status === "Done") !== (b.status === "Done")) return a.status === "Done" ? 1 : -1;
      if (!a.due && b.due) return 1;
      if (a.due && !b.due) return -1;
      return (a.due || "").localeCompare(b.due || "");
    });
    $("#reminder-summary").textContent = `${reminders.length} ${reminders.length === 1 ? "reminder" : "reminders"}`;
    if (!reminders.length) {
      list.innerHTML = '<div class="empty-state"><span class="empty-icon">♧</span><strong>All clear for now.</strong>Add a reminder above to keep a date or detail in view.</div>';
      return;
    }
    list.innerHTML = reminders.map(item => {
      const overdue = isOverdue(item);
      const dueValue = item.due ? new Date(item.due) : null;
      const dueDate = dueValue && !Number.isNaN(dueValue.getTime()) ? localDateKey(dueValue) : "";
      const dueTime = dueValue && !Number.isNaN(dueValue.getTime()) ? `${String(dueValue.getHours()).padStart(2, "0")}:${String(dueValue.getMinutes()).padStart(2, "0")}` : "";
      return `
        <article class="reminder-card ${overdue ? "overdue" : ""} ${item.status === "Done" ? "is-done" : ""}">
          <div class="reminder-main">
            <button class="check-button ${item.status === "Done" ? "checked" : ""}" data-reminder-toggle="${escapeHtml(item.id)}" type="button" aria-label="${item.status === "Done" ? "Mark reminder incomplete" : "Mark reminder done"}">${item.status === "Done" ? "✓" : ""}</button>
            <div>
              <h3 class="reminder-title">${escapeHtml(item.title)}</h3>
              <div class="reminder-meta">
                <span class="priority-chip ${item.priority.toLowerCase()}">${escapeHtml(item.priority)} priority</span>
                ${item.status === "Done" ? '<span class="status-chip done">Done</span>' : ""}
                ${item.subject ? `<span class="subject-tag">${escapeHtml(item.subject)}</span>` : ""}
                <span>${overdue ? "Overdue · " : ""}${escapeHtml(formatDue(item.due))}</span>
              </div>
            </div>
          </div>
          <div class="reminder-actions"><button class="icon-button" data-reminder-delete="${escapeHtml(item.id)}" type="button" aria-label="Delete reminder">×</button></div>
          <details class="reminder-details">
            <summary>Edit details${item.notes ? " · notes" : ""}</summary>
            <form class="reminder-edit" data-reminder-edit="${escapeHtml(item.id)}">
              <label>Title<input name="title" maxlength="120" value="${escapeHtml(item.title)}" required></label>
              <label>Due date<input name="date" type="date" value="${escapeHtml(dueDate)}"></label>
              <label>Time<input name="time" type="time" value="${escapeHtml(dueTime)}"></label>
              <label>Priority<select name="priority">${["High", "Medium", "Low"].map(option => `<option ${item.priority === option ? "selected" : ""}>${option}</option>`).join("")}</select></label>
              <label>Status<select name="status">${["To do", "In progress", "Done"].map(option => `<option ${item.status === option ? "selected" : ""}>${option}</option>`).join("")}</select></label>
              <label>Subject<select name="subject"><option value="">No subject</option>${state.subjects.map(option => `<option value="${escapeHtml(option)}" ${item.subject === option ? "selected" : ""}>${escapeHtml(option)}</option>`).join("")}</select></label>
              <label class="notes-field">Notes<textarea name="notes" maxlength="2000">${escapeHtml(item.notes)}</textarea></label>
              <div class="edit-actions"><button class="button button-primary" type="submit">Save changes</button></div>
            </form>
          </details>
        </article>`;
    }).join("");
  }

  function isOverdue(item) {
    if (!item.due || item.status === "Done") return false;
    const due = new Date(item.due);
    return !Number.isNaN(due.getTime()) && due.getTime() < Date.now();
  }

  function renderAnalytics() {
    const cutoff = analyticsRange ? Date.now() - analyticsRange * 86400000 : 0;
    const sessions = state.sessions.filter(session => !cutoff || new Date(session.ts).getTime() >= cutoff);
    const totals = Object.fromEntries(state.subjects.map(subject => [subject, 0]));
    sessions.forEach(session => { totals[session.subject] = (totals[session.subject] || 0) + Number(session.min); });
    const ranked = Object.entries(totals).sort((a, b) => b[1] - a[1]);
    const total = ranked.reduce((sum, [, minutes]) => sum + minutes, 0);
    const chart = $("#subject-chart");
    if (!total) {
      $("#analytics-callout").textContent = "No focus time in this range yet. Complete a focus session to start your progress.";
      chart.innerHTML = '<div class="empty-state"><strong>Your progress will show here.</strong>Start a focus session and come back to see your study time.</div>';
    } else {
      const active = ranked.filter(([, minutes]) => minutes > 0);
      const most = active[0];
      const least = active[active.length - 1];
      $("#analytics-callout").textContent = `Most studied: ${most[0]} (${most[1]} min) · Least studied: ${least[0]} (${least[1]} min) · Total: ${total} min`;
      const max = Math.max(1, most[1]);
      chart.innerHTML = ranked.map(([subject, minutes], index) => `
        <div class="chart-row">
          <span class="chart-name">${escapeHtml(subject)}</span>
          <span class="chart-track"><span class="chart-fill" style="display:block;width:${minutes ? Math.max(2, (minutes / max) * 100) : 0}%;background:${COLORS[state.subjects.indexOf(subject) % COLORS.length]}"></span></span>
          <span class="chart-minutes">${minutes} min</span>
        </div>`).join("");
    }

    const today = new Date();
    const days = [];
    for (let offset = 6; offset >= 0; offset -= 1) {
      const day = new Date(today);
      day.setDate(today.getDate() - offset);
      const key = localDateKey(day);
      const minutes = state.sessions.reduce((sum, session) =>
        localDateKey(new Date(session.ts)) === key ? sum + Number(session.min) : sum, 0);
      days.push({ key, label: day.toLocaleDateString([], { weekday: "short" }), minutes });
    }
    const peak = Math.max(state.goal, ...days.map(day => day.minutes), 1);
    $("#weekly-total").textContent = `${days.reduce((sum, day) => sum + day.minutes, 0)} min this week`;
    $("#weekly-chart").innerHTML = days.map(day => `
      <div class="week-day" title="${escapeHtml(day.key)}: ${day.minutes} minutes">
        <div class="week-bar-area"><span class="week-value">${day.minutes ? day.minutes : ""}</span><span class="week-bar" style="height:${day.minutes ? Math.max(3, day.minutes / peak * 100) : 2}%"></span></div>
        <span class="week-label">${escapeHtml(day.label)}</span>
      </div>`).join("");
  }

  function renderHistory() {
    const list = $("#history-list");
    const sessions = [...state.sessions].sort((a, b) => new Date(b.ts) - new Date(a.ts));
    const total = sessions.reduce((sum, session) => sum + Number(session.min), 0);
    $("#history-summary").textContent = `${sessions.length} ${sessions.length === 1 ? "session" : "sessions"} · ${formatMinutes(total)} total`;
    if (!sessions.length) {
      list.innerHTML = '<div class="empty-state"><span class="empty-icon">↺</span><strong>Your history starts with your first session.</strong>Complete a focus session to see it here.</div>';
      return;
    }
    list.innerHTML = sessions.map((session, index) => {
      const date = new Date(session.ts);
      const label = Number.isNaN(date.getTime()) ? "Date unavailable" : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
      return `
        <article class="history-row">
          <span class="history-icon">◷</span>
          <div><div class="history-subject">${escapeHtml(session.subject)}</div><div class="history-date">${escapeHtml(label)}</div></div>
          <span class="history-duration">${escapeHtml(formatMinutes(Number(session.min)))}</span>
          <button class="icon-button" data-session-delete="${index}" type="button" aria-label="Delete session">×</button>
        </article>`;
    }).join("");
  }

  function renderAll() {
    renderHeader();
    renderSubjects();
    renderStats();
    renderTimer();
    renderTasks();
    renderPreview();
    renderReminders();
    if (activePage === "analytics") renderAnalytics();
    if (activePage === "history") renderHistory();
  }

  function addTask(event) {
    event.preventDefault();
    const input = $("#task-input");
    const text = input.value.trim();
    if (!text) return;
    state.tasks.push({ id: makeId(), text, subject: $("#task-subject").value, done: false });
    input.value = "";
    saveState();
    renderAll();
    input.focus();
    showToast("Task added to your list.", "success");
  }

  function createReminder(event) {
    event.preventDefault();
    const title = $("#reminder-title").value.trim();
    if (!title) return;
    const date = $("#reminder-date").value;
    const time = $("#reminder-time").value || "09:00";
    state.reminders.push({
      id: makeId(), title, due: date ? `${date}T${time}` : "",
      priority: $("#reminder-priority").value, status: "To do",
      subject: $("#reminder-subject").value, notes: "", notifiedAt: ""
    });
    $("#reminder-form").reset();
    saveState();
    renderAll();
    showToast("Reminder created.", "success");
  }

  function saveReminderEdit(event) {
    const form = event.target.closest("[data-reminder-edit]");
    if (!form) return;
    event.preventDefault();
    const reminder = state.reminders.find(item => item.id === form.dataset.reminderEdit);
    if (!reminder) return;
    const data = new FormData(form);
    reminder.title = String(data.get("title") || "").trim();
    const date = String(data.get("date") || "");
    const time = String(data.get("time") || "09:00");
    reminder.due = date ? `${date}T${time}` : "";
    reminder.priority = String(data.get("priority"));
    reminder.status = String(data.get("status"));
    reminder.subject = String(data.get("subject") || "");
    reminder.notes = String(data.get("notes") || "").trim();
    reminder.notifiedAt = "";
    saveState();
    renderAll();
    showToast("Reminder updated.", "success");
  }

  function checkDueReminders() {
    const now = Date.now();
    let changed = false;
    for (const reminder of state.reminders) {
      if (!reminder.due || reminder.status === "Done" || reminder.notifiedAt) continue;
      const due = new Date(reminder.due).getTime();
      if (Number.isFinite(due) && due <= now) {
        reminder.notifiedAt = new Date().toISOString();
        showToast(`Reminder: ${reminder.title}`);
        if ("Notification" in window && Notification.permission === "granted") {
          new Notification(reminder.title, { body: "Your Study Compass reminder is due.", icon: "./icon.svg" });
        }
        changed = true;
      }
    }
    if (changed) saveState();
  }

  function exportData() {
    const blob = new Blob([JSON.stringify(state, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `study-compass-backup-${localDateKey(new Date())}.json`;
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    showToast("Your Study Compass backup was downloaded.", "success");
  }

  async function importData(file) {
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text());
      const imported = normalizeState(parsed);
      if (!window.confirm("Replace this browser’s Study Compass data with the selected backup?")) return;
      state = imported;
      saveState();
      renderAll();
      showToast("Your Study Compass data was restored.", "success");
    } catch (error) {
      console.error("Could not import Study Compass backup:", error);
      showToast(`Could not import that backup: ${error.message || "invalid JSON file"}`);
    } finally {
      $("#import-data").value = "";
    }
  }

  function bindEvents() {
    document.addEventListener("click", event => {
      const nav = event.target.closest("[data-page], [data-navigate]");
      if (nav) {
        navigate(nav.dataset.page || nav.dataset.navigate);
        return;
      }
      const mode = event.target.closest("[data-mode]");
      if (mode) {
        setTimerMode(mode.dataset.mode);
        return;
      }
      const toggleTask = event.target.closest("[data-task-toggle]");
      if (toggleTask) {
        const task = state.tasks.find(item => item.id === toggleTask.dataset.taskToggle);
        if (task) task.done = !task.done;
        saveState();
        renderAll();
        return;
      }
      const deleteTask = event.target.closest("[data-task-delete]");
      if (deleteTask) {
        state.tasks = state.tasks.filter(item => item.id !== deleteTask.dataset.taskDelete);
        saveState();
        renderAll();
        return;
      }
      const deleteReminder = event.target.closest("[data-reminder-delete]");
      if (deleteReminder) {
        state.reminders = state.reminders.filter(item => item.id !== deleteReminder.dataset.reminderDelete);
        saveState();
        renderAll();
        return;
      }
      const toggleReminder = event.target.closest("[data-reminder-toggle]");
      if (toggleReminder) {
        const reminder = state.reminders.find(item => item.id === toggleReminder.dataset.reminderToggle);
        if (reminder) {
          reminder.status = reminder.status === "Done" ? "To do" : "Done";
          reminder.notifiedAt = "";
        }
        saveState();
        renderAll();
        return;
      }
      const deleteSession = event.target.closest("[data-session-delete]");
      if (deleteSession) {
        const sessions = [...state.sessions].sort((a, b) => new Date(b.ts) - new Date(a.ts));
        const session = sessions[Number(deleteSession.dataset.sessionDelete)];
        if (session && window.confirm("Delete this focus session from your history?")) {
          const index = state.sessions.indexOf(session);
          if (index >= 0) state.sessions.splice(index, 1);
          saveState();
          renderAll();
        }
        return;
      }
      const filter = event.target.closest("[data-filter]");
      if (filter) {
        reminderFilter = filter.dataset.filter;
        $$("#reminder-filters .filter-chip").forEach(button => button.classList.toggle("active", button === filter));
        renderReminders();
        return;
      }
      const range = event.target.closest("[data-range]");
      if (range) {
        analyticsRange = Number(range.dataset.range);
        $$("#range-filters .filter-chip").forEach(button => button.classList.toggle("active", button === range));
        renderAnalytics();
      }
    });

    $("#timer-start").addEventListener("click", toggleTimer);
    $("#timer-finish").addEventListener("click", finishFocusEarly);
    $("#timer-reset").addEventListener("click", () => setTimerMode(state.timer.mode));
    $("#task-form").addEventListener("submit", addTask);
    $("#reminder-form").addEventListener("submit", createReminder);
    $("#reminder-list").addEventListener("submit", saveReminderEdit);
    $("#clear-done").addEventListener("click", () => {
      state.tasks = state.tasks.filter(task => !task.done);
      saveState();
      renderAll();
      showToast("Completed tasks cleared.");
    });
    $("#add-subject-button").addEventListener("click", () => {
      $("#subject-form").classList.toggle("hidden");
      $("#new-subject").focus();
    });
    $("#subject-form").addEventListener("submit", event => {
      event.preventDefault();
      const input = $("#new-subject");
      const name = input.value.trim();
      if (!name) return;
      if (state.subjects.some(subject => subject.toLowerCase() === name.toLowerCase())) {
        showToast("That subject is already on your list.");
        return;
      }
      state.subjects.push(name);
      input.value = "";
      $("#subject-form").classList.add("hidden");
      saveState();
      renderAll();
      $("#subject-select").value = name;
      showToast(`${name} added to your subjects.`, "success");
    });
    for (const key of ["focus", "short", "long"]) {
      $(`#${key}-minutes`).addEventListener("change", event => {
        const next = clampNumber(event.target.value, state.cfg[key], 1, 120);
        event.target.value = next;
        state.cfg[key] = next;
        if (state.timer.mode === key && !state.timer.running) state.timer.remain = next * 60;
        saveState();
        renderAll();
      });
    }
    $("#goal-minutes").addEventListener("change", event => {
      state.goal = clampNumber(event.target.value, state.goal, 10, 600);
      event.target.value = state.goal;
      saveState();
      renderAll();
    });
    $("#export-data").addEventListener("click", exportData);
    $("#import-data").addEventListener("change", event => importData(event.target.files[0]));
    $("#clear-data").addEventListener("click", () => {
      if (!window.confirm("Delete all Study Compass data saved in this browser? Export a backup first if you may need this data later.")) return;
      state = structuredClone(DEFAULTS);
      saveState();
      renderAll();
      showToast("Browser data cleared.");
    });
    window.addEventListener("hashchange", () => navigate(location.hash.slice(1) || "timer"));
    window.addEventListener("beforeunload", saveState);
    window.addEventListener("storage", event => {
      if (event.key === STORAGE_KEY && event.newValue) {
        try {
          state = normalizeState(JSON.parse(event.newValue));
          renderAll();
        } catch (error) {
          console.error("Could not sync Study Compass data across tabs:", error);
          showToast("A change from another tab could not be loaded.");
        }
      }
    });
    window.addEventListener("beforeinstallprompt", event => {
      event.preventDefault();
      deferredInstallPrompt = event;
      $("#install-button").classList.remove("hidden");
    });
    $("#install-button").addEventListener("click", async () => {
      if (!deferredInstallPrompt) return;
      deferredInstallPrompt.prompt();
      await deferredInstallPrompt.userChoice;
      deferredInstallPrompt = null;
      $("#install-button").classList.add("hidden");
    });
  }

  function start() {
    renderAll();
    bindEvents();
    window.setInterval(() => {
      if (state.timer.running) renderTimer();
      checkDueReminders();
    }, 1000);
    $("#today-label").setAttribute("title", new Date().toLocaleDateString());
    const requestedPage = location.hash.slice(1);
    if (requestedPage) navigate(requestedPage);
    if ("serviceWorker" in navigator && /^https?:$/.test(location.protocol)) {
      navigator.serviceWorker.register("./service-worker.js").catch(error => {
        console.error("Study Compass offline support could not be enabled:", error);
      });
    }
  }

  start();
})();
