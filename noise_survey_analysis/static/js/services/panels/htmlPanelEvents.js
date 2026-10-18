/** Delegated events bind to the Div shadow root, not replaceable HTML children. */
window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';
    const sessions = new WeakMap();
    let current = null;
    function sessionFor(models) { return models?.htmlSidePanel ? sessions.get(models.htmlSidePanel) : null; }
    function findPanelRoot(model) {
        const roots = [document];
        while (roots.length) {
            const root = roots.shift();
            for (const panel of root.querySelectorAll('[data-nsa-panel="annotations"]')) {
                if (!model.id || panel.dataset.nsaModel === String(model.id)) return panel.getRootNode();
            }
            for (const element of root.querySelectorAll('*')) if (element.shadowRoot) roots.push(element.shadowRoot);
        }
        return null;
    }
    function capture(models) {
        const session = sessionFor(models);
        const root = session?.root;
        if (!root) return;
        session.scroll = new Map([...root.querySelectorAll('[data-scroll-key]')].map(element => [element.dataset.scrollKey, [element.scrollTop, element.scrollLeft]]));
        session.details = new Map([...root.querySelectorAll('details[data-key]')].map(element => [element.dataset.key, element.open]));
        const active = root.activeElement;
        session.focus = active?.dataset?.key ? { key: active.dataset.key, start: active.selectionStart, end: active.selectionEnd } : null;
    }
    function fitPanel(session) {
        const scroll = session.root?.querySelector('[data-scroll-key="panel"]');
        if (!scroll) return;
        // Fit below the actual page header initially, then reclaim that space
        // when the host sticks near the top after the chart page scrolls.
        const height = Math.max(180, window.innerHeight - Math.max(12, scroll.getBoundingClientRect().top) - 12);
        const value = `${Math.floor(height)}px`;
        if (scroll.style.maxHeight !== value) scroll.style.maxHeight = value;
    }
    function restore(session) {
        const root = session.root;
        if (!root) return;
        fitPanel(session);
        for (const element of root.querySelectorAll('[data-key]')) {
            const key = element.dataset.key;
            if (session.drafts.has(key)) element.value = session.drafts.get(key);
            if (element.tagName === 'DETAILS' && session.details.has(key)) element.open = session.details.get(key);
            if (session.focus?.key === key && !element.disabled) {
                element.focus({ preventScroll: true });
                if (Number.isInteger(session.focus.start) && element.setSelectionRange) {
                    try { element.setSelectionRange(session.focus.start, session.focus.end); } catch (_) { /* Some input types have no text selection. */ }
                }
            }
        }
        for (const element of root.querySelectorAll('[data-scroll-key]')) {
            const scroll = session.scroll.get(element.dataset.scrollKey);
            if (scroll) { element.scrollTop = scroll[0]; element.scrollLeft = scroll[1]; }
        }
    }
    function dispatchControl(session, control, value) {
        const data = control.dataset;
        const payload = { id: data.id, meter: data.meter, category: data.category, source: data.source, field: data.field, value };
        if (data.action === 'merge-region') payload.id = value;
        if (data.key) session.drafts.delete(data.key);
        app.store.dispatch(app.features.annotationPanel.thunks.panelCommandIntent(data.action, payload));
    }
    function bindRoot(session, root) {
        session.root = root;
        const click = event => {
            const control = event.target?.closest?.('button[data-action]');
            if (!control || control.disabled) return;
            event.preventDefault();
            const raw = control.dataset.value;
            dispatchControl(session, control, raw === 'true' ? true : raw === 'false' ? false : raw);
        };
        const change = event => {
            const control = event.target?.closest?.('input[data-action],select[data-action],textarea[data-action]');
            if (control) dispatchControl(session, control, control.type === 'checkbox' ? control.checked : control.value);
        };
        const input = event => {
            const control = event.target;
            if (control?.dataset?.key && 'value' in control) session.drafts.set(control.dataset.key, control.value);
        };
        const submit = event => {
            const form = event.target;
            if (form?.dataset?.action !== 'create-category') return;
            event.preventDefault();
            session.drafts.delete('new-category-label');
            app.store.dispatch(app.features.annotationPanel.thunks.panelCommandIntent('create-category', {
                label: form.elements.namedItem('label').value, color: form.elements.namedItem('color').value
            }));
        };
        const keydown = event => {
            const target = event.target;
            if (!target?.matches?.('textarea[data-action]')) return;
            if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
                event.preventDefault(); event.stopPropagation(); dispatchControl(session, target, target.value);
            } else if (event.key === 'Escape') {
                event.preventDefault(); event.stopPropagation();
                session.drafts.delete(target.dataset.key); target.value = target.defaultValue;
            }
        };
        const toggle = event => {
            if (event.target?.matches?.('details[data-key]')) session.details.set(event.target.dataset.key, event.target.open);
        };
        const listeners = { click, change, input, submit, keydown, toggle };
        Object.entries(listeners).forEach(([type, handler]) => root.addEventListener(type, handler, type === 'toggle'));
        let fitPending = false;
        const onViewportChange = () => {
            if (fitPending) return;
            fitPending = true;
            requestAnimationFrame(() => { fitPending = false; if (!session.disposed) fitPanel(session); });
        };
        window.addEventListener('resize', onViewportChange);
        window.addEventListener('scroll', onViewportChange, { passive: true });
        session.observer = new MutationObserver(() => restore(session));
        session.observer.observe(root, { childList: true, subtree: true });
        session.unbind = () => {
            session.observer.disconnect();
            Object.entries(listeners).forEach(([type, handler]) => root.removeEventListener(type, handler, type === 'toggle'));
            window.removeEventListener('resize', onViewportChange);
            window.removeEventListener('scroll', onViewportChange);
        };
        restore(session);
    }
    function attach(models) {
        const model = models?.htmlSidePanel;
        if (!model) return () => {};
        if (current?.model === model) return current.dispose;
        current?.dispose();
        const session = { model, root: null, drafts: new Map(), details: new Map(), scroll: new Map(), focus: null, discovery: [], disposed: false };
        sessions.set(model, session);
        const observed = new WeakSet();
        let pending = false;
        // Bokeh may finish building nested shadow roots after app initialization.
        // Observe each discovered root until the real Div appears, then stop scanning.
        const discover = () => {
            pending = false;
            if (session.disposed || session.root) return;
            const root = models.htmlSidePanelRoot || findPanelRoot(model);
            if (root) {
                session.discovery.forEach(observer => observer.disconnect());
                bindRoot(session, root); return;
            }
            const roots = [document];
            while (roots.length) {
                const candidate = roots.shift();
                if (!observed.has(candidate)) {
                    observed.add(candidate);
                    const observer = new MutationObserver(() => {
                        if (!pending) { pending = true; requestAnimationFrame(discover); }
                    });
                    observer.observe(candidate, { childList: true, subtree: true }); session.discovery.push(observer);
                }
                for (const element of candidate.querySelectorAll('*')) if (element.shadowRoot) roots.push(element.shadowRoot);
            }
        };
        session.dispose = () => {
            session.disposed = true; session.unbind?.(); session.discovery.forEach(observer => observer.disconnect());
            sessions.delete(model); if (current === session) current = null;
        };
        current = session; discover(); return session.dispose;
    }
    function focusNote(models) {
        const input = sessionFor(models)?.root?.querySelector('textarea[data-action="region-note"]');
        if (!input) return false;
        input.focus(); input.scrollIntoView?.({ block: 'nearest' }); return true;
    }
    app.services = app.services || {};
    app.services.htmlPanelEvents = { attach, capture, focusNote, dispose: () => current?.dispose() };
})(window.NoiseSurveyApp);
