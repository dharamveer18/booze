/* Booze Partner — small helpers: slide-to-confirm, bottom sheets, toasts. No libraries. */

(function () {
  /* ---------- Toasts disappear after a few seconds ---------- */
  document.querySelectorAll(".toast").forEach((toast) => {
    setTimeout(() => {
      toast.classList.add("is-leaving");
      setTimeout(() => toast.remove(), 300);
    }, 3500);
  });

  /* ---------- Bottom sheets ---------- */
  function openSheet(name) {
    const sheet = document.querySelector(`[data-sheet="${name}"]`);
    if (!sheet) return;
    sheet.classList.add("is-open");
    const firstInput = sheet.querySelector("input[type=text]");
    if (firstInput) setTimeout(() => firstInput.focus(), 300);
  }

  document.addEventListener("click", (e) => {
    const opener = e.target.closest("[data-open-sheet]");
    if (opener) return openSheet(opener.dataset.openSheet);

    if (e.target.closest("[data-close-sheet]")) {
      e.target.closest(".sheet").classList.remove("is-open");
    }

    const confirmBtn = e.target.closest("[data-confirm]");
    if (confirmBtn && !window.confirm(confirmBtn.dataset.confirm)) e.preventDefault();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") document.querySelectorAll(".sheet.is-open").forEach((s) => s.classList.remove("is-open"));
  });

  // Only allow digits in the OTP box
  document.querySelectorAll("input[name=otp]").forEach((input) => {
    input.addEventListener("input", () => (input.value = input.value.replace(/\D/g, "").slice(0, 4)));
  });

  /* ---------- Slide to confirm ----------
     Drag the knob to the end to submit the form. Without JS (or with a keyboard)
     the knob is a normal submit button, so the action still works. */
  document.querySelectorAll("[data-slide]").forEach((slide) => {
    const knob = slide.querySelector("[data-slide-knob]");
    const fill = slide.querySelector("[data-slide-fill]");
    const form = slide.closest("form");
    let startX = 0;
    let offset = 0;
    let dragging = false;
    let moved = false;

    const maxOffset = () => slide.clientWidth - knob.offsetWidth - 8;

    function setOffset(x) {
      offset = Math.max(0, Math.min(x, maxOffset()));
      knob.style.transform = `translateX(${offset}px)`;
      fill.style.width = `${offset + knob.offsetWidth + 8}px`;
    }

    knob.addEventListener("pointerdown", (e) => {
      dragging = true;
      moved = false;
      startX = e.clientX - offset;
      slide.classList.add("is-dragging");
      slide.classList.remove("is-animating");
      knob.setPointerCapture(e.pointerId);
    });

    knob.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      if (Math.abs(e.clientX - startX) > 4) moved = true;
      setOffset(e.clientX - startX);
    });

    function release() {
      if (!dragging) return;
      dragging = false;
      slide.classList.remove("is-dragging");
      slide.classList.add("is-animating");
      if (offset >= maxOffset() * 0.85) {
        setOffset(maxOffset());
        slide.classList.add("is-done");
        if (navigator.vibrate) navigator.vibrate(30);
        setTimeout(() => form.submit(), 180);
      } else {
        setOffset(0);
      }
    }

    knob.addEventListener("pointerup", release);
    knob.addEventListener("pointercancel", release);

    // A mouse click / tap without dragging shouldn't submit by accident — nudge instead
    knob.addEventListener("click", (e) => {
      if (e.detail === 0) return; // keyboard (Enter/Space) submits normally
      e.preventDefault();
      if (!moved) {
        slide.classList.add("is-animating");
        setOffset(40);
        setTimeout(() => setOffset(0), 250);
      }
    });
  });
})();
