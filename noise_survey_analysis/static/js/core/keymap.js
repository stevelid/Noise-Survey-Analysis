// noise_survey_analysis/static/js/core/keymap.js

/**
 * @fileoverview Declarative keyboard shortcut table.
 *
 * `eventHandlers.handleKeyPress` calls `app.keymap.match(event)` and acts on the returned entry, and
 * the help overlay renders `app.keymap.getKeyBindingsForHelp()`, so the overlay cannot drift from
 * behaviour. Add keys from your own file with `app.keymap.registerKeyBindings([...])` (load that file
 * after this one in js/manifest.py).
 *
 * Entry fields
 *   id           unique name; registering an existing id replaces that entry
 *   keys         array of `event.key` values. Single characters compare case-insensitively; 'Space' also
 *                matches event.code === 'Space'. Others ('ArrowLeft', 'Escape', ...) compare exactly.
 *   ctrl         true / false / undefined (undefined = either). Ctrl and Meta count as the same modifier.
 *   alt, shift   true / false / undefined (undefined = either)
 *   repeat       true / false / undefined (undefined = either); false ignores key auto-repeat
 *   intent       short name of what the key does (documentation and help)
 *   group        help overlay section
 *   label        key text shown in help (defaults to keys joined with ' / ')
 *   description  one line shown in help
 *   route        built-in routing used by handleKeyPress for the original shortcuts:
 *                'undo' | 'redo' | 'metric' | 'preview' | 'shortcutThunk'
 *   run          for new bindings: function (event, { dispatch, getState }) called when matched.
 *                handleKeyPress calls preventDefault first unless `preventDefault: false`.
 *
 * Precedence: entries registered later win over earlier ones, so a new, more specific binding
 * (for example Shift+ArrowLeft) overrides the built-in broader one without editing it.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const GROUPS = {
        navigation: 'Navigation',
        playback: 'Playback',
        regions: 'Regions',
        markers: 'Markers',
        metrics: 'Metrics',
        classifications: 'Classifications',
        edit: 'Edit'
    };

    // The original shortcuts, in the order handleKeyPress used to test them.
    const builtInBindings = [
        {
            id: 'undo', keys: ['z'], ctrl: true, shift: false, route: 'undo', intent: 'undo',
            group: GROUPS.edit, label: 'Ctrl+Z', description: 'Undo the last region or marker change'
        },
        {
            id: 'redo', keys: ['y'], ctrl: true, route: 'redo', intent: 'redo',
            group: GROUPS.edit, label: 'Ctrl+Y', description: 'Redo'
        },
        {
            id: 'redoShiftZ', keys: ['z'], ctrl: true, shift: true, route: 'redo', intent: 'redo',
            group: GROUPS.edit, label: 'Ctrl+Shift+Z', description: 'Redo', help: false
        },
        {
            id: 'metricEq', keys: ['e'], ctrl: false, alt: false, shift: false, repeat: false, route: 'metric',
            intent: 'selectMetricEq', metricPattern: 'eq$', group: GROUPS.metrics, label: 'E',
            description: 'Show LAeq (keeps the current weighting)'
        },
        {
            id: 'metricFmax', keys: ['x'], ctrl: false, alt: false, shift: false, repeat: false, route: 'metric',
            intent: 'selectMetricFmax', metricPattern: 'fmax$', group: GROUPS.metrics, label: 'X',
            description: 'Show LAFmax'
        },
        {
            id: 'metricL90', keys: ['l'], ctrl: false, alt: false, shift: false, repeat: false, route: 'metric',
            intent: 'selectMetricL90', metricPattern: 'f?90$', group: GROUPS.metrics, label: 'L',
            description: 'Show LA90'
        },
        {
            id: 'previewClassification', keys: ['p'], ctrl: false, route: 'preview',
            intent: 'previewSelectedClassification', group: GROUPS.classifications, label: 'P',
            description: 'Play a short preview of the selected classification'
        },
        {
            id: 'togglePlayback', keys: ['Space'], route: 'shortcutThunk', intent: 'togglePlayback',
            group: GROUPS.playback, label: 'Space', description: 'Play / pause audio at the tap line'
        },
        {
            id: 'escape', keys: ['Escape'], route: 'shortcutThunk', intent: 'cancelRegionCreation',
            group: GROUPS.regions, label: 'Esc', description: 'Cancel region creation'
        },
        {
            id: 'createMarker', keys: ['m'], route: 'shortcutThunk', intent: 'createMarker',
            group: GROUPS.markers, label: 'M', description: 'Add a marker at the tap line'
        },
        {
            id: 'toggleRegionCreation', keys: ['r'], route: 'shortcutThunk', intent: 'toggleRegionCreation',
            group: GROUPS.regions, label: 'R', description: 'Start / finish creating a region'
        },
        {
            id: 'focusRegionNote', keys: ['n'], ctrl: false, alt: false, route: 'shortcutThunk',
            intent: 'focusRegionNote', group: GROUPS.regions, label: 'N',
            description: 'Edit the note of the selected region'
        },
        {
            id: 'returnToPreviousView', keys: ['b'], ctrl: false, alt: false, route: 'shortcutThunk',
            intent: 'returnToPreviousRegionView', group: GROUPS.navigation, label: 'B',
            description: 'Return to the view before the last region jump'
        },
        {
            id: 'stepRegion', keys: ['[', ']'], ctrl: false, alt: false, route: 'shortcutThunk',
            intent: 'stepRegionSelection', group: GROUPS.regions, label: '[ / ]',
            description: 'Select the previous / next region'
        },
        {
            id: 'arrowNudge', keys: ['ArrowLeft', 'ArrowRight'], route: 'shortcutThunk', intent: 'nudge',
            group: GROUPS.navigation, label: 'Left / Right',
            description: 'Move the tap line; Ctrl moves the selected marker, Alt resizes the selected region'
        },
        {
            id: 'deleteSelection', keys: ['Delete', 'Backspace'], route: 'shortcutThunk',
            intent: 'deleteSelection', group: GROUPS.edit, label: 'Delete',
            description: 'Delete the selected marker or region'
        },
        {
            id: 'cycleMeterState', keys: ['1', '2', '3', '4', '5', '6', '7', '8', '9'],
            ctrl: false, alt: false, shift: false, repeat: false, route: 'shortcutThunk',
            intent: 'cycleRegionMeterState', group: GROUPS.regions, label: '1-9',
            description: 'Cycle the selected region\'s state at the Nth chart as displayed'
        }
    ];

    const bindings = [];

    function cloneEntry(entry) {
        return { ...entry, keys: Array.isArray(entry.keys) ? entry.keys.slice() : [] };
    }

    function isValidEntry(entry) {
        return entry && typeof entry === 'object'
            && typeof entry.id === 'string' && entry.id
            && Array.isArray(entry.keys) && entry.keys.length > 0
            && entry.keys.every(key => typeof key === 'string' && key);
    }

    /**
     * Adds or replaces bindings. Entries that are not valid are skipped with a console warning.
     * @param {Array<object>} entries
     * @returns {number} how many entries were registered
     */
    function registerKeyBindings(entries) {
        let count = 0;
        (Array.isArray(entries) ? entries : []).forEach(entry => {
            if (!isValidEntry(entry)) {
                console.warn('[Keymap] Ignoring invalid key binding:', entry);
                return;
            }
            const copy = cloneEntry(entry);
            const existing = bindings.findIndex(item => item.id === copy.id);
            if (existing >= 0) {
                bindings[existing] = copy;
            } else {
                bindings.push(copy);
            }
            count += 1;
        });
        return count;
    }

    function unregisterKeyBinding(id) {
        const index = bindings.findIndex(item => item.id === id);
        if (index >= 0) {
            bindings.splice(index, 1);
            return true;
        }
        return false;
    }

    function modifierMatches(expected, actual) {
        return expected === undefined || expected === null || Boolean(expected) === Boolean(actual);
    }

    function keyMatches(entryKeys, event) {
        const rawKey = typeof event.key === 'string' ? event.key : '';
        const normalized = rawKey.toLowerCase();
        const code = typeof event.code === 'string' ? event.code : '';
        const isSpace = code === 'Space' || rawKey === ' ' || rawKey === 'Spacebar';
        return entryKeys.some(key => {
            if (key === 'Space') return isSpace;
            if (key.length === 1) return key.toLowerCase() === normalized;
            return key === rawKey;
        });
    }

    /**
     * Returns the binding for a keyboard event, or null. Later-registered entries win.
     * @param {KeyboardEvent|object} event
     */
    function match(event) {
        if (!event) return null;
        const ctrlOrMeta = Boolean(event.ctrlKey) || Boolean(event.metaKey);
        for (let index = bindings.length - 1; index >= 0; index -= 1) {
            const entry = bindings[index];
            if (modifierMatches(entry.ctrl, ctrlOrMeta)
                && modifierMatches(entry.alt, event.altKey)
                && modifierMatches(entry.shift, event.shiftKey)
                && modifierMatches(entry.repeat, event.repeat)
                && keyMatches(entry.keys, event)) {
                return entry;
            }
        }
        return null;
    }

    /**
     * Table for a help overlay: one row per documented binding, grouped, in registration order.
     * Entries with `help: false` (for example a duplicate alias) are left out.
     * @returns {Array<{id: string, group: string, keys: string, description: string, intent: string}>}
     */
    function getKeyBindingsForHelp() {
        return bindings
            .filter(entry => entry.help !== false)
            .map(entry => ({
                id: entry.id,
                group: entry.group || 'Other',
                keys: entry.label || entry.keys.join(' / '),
                description: entry.description || '',
                intent: entry.intent || entry.id
            }));
    }

    function getKeyBindings() {
        return bindings.map(cloneEntry);
    }

    registerKeyBindings(builtInBindings);

    app.keymap = {
        GROUPS,
        registerKeyBindings,
        unregisterKeyBinding,
        match,
        getKeyBindings,
        getKeyBindingsForHelp
    };
})(window.NoiseSurveyApp);
