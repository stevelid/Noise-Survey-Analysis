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

describe('NoiseSurveyApp.utils binary searches', () => {
  let utils;

  beforeEach(() => {
    utils = window.NoiseSurveyApp.utils;
  });

  const values = [1000, 2000, 3000, 4000, 5000];

  // Reference implementations: the linear scans these replaced.
  const linearFirstAtOrAfter = (arr, t) => arr.findIndex(v => v >= t);
  const linearLastAtOrBefore = (arr, t) => arr.findLastIndex(v => v <= t);

  it('firstIndexAtOrAfter matches the linear scan it replaced', () => {
    const probes = [0, 999, 1000, 1500, 2000, 4999, 5000, 5001];
    probes.forEach(t => {
      expect(utils.firstIndexAtOrAfter(values, t)).toBe(linearFirstAtOrAfter(values, t));
    });
  });

  it('lastIndexAtOrBefore matches the linear scan it replaced', () => {
    const probes = [0, 999, 1000, 1500, 2000, 4999, 5000, 5001];
    probes.forEach(t => {
      expect(utils.lastIndexAtOrBefore(values, t)).toBe(linearLastAtOrBefore(values, t));
    });
  });

  it('handles duplicate values the same way as the linear scan', () => {
    const dupes = [1000, 2000, 2000, 2000, 3000];
    [1999, 2000, 2001].forEach(t => {
      expect(utils.firstIndexAtOrAfter(dupes, t)).toBe(linearFirstAtOrAfter(dupes, t));
      expect(utils.lastIndexAtOrBefore(dupes, t)).toBe(linearLastAtOrBefore(dupes, t));
    });
  });

  it('returns -1 for empty and missing arrays', () => {
    [[], null, undefined].forEach(arr => {
      expect(utils.firstIndexAtOrAfter(arr, 1000)).toBe(-1);
      expect(utils.lastIndexAtOrBefore(arr, 1000)).toBe(-1);
    });
  });

  it('works on typed arrays', () => {
    const typed = Float64Array.from(values);
    expect(utils.firstIndexAtOrAfter(typed, 2500)).toBe(2);
    expect(utils.lastIndexAtOrBefore(typed, 2500)).toBe(1);
  });

  it('agrees with the linear scan across a large random sorted array', () => {
    const large = Array.from({ length: 5000 }, (_, i) => i * 7);
    for (let n = 0; n < 200; n++) {
      const t = Math.floor(Math.random() * (large[large.length - 1] + 20)) - 10;
      expect(utils.firstIndexAtOrAfter(large, t)).toBe(linearFirstAtOrAfter(large, t));
      expect(utils.lastIndexAtOrBefore(large, t)).toBe(linearLastAtOrBefore(large, t));
    }
  });
});
