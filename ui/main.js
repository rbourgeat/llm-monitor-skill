(function () {
  const KB = window.KB = window.KB || {};
  let state = null;
  let refreshing = false;
  let draggingId = null;
  let draggingProjectId = null;
  let signature = null;
  let watching = false;
  let refreshQueued = false;
  const filters = { mode: "all", project: "", priority: "", search: "", sort: "priority" };
  KB.columnSorts = {};

  function setOffline(error) {
    const dot = document.getElementById("settings-sync-dot");
    const status = document.getElementById("server-status");
    const server = document.getElementById("settings-server-status");
    const port = document.getElementById("settings-server-port");
    if (dot) dot.classList.remove("online");
    if (status) status.textContent = "Server offline";
    if (server) server.textContent = "Server off";
    if (port) port.textContent = "";
    if (error && error.message !== "Server unreachable. Start it with: kanban serve --daemon") {
      KB.flashError(error);
    }
  }

  function loadState(silent) {
    if (refreshing) return Promise.resolve(state);
    refreshing = true;
    return KB.api.state().then(function (next) {
      state = next;
      if (state.server && state.server.signature) signature = state.server.signature;
      if (!KB.isModalOpen()) KB.renderAll(state, filters);
      else KB.renderEvents(state);
      return state;
    }).catch(function (error) {
      setOffline(error);
      if (!silent) KB.flashError(error);
      return null;
    }).finally(function () {
      refreshing = false;
      if (refreshQueued) {
        refreshQueued = false;
        loadState(true);
      }
    });
  }

  KB.refresh = function () { return loadState(false); };
  KB.onModalClosed = function () {
    if (state) KB.renderAll(state, filters);
  };

  function watchChanges() {
    if (watching) return;
    if (!state) {
      setTimeout(watchChanges, 5000);
      return;
    }
    if (!signature) {
      setTimeout(function () {
        loadState(true).then(watchChanges);
      }, 5000);
      return;
    }
    watching = true;
    KB.api.watch(signature).then(function (result) {
      if (result.signature) signature = result.signature;
      if (result.changed) {
        if (refreshing) {
          refreshQueued = true;
          return null;
        }
        return loadState(true);
      }
    }).catch(function (error) {
      setOffline(error);
    }).finally(function () {
      watching = false;
      setTimeout(watchChanges, 500);
    });
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("kanban-theme", theme); } catch (error) {}
    const value = document.getElementById("settings-theme-value");
    if (value) value.textContent = theme === "dark" ? "Dark" : "Light";
    const button = document.querySelector('[data-action="settings"]');
    if (button) button.title = "Open settings · " + (theme === "dark" ? "dark" : "light") + " theme";
  }

  function initialTheme() {
    let saved = null;
    try { saved = localStorage.getItem("kanban-theme"); } catch (error) {}
    if (saved === "light" || saved === "dark") return saved;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function tick() {
    const node = document.querySelector(".timer-elapsed");
    if (!node) return;
    const start = Number(node.getAttribute("data-start"));
    if (!start) return;
    node.textContent = KB.duration((Date.now() - start) / 1000);
  }

  function cardFromElement(element) {
    const holder = element.closest("[data-card-id]");
    if (!holder || !state) return null;
    const id = holder.getAttribute("data-card-id");
    return (state.cards || []).find(function (card) { return card.id === id; }) || null;
  }

  function projectFromElement(element) {
    const holder = element.closest("[data-project-id]");
    if (!holder || !state) return null;
    const id = holder.getAttribute("data-project-id");
    return (state.projects || []).find(function (project) { return project.id === id; }) || null;
  }

  function setSettingsOpen(open) {
    const menu = document.getElementById("settings-menu");
    const button = document.querySelector('[data-action="settings"]');
    if (!menu) return;
    menu.classList.toggle("hidden", !open);
    menu.classList.toggle("open", open);
    if (button) button.setAttribute("aria-expanded", open ? "true" : "false");
  }

  KB.closeSettings = function () { setSettingsOpen(false); };

  document.addEventListener("click", function (event) {
    const actionNode = event.target.closest("[data-action]");
    if (!actionNode) return;
    const action = actionNode.getAttribute("data-action");
    if (action === "settings") {
      const menu = document.getElementById("settings-menu");
      setSettingsOpen(!menu || menu.classList.contains("hidden"));
      return;
    }
    if (action === "theme") {
      applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark");
      return;
    }
    if (!state) return;

    if (action === "refresh") {
      loadState(false);
    } else if (action === "events") {
      KB.openEventsModal(state);
    } else if (action === "filter") {
      filters.mode = actionNode.getAttribute("data-filter") || "all";
      KB.renderAll(state, filters);
    } else if (action === "add-card") {
      KB.openCardModal(state, null, actionNode.getAttribute("data-column-id") || "");
    } else if (action === "edit-column") {
      KB.openColumnManager(state);
    } else if (action === "manage-columns") {
      KB.openColumnManager(state);
    } else if (action === "add-project") {
      KB.openProjectModal(state, null);
    } else if (action === "project-select") {
      const project = projectFromElement(actionNode);
      if (project) {
        KB.selectProject(project.id);
        filters.project = project.id;
        KB.renderAll(state, filters);
      }
    } else if (action === "project-all") {
      KB.selectProject(null);
      filters.project = "";
      KB.renderAll(state, filters);
    } else if (action === "project-edit") {
      const project = projectFromElement(actionNode);
      if (project) KB.openProjectModal(state, project);
    } else if (action === "card-details") {
      const card = cardFromElement(actionNode);
      if (card) KB.openDetailsModal(state, card);
    } else if (action === "card-edit") {
      const card = cardFromElement(actionNode);
      if (card) KB.openCardModal(state, card);
    } else if (action === "card-comment") {
      const card = cardFromElement(actionNode);
      if (card) KB.openCommentModal(state, card);
    } else if (action === "card-toggle-close") {
      const card = cardFromElement(actionNode);
      if (card) KB.openCloseModal(state, card);
    }
  });

  document.getElementById("project-filter").addEventListener("change", function (event) {
    filters.project = event.target.value;
    KB.selectProject(filters.project || null);
    if (state) KB.renderAll(state, filters);
  });

  document.getElementById("priority-filter").addEventListener("change", function (event) {
    filters.priority = event.target.value;
    if (state) KB.renderAll(state, filters);
  });

  document.getElementById("sort-order").addEventListener("change", function (event) {
    filters.sort = event.target.value;
    if (state) KB.renderAll(state, filters);
  });

  document.addEventListener("change", function (event) {
    const select = event.target.closest("[data-column-sort]");
    if (!select || !state) return;
    KB.columnSorts[select.getAttribute("data-column-sort")] = select.value;
    KB.renderBoard(state, filters);
  });

  document.getElementById("search").addEventListener("input", function (event) {
    filters.search = event.target.value.trim();
    if (state) KB.renderAll(state, filters);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    if (KB.isModalOpen()) KB.closeModal();
    else if (KB.closeSettings) KB.closeSettings();
  });

  document.addEventListener("click", function (event) {
    const menu = document.getElementById("settings-menu");
    if (!menu || menu.classList.contains("hidden")) return;
    if (event.target.closest(".settings-wrap")) return;
    setSettingsOpen(false);
  });

  function clearProjectDropMarks() {
    document.querySelectorAll(".project-row.drop-before, .project-row.drop-after").forEach(function (node) {
      node.classList.remove("drop-before", "drop-after");
    });
  }

  document.addEventListener("dragstart", function (event) {
    const projectRow = event.target.closest(".project-row");
    if (projectRow) {
      if (event.target.closest(".icon-btn")) {
        event.preventDefault();
        return;
      }
      const projectId = projectRow.getAttribute("data-project-id");
      if (!projectId) return;
      draggingProjectId = projectId;
      projectRow.classList.add("dragging");
      if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", draggingProjectId);
      }
      return;
    }
    const card = event.target.closest(".card");
    if (!card) return;
    draggingId = card.getAttribute("data-card-id");
    card.classList.add("dragging");
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", draggingId);
    }
  });

  document.addEventListener("dragend", function (event) {
    const projectRow = event.target.closest(".project-row");
    if (projectRow) projectRow.classList.remove("dragging");
    clearProjectDropMarks();
    const card = event.target.closest(".card");
    if (card) card.classList.remove("dragging");
    document.querySelectorAll(".card-list.drag-over").forEach(function (node) {
      node.classList.remove("drag-over");
    });
    draggingId = null;
    draggingProjectId = null;
  });

  document.addEventListener("dragover", function (event) {
    const projectRow = event.target.closest(".project-row");
    if (!projectRow || !draggingProjectId) return;
    const targetId = projectRow.getAttribute("data-project-id");
    if (!targetId) return;
    if (targetId === draggingProjectId) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
    clearProjectDropMarks();
    const rect = projectRow.getBoundingClientRect();
    projectRow.classList.add(event.clientY > rect.top + rect.height / 2 ?
      "drop-after" : "drop-before");
  });

  document.addEventListener("dragleave", function (event) {
    const projectRow = event.target.closest(".project-row");
    if (!projectRow) return;
    if (event.relatedTarget && projectRow.contains(event.relatedTarget)) return;
    projectRow.classList.remove("drop-before", "drop-after");
  });

  document.addEventListener("drop", function (event) {
    const projectRow = event.target.closest(".project-row");
    if (!projectRow || !draggingProjectId) return;
    event.preventDefault();
    const targetId = projectRow.getAttribute("data-project-id");
    const draggedId = draggingProjectId;
    const after = projectRow.classList.contains("drop-after");
    clearProjectDropMarks();
    if (!targetId) return;
    if (targetId === draggedId) {
      draggingProjectId = null;
      return;
    }
    const ids = (state.projects || []).map(function (project) { return project.id; });
    const from = ids.indexOf(draggedId);
    if (from === -1 || ids.indexOf(targetId) === -1) return;
    ids.splice(from, 1);
    let to = ids.indexOf(targetId);
    if (after) to += 1;
    ids.splice(to, 0, draggedId);
    draggingProjectId = null;
    KB.api.request("POST", "/api/projects/reorder", { order: ids })
      .then(function () { KB.refresh(); KB.toast("Project order saved"); })
      .catch(KB.flashError);
  });

  document.addEventListener("dragover", function (event) {
    const list = event.target.closest(".card-list");
    if (!list || !draggingId) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
    list.classList.add("drag-over");
  });

  document.addEventListener("dragleave", function (event) {
    const list = event.target.closest(".card-list");
    if (!list) return;
    if (event.relatedTarget && list.contains(event.relatedTarget)) return;
    list.classList.remove("drag-over");
  });

  document.addEventListener("drop", function (event) {
    const list = event.target.closest(".card-list");
    if (!list || !draggingId) return;
    event.preventDefault();
    list.classList.remove("drag-over");
    const targetColumn = list.getAttribute("data-drop-column");
    const card = (state.cards || []).find(function (item) { return item.id === draggingId; });
    if (!card || !targetColumn || card.column === targetColumn) return;
    KB.api.request("PATCH", "/api/cards/" + encodeURIComponent(card.id),
      { column: targetColumn, note: "Moved via board" })
      .then(function () { KB.refresh(); KB.toast("Card moved"); })
      .catch(KB.flashError);
  });

  document.addEventListener("scroll", function (event) {
    const target = event.target;
    if (!target || target.nodeType !== 1 || !target.matches ||
        !target.matches(".card-list, .project-list, .event-list, .sidebar")) return;
    if (KB.updateScrollShadow) KB.updateScrollShadow(target);
  }, true);

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") loadState(true);
  });

  applyTheme(initialTheme());
  loadState(false).then(function () {
    if (state) {
      KB.renderAll(state, filters);
      watchChanges();
    }
  });
  setInterval(tick, 1000);
})();
