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
    function focusDescriptor(element) {
        if (element?.dataset?.key) return { key: element.dataset.key, start: element.selectionStart, end: element.selectionEnd };
        if (element?.matches?.('summary') && element.parentElement?.dataset?.key) {
            return { detailsKey: element.parentElement.dataset.key };
        }
        return null;
    }
    function takeNoteDraft(session) {
        const active = session.root.activeElement;
        if (!active?.matches?.('textarea[data-action]') || !session.drafts.has(active.dataset.key)) return null;
        session.drafts.delete(active.dataset.key);
        return { command: active.dataset.action, id: active.dataset.id, value: active.value };
    }
    function nextTabTarget(root, current, backwards) {
        const controls = [...root.querySelectorAll('button,input,select,textarea,a[href],summary,[tabindex]')].filter(element => {
            if (element.disabled || element.getAttribute('tabindex') === '-1') return false;
            for (let ancestor = element; ancestor; ancestor = ancestor.parentElement) {
                if (ancestor.hidden || ancestor.hasAttribute('inert')) return false;
                const style = getComputedStyle(ancestor);
                if (style.display === 'none' || style.visibility === 'hidden') return false;
                if (ancestor.tagName === 'DETAILS' && !ancestor.open
                    && !ancestor.querySelector(':scope > summary')?.contains(element)) return false;
            }
            return true;
        });
        return controls[controls.indexOf(current) + (backwards ? -1 : 1)];
    }
    function capture(models) {
        const session = sessionFor(models);
        const root = session?.root;
        if (!root) return;
        session.scroll = new Map([...root.querySelectorAll('[data-scroll-key]')].map(element => [element.dataset.scrollKey, [element.scrollTop, element.scrollLeft]]));
        session.details = new Map([...root.querySelectorAll('details[data-key]')].map(element => [element.dataset.key, element.open]));
        session.focus = focusDescriptor(root.activeElement);
    }
    function fitPanel(session) {
        const scroll = session.root?.querySelector('[data-scroll-key="panel"]');
        if (!scroll) return;
        // Bokeh puts each layout in a separate shadow root. Walk outward to
        // find the shared sticky toolbar and the sidebar host without relying
        // on generated model IDs or penetrating unrelated chart shadow roots.
        const panelHost = session.root.host;
        let sidebar = panelHost?.closest('.nsa-annotation-sidebar');
        let toolbar = null;
        for (let scope = session.root; scope; scope = scope.host?.getRootNode()) {
            toolbar = toolbar || scope.querySelector('.nsa-dashboard-controls');
            if (scope.host?.classList.contains('nsa-annotation-sidebar')) sidebar = scope.host;
        }
        const toolbarBounds = toolbar?.getBoundingClientRect();
        const top = Math.max(12, toolbarBounds?.height > 0 ? toolbarBounds.bottom + 12 : 12);
        for (const host of [sidebar, panelHost]) {
            if (host && host.style.top !== `${top}px`) host.style.top = `${top}px`;
        }
        // The natural chart-row position may still be lower than the toolbar.
        const height = Math.max(180, window.innerHeight - Math.max(top, scroll.getBoundingClientRect().top) - 12);
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
        }
        const focus = session.focus;
        const target = focus?.detailsKey
            ? [...root.querySelectorAll('details[data-key]')].find(element => element.dataset.key === focus.detailsKey)?.querySelector(':scope > summary')
            : [...root.querySelectorAll('[data-key]')].find(element => element.dataset.key === focus?.key);
        if (target && !target.disabled) {
            target.focus({ preventScroll: true });
            if (Number.isInteger(focus.start) && target.setSelectionRange) {
                try { target.setSelectionRange(focus.start, focus.end); } catch (_) { /* Some input types have no text selection. */ }
            }
        }
        for (const element of root.querySelectorAll('[data-scroll-key]')) {
            const scroll = session.scroll.get(element.dataset.scrollKey);
            if (scroll) { element.scrollTop = scroll[0]; element.scrollLeft = scroll[1]; }
        }
    }
    function dispatchControl(session, control, value, draft) {
        const data = control.dataset;
        const payload = { id: data.id, meter: data.meter, category: data.category, source: data.source, field: data.field, value };
        if (draft) payload.draft = draft;
        if (data.action === 'merge-region') payload.id = value;
        if (data.key) session.drafts.delete(data.key);
        app.store.dispatch(app.features.annotationPanel.thunks.panelCommandIntent(data.action, payload));
    }
    function bindRoot(session, root) {
        session.root = root;
        const pointerdown = event => {
            const control = event.target?.closest?.('button[data-action],details[data-key] > summary');
            // A textarea change normally saves on blur and replaces the Div.
            // Keep this control alive until click can submit both intents together.
            const active = root.activeElement;
            const hasNoteDraft = active?.matches?.('textarea[data-action]') && session.drafts.has(active.dataset.key);
            if (control && !control.disabled && event.button === 0 && hasNoteDraft) event.preventDefault();
        };
        const click = event => {
            const summary = event.target?.closest?.('details[data-key] > summary');
            if (summary) {
                const draft = takeNoteDraft(session);
                if (!draft) return;
                event.preventDefault();
                // Toggle before saving so the renderer captures the requested
                // disclosure state, rather than the pre-click closed state.
                summary.parentElement.open = !summary.parentElement.open;
                const focus = focusDescriptor(summary);
                app.store.dispatch(app.features.annotationPanel.thunks.panelCommandIntent('commit-note-draft', { draft }));
                session.focus = focus;
                queueMicrotask(() => { if (!session.disposed) restore(session); });
                return;
            }
            const control = event.target?.closest?.('button[data-action]');
            if (!control || control.disabled) return;
            event.preventDefault();
            const draft = takeNoteDraft(session);
            const raw = control.dataset.value;
            dispatchControl(session, control, raw === 'true' ? true : raw === 'false' ? false : raw, draft);
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
            if (event.key === 'Tab' && !event.ctrlKey && !event.metaKey && !event.altKey && session.drafts.has(target.dataset.key)) {
                const focus = focusDescriptor(nextTabTarget(root, target, event.shiftKey));
                if (!focus) return;
                // Saving replaces this textarea before the browser can move
                // focus. Resume the intended Tab order in the replacement DOM.
                event.preventDefault(); event.stopPropagation();
                dispatchControl(session, target, target.value);
                session.focus = focus;
                queueMicrotask(() => { if (!session.disposed) restore(session); });
            } else if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
                event.preventDefault(); event.stopPropagation(); dispatchControl(session, target, target.value);
            } else if (event.key === 'Escape') {
                event.preventDefault(); event.stopPropagation();
                session.drafts.delete(target.dataset.key); target.value = target.defaultValue;
            }
        };
        const toggle = event => {
            if (event.target?.matches?.('details[data-key]')) session.details.set(event.target.dataset.key, event.target.open);
        };
        // mousedown covers browsers without Pointer Events. Keyboard buttons
        // retain native activation; only dirty-note Tab needs focus restoration.
        const listeners = { pointerdown, mousedown: pointerdown, click, change, input, submit, keydown, toggle };
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
