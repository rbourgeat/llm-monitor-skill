(function () {
  const KB = window.KB = window.KB || {};

  KB.esc = function (value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  };

  KB.color = function (value) {
    return /^#[0-9a-fA-F]{6}$/.test(String(value || "")) ? value : "#6366f1";
  };

  KB.actorTag = function (actor, title) {
    const kind = actor === "human" ? "human" : "ai";
    const label = kind === "human" ? "Human" : "AI";
    return '<span class="actor ' + kind + '" title="' + KB.esc(title || (label + " action")) +
      '"><span class="actor-dot"></span>' + label + "</span>";
  };

  KB.provenance = function (card) {
    const parts = [KB.actorTag(card.created_by, "Created by " + (card.created_by === "ai" ? "AI" : "human")) + " created"];
    parts.push(KB.actorTag(card.updated_by, "Last edited by " + (card.updated_by === "ai" ? "AI" : "human")) + " edited");
    if (card.closed_at) {
      parts.push(KB.actorTag(card.closed_by, "Closed by " + (card.closed_by === "ai" ? "AI" : "human")) + " closed");
    }
    return parts.join('<span class="prov-sep">·</span>');
  };

  KB.priorityPill = function (priority) {
    const value = ["low", "normal", "high", "urgent"].includes(priority) ? priority : "normal";
    return '<span class="pill prio-' + value + '">' + value + "</span>";
  };

  KB.projectById = function (state, id) {
    return (state.projects || []).find(function (project) { return project.id === id; }) || null;
  };

  KB.columnById = function (state, id) {
    return (state.columns || []).find(function (column) { return column.id === id; }) || null;
  };

  KB.ago = function (iso) {
    if (!iso) return "unknown";
    const then = Date.parse(iso);
    if (Number.isNaN(then)) return "unknown";
    const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
    if (seconds < 60) return seconds + "s ago";
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return minutes + "m ago";
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return hours + "h ago";
    return Math.floor(hours / 24) + "d ago";
  };

  KB.duration = function (seconds) {
    const value = Math.max(0, Math.round(Number(seconds) || 0));
    const hours = Math.floor(value / 3600);
    const minutes = Math.floor((value % 3600) / 60);
    if (hours > 0) return hours + "h " + String(minutes).padStart(2, "0") + "m";
    if (minutes > 0) return minutes + "m";
    return value + "s";
  };

  KB.elapsed = function (seconds) {
    const value = Math.max(0, Math.round(Number(seconds) || 0));
    const days = Math.floor(value / 86400);
    const hours = Math.floor((value % 86400) / 3600);
    const minutes = Math.floor((value % 3600) / 60);
    if (days > 0) return days + "d " + hours + "h";
    if (hours > 0) return hours + "h " + String(minutes).padStart(2, "0") + "m";
    if (minutes > 0) return minutes + "m";
    return value + "s";
  };

  KB.finishedIn = function (card) {
    const start = Date.parse(card && card.created_at);
    const end = Date.parse(card && card.closed_at);
    if (!card || !card.closed_at || !card.created_at || Number.isNaN(start) || Number.isNaN(end)) {
      return "";
    }
    return KB.elapsed((end - start) / 1000);
  };

  KB.bytes = function (size) {
    const value = Math.max(0, Number(size) || 0);
    if (value >= 1_000_000) return (value / 1_000_000).toFixed(1) + " MB";
    if (value >= 1_000) return Math.round(value / 1_000) + " KB";
    return value + " B";
  };

  KB.splitTags = function (value) {
    return String(value || "").split(",").map(function (tag) {
      return tag.trim().toLowerCase();
    }).filter(function (tag, index, list) {
      return tag && list.indexOf(tag) === index;
    });
  };

  KB.uncommittedLabel = function (count) {
    if (count == null) return "uncommitted ?";
    const files = Number(count) || 0;
    if (files === 0) return "clean tree";
    return files + " uncommitted file" + (files === 1 ? "" : "s");
  };

  KB.uncommittedTitle = function (count) {
    if (count == null) return "Git working tree state unavailable";
    const files = Number(count) || 0;
    if (files === 0) return "Git working tree is clean";
    return "Git working tree has " + files + " uncommitted file" + (files === 1 ? "" : "s");
  };

  const SCROLL_SHADOW_SELECTOR = ".card-list, .project-list, .event-list, .sidebar";

  function updateScrollShadow(node) {
    if (!node || !node.classList) return;
    const more = node.scrollHeight - node.scrollTop - node.clientHeight > 4;
    node.classList.toggle("scroll-shadow", more);
  }

  KB.updateScrollShadow = updateScrollShadow;

  KB.refreshScrollShadows = function (root) {
    const scope = root || document;
    const nodes = [];
    if (scope.nodeType === 1 && scope.matches(SCROLL_SHADOW_SELECTOR)) nodes.push(scope);
    scope.querySelectorAll(SCROLL_SHADOW_SELECTOR).forEach(function (node) { nodes.push(node); });
    nodes.forEach(updateScrollShadow);
  };

  KB.isModalOpen = function () {
    const root = document.getElementById("modal-root");
    return Boolean(root && root.childElementCount > 0);
  };

  let toastTimer = null;
  KB.toast = function (message, kind) {
    const node = document.getElementById("toast");
    if (!node) return;
    const type = kind || "ok";
    const glyph = KB.icon ? KB.icon(type === "error" ? "warning" : "check") : "";
    node.innerHTML = glyph + '<span class="toast-message">' + KB.esc(message) + "</span>";
    node.className = "toast " + type;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { node.classList.add("hidden"); }, 4500);
  };

  KB.flashError = function (error) {
    KB.toast(error && error.message ? error.message : String(error), "error");
  };
})();
