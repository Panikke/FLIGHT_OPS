import { useEffect } from "react";

/**
 * Global accelerators for the ops console.
 *
 * The design system says the interface should feel like certified ops
 * equipment, and certified ops equipment is driven from the keyboard. Every
 * frequent action here — play/pause, speed, ticking the clock, switching desk
 * — was mouse-only.
 *
 * `bindings` maps a key to a handler. Deliberately inert while the user is
 * typing, and while a modal is open: the modal owns the keyboard then, and its
 * own Escape handler is the only binding that should fire.
 */
export default function useHotkeys(bindings, { enabled = true } = {}) {
    useEffect(() => {
        if (!enabled) return undefined;

        function onKeyDown(e) {
            if (e.metaKey || e.ctrlKey || e.altKey) return;
            const el = e.target;
            const tag = el?.tagName;
            if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el?.isContentEditable) {
                return;
            }
            if (document.querySelector('[role="dialog"]')) return;

            const handler = bindings[e.key];
            if (!handler) return;
            e.preventDefault();
            handler(e);
        }

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [bindings, enabled]);
}
