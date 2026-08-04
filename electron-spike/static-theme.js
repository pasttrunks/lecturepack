'use strict';

(function () {
  function applyTheme(theme) {
    var next = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.dataset.theme = next;
    var label = document.getElementById('theme-label');
    if (label) label.textContent = next === 'light' ? 'DARK' : 'LIGHT';
    var icon = document.getElementById('theme-icon');
    if (icon) icon.setAttribute('d', next === 'light'
      ? 'M12 3v2M12 19v2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M3 12h2M19 12h2M5.6 18.4 7 17M17 7l1.4-1.4'
      : 'M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z');
    var light = document.getElementById('btn-set-light');
    var dark = document.getElementById('btn-set-dark');
    if (light) light.classList.toggle('active', next === 'light');
    if (dark) dark.classList.toggle('active', next === 'dark');
  }

  function bind() {
    var toggle = document.getElementById('btn-theme');
    if (toggle) toggle.addEventListener('click', function () {
      applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
    });
    var light = document.getElementById('btn-set-light');
    var dark = document.getElementById('btn-set-dark');
    if (light) light.addEventListener('click', function () { applyTheme('light'); });
    if (dark) dark.addEventListener('click', function () { applyTheme('dark'); });
    applyTheme(document.documentElement.dataset.theme || 'light');
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, { once: true });
  else bind();
}());
