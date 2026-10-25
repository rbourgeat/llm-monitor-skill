(function () {
  const KB = window.KB = window.KB || {};
  const PATHS = {
    board: '<rect x="2" y="2" width="12" height="12" rx="2"/><path d="M2 7h12M7 2v12"/>',
    refresh: '<path d="M13.5 8a5.5 5.5 0 1 1-1.7-4"/><path d="M13.5 2.5v3.5H10"/>',
    clock: '<circle cx="8" cy="8" r="5.5"/><path d="M8 4.5v3.5l2.2 1.4"/>',
    theme: '<circle cx="8" cy="8" r="5.5"/><path d="M8 2.5a5.5 5.5 0 0 0 0 11z" fill="currentColor" stroke="none"/>',
    plus: '<path d="M8 3v10M3 8h10"/>',
    settings: '<path d="M4 2v12M8 2v12M12 2v12"/><circle cx="4" cy="6" r="1.8"/><circle cx="8" cy="10" r="1.8"/><circle cx="12" cy="4" r="1.8"/>',
    pencil: '<path d="M11.2 2.8l2 2-8.4 8.4-2.8.8.8-2.8z"/><path d="M10 4l2 2"/>',
    comment: '<path d="M2.5 3.5h11v7.5H7l-3 2.5v-2.5H2.5z"/>',
    check: '<path d="M3 8.5l3 3L13 4.5"/>',
    rotate: '<path d="M3 8a5 5 0 1 1 1.6 3.8"/><path d="M3 3v3h3"/>',
    close: '<path d="M4 4l8 8M12 4l-8 8"/>',
    columns: '<rect x="2" y="2" width="12" height="12" rx="1.5"/><path d="M6 2v12M10 2v12"/>',
    reorder: '<path d="M8 2v12"/><path d="M5.5 4.5L8 2l2.5 2.5"/><path d="M5.5 11.5L8 14l2.5-2.5"/>',
    project: '<path d="M2.5 7L8 2.5l5.5 4.5"/><path d="M4 6.5v7h8v-7"/><path d="M6.5 13.5v-4h3v4"/>',
    warning: '<path d="M8 2.5l6 11H2z"/><path d="M8 6v4M8 11.5v.1"/>',
    paperclip: '<path d="M10.5 5.5l-4.6 4.6a2 2 0 0 0 2.8 2.8l4.6-4.6a3.2 3.2 0 0 0-4.5-4.5L4 8.4a4.5 4.5 0 0 0 6.4 6.4"/>',
    file: '<path d="M4 2.5h5l3 3v8H4z"/><path d="M9 2.5v3h3"/>',
    chevron: '<path d="M4 6l4 4 4-4"/>',
    arrowRight: '<path d="M2.5 8h11"/><path d="M10 4.5L13.5 8 10 11.5"/>',
    eye: '<path d="M1.5 8s2.5-4.5 6.5-4.5S14.5 8 14.5 8s-2.5 4.5-6.5 4.5S1.5 8 1.5 8z"/><circle cx="8" cy="8" r="2"/>',
    arrowUp: '<path d="M8 13V3M5 6l3-3 3 3"/>',
    arrowDown: '<path d="M8 3v10M5 10l3 3 3-3"/>',
    dot: '<circle cx="8" cy="8" r="2" fill="currentColor" stroke="none"/>'
  };

  KB.icon = function (name, extraClass) {
    const paths = PATHS[name];
    if (!paths) return "";
    return '<svg class="icon' + (extraClass ? " " + extraClass : "") +
      '" viewBox="0 0 16 16" aria-hidden="true" focusable="false">' + paths + "</svg>";
  };
})();
