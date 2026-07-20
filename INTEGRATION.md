# Wiring the LecturePack engine into the new app

The new UI + desktop shell is fully working on a **demo adapter** — every screen
renders and every interaction works with sample data. To make it drive your real
engine, you implement **one class**. Nothing in `ui/` or the rest of `desktop/`
needs to change.

## The one file you touch: `app/desktop/engine_adapter.py`

It defines `EngineAdapter` (the interface, with docstrings) and `DemoAdapter`
(the working simulation). Create `LecturePackAdapter(EngineAdapter)` that calls
your engine, then return it from `make_adapter()`:

```python
def make_adapter(backend):
    return LecturePackAdapter(backend)   # instead of DemoAdapter(backend)
```

Your adapter receives `backend` (the QWebChannel object). You **emit signals** on
it to push data to the UI, and the shell **calls your methods** when the user acts.

### How data reaches the UI: emit signals

Every payload is a JSON string. Example — reporting pipeline progress:

```python
self.backend.pipeline_changed.emit(json.dumps({
    "title": "Transcribing…",
    "meta": "elapsed 00:41 · 62%",
    "stages": [
        {"label": "Inspect",       "state": "done"},
        {"label": "Extract audio", "state": "done"},
        {"label": "Transcribe",    "state": "active", "pct": 62, "color": "orange"},
        {"label": "Detect slides", "state": "active", "pct": 38, "color": "blue"},
        {"label": "Align",         "state": "pending"},
    ],
}))
self.backend.log_line.emit(json.dumps(
    {"tag": "[whisper]", "color": "var(--orange-ink)", "text": "ggml-base.en · 8 threads"}))
```

### Signal reference

| Signal | JSON payload | Drives |
|---|---|---|
| `jobs_changed` | `[{name,file,meta,status,pct?,stage?,eta?}]` | Home job cards |
| `pipeline_changed` | `{title,meta,stages:[{label,state,pct?,color?}]}` | Process stage list |
| `log_line` | `{tag,color,text}` | Process live log (appended) |
| `status_changed` | `{label?,pct?,detail?,right?,job?,side?}` | Footer status bar + sidebar job chip |
| `slides_changed` | `{slides:[{pct,time,state,sel?,frame?}],duration?,durationMid?}` | Review timeline + slide list |
| `transcript_changed` | `{reviewSegments?:[{t,text,hot?}], transcript?:{title,duration,segments,corrections,blocks:[{t,html,hotTime?}]}}` | Review + Transcript screens |
| `study_changed` | `{topics,topicBlocks,topicLabels,keyTerms,bookmarks,stats,cards}` | Study screen |
| `export_progress` | `{pct,label}` | Exports running bar |
| `export_done` | `{files:[name],meta}` | Exports success panel |
| `ai_token` | `"<accumulated answer so far>"` (plain string) | Study chat streaming |
| `ai_done` | — | ends chat streaming |
| `ai_status` | `{label,model?}` | Study assistant status pill |
| `settings_changed` | `{theme?,version?,model_path?,endpoint?,export_dir?,update_status?}` | Settings fields |

`state` for slides/stages is `accepted` / `rejected` / `viewing` (slides) and
`done` / `active` / `pending` (stages). `color` is `"orange"` or `"blue"`.

### How user actions reach you: implement methods

The shell calls these on your adapter (see the interface docstrings for the full
contract):

| Method | When |
|---|---|
| `on_ui_ready()` | UI finished loading — push initial state here |
| `browse_video(parent)` / `import_video(path)` | Browse button / dropped file |
| `start_processing(mode)` | Start button in the New-job overlay (`mode`: `study`/`transcript`/`slides`) |
| `cancel_job()` | Cancel in Process |
| `set_slide_state(index, state)` | Keep/Reject in Review |
| `save_corrections(texts)` | Save corrections in Review (`texts`: list of edited segment strings) |
| `repair_selection()` | Repair button in Review |
| `ask_ai(prompt)` | Study chat send — stream back via `ai_token`/`ai_done` |
| `export_all(formats)` / `export_one(kind)` | Export buttons (`kind`: `pdf`/`html`) |
| `export_folder()` | return path for the "Open folder" button |
| `test_endpoint()` / `browse_model(parent)` / `save_project()` | Settings + header |

### Streaming AI (the Study chat)

`ask_ai` should emit `ai_token` with the **cumulative** text each step (the UI
replaces the last bubble's contents), then `ai_done`. To connect Ollama:

```python
def ask_ai(self, prompt):
    def worker():
        acc = ""
        for chunk in self.engine.stream_chat(prompt):   # your local-AI call
            acc += chunk
            self.backend.ai_token.emit(acc)
        self.backend.ai_done.emit()
    threading.Thread(target=worker, daemon=True).start()   # keep the UI responsive
```

Run any blocking engine work off the Qt main thread (a `QThread` or
`threading.Thread`) and emit signals from there — Qt queues them to the UI thread
safely.

## Threading & the engine

The demo adapter uses `QTimer` to fake async work. Your real engine should run on
worker threads so the 60fps UI never blocks. Signals emitted from a worker thread
are delivered to the UI thread automatically by Qt's queued connections.

## Native drag-and-drop

"Drop a video anywhere" is handled in `desktop/main.py` (`WebView.dropEvent`),
which calls `backend.import_video(path)` with the real filesystem path. You don't
wire anything for this — just implement `import_video`.

## Auto-update

Set `GITHUB_REPO` in `desktop/version.py` (already `pasttrunks/lecturepack`). The
updater checks that repo's releases on launch. You publish updates with
`python packaging/release.py <version> --note "..."` — see `app/README.md`.
The GitHub Action needs the repo's default `GITHUB_TOKEN` only (already granted in
`release.yml`); no secrets to configure.

## Checklist

- [ ] Implement `LecturePackAdapter(EngineAdapter)` against your engine
- [ ] Return it from `make_adapter()`
- [ ] Add your engine's Python deps to `app/requirements.txt`
- [ ] `python -m desktop.main` — confirm real data flows
- [ ] `python packaging/build.py` on Windows — confirm the installer builds
- [ ] Tag a release and confirm the workflow publishes it
