(function bootstrapHarness() {
  const app = window.NoiseSurveyApp;
  if (!app) {
    throw new Error('NoiseSurveyApp globals are not available.');
  }

  if (app.init?.reInitializeStore) {
    app.init.reInitializeStore();
  }

  const store = app.store;
  const actions = app.actions;
  const eventHandlers = app.eventHandlers;

  if (!store || !actions || !eventHandlers) {
    throw new Error('Harness could not locate store, actions, or event handlers.');
  }

  const VIEWPORT_MIN = 0;
  const VIEWPORT_MAX = 600_000; // 10 minutes span expressed in milliseconds

  store.dispatch(actions.initializeState({
    availablePositions: ['P1'],
    selectedParameter: 'LZeq',
    viewport: { min: VIEWPORT_MIN, max: VIEWPORT_MAX },
    chartVisibility: { figure_P1_timeseries: true },
  }));

  const parameterSelect = document.querySelector('[data-testid="parameter-select"]');
  const selectedParameterLabel = document.querySelector('[data-testid="selected-parameter"]');
  const viewToggleButton = document.querySelector('[data-testid="view-toggle"]');
  const viewModeLabel = document.querySelector('[data-testid="view-mode"]');
  const chartSurface = document.querySelector('[data-testid="chart"]');
  const regionOverlayLayer = document.querySelector('[data-region-overlay]');
  const tapLine = document.querySelector('[data-testid="tap-line"]');
  const tapSummary = document.querySelector('[data-testid="tap-summary"]');
  const selectedRegionSummary = document.querySelector('[data-testid="selected-region"]');
  const regionCountLabel = document.querySelector('[data-testid="region-count"]');
  const regionList = document.querySelector('[data-testid="region-list"]');

  if (!parameterSelect || !selectedParameterLabel || !viewToggleButton || !viewModeLabel || !chartSurface ||
      !regionOverlayLayer || !tapLine || !tapSummary || !selectedRegionSummary || !regionCountLabel || !regionList) {
    throw new Error('Harness failed to locate required DOM nodes.');
  }

  const toggleWidgetAdapter = {
    get label() {
      return viewToggleButton.textContent || '';
    },
    set label(value) {
      viewToggleButton.textContent = value;
    },
  };

  parameterSelect.addEventListener('change', (event) => {
    eventHandlers.handleParameterChange(event.target.value);
  });

  viewToggleButton.addEventListener('click', () => {
    const currentView = store.getState().view.globalViewType;
    const nextIsLog = currentView !== 'log';
    eventHandlers.handleViewToggle(nextIsLog, toggleWidgetAdapter);
  });

  const chartName = chartSurface.getAttribute('data-chart-name') || 'figure_P1_timeseries';

  function getViewport() {
    const { min, max } = store.getState().view.viewport || {};
    const span = Math.max((max ?? VIEWPORT_MAX) - (min ?? VIEWPORT_MIN), 1);
    return {
      min: Number.isFinite(min) ? min : VIEWPORT_MIN,
      max: Number.isFinite(max) ? max : VIEWPORT_MAX,
      span,
    };
  }

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function clientXToTimestamp(clientX) {
    const rect = chartSurface.getBoundingClientRect();
    if (rect.width === 0) {
      return getViewport().min;
    }
    const clampedX = clamp(clientX, rect.left, rect.right);
    const ratio = (clampedX - rect.left) / rect.width;
    const viewport = getViewport();
    return Math.round(viewport.min + ratio * viewport.span);
  }

  let activeRegionDrag = null;
  let skipNextClick = false;

  chartSurface.addEventListener('pointerdown', (event) => {
    if (!event.shiftKey) {
      activeRegionDrag = null;
      return;
    }
    activeRegionDrag = {
      pointerId: event.pointerId,
      startClientX: event.clientX,
    };
    skipNextClick = true;
    chartSurface.setPointerCapture(event.pointerId);
    event.preventDefault();
  });

  function finishRegionDrag(endClientX, pointerId) {
    if (!activeRegionDrag || activeRegionDrag.pointerId !== pointerId) {
      return;
    }
    const start = clientXToTimestamp(activeRegionDrag.startClientX);
    const end = clientXToTimestamp(endClientX);
    activeRegionDrag = null;
    eventHandlers.handleRegionBoxSelect({
      final: true,
      modifiers: { shift: true },
      geometry: { type: 'rect', x0: start, x1: end },
      model: { name: chartName },
    });
  }

  chartSurface.addEventListener('pointerup', (event) => {
    if (event.pointerId === activeRegionDrag?.pointerId) {
      finishRegionDrag(event.clientX, event.pointerId);
      chartSurface.releasePointerCapture(event.pointerId);
    }
  });

  chartSurface.addEventListener('pointercancel', (event) => {
    if (event.pointerId === activeRegionDrag?.pointerId) {
      activeRegionDrag = null;
      chartSurface.releasePointerCapture(event.pointerId);
    }
  });

  chartSurface.addEventListener('click', (event) => {
    if (skipNextClick) {
      skipNextClick = false;
      return;
    }
    if (event.shiftKey) {
      return;
    }
    const timestamp = clientXToTimestamp(event.clientX);
    eventHandlers.handleTap({
      origin: { name: chartName },
      x: timestamp,
      modifiers: { ctrl: event.ctrlKey },
    });
  });

  document.addEventListener('keydown', (event) => {
    eventHandlers.handleKeyPress(event);
  });

  function formatRegionLabel(region) {
    const start = Math.round(region.start);
    const end = Math.round(region.end);
    return `Region ${region.id}: start=${start}ms end=${end}ms`;
  }

  function renderRegions(state) {
    regionOverlayLayer.innerHTML = '';
    regionList.innerHTML = '';

    const { byId, allIds, selectedId } = state.markers.regions;
    const positions = allIds
      .map((id) => byId[id])
      .filter((region) => region && region.positionId === 'P1');

    regionCountLabel.textContent = String(positions.length);

    if (positions.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'region-empty';
      empty.textContent = 'No regions defined';
      regionList.appendChild(empty);
      return;
    }

    const viewport = getViewport();

    positions.forEach((region) => {
      const entry = document.createElement('div');
      entry.className = 'region-entry';
      entry.dataset.regionId = String(region.id);
      entry.textContent = formatRegionLabel(region);
      if (selectedId === region.id) {
        entry.classList.add('selected');
      }
      regionList.appendChild(entry);

      const overlay = document.createElement('div');
      overlay.className = 'region-overlay';
      overlay.dataset.regionId = String(region.id);
      const startPercent = ((region.start - viewport.min) / viewport.span) * 100;
      const widthPercent = ((region.end - region.start) / viewport.span) * 100;
      overlay.style.left = `${clamp(startPercent, 0, 100)}%`;
      overlay.style.width = `${clamp(widthPercent, 0.5, 100)}%`;
      if (selectedId === region.id) {
        overlay.classList.add('selected');
      }
      regionOverlayLayer.appendChild(overlay);
    });
  }

  function renderTapState(state) {
    const tap = state.interaction.tap;
    if (tap.isActive) {
      tapSummary.textContent = `Active tap at ${Math.round(tap.timestamp)}ms on ${tap.position}`;
      const viewport = getViewport();
      const leftPercent = ((tap.timestamp - viewport.min) / viewport.span) * 100;
      tapLine.style.left = `${clamp(leftPercent, 0, 100)}%`;
      tapLine.style.visibility = 'visible';
    } else {
      tapSummary.textContent = 'No active tap';
      tapLine.style.visibility = 'hidden';
    }
  }

  function renderSelectedRegion(state) {
    const selectedId = state.markers.regions.selectedId;
    if (selectedId) {
      selectedRegionSummary.textContent = `Selected region: Region ${selectedId}`;
    } else {
      selectedRegionSummary.textContent = 'Selected region: none';
    }
  }

  function renderViewState(state) {
    const parameter = state.view.selectedParameter;
    selectedParameterLabel.textContent = parameter;
    parameterSelect.value = parameter;

    const mode = state.view.globalViewType;
    viewModeLabel.textContent = mode;
    toggleWidgetAdapter.label = mode === 'log' ? 'Log View Enabled' : 'Log View Disabled';
    viewToggleButton.setAttribute('data-current-view', mode);
  }

  function render() {
    const state = store.getState();
    renderViewState(state);
    renderTapState(state);
    renderRegions(state);
    renderSelectedRegion(state);
  }

  render();
  store.subscribe(render);
})();
