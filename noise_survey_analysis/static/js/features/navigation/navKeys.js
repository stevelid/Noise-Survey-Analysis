// noise_survey_analysis/static/js/features/navigation/navKeys.js

/**
 * @fileoverview Registers the layout / navigation shortcuts with the keymap (loads after app.js).
 * The help overlay renders app.keymap.getKeyBindingsForHelp(), so these rows appear there too.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    if (!app.keymap || typeof app.keymap.registerKeyBindings !== 'function') {
        return;
    }

    const NAV = 'Navigation';
    const VIEW = 'Layout';
    const thunk = (name, args) => ({ dispatch }) => {
        const creator = app.thunks && app.thunks[name];
        if (typeof creator === 'function') dispatch(creator(args));
    };

    app.keymap.registerKeyBindings([
        {
            id: 'nav.zoomIn', keys: ['+', '='], ctrl: false, alt: false, intent: 'zoomIn', group: NAV,
            label: '+ / =', description: 'Zoom in (around the tap line, else the centre)',
            run: (e, ctx) => thunk('zoomIntent', { factor: 0.5 })(ctx)
        },
        {
            id: 'nav.zoomOut', keys: ['-', '_'], ctrl: false, alt: false, intent: 'zoomOut', group: NAV,
            label: '-', description: 'Zoom out',
            run: (e, ctx) => thunk('zoomIntent', { factor: 2 })(ctx)
        },
        {
            id: 'nav.panLeft', keys: ['ArrowLeft'], shift: true, ctrl: false, alt: false, intent: 'panLeft', group: NAV,
            label: 'Shift+Left', description: 'Pan earlier by a quarter of the window',
            run: (e, ctx) => thunk('panIntent', { fraction: -0.25 })(ctx)
        },
        {
            id: 'nav.panRight', keys: ['ArrowRight'], shift: true, ctrl: false, alt: false, intent: 'panRight', group: NAV,
            label: 'Shift+Right', description: 'Pan later by a quarter of the window',
            run: (e, ctx) => thunk('panIntent', { fraction: 0.25 })(ctx)
        },
        {
            id: 'nav.fitAll', keys: ['0'], ctrl: false, alt: false, shift: false, intent: 'fitAll', group: NAV,
            label: '0', description: 'Fit the whole survey',
            run: (e, ctx) => thunk('fitAllIntent')(ctx)
        },
        {
            id: 'nav.zoomRegion', keys: ['z'], ctrl: false, alt: false, shift: false, intent: 'zoomToRegion', group: NAV,
            label: 'Z', description: 'Zoom to the selected region (B returns)',
            run: (e, ctx) => thunk('zoomToSelectedRegionIntent')(ctx)
        },
        {
            id: 'nav.focusPrev', keys: ['ArrowUp'], ctrl: false, alt: false, shift: false, intent: 'focusPrevious', group: NAV,
            label: 'Up', description: 'Focus the previous position',
            run: (e, ctx) => thunk('focusPositionIntent', { delta: -1 })(ctx)
        },
        {
            id: 'nav.focusNext', keys: ['ArrowDown'], ctrl: false, alt: false, shift: false, intent: 'focusNext', group: NAV,
            label: 'Down', description: 'Focus the next position',
            run: (e, ctx) => thunk('focusPositionIntent', { delta: 1 })(ctx)
        },
        {
            id: 'nav.moveUp', keys: ['ArrowUp'], alt: true, ctrl: false, intent: 'movePositionUp', group: NAV,
            label: 'Alt+Up', description: 'Move the focused position up',
            run: (e, ctx) => thunk('moveFocusedPositionIntent', { delta: -1 })(ctx)
        },
        {
            id: 'nav.moveDown', keys: ['ArrowDown'], alt: true, ctrl: false, intent: 'movePositionDown', group: NAV,
            label: 'Alt+Down', description: 'Move the focused position down',
            run: (e, ctx) => thunk('moveFocusedPositionIntent', { delta: 1 })(ctx)
        },
        {
            id: 'layout.spectrogram', keys: ['s'], ctrl: false, alt: false, shift: false, intent: 'toggleSpectrogram', group: VIEW,
            label: 'S', description: 'Collapse / expand the focused spectrogram',
            run: (e, ctx) => thunk('cycleSpectrogramModeIntent', {})(ctx)
        },
        {
            id: 'layout.spectrogramAll', keys: ['s'], ctrl: false, alt: false, shift: true, intent: 'toggleAllSpectrograms', group: VIEW,
            label: 'Shift+S', description: 'Collapse / expand every spectrogram',
            run: (e, ctx) => thunk('cycleAllSpectrogramModesIntent')(ctx)
        },
        {
            id: 'layout.solo', keys: ['o'], ctrl: false, alt: false, shift: false, intent: 'soloPosition', group: VIEW,
            label: 'O', description: 'Show only the focused position (again to restore)',
            run: (e, ctx) => thunk('soloPositionIntent')(ctx)
        },
        {
            id: 'layout.frequencyDock', keys: ['f'], ctrl: false, alt: false, shift: false, intent: 'toggleFrequencyDock', group: VIEW,
            label: 'F', description: 'Show / hide the frequency slice dock',
            run: (e, ctx) => thunk('toggleFrequencyDockIntent')(ctx)
        },
        {
            id: 'layout.yMode', keys: ['y'], ctrl: false, alt: false, shift: false, intent: 'cycleYAxisMode', group: VIEW,
            label: 'Y', description: 'Cycle y axis: auto fit / shared / locked',
            run: (e, ctx) => thunk('cycleYAxisModeIntent')(ctx)
        },
        {
            id: 'layout.wheelLock', keys: ['w'], ctrl: false, alt: false, shift: false, intent: 'toggleWheelZoomLock', group: VIEW,
            label: 'W', description: 'Wheel zoom lock (wheel always zooms, never scrolls the page)',
            run: (e, ctx) => thunk('toggleWheelZoomLockIntent')(ctx)
        },
        {
            id: 'layout.help', keys: ['?'], ctrl: false, alt: false, intent: 'toggleHelp', group: VIEW,
            label: '?', description: 'Show this help',
            run: () => app.services?.helpOverlay?.toggle?.()
        }
    ]);
})(window.NoiseSurveyApp);
