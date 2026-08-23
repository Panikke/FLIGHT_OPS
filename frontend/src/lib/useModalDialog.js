import { useEffect, useRef } from "react";

const FOCUSABLE =
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * The modal-dialog contract, applied once instead of not at all.
 *
 * Both modals in this app were plain fixed-position divs: no `role="dialog"`,
 * no `aria-modal`, no focus move on open, no focus trap, and no Escape
 * handler — the only way out was the CLOSE button. That fails every clause of
 * the W3C dialog pattern, and PR #18's accessibility work never propagated to
 * the components written after it.
 *
 * Returns a ref to put on the dialog container.
 */
export default function useModalDialog(onClose) {
    const ref = useRef(null);
    const previouslyFocused = useRef(null);

    useEffect(() => {
        previouslyFocused.current = document.activeElement;
        const node = ref.current;
        if (node) {
            const first = node.querySelector(FOCUSABLE);
            (first || node).focus();
        }

        function onKeyDown(e) {
            if (e.key === "Escape") {
                e.stopPropagation();
                onClose?.();
                return;
            }
            if (e.key !== "Tab" || !ref.current) return;
            const items = Array.from(ref.current.querySelectorAll(FOCUSABLE)).filter(
                (el) => el.offsetParent !== null
            );
            if (!items.length) return;
            const first = items[0];
            const last = items[items.length - 1];
            // Wrap, so focus can never escape the dialog into the frozen page.
            if (e.shiftKey && document.activeElement === first) {
                e.preventDefault();
                last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault();
                first.focus();
            }
        }

        document.addEventListener("keydown", onKeyDown, true);
        return () => {
            document.removeEventListener("keydown", onKeyDown, true);
            // Put the caller back where they were, not at the top of the page.
            if (previouslyFocused.current?.focus) previouslyFocused.current.focus();
        };
    }, [onClose]);

    return ref;
}
