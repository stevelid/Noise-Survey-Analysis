# Glyph Refactor Options

## Purpose

This document summarizes two possible architectures for streamed spectrogram rendering in the Noise Survey Analysis application. It is intended as a handoff note for another developer to help explain the options, challenge the assumptions, and determine the best path forward.

The goal is to decide how live server-mode spectrogram streaming should relate to the older static / fully preloaded browser model.

## Current problem in one paragraph

Historically, the browser could hold all prepared log spectrogram data and JavaScript would choose the visible chunk to paint into the glyph based on the current viewport. That model was simple and robust. In the newer streaming path, the server now sends only a chunk-local spectrogram payload rather than a browser-side backing reservoir. This reduces payload size, but it means the browser no longer has a larger spectrogram reservoir to slice from. That creates more coupling between server-side chunk selection and client-side viewport coverage logic, and it reduces parity with the static HTML path.

## Important invariant

One constraint is real and should be treated as non-negotiable unless a deeper Bokeh redesign is undertaken:

- The Bokeh `Image` glyph buffer in the browser should be treated as fixed-size after initialization.
- For this project, the spectrogram buffer width is chosen once per position and reused.
- For log spectral data, the fixed width currently depends on the log cadence.
  - 100 ms data -> 9000 bins -> 15 minutes
  - 1 s data -> 3600 bins -> 1 hour

This does **not** necessarily mean the browser-side **reservoir** must be fixed-size. It means the final **display buffer** should remain shape-stable.

## The two main options

# Option A - Keep the current chunk-only streaming model

## Summary

The server remains responsible for selecting the spectrogram chunk to display. It sends only the current display chunk, already shaped to match the fixed Bokeh image buffer. The browser receives this chunk-local payload and paints it if it sufficiently covers the current viewport.

## How it works

- Server tracks viewport changes.
- Server loads / slices the relevant log spectral data.
- Server prepares spectrogram data and selects the display chunk.
- Server pushes only that chunk into the spectrogram log source.
- Browser checks whether the streamed chunk covers enough of the viewport.
- Browser paints the chunk or falls back to overview.

## Why you might choose it

- Smallest payload size.
- Lower browser memory usage.
- Lower amount of streamed spectral data held client-side.
- Clear upper bound on image payload size.
- Useful if bandwidth or client memory is the main concern.

## Pros

- Efficient transport.
- Lower client memory pressure.
- Predictable streamed payload size.
- Keeps server in control of chunk selection.
- Fits the current code path with incremental evolution rather than major redesign.

## Cons

- Static and live paths behave differently.
- Browser no longer owns a reusable backing reservoir.
- More client/server coupling.
- More places for thresholds and coverage logic to drift.
- Panning can require the “right” new chunk to arrive before log rendering can continue.
- Harder to reason about than the old simple model.
- More fallback logic is needed when viewport width exceeds chunk coverage.

## Best fit when

- Minimizing payload size is the top priority.
- Browser memory use must stay low.
- It is acceptable for streamed spectrogram logic to differ from static HTML mode.
- The team prefers to refine the existing approach rather than revisit the architecture.

## Key risks / technical concerns

- Coverage checks can feel unintuitive to users if line log data remains available while spectrogram log falls back.
- Threshold logic must stay aligned across Python and JavaScript.
- Server-side chunk selection becomes a critical correctness path.
- Debugging becomes harder because rendering depends on both viewport logic and transport timing.

# Option B - Refactor to a browser-side buffered reservoir model

## Summary

The server streams a buffered spectrogram backing slice into the browser, rather than a single preselected display chunk. The browser then behaves more like the old static model: JavaScript slices the visible chunk from that buffered reservoir and paints it into the fixed-size display glyph.

## How it works

- Server tracks viewport changes.
- Server loads / slices a buffered log spectral window around the viewport.
- Server pushes that buffered spectral reservoir to the browser.
- Browser stores that reservoir in a backing structure.
- JavaScript selects the visible chunk from that reservoir using the same or similar logic as the static path.
- JavaScript paints the selected display chunk into the fixed-size Bokeh image buffer.

## Why you might choose it

- Closer to the historical model that already worked well.
- Better parity between live server mode and static HTML mode.
- Simpler mental model.
- Allows the browser to continue painting while the viewport stays within the buffered reservoir.
- Keeps chunk selection logic closer to the renderer / data processor where the viewport is already known.

## Pros

