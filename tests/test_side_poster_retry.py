"""BUG-26: the sidebar chip's poster must recover from the import-time 404."""
from pathlib import Path
import subprocess

UI = Path(__file__).resolve().parents[1] / "app" / "ui"


def test_side_poster_retries_with_a_cache_buster_after_the_first_404() -> None:
    source = (UI / "app.js").read_text(encoding="utf-8")
    fn = "function posterSrc" + source.split("function posterSrc", 1)[1].split("function posterHtml", 1)[0]
    side = "function renderSidePoster" + source.split("function renderSidePoster", 1)[1].split("/* ======================= renderers", 1)[0]
    program = r'''
      const fail = (n) => process.exit(n);
      var POSTER_RETRIES = 9;
      const timers = []; global.setTimeout = (f) => timers.push(f);
      const attrs = {}; const srcs = [];
      const img = { hidden: true, style: {}, setAttribute(k, v) { attrs[k] = v; }, getAttribute(k) { return attrs[k]; },
        removeAttribute() {}, set src(v) { srcs.push(v); }, get src() { return srcs[srcs.length - 1]; } };
      const ph = { querySelector() { return { hidden: false }; } };
      const $ = (id) => id === 'side-job-poster' ? img : ph;
    ''' + fn + side + r'''
      renderSidePoster('job-1');
      if (srcs.length !== 1 || /\?r=/.test(srcs[0])) fail(1);
      img.onerror();                       // import-time 404: poster not written yet
      if (img.hidden) fail(2);             // must not give up on the first miss
      timers.shift()();
      if (srcs.length !== 2 || !/\?r=1$/.test(srcs[1])) fail(3);   // fresh URL, not the failed one
      process.exit(0);
    '''
    result = subprocess.run(["node", "-e", program], capture_output=True, text=True)
    assert result.returncode == 0, f"check {result.returncode} failed: {result.stderr}"
