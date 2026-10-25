(function () {
  const KB = window.KB = window.KB || {};
  const PRIORITY = { urgent: 0, high: 1, normal: 2, low: 3 };
  const EVENT_META = {
    created: { icon: "plus", label: "Created" },
    edited: { icon: "pencil", label: "Edited" },
    moved: { icon: "arrowRight", label: "Moved" },
    closed: { icon: "check", label: "Closed" },
    reopened: { icon: "rotate", label: "Reopened" },
    noted: { icon: "dot", label: "Note added" },
    commented: { icon: "comment", label: "Comment added" },
    attachment_added: { icon: "paperclip", label: "Attachment added" },
    deleted: { icon: "close", label: "Deleted" },
    column_added: { icon: "columns", label: "Column added" },
    column_updated: { icon: "columns", label: "Column updated" },
    column_deleted: { icon: "columns", label: "Column deleted" },
    columns_reordered: { icon: "reorder", label: "Columns reordered" },
    project_added: { icon: "project", label: "Project added" },
    project_updated: { icon: "project", label: "Project updated" },
    project_deleted: { icon: "close", label: "Project deleted" },
    project_order_updated: { icon: "reorder", label: "Project order updated" },
    timer_started: { icon: "clock", label: "Timer started" },
    timer_stopped: { icon: "clock", label: "Timer stopped" },
    timer_auto_stopped: { icon: "clock", label: "Timer auto-stopped" }
  };

  function matches(card, filters) {
    if (filters.project && card.project !== filters.project) return false;
    if (filters.priority && card.priority !== filters.priority) return false;
    if (filters.search) {
      const haystack = (card.title + " " + card.body + " " + (card.tags || []).join(" ")).toLowerCase();
      if (!haystack.includes(filters.search.toLowerCase())) return false;
    }
    if (filters.mode === "human") return card.updated_by === "human";
    if (filters.mode === "ai") return card.updated_by === "ai";
    if (filters.mode === "ai-touched") {
      return card.created_by === "ai" || card.updated_by === "ai" || card.closed_by === "ai";
    }
    return true;
  }

  KB.filterCards = function (state, filters) {
    return (state.cards || []).filter(function (card) { return matches(card, filters); });
  };

  function baseCards(state, filters) {
    return (state.cards || []).filter(function (card) {
      return matches(card, Object.assign({}, filters, { mode: "all" }));
    });
  }

  KB.renderFilters = function (state, filters) {
    const base = baseCards(state, filters);
    const modes = [
      { id: "all", label: "All", hint: "All cards" },
      { id: "human", label: "Human", hint: "Cards whose last edit was by a human" },
      { id: "ai", label: "AI", hint: "Cards whose last edit was by AI" },
      { id: "ai-touched", label: "Touched by AI", hint: "Cards created, edited or closed by AI" },
    ];
    const html = modes.map(function (mode) {
      const count = mode.id === "all" ? base.length : base.filter(function (card) {
        return matches(card, Object.assign({}, filters, { mode: mode.id }));
      }).length;
      return '<button class="filter-btn ' + (filters.mode === mode.id ? "active" : "") +
        '" data-action="filter" data-filter="' + mode.id + '" title="' + KB.esc(mode.hint) + '">' +
        mode.label + '<span class="filter-count">' + count + "</span></button>";
    }).join("");
    document.getElementById("filters").innerHTML = html;
  };

  KB.renderProjectSelect = function (state, filters) {
    const select = document.getElementById("project-filter");
    const projects = state.projects || [];
    const options = ['<option value="">All projects</option>'].concat(projects.map(function (project) {
      return '<option value="' + KB.esc(project.id) + '">' + KB.esc(project.name) + "</option>";
    })).join("");
    select.innerHTML = options;
    const exists = projects.some(function (project) { return project.id === filters.project; });
    if (!exists) filters.project = "";
    select.value = filters.project || "";
  };

  function cardHtml(state, card) {
    const column = KB.columnById(state, card.column);
    const project = KB.projectById(state, card.project);
    const closed = Boolean(column && column.closed);
    const tags = (card.tags || []).map(function (tag) {
      return '<span class="tag">#' + KB.esc(tag) + "</span>";
    }).join("");
    const body = card.body ? '<p class="card-body-preview">' + KB.esc(card.body.slice(0, 160)) +
      (card.body.length > 160 ? "…" : "") + "</p>" : "";
    const closeNote = card.close_note ? '<p class="card-body-preview">Closed: ' + KB.esc(card.close_note) + "</p>" : "";
    const doneIn = closed ? KB.finishedIn(card) : "";
    return '<article class="card ' + (closed ? "is-closed" : "") + '" draggable="true" data-card-id="' +
      KB.esc(card.id) + '">' +
      '<div class="card-top">' + KB.priorityPill(card.priority) +
      (project ? '<span class="pill project">' + KB.esc(project.name) + "</span>" : "") + "</div>" +
      "<h4>" + KB.esc(card.title) + "</h4>" + body + closeNote +
      (tags ? '<div class="tag-list">' + tags + "</div>" : "") +
      '<div class="card-meta">' + KB.provenance(card) +
      '<span class="prov-sep">·</span><span>' + KB.ago(card.updated_at) + "</span>" +
      (doneIn ? '<span class="prov-sep">·</span><span class="card-done-time" title="Time from creation to close">' +
        "Done in " + doneIn + "</span>" : "") +
      '<span class="tag">' + KB.esc(card.id) + "</span>" +
      (card.comments && card.comments.length ? '<span class="comment-count" title="Comments">' +
        KB.icon("comment") + card.comments.length + "</span>" : "") +
      "</div>" +
      '<div class="card-actions">' +
      '<button data-action="card-details" title="Open full details">' + KB.icon("eye") +
        "Details</button>" +
      '<button data-action="card-edit" title="Edit card">' + KB.icon("pencil") + "Edit</button>" +
      '<button data-action="card-comment" title="Add comment">' + KB.icon("comment") +
        "Comment</button>" +
      '<button data-action="card-toggle-close" title="' + (closed ? "Reopen card" : "Close card") + '">' +
      KB.icon(closed ? "rotate" : "close") + (closed ? "Reopen" : "Close") + "</button>" +
      "</div></article>";
  }

  const COLUMN_SORT_OPTIONS = [
    ["priority", "Priority"],
    ["updated", "Newest update"],
    ["oldest", "Oldest update"],
    ["created", "Newest created"],
    ["created-asc", "Oldest created"],
    ["title-asc", "Name A–Z"],
    ["title-desc", "Name Z–A"],
  ];

  function dateValue(value) {
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? 0 : parsed;
  }

  function compareCards(a, b, mode) {
    const byUpdated = dateValue(b.updated_at) - dateValue(a.updated_at);
    if (mode === "updated") return byUpdated;
    if (mode === "oldest") return -byUpdated;
    if (mode === "created") return dateValue(b.created_at) - dateValue(a.created_at) || byUpdated;
    if (mode === "created-asc") return dateValue(a.created_at) - dateValue(b.created_at) || byUpdated;
    if (mode === "title-asc" || mode === "title-desc") {
      const order = String(a.title || "").localeCompare(String(b.title || ""));
      return (mode === "title-desc" ? -order : order) || byUpdated;
    }
    const pa = PRIORITY[a.priority] == null ? 2 : PRIORITY[a.priority];
    const pb = PRIORITY[b.priority] == null ? 2 : PRIORITY[b.priority];
    return pa - pb || byUpdated;
  }

  function columnSortSelect(column, selected) {
    return '<select class="column-sort" data-column-sort="' + KB.esc(column.id) +
      '" title="Sort cards in this column" aria-label="Sort cards in ' + KB.esc(column.title) + '">' +
      COLUMN_SORT_OPTIONS.map(function (option) {
        return '<option value="' + option[0] + '"' +
          (option[0] === selected ? " selected" : "") + ">" + option[1] + "</option>";
      }).join("") + "</select>";
  }

  KB.renderBoard = function (state, filters) {
    const board = document.getElementById("board");
    const scroll = board.scrollLeft;
    const columns = (state.columns || []).slice().sort(function (a, b) { return a.order - b.order; });
    if (!columns.length) {
      board.innerHTML = '<div class="empty-note">No columns yet. Use the Columns button in the toolbar to create the board.</div>';
      return;
    }
    const cards = KB.filterCards(state, filters);
    const overrides = KB.columnSorts || {};
    board.innerHTML = columns.map(function (column) {
      const sortMode = overrides[column.id] || filters.sort || "priority";
      const inColumn = cards.filter(function (card) { return card.column === column.id; })
        .sort(function (a, b) { return compareCards(a, b, sortMode); });
      return '<section class="column ' + (column.closed ? "closed" : "") + '" data-column-id="' + KB.esc(column.id) + '">' +
        '<header class="column-head" style="--col-color:' + KB.color(column.color) + '">' +
        '<span class="col-dot"></span><h3>' + KB.esc(column.title) + "</h3>" +
        '<span class="column-count">' + inColumn.length + "</span>" +
        (column.closed ? '<span class="closed-pill">closed</span>' : "") +
        columnSortSelect(column, sortMode) +
        '<button class="icon-btn" data-action="add-card" data-column-id="' + KB.esc(column.id) +
        '" title="Add card to this column" aria-label="Add card to this column">' +
        KB.icon("plus") + "</button>" +
        '<button class="icon-btn" data-action="edit-column" data-column-id="' + KB.esc(column.id) +
        '" title="Edit this column" aria-label="Edit this column">' +
        KB.icon("pencil") + "</button></header>" +
        '<div class="card-list" data-drop-column="' + KB.esc(column.id) + '">' +
        (inColumn.length ? inColumn.map(function (card) { return cardHtml(state, card); }).join("")
          : '<div class="empty-column">Drop cards here</div>') +
        "</div></section>";
    }).join("");
    board.scrollLeft = scroll;
    if (KB.enhanceSelects) KB.enhanceSelects(board);
    if (KB.refreshScrollShadows) KB.refreshScrollShadows(board);
  };

  let selectedProjectId = null;

  KB.selectProject = function (id) { selectedProjectId = id || null; };
  KB.selectedProjectId = function () { return selectedProjectId; };

  function allProjectsRowHtml(state) {
    const cards = state.cards || [];
    const selected = !selectedProjectId;
    return '<article class="project-row all-projects ' + (selected ? "selected " : "") +
      '" data-action="project-all" title="Show cards from every project">' +
      '<div class="project-row-main"><div class="project-row-name">' +
      KB.icon("board") + '<span class="project-row-label">All projects</span></div></div>' +
      '<span class="progress-label" title="All cards on the board">' + cards.length + "</span></article>";
  }

  function projectRowHtml(state, project) {
    const active = Boolean(state.active_timer && state.active_timer.project &&
      state.active_timer.project.id === project.id);
    const progress = Math.max(0, Math.min(100, Number(project.progress) || 0));
    const selected = selectedProjectId === project.id;
    const color = KB.color(project.color);
    return '<article class="project-row ' + (selected ? "selected " : "") + (active ? "active " : "") +
      '" data-project-id="' + KB.esc(project.id) + '" data-action="project-select" draggable="true" ' +
      'style="--project-color:' + color + '" ' +
      'title="Drag to reorder; click for project details">' +
      '<div class="project-row-main"><div class="project-row-name">' +
      '<span class="project-color-dot" style="--project-color:' + color + '"></span>' +
      '<span class="project-row-label">' + KB.esc(project.name) + "</span></div></div>" +
      '<span class="progress-label" title="Automatic progress: closed cards divided by all cards">' +
      progress + "%</span>" +
      '<button type="button" class="icon-btn" data-action="project-edit" data-project-id="' + KB.esc(project.id) +
      '" title="Edit project" aria-label="Edit project">' +
      KB.icon("pencil") + "</button></article>";
  }

  function projectDetailHtml(state, project) {
    const metrics = project.metrics || {};
    const activity = project.activity || {};
    const active = Boolean(state.active_timer && state.active_timer.project &&
      state.active_timer.project.id === project.id);
    const progress = Math.max(0, Math.min(100, Number(project.progress) || 0));
    const git = activity.git ? [
      '<span class="git-pill">' + KB.esc(activity.branch || "detached") + "</span>",
      '<span class="git-pill ' + (activity.dirty ? "dirty" : "") + '" title="' +
        KB.esc(KB.uncommittedTitle(activity.dirty)) + '">' +
        KB.esc(KB.uncommittedLabel(activity.dirty)) + "</span>",
      '<span class="git-pill" title="' + KB.esc(activity.last_commit ? activity.last_commit.subject : "") + '">last ' +
        (activity.last_commit ? KB.ago(activity.last_commit.ts) : "no commits") + "</span>",
      '<span class="git-pill">' + (activity.commits_7d == null ? "?" : activity.commits_7d) + " commits/7d</span>",
    ].join("") : '<span class="git-warning" role="img" tabindex="0" aria-label="Git activity unavailable" title="' +
      KB.esc(activity.error || "not a git repository") + '">' +
      KB.icon("warning") + (activity.exists ? "git unavailable" : "path missing") + "</span>";
    const docs = activity.docs;
    const docsLine = docs && docs.exists ? '<div class="docs-line">' +
      (docs.found || []).map(function (name) {
        return '<span class="doc-pill" title="Project documentation available to agents">' +
          KB.icon("file") + KB.esc(name) + "</span>";
      }).join("") +
      (docs.warnings || []).map(function (text) {
        return '<span class="doc-warning" role="img" tabindex="0" aria-label="Missing project documentation" ' +
          'title="Agents must read the project README.md, AGENTS.md, SKILL.md and docs/ before working its cards">' +
          KB.icon("warning") + KB.esc(text) + "</span>";
      }).join("") + "</div>" : "";
    return '<article class="project-card project-detail-card ' + (active ? "active" : "") +
      '" data-project-id="' + KB.esc(project.id) + '">' +
      '<div class="project-head"><div class="project-head-main"><div class="project-name">' + KB.esc(project.name) + "</div>" +
      '<div class="project-path" title="' + KB.esc(project.path) + '">' + KB.esc(project.path) + "</div></div>" +
      '<button type="button" class="icon-btn" data-action="project-edit" data-project-id="' + KB.esc(project.id) +
      '" title="Edit project" aria-label="Edit project">' +
      KB.icon("pencil") + "</button></div>" +
      '<div class="progress-row" title="Automatic progress: closed cards divided by all cards">' +
      '<div class="progress-track"><div class="progress-fill" style="width:' +
      progress + '%"></div></div><span class="progress-label">' + progress + "%</span></div>" +
      '<div class="project-metrics"><div>Open<b>' + (metrics.cards_open || 0) + "</b></div>" +
      "<div>Closed<b>" + (metrics.cards_closed || 0) + "</b></div>" +
      "<div>Today<b>" + KB.duration(metrics.tracked_today || 0) + "</b></div></div>" +
      '<div class="git-line">' + git + "</div>" +
      docsLine +
      (project.progress_note ? '<div class="card-body-preview">' + KB.esc(project.progress_note.slice(0, 110)) + "</div>" : "") +
      '<div class="project-actions"><span class="project-timer-note">Timer follows AI card work</span>' +
      '<span class="progress-label">total ' + KB.duration(metrics.tracked_total || 0) + "</span></div>" +
      "</article>";
  }

  function allProjectsDetailHtml() {
    return '<article class="project-card project-detail-card">' +
      '<div class="project-head"><div class="project-head-main">' +
      '<div class="project-name">All projects</div></div></div>' +
      '<p class="empty-note">Select a project above to filter the board to its cards and see its details.</p>' +
      "</article>";
  }

  KB.renderProjects = function (state) {
    const node = document.getElementById("project-list");
    const detail = document.getElementById("project-detail");
    const projects = state.projects || [];
    if (!projects.length) {
      node.innerHTML = '<div class="empty-note">Register a local project by absolute path to see its git activity, progress and tracked time.</div>';
      if (detail) detail.innerHTML = "";
      if (KB.refreshScrollShadows) KB.refreshScrollShadows(node);
      return;
    }
    const exists = projects.some(function (project) { return project.id === selectedProjectId; });
    if (!exists) selectedProjectId = null;
    const selected = projects.find(function (project) { return project.id === selectedProjectId; }) || null;
    node.innerHTML = allProjectsRowHtml(state) +
      projects.map(function (project) { return projectRowHtml(state, project); }).join("");
    if (detail) detail.innerHTML = selected ? projectDetailHtml(state, selected) : allProjectsDetailHtml();
    if (KB.refreshScrollShadows) KB.refreshScrollShadows(node);
  };

  KB.renderOverview = function (state) {
    const overview = state.overview || {};
    const today = overview.events_today || { ai: 0, human: 0 };
    const entries = [
      ["Projects", overview.projects || 0],
      ["Open cards", overview.cards_open || 0],
      ["Closed cards", overview.cards_closed || 0],
      ["Tracked today", KB.duration(overview.tracked_today || 0)],
      ["Tracked week", KB.duration(overview.tracked_week || 0)],
      ["AI events today", today.ai || 0],
      ["Human events today", today.human || 0],
    ];
    document.getElementById("overview").innerHTML = entries.map(function (entry) {
      return "<div>" + entry[0] + "<b>" + KB.esc(entry[1]) + "</b></div>";
    }).join("");
  };

  KB.renderEvents = function (state) {
    const node = document.getElementById("event-list");
    if (!node) return;
    const events = (state.events || []).slice(0, 50);
    if (!events.length) {
      node.innerHTML = '<div class="empty-note">No events yet.</div>';
      if (KB.refreshScrollShadows) KB.refreshScrollShadows(node);
      return;
    }
    node.innerHTML = events.map(function (event) {
      const meta = EVENT_META[event.kind] || { icon: "dot", label: "Activity" };
      return '<div class="event-item">' +
        '<span class="event-icon" role="img" aria-label="' + KB.esc(meta.label) +
        '" title="' + KB.esc(meta.label) + '">' + KB.icon(meta.icon) + "</span>" +
        '<div class="event-main"><div><span class="event-text">' + KB.esc(event.summary) +
        '</span> ' + KB.actorTag(event.actor, event.actor === "ai" ? "AI event" : "Human event") +
        '</div><div class="event-time">' + KB.ago(event.ts) + "</div></div></div>";
    }).join("");
    if (KB.refreshScrollShadows) KB.refreshScrollShadows(node);
  };

  KB.renderTimer = function (state) {
    const banner = document.getElementById("timer-banner");
    const active = state.active_timer;
    if (!active) {
      banner.classList.add("hidden");
      banner.innerHTML = "";
      return;
    }
    const project = active.project || KB.projectById(state, active.session && active.session.project);
    const cardId = active.session && active.session.card_id;
    const card = cardId ? (state.cards || []).find(function (item) { return item.id === cardId; }) : null;
    const start = Date.parse(active.session ? active.session.start : "");
    const elapsed = Number.isNaN(start) ? active.elapsed || 0 : Math.max(0, (Date.now() - start) / 1000);
    banner.innerHTML = '<span class="timer-dot"></span><strong>' +
      KB.esc(project ? project.name : "Unknown project") + "</strong>" +
      (card ? '<span class="timer-card">' + KB.esc(card.title) + "</span>" : "") +
      '<span class="timer-elapsed" data-start="' + (Number.isNaN(start) ? "" : start) + '">' +
      KB.duration(elapsed) + "</span><span>tracked time running</span><span class=\"spacer\"></span>" +
      '<span class="timer-auto">auto timer</span>';
    banner.classList.remove("hidden");
  };

  KB.renderAll = function (state, filters) {
    if (KB.closeDropdowns) KB.closeDropdowns();
    KB.renderFilters(state, filters);
    KB.renderProjectSelect(state, filters);
    KB.renderBoard(state, filters);
    KB.renderProjects(state);
    KB.renderOverview(state);
    KB.renderEvents(state);
    KB.renderTimer(state);
    if (KB.enhanceSelects) KB.enhanceSelects(document);
    if (KB.refreshScrollShadows) KB.refreshScrollShadows(document);
    const home = document.getElementById("footer-home");
    if (home) home.textContent = "Data: " + (state.server && state.server.home ? state.server.home : "~/.kanban");
    const status = document.getElementById("server-status");
    if (status) status.textContent = "Local board · synced " + new Date().toLocaleTimeString();
    const dot = document.getElementById("settings-sync-dot");
    if (dot) dot.classList.add("online");
    const server = document.getElementById("settings-server-status");
    if (server) server.textContent = "Server on";
    const port = document.getElementById("settings-server-port");
    if (port) port.textContent = state.server && state.server.port ? "port " + state.server.port : "";
  };
})();
