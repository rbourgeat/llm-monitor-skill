(function () {
  const KB = window.KB = window.KB || {};
  let openWrapper = null;
  let openMenu = null;

  function optionLabel(select) {
    const option = select.options[select.selectedIndex];
    return option ? option.textContent : "";
  }

  function triggerLabel(wrapper) {
    return wrapper.querySelector(".kb-trigger-label");
  }

  function updateLabel(wrapper) {
    const select = wrapper.querySelector("select");
    const label = triggerLabel(wrapper);
    if (!select || !label) return;
    label.textContent = optionLabel(select) || "Select…";
    label.title = label.textContent;
  }

  function closeMenu(restoreFocus) {
    if (openMenu && openMenu.parentNode) openMenu.parentNode.removeChild(openMenu);
    if (openWrapper) {
      openWrapper.classList.remove("open");
      const trigger = openWrapper.querySelector(".kb-trigger");
      if (trigger) {
        trigger.setAttribute("aria-expanded", "false");
        if (restoreFocus) trigger.focus();
      }
    }
    openWrapper = null;
    openMenu = null;
  }

  function buildMenu(wrapper) {
    const select = wrapper.querySelector("select");
    const menu = document.createElement("div");
    menu.className = "kb-menu-layer";
    menu.setAttribute("role", "listbox");
    menu.setAttribute("aria-label", select.getAttribute("aria-label") || "Options");
    Array.prototype.forEach.call(select.options, function (option) {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "kb-option";
      item.setAttribute("role", "option");
      item.setAttribute("data-kb-value", option.value);
      item.setAttribute("aria-selected", option.selected ? "true" : "false");
      item.textContent = option.textContent;
      if (option.selected) item.classList.add("selected");
      menu.appendChild(item);
    });
    return menu;
  }

  function positionMenu(wrapper, menu) {
    const rect = wrapper.querySelector(".kb-trigger").getBoundingClientRect();
    const width = Math.max(rect.width, 160);
    menu.style.width = width + "px";
    menu.style.left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8)) + "px";
    menu.style.top = (rect.bottom + 4) + "px";
    menu.style.maxHeight = Math.min(260, window.innerHeight - rect.bottom - 16) + "px";
    if (rect.bottom + 4 + 160 > window.innerHeight) {
      menu.style.top = Math.max(8, rect.top - 4 - Math.min(260, 180)) + "px";
    }
  }

  function openFor(wrapper) {
    const select = wrapper.querySelector("select");
    if (!select) return;
    closeMenu(false);
    const menu = buildMenu(wrapper);
    document.body.appendChild(menu);
    wrapper.classList.add("open");
    wrapper.querySelector(".kb-trigger").setAttribute("aria-expanded", "true");
    positionMenu(wrapper, menu);
    openWrapper = wrapper;
    openMenu = menu;
    const selected = menu.querySelector(".kb-option.selected") || menu.querySelector(".kb-option");
    if (selected) selected.focus();
  }

  function choose(wrapper, value) {
    const select = wrapper.querySelector("select");
    if (!select) return;
    select.value = value;
    updateLabel(wrapper);
    closeMenu(true);
    select.dispatchEvent(new Event("change", { bubbles: true }));
  }

  KB.closeDropdowns = function () { closeMenu(false); };

  KB.enhanceSelects = function (root) {
    const scope = root || document;
    const selects = scope.querySelectorAll("select:not([data-kb-ready])");
    Array.prototype.forEach.call(selects, function (select) {
      select.setAttribute("data-kb-ready", "true");
      select.classList.add("kb-native");
      select.setAttribute("tabindex", "-1");
      select.setAttribute("aria-hidden", "true");
      const wrapper = document.createElement("span");
      wrapper.className = "kb-dropdown";
      if (select.classList.contains("column-sort")) wrapper.classList.add("kb-compact");
      wrapper.setAttribute("data-kb-dropdown", "true");
      select.parentNode.insertBefore(wrapper, select);
      wrapper.appendChild(select);
      const trigger = document.createElement("button");
      trigger.type = "button";
      trigger.className = "kb-trigger";
      trigger.setAttribute("aria-haspopup", "listbox");
      trigger.setAttribute("aria-expanded", "false");
      trigger.innerHTML = '<span class="kb-trigger-label"></span><span class="kb-chevron" aria-hidden="true">' +
        KB.icon("chevron") + "</span>";
      wrapper.appendChild(trigger);
      updateLabel(wrapper);
      if (select.closest(".select-wrap")) select.closest(".select-wrap").classList.add("has-kb-dropdown");
    });
    Array.prototype.forEach.call(scope.querySelectorAll(".kb-dropdown"), function (wrapper) {
      updateLabel(wrapper);
    });
  };

  document.addEventListener("click", function (event) {
    const trigger = event.target.closest(".kb-trigger");
    if (trigger) {
      const wrapper = trigger.closest(".kb-dropdown");
      if (!wrapper) return;
      if (openWrapper === wrapper) closeMenu(false);
      else openFor(wrapper);
      return;
    }
    const option = event.target.closest(".kb-option");
    if (option && openWrapper) {
      choose(openWrapper, option.getAttribute("data-kb-value"));
      return;
    }
    if (!event.target.closest(".kb-dropdown") && !event.target.closest(".kb-menu-layer")) {
      closeMenu(false);
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && openMenu) {
      event.preventDefault();
      closeMenu(true);
      return;
    }
    const trigger = event.target.closest(".kb-trigger");
    if (trigger && event.key === "ArrowDown") {
      event.preventDefault();
      openFor(trigger.closest(".kb-dropdown"));
      return;
    }
    if (openMenu && openMenu.contains(event.target) && event.key.indexOf("Arrow") === 0) {
      const items = Array.prototype.slice.call(openMenu.querySelectorAll(".kb-option"));
      const index = items.indexOf(document.activeElement);
      const next = event.key === "ArrowDown" ? index + 1 : index - 1;
      if (items[next]) {
        event.preventDefault();
        items[next].focus();
      }
    }
  });

  window.addEventListener("resize", function () { closeMenu(false); });
  document.addEventListener("scroll", function (event) {
    if (event.target && event.target.closest && event.target.closest(".kb-menu-layer")) return;
    closeMenu(false);
  }, true);
})();
