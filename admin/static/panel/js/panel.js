/* Booze admin panel — tiny helpers, no libraries. */

(function () {
  // Filter bars: submit as soon as a dropdown or date changes (search submits on Enter)
  document.querySelectorAll("form[data-auto-submit]").forEach((form) => {
    form.addEventListener("change", (e) => {
      if (e.target.matches("[data-no-auto]")) return;
      const page = form.querySelector("input[name=page]");
      if (page) page.remove(); // new filters always start from page 1
      form.submit();
    });
  });

  document.addEventListener("click", (e) => {
    // Ask before risky actions (buttons with data-confirm="...")
    const confirmBtn = e.target.closest("[data-confirm]");
    if (confirmBtn && !window.confirm(confirmBtn.dataset.confirm)) {
      e.preventDefault();
      return;
    }

    // Clickable table rows (<tr data-href="...">), unless a link/button inside was clicked
    const row = e.target.closest("tr[data-href]");
    if (row && !e.target.closest("a, button, form")) {
      window.location = row.dataset.href;
      return;
    }

    // Mobile sidebar
    if (e.target.closest("[data-open-sidebar]")) document.body.classList.add("sidebar-open");
    if (e.target.closest("[data-close-sidebar]")) document.body.classList.remove("sidebar-open");

    // Dismiss flash message
    const dismiss = e.target.closest("[data-dismiss]");
    if (dismiss) dismiss.parentElement.remove();

    // Close the custom date popover when clicking outside it
    document.querySelectorAll("details.date-range[open]").forEach((d) => {
      if (!d.contains(e.target)) d.removeAttribute("open");
    });
  });

  // Flash messages fade away on their own
  setTimeout(() => document.querySelectorAll(".flash--success").forEach((el) => el.remove()), 5000);
})();

/* Add user page: only show the fields for the chosen account type */
(function () {
  const inputs = document.querySelectorAll("[data-role-input]");
  if (!inputs.length) return;

  function showSectionsFor(role) {
    document.querySelectorAll("[data-role-section]").forEach((section) => {
      const roles = section.dataset.roleSection.split(" ");
      const visible = roles.includes(role);
      section.hidden = !visible;
      // Hidden fields must not be sent with the form
      section.querySelectorAll("input, select, textarea").forEach((field) => (field.disabled = !visible));
    });
  }

  inputs.forEach((input) => input.addEventListener("change", () => showSectionsFor(input.value)));
  const checked = document.querySelector("[data-role-input]:checked");
  if (checked) showSectionsFor(checked.value);
})();
