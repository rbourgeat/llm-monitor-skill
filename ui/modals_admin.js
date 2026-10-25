(function () {
  const KB = window.KB = window.KB || {};

  function countCards(state, columnId) {
    return (state.cards || []).filter(function (card) { return card.column === columnId; }).length;
  }

  function columnRow(state, column) {
    const count = countCards(state, column.id);
    return '<div class="column-row ' + (column.closed ? "closed-row" : "") + '" data-column-id="' +
      KB.esc(column.id) + '">' +
      '<input type="color" data-col-color value="' + KB.color(column.color) + '" title="Column color">' +
      '<input type="text" data-col-title value="' + KB.esc(column.title) + '" title="Column title">' +
      '<label class="checkbox-row"><input type="checkbox" data-col-closed' + (column.closed ? " checked" : "") +
      "> closed</label>" +
      '<span class="count-hint">' + count + " card" + (count === 1 ? "" : "s") + "</span>" +
      '<span><button class="reorder-btn" data-col-up title="Move left" aria-label="Move column left">' +
      KB.icon("arrowUp") + '</button><button class="reorder-btn" data-col-down title="Move right" ' +
      'aria-label="Move column right">' + KB.icon("arrowDown") + "</button></span>" +
      '<span class="column-actions"><button class="btn small" data-col-save>Save</button>' +
      '<button class="btn danger small" data-col-delete>Delete</button></span></div>';
  }

  KB.openColumnManager = function (state) {
    const columns = (state.columns || []).slice().sort(function (a, b) { return a.order - b.order; });
    const rows = columns.map(function (column) { return columnRow(state, column); }).join("");
    const body = '<p class="form-help">Columns are fully editable. Marking a column closed closes every card inside it; reopening the column reopens them. Use the arrow buttons to reorder.</p>' +
      '<div class="column-list">' + (rows || '<div class="empty-note">No columns yet.</div>') + "</div>" +
      '<div class="details-section"><h3>Add column</h3><div class="column-row">' +
      '<input type="color" id="new-col-color" value="#6366f1" title="New column color">' +
      '<input type="text" id="new-col-title" placeholder="Column title">' +
      '<label class="checkbox-row"><input type="checkbox" id="new-col-closed"> closed</label>' +
      '<span class="count-hint"></span><span></span><span><button class="btn primary small" id="add-column">Add</button></span>' +
      '</div></div><div id="modal-error" class="form-error"></div>';
    const modal = KB.openModal({
      title: "Board columns", wide: true, body: body,
      footer: '<button class="btn ghost" data-close>Close</button>',
    });

    function reload() {
      KB.api.state().then(function (next) {
        KB.openColumnManager(next);
        if (KB.refresh) KB.refresh();
      }).catch(KB.flashError);
    }

    function columnById(id) {
      return columns.find(function (column) { return column.id === id; }) || null;
    }

    modal.addEventListener("click", function (event) {
      const row = event.target.closest(".column-row[data-column-id]");
      if (!row) return;
      const column = columnById(row.getAttribute("data-column-id"));
      if (!column) return;
      if (event.target.closest("[data-col-save]")) {
        const payload = {
          title: row.querySelector("[data-col-title]").value.trim(),
          color: row.querySelector("[data-col-color]").value,
          closed: row.querySelector("[data-col-closed]").checked,
        };
        KB.api.request("PATCH", "/api/columns/" + encodeURIComponent(column.id), payload)
          .then(reload).catch(KB.flashError);
        return;
      }
      if (event.target.closest("[data-col-delete]")) {
        deleteColumn(state, column);
        return;
      }
      if (event.target.closest("[data-col-up]") || event.target.closest("[data-col-down]")) {
        const ids = columns.map(function (item) { return item.id; });
        const index = ids.indexOf(column.id);
        const target = event.target.closest("[data-col-up]") ? index - 1 : index + 1;
        if (target < 0 || target >= ids.length) return;
        const swap = ids[index]; ids[index] = ids[target]; ids[target] = swap;
        KB.api.request("POST", "/api/columns/reorder", { ids: ids }).then(reload).catch(KB.flashError);
      }
    });

    function deleteColumn(currentState, column) {
      const count = countCards(currentState, column.id);
      if (!count) {
        if (!window.confirm('Delete empty column "' + column.title + '"?')) return;
        KB.api.request("DELETE", "/api/columns/" + encodeURIComponent(column.id))
          .then(reload).catch(KB.flashError);
        return;
      }
      const targets = columns.filter(function (item) { return item.id !== column.id; });
      if (!targets.length) {
        KB.toast("Cannot delete the last column. Add another column first.", "error");
        return;
      }
      KB.openModal({
        title: "Delete column with cards",
        body: '<p class="form-help">Delete <b>' + KB.esc(column.title) + "</b> and move its " + count +
          " cards to another column.</p><div class=\"form-row full\"><label>Move cards to</label><select id=\"delete-column-target\">" +
          targets.map(function (item) {
            return '<option value="' + KB.esc(item.id) + '">' + KB.esc(item.title) + "</option>";
          }).join("") + '</select></div><div id="modal-error" class="form-error"></div>',
        footer: '<button class="btn ghost" data-close>Cancel</button><button class="btn danger" id="modal-submit">Delete and move</button>',
      });
      document.getElementById("modal-submit").addEventListener("click", function () {
        const target = document.getElementById("delete-column-target").value;
        KB.api.request("DELETE", "/api/columns/" + encodeURIComponent(column.id), { move_to: target })
          .then(function () { KB.closeModal(); if (KB.refresh) KB.refresh(); KB.toast("Column deleted"); })
          .catch(function (error) {
            const node = document.querySelector("#modal-error");
            if (node) node.textContent = error.message;
          });
      });
    }

    document.getElementById("add-column").addEventListener("click", function () {
      const title = document.getElementById("new-col-title").value.trim();
      if (!title) {
        const node = document.querySelector("#modal-error");
        if (node) node.textContent = "Column title is required.";
        return;
      }
      KB.api.request("POST", "/api/columns", {
        title: title,
        color: document.getElementById("new-col-color").value,
        closed: document.getElementById("new-col-closed").checked,
      }).then(reload).catch(KB.flashError);
    });
  };

  KB.openProjectModal = function (state, project) {
    const editing = Boolean(project);
    const activity = project && project.activity ? project.activity : null;
    const metrics = project && project.metrics ? project.metrics : null;
    const git = activity ? (activity.git ?
      '<span class="git-pill">' + KB.esc(activity.branch || "detached") + "</span>" +
      '<span class="git-pill ' + (activity.dirty ? "dirty" : "") + '" title="' +
        KB.esc(KB.uncommittedTitle(activity.dirty)) + '">' +
        KB.esc(KB.uncommittedLabel(activity.dirty)) + "</span>" +
      '<span class="git-pill">last ' + (activity.last_commit ? KB.ago(activity.last_commit.ts) : "no commits") + "</span>" +
      '<span class="git-pill">' + (activity.commits_7d == null ? "?" : activity.commits_7d) + " commits/7d</span>"
      : '<span class="git-pill">' + KB.esc(activity.error || "not a git repository") + "</span>") : "";
    const summary = editing ? '<div class="project-summary"><div>Open cards<b>' + (metrics.cards_open || 0) +
      "</b></div><div>Closed cards<b>" + (metrics.cards_closed || 0) + "</b></div><div>Tracked today<b>" +
      KB.duration(metrics.tracked_today || 0) + "</b></div></div>" +
      '<div class="git-box">' + git + "</div>" : "";
    const body = summary + '<div class="form-grid">' +
      '<div class="form-row full"><label>Absolute path</label><div class="path-picker">' +
      '<input id="project-path" value="' + KB.esc(project ? project.path : "") +
      '" placeholder="/Volumes/…/project">' +
      '<button type="button" class="btn ghost small" id="project-browse" aria-label="Browse for project folder" title="Open native folder chooser">Browse…</button></div>' +
      '<span class="form-help">Existing local directory; git data is read-only. Browse opens the native folder chooser on this machine.</span></div>' +
      '<div class="form-row full"><label>Name</label><input id="project-name" value="' +
      KB.esc(project ? project.name : "") + '" placeholder="Optional display name"></div>' +
      (editing ? '<div class="form-row"><label>Progress %</label><input type="number" id="project-progress" min="0" max="100" value="' +
        (project.progress || 0) + '" title="Automatic: closed cards divided by all cards">' +
        '<span class="form-help">Auto from closed cards; manual edits are temporary.</span></div>' +
        '<div class="form-row"><label>Color</label><input type="color" id="project-color" value="' +
        KB.color(project.color) + '"></div><div class="form-row full"><label>Progress note</label><textarea id="project-note" placeholder="What is done, what remains">' +
        KB.esc(project.progress_note || "") + "</textarea></div>" : "") +
      '</div><div id="modal-error" class="form-error"></div>';
    const footer = (editing ? '<button class="btn danger" id="project-delete" ' +
      'title="Remove the project from this board; its folder and cards are not deleted">Remove from registry</button>' : "") +
      '<button class="btn ghost" data-close>Cancel</button><button class="btn primary" id="modal-submit">' +
      (editing ? "Save project" : "Register project") + "</button>";
    KB.openModal({ title: editing ? "Edit project" : "Register project", wide: true, body: body, footer: footer });

    document.getElementById("modal-submit").addEventListener("click", function () {
      const path = document.getElementById("project-path").value.trim();
      const name = document.getElementById("project-name").value.trim();
      if (!path) { setError("An absolute path is required."); return; }
      if (!path.startsWith("/")) { setError("Path must be absolute (start with /)."); return; }
      let payload, method, endpoint;
      if (editing) {
        const progress = Number(document.getElementById("project-progress").value);
        if (Number.isNaN(progress) || progress < 0 || progress > 100) {
          setError("Progress must be between 0 and 100."); return;
        }
        payload = { name: name, path: path, progress: progress,
          progress_note: document.getElementById("project-note").value.trim(),
          color: document.getElementById("project-color").value };
        method = "PATCH"; endpoint = "/api/projects/" + encodeURIComponent(project.id);
      } else {
        payload = { path: path, name: name };
        method = "POST"; endpoint = "/api/projects";
      }
      const button = document.getElementById("modal-submit");
      button.disabled = true;
      setError("");
      KB.api.request(method, endpoint, payload).then(function () {
        KB.closeModal(); if (KB.refresh) KB.refresh();
        KB.toast(editing ? "Project updated" : "Project registered");
      }).catch(function (error) { button.disabled = false; setError(error.message); });
    });

    function setError(message) {
      const node = document.querySelector("#modal-error");
      if (node) node.textContent = message;
    }

    const browseButton = document.getElementById("project-browse");
    if (browseButton) {
      browseButton.addEventListener("click", function () {
        const pathInput = document.getElementById("project-path");
        const start = pathInput.value.trim();
        const label = browseButton.textContent;
        browseButton.disabled = true;
        browseButton.textContent = "Opening…";
        setError("");
        KB.api.request("POST", "/api/browse-folder", { start: start || null })
          .then(function (result) {
            if (!result || !result.path) return;
            pathInput.value = result.path;
            pathInput.focus();
            const nameInput = document.getElementById("project-name");
            if (!editing && nameInput && !nameInput.value.trim()) {
              const parts = result.path.split("/").filter(Boolean);
              nameInput.value = parts[parts.length - 1] || "";
            }
            KB.toast("Folder selected");
          })
          .catch(function (error) { setError(error.message); })
          .finally(function () {
            browseButton.disabled = false;
            browseButton.textContent = label;
          });
      });
    }

    if (editing) {
      document.getElementById("project-delete").addEventListener("click", function () {
        if (!window.confirm('Remove project "' + project.name + '" from the registry? ' +
          'Its cards are detached, not deleted; the folder is untouched.')) return;
        KB.api.request("DELETE", "/api/projects/" + encodeURIComponent(project.id))
          .then(function () { KB.closeModal(); if (KB.refresh) KB.refresh(); KB.toast("Project removed from registry"); })
          .catch(KB.flashError);
      });
    }
  };
})();
