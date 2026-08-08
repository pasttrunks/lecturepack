"""Focused renderer coverage for the Study V2 interaction seam."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "ui" / "app.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_study_v2_edit_delete_explain_and_binding_are_single_shot(tmp_path: Path) -> None:
    harness = tmp_path / "study-renderer.js"
    harness.write_text(
        r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert');
const source = fs.readFileSync(process.argv[2], 'utf8');

function extract(name) {
  const start = source.indexOf('function ' + name);
  if (start < 0) throw new Error(name + ' not found');
  const brace = source.indexOf('{', start);
  let depth = 0;
  for (let i = brace; i < source.length; i++) {
    if (source[i] === '{') depth++;
    else if (source[i] === '}') {
      depth--;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error(name + ' not closed');
}

function button(dataset = {}) {
  return {
    dataset,
    listeners: {},
    addEventListener(type, handler) {
      (this.listeners[type] ||= []).push(handler);
    }
  };
}

const tabs = [button({studyMode: 'overview'}), button({studyMode: 'flashcards'})];
const quick = button();
const cont = button();
const review = button();
const send = button();
const askInput = Object.assign(button(), { value: '' });
const concepts = button();
const flashRoot = button();
const quizRoot = button();
const input = { value: '', focus() {}, select() {} };
const ids = {
  'btn-study-quick': quick,
  'btn-study-continue': cont,
  'btn-study-review': review,
  'btn-study-ask-send': send,
  'study-ask-input': askInput,
  'study-concepts-list': concepts,
  'study-flashcards-root': flashRoot,
  'study-quiz-root': quizRoot,
  'lp-study-edit-input': input
};

let modal = null;
let refreshes = 0;
let modes = [];
let calls = [];
let askSends = 0;
const context = {
  console,
  setTimeout: (fn) => { fn(); return 1; },
  document: {
    querySelectorAll(selector) {
      if (selector === '.study-mode-tab') return tabs;
      if (selector === '.study-ask-chip') return [];
      return [];
    },
    getElementById(id) { return ids[id] || null; }
  },
  $: (id) => ids[id] || null,
  esc: (value) => String(value == null ? '' : value),
  lpModal: (value) => { modal = value; },
  lpBridge: {
    connected: () => true,
    call: (name, payload) => { calls.push({name, payload}); return Promise.resolve({ok: true}); }
  },
  studyV2: {
    content: { concepts: [{id: 'c1', title: 'Troy'}] }
  },
  studyV2Load: () => { refreshes++; },
  setStudyV2Mode: (mode) => { modes.push(mode); },
  studyAskSend: () => { askSends++; }
};
vm.createContext(context);
vm.runInContext(
  extract('bindStudyV2Events') + '\n' +
  extract('studyV2EditItem') + '\n' +
  extract('studyV2DeleteItem') + '\n' +
  extract('studyV2ExplainItem'),
  context,
  {filename: 'app.js'}
);

context.bindStudyV2Events();
context.bindStudyV2Events();
for (const element of [quick, cont, review, send, concepts, flashRoot, quizRoot]) {
  assert.strictEqual((element.listeners.click || []).length, 1, 'Study click handler duplicated');
}
assert.strictEqual((askInput.listeners.keydown || []).length, 1, 'Study key handler duplicated');
for (const tab of tabs) assert.strictEqual((tab.listeners.click || []).length, 1, 'tab handler duplicated');

context.studyV2EditItem('concept', 'c1');
assert.ok(modal && modal.actions && modal.actions[1], 'edit modal did not open');
input.value = 'Troy in this lecture';
modal.actions[1].onClick();

context.studyV2DeleteItem('concept', 'c1');
assert.ok(modal && modal.actions && modal.actions[1], 'delete modal did not open');
modal.actions[1].onClick();

context.studyV2ExplainItem('c1');
assert.deepStrictEqual(modes, ['ask']);
assert.strictEqual(askSends, 1);
assert.strictEqual(askInput.value, 'Explain "Troy" in this lecture');

Promise.resolve().then(() => Promise.resolve()).then(() => {
  assert.strictEqual(JSON.stringify(calls), JSON.stringify([
    {name: 'study_v2_edit', payload: {kind: 'concept', id: 'c1', title: 'Troy in this lecture'}},
    {name: 'study_v2_delete', payload: {kind: 'concept', id: 'c1'}}
  ]));
  assert.strictEqual(refreshes, 2, 'edit/delete did not refresh Study content');
});
""".strip()
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [shutil.which("node"), str(harness), str(APP)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
