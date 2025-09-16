// Since utils.js assigns to window.NoiseSurveyApp, we need to ensure the global exists first.
global.window = {
  NoiseSurveyApp: {}
};

// Import the functions to be tested. This will attach them to window.NoiseSurveyApp.
require('../noise_survey_analysis/static/js/utils.js');

// Now we can destructure the utils from the global object.
const { findAssociatedDateIndex } = window.NoiseSurveyApp.utils;

describe('NoiseSurveyApp.utils.findAssociatedDateIndex', () => {

  it('returns exact index when timestamp matches an entry', () => {
    const activeData = { Datetime: [1000, 2000, 3000] };
    const idx = findAssociatedDateIndex(activeData, 2000);
    expect(idx).toBe(1);
  });

  it('returns index of last value <= timestamp when in-between', () => {
    const activeData = { Datetime: [1000, 2000, 3000] };
    const idx = findAssociatedDateIndex(activeData, 2500);
    expect(idx).toBe(1);
  });

  it('returns -1 when timestamp is before the first entry', () => {
    const activeData = { Datetime: [1000, 2000, 3000] };
    const idx = findAssociatedDateIndex(activeData, 999);
    expect(idx).toBe(-1);
  });

  it('returns -1 for empty or undefined data', () => {
    expect(findAssociatedDateIndex({}, 1000)).toBe(-1);
    expect(findAssociatedDateIndex({ Datetime: [] }, 1000)).toBe(-1);
    expect(findAssociatedDateIndex(undefined, 1000)).toBe(-1);
  });

  it('returns the last index if timestamp is after the last entry', () => {
    const activeData = { Datetime: [1000, 2000, 3000] };
    const idx = findAssociatedDateIndex(activeData, 4000);
    expect(idx).toBe(2);
  });
});