- Much better conceptual alignment with the old static path.
- Static and live behavior can be mostly the same.
- Simpler separation of concerns.
  - Server supplies buffered data.
  - Browser chooses what part to paint.
- Less dependence on exact server-side chunk choice.
- Smoother panning inside the buffered reservoir.
- Easier to explain and reason about.
- Reduces the need for chunk-coverage fallback as a central design feature.

## Cons

- Larger streamed payloads than chunk-only transport.
- More browser memory usage.
- More client-side backing data management.
- The reservoir update contract still needs to be carefully designed.
- The display buffer still needs to stay fixed-size, so JS must copy from reservoir into display data cleanly.

## Best fit when

- Simplicity and maintainability matter more than minimum payload size.
- Static HTML parity is important.
- The team wants one dominant mental model for both static and live paths.
- The project can afford somewhat larger spectral payloads.

## Key risks / technical concerns

- Need to define the browser-side reservoir structure clearly.
- Need a clean contract for when the server replaces or refreshes the reservoir.
- Must avoid conflating the backing reservoir with the final Bokeh glyph buffer.
- Reservoir size policy still needs to be chosen.
  - Example: viewport plus 10% / 50% buffer
  - Example: fixed multi-chunk width per position

## Core clarification

This option does **not** require the final Bokeh `Image` glyph to resize arbitrarily on each update.

A good implementation would separate:

- browser-side backing reservoir
- fixed-size display glyph buffer

The browser reservoir may be conceptually flexible or refreshed in larger buffered windows. The final painted glyph should remain shape-stable.

# Comparison table

| Topic | Option A: Chunk-only streaming | Option B: Buffered reservoir |
| --- | --- | --- |
| Main owner of chunk selection | Server | Browser / JS |
| Browser has reusable backing log reservoir | No, only current chunk | Yes |
| Payload size | Smaller | Larger |
| Browser memory | Lower | Higher |
| Static/live parity | Lower | Higher |
| Complexity of reasoning | Higher | Lower |
| Sensitivity to threshold mismatch | Higher | Lower |
| Panning within an already-buffered window | Weaker | Stronger |
| Similarity to old working model | Lower | Higher |
| Ease of explaining behavior to users/developers | Lower | Higher |

# Recommendation framing

At a high level:

- Choose **Option A** if transport efficiency and minimum client memory are the dominant concerns.
- Choose **Option B** if architectural clarity, static/live parity, and easier long-term maintenance are the dominant concerns.

For this project, **Option B appears more aligned with the historical workflow and with the desired “mostly invisible to JS” streaming behavior**, provided the implementation cleanly separates:

- the browser-side streamed reservoir
- the fixed-size Bokeh image display buffer

## Why Option B currently looks attractive

- The old static approach already worked well and was easier to reason about.
- The current chunk-only path introduced more moving parts and more debug surface.
- The user expectation is strongly aligned with a buffered reservoir model.
- A unified static/live rendering story is valuable.

## Why Option A may still be preferred

- If there are hard limits on payload volume or browser memory.
- If the current streaming approach is already close enough and only needs smaller corrections.
- If the team wants to avoid a larger refactor.

# Suggested decision questions for another developer

- Is minimizing streamed payload size more important than static/live parity?
- How much browser memory can we realistically spend on spectral backing data?
- Do we want one shared chunk-selection path in JavaScript for both static and live modes?
- Should the server be responsible only for supplying buffered data, or also for selecting the exact display chunk?
- Would a browser-side buffered reservoir materially simplify the implementation and debugging burden?
- If we adopt a reservoir model, what should define its width?
  - viewport plus margin
  - fixed multi-chunk span
  - cadence-dependent fixed backing width

# Practical implementation note

If Option B is chosen, the likely clean architecture is:

- Server streams buffered spectral data into a browser-side reservoir source or cache.
- `data-processors.js` reuses the same chunk-selection logic for static and live paths.
- The final Bokeh image buffer remains fixed-size and is updated from the reservoir in place.

That would preserve the Bokeh image invariant while restoring the simpler mental model.

# Bottom line

This is not really a choice between “fixed-size reservoir” and “variable-size reservoir.”

It is a choice between:

- **Option A:** server-selected display chunk only
- **Option B:** server-supplied buffered reservoir, browser-selected display chunk

The strongest argument for Option A is efficiency.
The strongest argument for Option B is simplicity, parity, and maintainability.
