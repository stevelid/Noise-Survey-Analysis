// noise_survey_analysis/static/js/store.js

/**
 * @fileoverview Creates the central state store for the application.
 * This is a lightweight, Redux-inspired implementation that holds state,
 * allows state to be updated via a reducer, and lets listeners subscribe
 * to state changes.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    /**
     * Creates a store that holds the complete state tree of your app.
     * @param {Object} reducer - The reducer function that specifies how to update the state.
     * @returns {Object} An object representing the store. 
     */

    function createStore(reducer) {
        // ------ PRIVATE VARIABLES ------
        let state;
        let listeners = [];

        // ------ PUBLIC METHODS ------
        /**
         * Returns the current state.
         * @returns {Object} The current state.
         */
        const getState = () => state;

        /**
         * Adds a change listener to the store.
         * @param {Function} listener - The listener function to be called when the state changes.
         * @returns {Function} A function to unsubscribe the listener.
         */
        const subscribe = (listener) => {
            listeners.push(listener);

            return function unsubscribe() {
                listeners = listeners.filter(l => l !== listener);
            }
        };

        /**
         * Dispatches an action to change the state.
         * @param {Object} action - The action object to dispatch.
         */
        const dispatch = (action) => {
            if (typeof action === 'function') {
                return action(dispatch, getState);
            }

            state = reducer(state, action);
            listeners.forEach(listener => listener());
            return action;
        };

        //--- Initialisation ---

        // When the store is created, an initial "dummy" action is dispatched to populate the state with the reducer's initial state.
        dispatch({ type: '@@INIT' });

        // Return the public API
        return {
            getState,
            subscribe,
            dispatch
        };
    }

    // Attach the public API to the global object
    app.createStore = createStore;  
})(window.NoiseSurveyApp);