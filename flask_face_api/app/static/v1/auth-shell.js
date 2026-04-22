(function () {
  const THEME_KEY = "faceapi2.ui.theme";
  const SETTINGS_KEY = "appSettings";

  function safeParse(jsonValue, fallback) {
    try {
      return jsonValue ? JSON.parse(jsonValue) : fallback;
    } catch (_error) {
      return fallback;
    }
  }

  function getStoredSettings() {
    return safeParse(window.localStorage.getItem(SETTINGS_KEY), {});
  }

  function persistTheme(theme) {
    window.localStorage.setItem(THEME_KEY, theme);
    const settings = { ...getStoredSettings(), theme };
    window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  }

  function getPreferredTheme() {
    const directTheme = window.localStorage.getItem(THEME_KEY);
    if (directTheme === "light" || directTheme === "dark") {
      return directTheme;
    }

    const settingsTheme = getStoredSettings().theme;
    if (settingsTheme === "light" || settingsTheme === "dark") {
      return settingsTheme;
    }

    const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    return prefersDark ? "dark" : "light";
  }

  function applyTheme(theme) {
    document.body.classList.remove("theme-dark", "theme-light");
    document.body.classList.add(`theme-${theme}`);
    const toggleButton = document.getElementById("theme-toggle");
    if (toggleButton) {
      toggleButton.innerHTML = theme === "dark" ? '<i class="fas fa-sun"></i>' : '<i class="fas fa-moon"></i>';
    }
    persistTheme(theme);
  }

  function initializeTheme() {
    applyTheme(getPreferredTheme());
    const toggleButton = document.getElementById("theme-toggle");
    if (!toggleButton) {
      return;
    }

    toggleButton.addEventListener("click", function () {
      const nextTheme = document.body.classList.contains("theme-dark") ? "light" : "dark";
      applyTheme(nextTheme);
    });
  }

  function showToast(message, kind) {
    const toastRegion = document.getElementById("auth-toast-region");
    if (!toastRegion) {
      return;
    }

    const toast = document.createElement("div");
    const tone = kind || "info";
    toast.className = "toast";
    toast.dataset.kind = tone;
    toast.innerHTML = `<strong>${tone === "error" ? "Action needed" : tone === "success" ? "Success" : "Notice"}</strong><span>${String(message)}</span>`;
    toastRegion.appendChild(toast);

    window.setTimeout(function () {
      toast.remove();
    }, 4200);
  }

  function validateEmail(email) {
    return /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,}$/.test(String(email || "").trim());
  }

  function bindPasswordToggles(scope) {
    (scope || document).querySelectorAll("[data-password-toggle]").forEach(function (button) {
      button.addEventListener("click", function () {
        const wrapper = button.closest(".field-shell, .input-shell");
        if (!wrapper) {
          return;
        }

        const input = wrapper.querySelector("input");
        const icon = button.querySelector("i");
        const isPassword = input && input.type === "password";
        if (!input || !icon) {
          return;
        }

        input.type = isPassword ? "text" : "password";
        icon.classList.toggle("fa-eye", !isPassword);
        icon.classList.toggle("fa-eye-slash", isPassword);
      });
    });
  }

  function createButtonState(button, workingText) {
    const originalText = button.innerHTML;
    button.disabled = true;
    button.innerHTML = workingText;

    return function reset() {
      button.disabled = false;
      button.innerHTML = originalText;
    };
  }

  function startCooldown(button, seconds, buildLabel) {
    let remaining = Number(seconds);
    button.disabled = true;
    button.textContent = buildLabel(remaining);

    const timer = window.setInterval(function () {
      remaining -= 1;
      if (remaining <= 0) {
        window.clearInterval(timer);
        button.disabled = false;
        button.textContent = buildLabel(0);
        return;
      }

      button.textContent = buildLabel(remaining);
    }, 1000);

    return function cancel() {
      window.clearInterval(timer);
      button.disabled = false;
    };
  }

  function computePasswordStrength(password) {
    let score = 0;
    if ((password || "").length >= 10) score += 1;
    if (/[A-Z]/.test(password || "")) score += 1;
    if (/[a-z]/.test(password || "")) score += 1;
    if (/\d/.test(password || "")) score += 1;
    if (/[^A-Za-z0-9]/.test(password || "")) score += 1;

    if (score <= 2) {
      return { score, tone: "weak", label: "Weak" };
    }
    if (score <= 4) {
      return { score, tone: "medium", label: "Moderate" };
    }
    return { score, tone: "strong", label: "Strong" };
  }

  function bindStrengthMeter(input, barsSelector, labelSelector) {
    const bars = Array.from(document.querySelectorAll(barsSelector));
    const label = document.querySelector(labelSelector);
    if (!input || !bars.length || !label) {
      return;
    }

    const render = function () {
      const strength = computePasswordStrength(input.value);
      bars.forEach(function (bar, index) {
        bar.classList.toggle("is-active", index < Math.min(strength.score, bars.length));
        bar.dataset.strength = strength.tone;
      });
      label.textContent = input.value ? `${strength.label} password` : "Use 10+ characters with mixed case, numbers, and symbols.";
    };

    input.addEventListener("input", render);
    render();
  }

  window.FaceAPIAuth = {
    applyTheme,
    bindPasswordToggles,
    bindStrengthMeter,
    computePasswordStrength,
    createButtonState,
    getStoredSettings,
    initializeTheme,
    showToast,
    startCooldown,
    validateEmail,
  };

  document.addEventListener("DOMContentLoaded", function () {
    initializeTheme();
    bindPasswordToggles(document);
  });
})();
