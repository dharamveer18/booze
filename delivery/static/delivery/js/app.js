/* Booze storefront — small vanilla JS: cart drawer, add/remove items, age gate. */

(function () {
  const csrfToken = document.querySelector("[name=csrfmiddlewaretoken]").value;

  function post(url, data) {
    return fetch(url, {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken },
      body: new URLSearchParams(data),
    }).then((res) => {
      if (!res.ok) throw new Error("Request failed");
      return res.json();
    });
  }

  /* ---------- Cart drawer ---------- */
  const openCart = () => document.body.classList.add("cart-open");
  const closeCart = () => document.body.classList.remove("cart-open");

  document.addEventListener("keydown", (e) => e.key === "Escape" && closeCart());

  /* ---------- Quantity controls ---------- */
  function qtyControlHtml(id, qty) {
    if (qty > 0) {
      return `<div class="stepper">
        <button data-cart-change="-1" data-id="${id}" aria-label="Remove one">−</button>
        <span>${qty}</span>
        <button data-cart-change="1" data-id="${id}" aria-label="Add one">+</button>
      </div>`;
    }
    return `<button class="add-btn" data-cart-change="1" data-id="${id}">ADD</button>`;
  }

  function formatRupees(amount) {
    return "₹" + Math.round(Number(amount));
  }

  function updateCartUI(data) {
    // 1. Every ADD/stepper for this product (it can appear in a rail and in the drawer)
    document.querySelectorAll(`[data-qty-for="${data.id}"]`).forEach((el) => {
      el.innerHTML = qtyControlHtml(data.id, data.quantity);
      el.classList.remove("is-loading");
    });

    // 2. Drawer contents
    document.querySelector("[data-drawer-body]").innerHTML = data.drawer_html;

    // 3. Header button + mobile bar
    const items = `${data.count} item${data.count === 1 ? "" : "s"}`;
    document.querySelector("[data-cart-label]").innerHTML =
      data.count ? `<b>${items}</b><b>${formatRupees(data.grand_total)}</b>` : "My Cart";

    const bar = document.querySelector("[data-cart-bar]");
    if (bar) {
      bar.classList.toggle("is-hidden", data.count === 0);
      bar.querySelector("[data-cart-bar-label]").textContent = `${items} · ${formatRupees(data.grand_total)}`;
    }
  }

  /* ---------- One click handler for everything ---------- */
  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-open-cart]")) return openCart();
    if (e.target.closest("[data-close-cart]")) return closeCart();

    const changeBtn = e.target.closest("[data-cart-change]");
    if (changeBtn) {
      const id = changeBtn.dataset.id;
      document.querySelectorAll(`[data-qty-for="${id}"]`).forEach((el) => el.classList.add("is-loading"));
      post(window.BOOZE.cartUpdateUrl, { id, delta: changeBtn.dataset.cartChange })
        .then(updateCartUI)
        .catch(() => window.location.reload());
      return;
    }

    // Close open dropdowns (store picker / account) when clicking outside them
    document.querySelectorAll("details[open]").forEach((d) => {
      if (!d.contains(e.target) && !d.classList.contains("panel")) d.removeAttribute("open");
    });
  });

  /* ---------- Age gate ---------- */
  const gate = document.querySelector("[data-age-gate]");
  if (gate) {
    gate.querySelector("[data-age-yes]").addEventListener("click", (e) => {
      post(e.currentTarget.dataset.url, {}).then(() => gate.remove());
    });
    gate.querySelector("[data-age-no]").addEventListener("click", () => {
      gate.querySelector("[data-age-denied]").hidden = false;
      gate.querySelector(".age-gate__actions").hidden = true;
    });
  }
})();
