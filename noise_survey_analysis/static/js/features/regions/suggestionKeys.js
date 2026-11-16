// noise_survey_analysis/static/js/features/regions/suggestionKeys.js

/**
 * @fileoverview Keyboard bindings for reviewing agent suggestions.
 *   A  accept the selected suggestion, then select the next one
 *   D  reject the selected suggestion, then select the next one
 *   {  previous proposed region (scrolls the chart to it)
 *   }  next proposed region
 * Loaded after core/keymap.js. `[` and `]` (every region) are unchanged; `{` and `}` are Shift+[ and Shift+]
 * so `event.key` differs and the two sets never clash.
 */
window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    if (!app.keymap || typeof app.keymap.registerKeyBindings !== 'function') return;
    const group = 'Suggestions';
    const thunks = () => app.features.review.thunks;

    app.keymap.registerKeyBindings([
        {
            id: 'acceptSuggestion', keys: ['a'], ctrl: false, alt: false, shift: false, repeat: false,
            intent: 'acceptSuggestion', group, label: 'A',
            description: 'Accept the selected suggestion and select the next',
            run: (event, { dispatch }) => dispatch(thunks().acceptSelectedIntent())
        },
        {
            id: 'rejectSuggestion', keys: ['d'], ctrl: false, alt: false, shift: false, repeat: false,
            intent: 'rejectSuggestion', group, label: 'D',
            description: 'Reject the selected suggestion and select the next',
            run: (event, { dispatch }) => dispatch(thunks().rejectSelectedIntent())
        },
        {
            id: 'previousSuggestion', keys: ['{'], ctrl: false, alt: false, repeat: false,
            intent: 'previousSuggestion', group, label: '{',
            description: 'Select the previous proposed region',
            run: (event, { dispatch }) => dispatch(thunks().stepProposedRegionIntent(-1))
        },
        {
            id: 'nextSuggestion', keys: ['}'], ctrl: false, alt: false, repeat: false,
            intent: 'nextSuggestion', group, label: '}',
            description: 'Select the next proposed region',
            run: (event, { dispatch }) => dispatch(thunks().stepProposedRegionIntent(1))
        }
    ]);
})(window.NoiseSurveyApp);
