(function () {
  const KB = window.KB = window.KB || {};

  function row(label, control, full, help) {
    return '<div class="form-row ' + (full ? "full" : "") + '"><label>' + KB.esc(label) + "</label>" +
      control + (help ? '<span class="form-help">' + KB.esc(help) + "</span>" : "") + "</div>";
  }

  function select(name, options, value) {
    return '<select id="' + name + '">' + options.map(function (option) {
      return '<option value="' + KB.esc(option.value) + '"' +
        (option.value === value ? " selected" : "") + ">" + KB.esc(option.label) + "</option>";
    }).join("") + "</select>";
  }

  function columnOptions(state, closed) {
    return (state.columns || []).slice().sort(function (a, b) { return a.order - b.order; })
      .filter(function (column) { return Boolean(column.closed) === Boolean(closed); })
      .map(function (column) { return { value: column.id, label: column.title }; });
  }

  function projectOptions(state) {
    return (state.projects || []).map(function (project) {
      return { value: project.id, label: project.name };
    });
  }

  function defaultProject(state) {
    const selected = KB.selectedProjectId ? KB.selectedProjectId() : null;
    const match = (state.projects || []).find(function (project) { return project.id === selected; });
    return (match || state.projects[0] || {}).id || "";
  }

  function isClosed(state, card) {
    const column = KB.columnById(state, card.column);
    return Boolean(column && column.closed);
  }

  KB.isCardClosed = function (state, card) { return isClosed(state, card); };

  KB.openModal = function (options) {
    if (KB.closeSettings) KB.closeSettings();
    if (KB.closeDropdowns) KB.closeDropdowns();
    const root = document.getElementById("modal-root");
    root.innerHTML = '<div class="modal-backdrop"><div class="modal ' + (options.wide ? "wide" : "") +
      '" role="dialog" aria-modal="true" aria-label="' + KB.esc(options.title) + '">' +
      '<div class="modal-head"><h2>' + KB.esc(options.title) + '</h2>' +
      '<button class="modal-close" data-close title="Close" aria-label="Close dialog">' +
      KB.icon("close") + "</button></div>" +
      '<div class="modal-body">' + options.body + "</div>" +
      (options.footer ? '<div class="modal-foot">' + options.footer + "</div>" : "") +
      "</div></div>";
    document.body.classList.add("modal-open");
    const backdrop = root.querySelector(".modal-backdrop");
    backdrop.addEventListener("click", function (event) {
      if (event.target === backdrop || event.target.closest("[data-close]")) KB.closeModal();
    });
    if (KB.enhanceSelects) KB.enhanceSelects(root);
    if (KB.refreshScrollShadows) KB.refreshScrollShadows(root);
    const first = root.querySelector("input, textarea, .kb-trigger");
    if (first) first.focus();
    return root.querySelector(".modal");
  };

  KB.closeModal = function () {
    if (KB.closeDropdowns) KB.closeDropdowns();
    const root = document.getElementById("modal-root");
    if (!root) return;
    root.innerHTML = "";
    document.body.classList.remove("modal-open");
    if (KB.onModalClosed) KB.onModalClosed();
  };

  function errorNode(message) {
    const node = document.querySelector("#modal-error");
    if (node) node.textContent = message || "";
  }

  function submitter(label, action) {
    return '<button class="btn ghost" data-close>Cancel</button>' +
      '<button class="btn primary" id="modal-submit" data-submit="' + action + '">' + KB.esc(label) + "</button>";
  }

  function save(promise, success, label) {
    const button = document.getElementById("modal-submit");
    if (button) { button.disabled = true; button.textContent = "Saving…"; }
    errorNode("");
    promise.then(function () {
      KB.closeModal();
      if (KB.refresh) KB.refresh();
      KB.toast(success);
    }).catch(function (error) {
      if (button) { button.disabled = false; button.textContent = label; }
      errorNode(error.message);
    });
  }

  function readAttachment(file) {
    return new Promise(function (resolve, reject) {
      const reader = new FileReader();
      reader.onload = function () {
        resolve(String(reader.result || "").split(",")[1] || "");
      };
      reader.onerror = function () { reject(new Error("Could not read " + file.name)); };
      reader.readAsDataURL(file);
    });
  }

  function uploadAttachments(cardId, files) {
    return files.reduce(function (chain, file) {
      return chain.then(function () {
        return readAttachment(file).then(function (encoded) {
          return KB.api.request("POST", "/api/cards/" + encodeURIComponent(cardId) + "/attachments", {
            name: file.name,
            mime: file.type || "application/octet-stream",
            data: encoded,
          });
        });
      });
    }, Promise.resolve());
  }

  function saveCard(promise, files, success, label) {
    const button = document.getElementById("modal-submit");
    if (button) { button.disabled = true; button.textContent = "Saving…"; }
    errorNode("");
    function finish() {
      KB.closeModal();
      if (KB.refresh) KB.refresh();
      KB.toast(success);
    }
    promise.then(function (result) {
      if (!files.length) { finish(); return; }
      uploadAttachments(result.card.id, files).then(function () {
        finish();
      }).catch(function (error) {
        KB.closeModal();
        if (KB.refresh) KB.refresh();
        KB.toast("Card saved; attachment failed: " + error.message, "error");
      });
    }).catch(function (error) {
      if (button) { button.disabled = false; button.textContent = label; }
      errorNode(error.message);
    });
  }

  KB.openEventsModal = function (state) {
    const body = '<div id="event-list" class="event-list modal-event-list"></div>' +
      '<p class="form-help">Newest first. AI and human actions are tagged in the audit trail.</p>';
    KB.openModal({
      title: "Recent events", wide: true, body: body,
      footer: '<button class="btn ghost" data-close>Close</button>',
    });
    KB.renderEvents(state);
  };

  KB.openCardModal = function (state, card, presetColumn) {
    if (!(state.projects || []).length) {
      KB.toast("Register a project before creating or editing cards.");
      return;
    }
    const editing = Boolean(card);
    const columns = (state.columns || []).slice().sort(function (a, b) { return a.order - b.order; });
    const colOptions = columns.map(function (column) {
      return { value: column.id, label: column.title + (column.closed ? " (closed)" : "") };
    });
    const selectedColumn = (card && card.column) || presetColumn ||
      (columns.find(function (column) { return !column.closed; }) || columns[0] || {}).id || "";
    const body = '<div class="form-grid">' +
      row("Title", '<input id="card-title" value="' + KB.esc(card ? card.title : "") + '" placeholder="What needs to be done?">', true) +
      row("Description", '<textarea id="card-body" placeholder="Context, acceptance criteria, links…">' +
        KB.esc(card ? card.body : "") + "</textarea>", true) +
      row("Column", select("card-column", colOptions, selectedColumn)) +
      row("Project", select("card-project", projectOptions(state),
        card ? card.project || "" : defaultProject(state))) +
      row("Priority", select("card-priority", ["low", "normal", "high", "urgent"].map(function (value) {
        return { value: value, label: value };
      }), card ? card.priority : "normal")) +
      row("Tags", '<input id="card-tags" value="' + KB.esc((card && card.tags || []).join(", ")) +
        '" placeholder="comma, separated">') +
      row("Attachments",
        '<div class="attachment-upload"><input id="card-attach-file" type="file" multiple ' +
        'aria-label="Choose attachments"></div>', true,
        "Images, PDFs or files up to 5 MB each (20 per card). Uploaded when you save the card." +
        (editing && (card.attachments || []).length ? " Existing attachments: " +
          (card.attachments || []).length + "." : "")) +
      (editing ? row("Edit note", '<input id="card-note" placeholder="Why this change? Stored in history">', true,
        "The note is appended to the card history.") : "") +
      '</div><div id="modal-error" class="form-error"></div>';
    KB.openModal({
      title: editing ? "Edit card" : "New card",
      body: body,
      footer: submitter(editing ? "Save card" : "Create card", "card"),
    });
    document.getElementById("modal-submit").addEventListener("click", function () {
      const title = document.getElementById("card-title").value.trim();
      const column = document.getElementById("card-column").value;
      const project = document.getElementById("card-project").value;
      if (!title) { errorNode("Title is required."); return; }
      if (!column) { errorNode("Create a column first."); return; }
      if (!project) { errorNode("Project is required."); return; }
      const payload = {
        title: title,
        body: document.getElementById("card-body").value,
        column: column,
        project: project,
        tags: KB.splitTags(document.getElementById("card-tags").value),
        priority: document.getElementById("card-priority").value,
      };
      const files = Array.from(document.getElementById("card-attach-file").files || []);
      const existingCount = editing ? (card.attachments || []).length : 0;
      if (existingCount + files.length > 20) {
        errorNode("A card can have at most 20 attachments.");
        return;
      }
      const oversized = files.find(function (file) { return file.size > 5_000_000; });
      if (oversized) {
        errorNode(oversized.name + " exceeds 5 MB.");
        return;
      }
      const success = (editing ? "Card updated" : "Card created") +
        (files.length ? " with " + files.length + " attachment(s)" : "");
      if (editing) {
        payload.note = document.getElementById("card-note").value.trim();
        saveCard(KB.api.request("PATCH", "/api/cards/" + encodeURIComponent(card.id), payload),
          files, success, "Save card");
      } else {
        saveCard(KB.api.request("POST", "/api/cards", payload), files, success, "Create card");
      }
    });
  };

  KB.openCommentModal = function (state, card) {
    const body = '<p class="form-help">Comment on <b>' + KB.esc(card.title) + "</b>. The comment is recorded as a human action.</p>" +
      '<textarea id="comment-text" placeholder="Evidence, decision, link…"></textarea>' +
      '<div id="modal-error" class="form-error"></div>';
    KB.openModal({ title: "Add comment", body: body, footer: submitter("Add comment", "comment") });
    document.getElementById("modal-submit").addEventListener("click", function () {
      const text = document.getElementById("comment-text").value.trim();
      if (!text) { errorNode("Comment text is required."); return; }
      save(KB.api.request("POST", "/api/cards/" + encodeURIComponent(card.id) + "/comment", { text: text }),
        "Comment added", "Add comment");
    });
  };

  KB.openCloseModal = function (state, card) {
    const closed = isClosed(state, card);
    let body, footer, title;
    if (closed) {
      const openColumns = columnOptions(state, false);
      if (!openColumns.length) { KB.toast("No open column available. Edit columns first.", "error"); return; }
      title = "Reopen card";
      body = '<p class="form-help">Reopen <b>' + KB.esc(card.title) + "</b> into an open column.</p>" +
        '<div class="form-row full"><label>Column</label>' + select("close-column", openColumns, openColumns[0].value) +
        '</div><div id="modal-error" class="form-error"></div>';
      footer = submitter("Reopen", "reopen");
    } else {
      const closedColumns = columnOptions(state, true);
      if (!closedColumns.length) { KB.toast("No closed column available. Mark a column as closed first.", "error"); return; }
      title = "Close card";
      body = '<p class="form-help">Close <b>' + KB.esc(card.title) + "</b>. A note keeps the reason visible in history.</p>" +
        '<div class="form-row full"><label>Close note</label><textarea id="close-note" placeholder="Why is this done or cancelled?"></textarea></div>' +
        '<div class="form-row full"><label>Closed column</label>' +
        select("close-column", closedColumns, closedColumns[0].value) + "</div>" +
        '<div id="modal-error" class="form-error"></div>';
      footer = submitter("Close card", "close");
    }
    KB.openModal({ title: title, body: body, footer: footer });
    document.getElementById("modal-submit").addEventListener("click", function () {
      const column = document.getElementById("close-column").value;
      if (closed) {
        save(KB.api.request("POST", "/api/cards/" + encodeURIComponent(card.id) + "/reopen", { column: column }),
          "Card reopened", "Reopen");
      } else {
        const note = document.getElementById("close-note").value.trim();
        save(KB.api.request("POST", "/api/cards/" + encodeURIComponent(card.id) + "/close",
          { note: note, column: column }), "Card closed", "Close card");
      }
    });
  };

  function attachmentUrl(card, attachment) {
    return "/attachments/" + encodeURIComponent(card.id) + "/" + encodeURIComponent(attachment.id);
  }

  function attachmentList(card) {
    const items = (card.attachments || []).map(function (attachment) {
      const url = attachmentUrl(card, attachment);
      const image = (attachment.mime || "").startsWith("image/");
      const preview = image ? '<a href="' + url + '" target="_blank" rel="noopener">' +
        '<img class="attachment-thumb" loading="lazy" src="' + url + '" alt="' +
        KB.esc(attachment.name) + '"></a>' : '<span class="attachment-icon">' +
        KB.icon("file") + "</span>";
      return '<div class="attachment-item">' + preview +
        '<div class="attachment-meta"><a href="' + url + '" target="_blank" rel="noopener">' +
        KB.esc(attachment.name) + '</a><span>' + KB.bytes(attachment.size) + "</span></div></div>";
    }).join("");
    return items || '<div class="empty-note">No attachments.</div>';
  }

  KB.openDetailsModal = function (state, card) {
    const column = KB.columnById(state, card.column);
    const project = KB.projectById(state, card.project);
    const comments = (card.comments || []).map(function (comment) {
      return '<div class="comment-item"><div class="meta">' + KB.actorTag(comment.actor) +
        "<span>" + KB.esc(comment.ts) + "</span></div>" + KB.esc(comment.text) + "</div>";
    }).join("") || '<div class="empty-note">No comments.</div>';
    const history = (card.history || []).slice().reverse().slice(0, 20).map(function (entry) {
      return '<div class="history-item"><span class="history-time">' + KB.esc(entry.ts.slice(5, 16).replace("T", " ")) +
        '</span><div class="history-text">' + KB.actorTag(entry.actor) + " " + KB.esc(entry.summary) + "</div></div>";
    }).join("") || '<div class="empty-note">No history.</div>';
    const doneIn = isClosed(state, card) ? KB.finishedIn(card) : "";
    const body = '<h3 class="details-title">' + KB.esc(card.title) + "</h3>" +
      '<div class="details-meta">' + KB.priorityPill(card.priority) +
      '<span class="pill project">' + KB.esc(column ? column.title : card.column) + "</span>" +
      (project ? '<span class="pill project">' + KB.esc(project.name) + "</span>" : "") +
      '<span class="tag">' + KB.esc(card.id) + "</span></div>" +
      '<div class="details-meta">' + KB.provenance(card) +
      (doneIn ? '<span class="prov-sep">·</span><span class="done-time">Done in ' + doneIn + "</span>" : "") +
      "</div>" +
      '<div class="details-body">' + KB.esc(card.body || "(no description)") + "</div>" +
      (card.close_note ? '<div class="form-help">Close note: ' + KB.esc(card.close_note) + "</div>" : "") +
      '<div class="details-section"><h3>Attachments (' + (card.attachments || []).length + ")</h3>" +
      '<div class="attachment-list">' + attachmentList(card) + "</div>" +
      '<div class="attachment-upload"><input id="attach-file" type="file" aria-label="Choose attachment">' +
      '<button class="btn small" id="attach-upload" type="button">Attach file</button>' +
      '<span class="form-help">Images, PDFs or files up to 5 MB. Stored locally beside the board.</span></div>' +
      '<div id="modal-error" class="form-error"></div></div>' +
      '<div class="details-section"><h3>Comments (' + (card.comments || []).length + ")</h3>" + comments + "</div>" +
      '<div class="details-section"><h3>History (newest first)</h3>' + history + "</div>";
    KB.openModal({
      title: "Card details", wide: true, body: body,
      footer: '<button class="btn danger" id="details-delete">Delete</button>' +
        '<button class="btn ghost" id="details-comment">Comment</button>' +
        '<button class="btn ghost" id="details-edit">Edit</button>' +
        '<button class="btn primary" id="details-close">' + (isClosed(state, card) ? "Reopen" : "Close") + "</button>",
    });
    document.getElementById("attach-upload").addEventListener("click", function () {
      const input = document.getElementById("attach-file");
      const button = document.getElementById("attach-upload");
      const file = input.files && input.files[0];
      if (!file) { errorNode("Choose a file first."); return; }
      if (file.size > 5_000_000) { errorNode("Attachment exceeds 5 MB."); return; }
      button.disabled = true;
      button.textContent = "Uploading…";
      const reader = new FileReader();
      reader.onload = function () {
        const encoded = String(reader.result || "").split(",")[1] || "";
        KB.api.request("POST", "/api/cards/" + encodeURIComponent(card.id) + "/attachments", {
          name: file.name,
          mime: file.type || "application/octet-stream",
          data: encoded,
        }).then(function () {
          return KB.refresh();
        }).then(function (next) {
          if (next) {
            const fresh = (next.cards || []).find(function (item) { return item.id === card.id; });
            if (fresh) KB.openDetailsModal(next, fresh);
          }
          KB.toast("Attachment added");
        }).catch(function (error) {
          button.disabled = false;
          button.textContent = "Attach file";
          errorNode(error.message);
        });
      };
      reader.onerror = function () {
        button.disabled = false;
        button.textContent = "Attach file";
        errorNode("Could not read the file.");
      };
      reader.readAsDataURL(file);
    });

    document.getElementById("details-edit").addEventListener("click", function () {
      KB.openCardModal(state, card);
    });
    document.getElementById("details-comment").addEventListener("click", function () {
      KB.openCommentModal(state, card);
    });
    document.getElementById("details-close").addEventListener("click", function () {
      KB.openCloseModal(state, card);
    });
    document.getElementById("details-delete").addEventListener("click", function () {
      if (!window.confirm("Delete card \"" + card.title + "\"? This cannot be undone.")) return;
      KB.api.request("DELETE", "/api/cards/" + encodeURIComponent(card.id))
        .then(function () { KB.closeModal(); if (KB.refresh) KB.refresh(); KB.toast("Card deleted"); })
        .catch(KB.flashError);
    });
  };
})();
