# Annotation refactor rollback

All checkpoints are on the existing branch. Never force-push or move these tags.

| Tag | Change |
| --- | --- |
| `baseline-pre-annotation-refactor` | Preserves Steve's pre-existing audio changes (`66bd8df`). |
| `stage-0-baseline` | Baseline suites, full-size static benchmark and evidence; server timing unavailable. |
| `stage-1-split-modules` | Feature module extraction with unchanged public imports and processing facade. |
| `stage-2-annotation-model` | Categories, per-meter states, atomic merge/split and explicit v1-to-v2 migration. |
| `stage-3-drawing` | Present/absent/ghost overlays, ghost setting, click cycle and number shortcuts. |
| `stage-4-html-side-panel` | HTML panel, independent sticky scrolling, single browser metrics and sectioned quick CSV. |
| `stage-5-sectioned-export` | Bounded full-source exporter, section reader, server/CLI/Windows entry points and metric fallbacks. |
| `stage-5-export-evaluation` | Stage-5 evaluation documentation follow-up; same application code as the preceding tag. |
| `stage-6-clean-up` | Retire legacy panel/flag and duplicate controls; retain confirmed marker clearing; finish focus/scroll checks and guides. |
| `stage-7-html-shell` / `stage-7-html-shell-reverted` | Evaluated page-shell outcome (pending). |

Compare stages with `git diff <earlier-tag> <later-tag>`, for example `git diff stage-2-annotation-model stage-3-drawing`.

Use `git checkout <tag>` to inspect a checkpoint in detached HEAD. Return with `git checkout main`.

Undo a stage without rewriting history using `git revert <earlier-tag>..<later-tag>` after reviewing that range. For a single checkpoint commit, use `git revert <commit>`.

Reverting application code does not downgrade newer version-2 workspaces or sectioned CSVs. Keep the original workspace/annotation files before migration; migration never overwrites them. Generated full-resolution exports, benchmark data, local verification copies and already-downloaded files are not undone by Git revert.
