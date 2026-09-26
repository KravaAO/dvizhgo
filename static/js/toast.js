(() => {
    const DEFAULT_DURATION = 4200;

    function getStack() {
        let stack = document.getElementById("toastStack");
        if (stack) return stack;

        stack = document.createElement("div");
        stack.id = "toastStack";
        stack.className = "toast-stack";
        stack.setAttribute("aria-live", "polite");
        stack.setAttribute("aria-atomic", "false");
        document.body.appendChild(stack);
        return stack;
    }

    function showToast(message, { type = "info", duration = DEFAULT_DURATION } = {}) {
        if (!message) return;

        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;
        toast.setAttribute("role", type === "error" ? "alert" : "status");

        const text = document.createElement("span");
        text.className = "toast-text";
        text.textContent = message;

        const close = document.createElement("button");
        close.className = "toast-close";
        close.type = "button";
        close.setAttribute("aria-label", "Закрити повідомлення");
        close.textContent = "×";

        let timer;
        const remove = () => {
            clearTimeout(timer);
            toast.classList.add("toast-leaving");
            toast.addEventListener("animationend", () => toast.remove(), { once: true });
        };

        close.addEventListener("click", remove);
        toast.append(text, close);
        getStack().appendChild(toast);
        timer = setTimeout(remove, duration);
    }

    window.showToast = showToast;

    document.addEventListener("DOMContentLoaded", () => {
        document.querySelectorAll("[data-toast-message]").forEach(element => {
            showToast(element.getAttribute("data-toast-message"), {
                type: element.getAttribute("data-toast-type") || "info"
            });
            element.remove();
        });
    });
})();
