"""Controlled, network-free A-to-B lifecycle tests for the production updater."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
UPDATER = ROOT / "electron-spike" / "updater.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node is required")


def _run_harness(tmp_path: Path, scenario: str) -> dict:
    source = r"""
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const u = require(process.argv[1]);
const dir = process.argv[2];
const scenario = process.argv[3];
const bytes = Buffer.from('LecturePack controlled installer B');
const digest = crypto.createHash('sha256').update(bytes).digest('hex');
const releases = [
  {tag_name:'v1.9.9',draft:false,prerelease:false,assets:[{name:'LecturePack-1.9.9-Setup.exe'}]},
  {tag_name:'v2.0.0',draft:false,prerelease:false,assets:[{name:'LecturePack-2.0.0-Setup.exe'}]},
  {tag_name:'v2.0.1-beta.1',draft:false,prerelease:true,assets:[{name:'LecturePack-2.0.1-beta.1-Setup.exe'}]},
  {tag_name:'v9.0.0',draft:true,prerelease:false,assets:[{name:'LecturePack-9.0.0-Setup.exe'}]},
  {tag_name:'v2.1.0',draft:false,prerelease:false,body:'controlled B',assets:[
    {name:'LecturePack-2.1.0-Setup.exe',browser_download_url:'https://fixture/installer',size:bytes.length},
    {name:'LecturePack-2.1.0-release-manifest.json',browser_download_url:'https://fixture/manifest'}
  ]}
];
function response(body, status=200) { return new Response(body, {status}); }
async function goodFetch(url) {
  if (url.includes('/releases?')) return response(JSON.stringify(releases));
  if (url.endsWith('/manifest')) return response(JSON.stringify({version:'2.1.0',platform:'win32',architecture:'x64',installers:[{filename:'LecturePack-2.1.0-Setup.exe',sha256:digest}]}));
  if (url.endsWith('/installer')) return response(bytes);
  return response('missing',404);
}
(async () => {
  const states=[];
  const fetchImpl = scenario==='offline' ? async()=>{throw new Error('controlled offline');} : goodFetch;
  const updater=u.createUpdater({version:'2.0.0',repo:'fixture/repo',userDataDir:dir,fetchImpl,onState:s=>states.push(s)});
  if (scenario==='good') {
    const checked=await updater.check();
    const file=await updater.download(checked.update);
    process.stdout.write(JSON.stringify({checked,exists:fs.existsSync(file),hash:u.sha256File(file),digest,states}));
    return;
  }
  if (scenario==='offline') {
    process.stdout.write(JSON.stringify(await updater.check())); return;
  }
  if (scenario==='bad-checksum') {
    let error='';
    try { await updater.download({version:'2.1.0',downloadUrl:'https://fixture/installer',expectedSha256:'0'.repeat(64)}); }
    catch (e) { error=e.message; }
    process.stdout.write(JSON.stringify({error,files:fs.readdirSync(dir)})); return;
  }
  if (scenario==='interrupted') {
    const interrupted = async () => response(new ReadableStream({start(controller){controller.enqueue(bytes.subarray(0,5));controller.error(new Error('controlled interruption'));}}));
    const broken=u.createUpdater({version:'2.0.0',repo:'fixture/repo',userDataDir:dir,fetchImpl:interrupted});
    let error='';
    try { await broken.download({version:'2.1.0',downloadUrl:'https://fixture/installer',expectedSha256:digest}); }
    catch (e) { error=e.message; }
    process.stdout.write(JSON.stringify({error,files:fs.readdirSync(dir)})); return;
  }
})().catch(e=>{console.error(e);process.exit(1);});
"""
    completed = subprocess.run(
        [NODE, "-e", source, str(UPDATER), str(tmp_path), scenario],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return json.loads(completed.stdout)


def test_controlled_old_to_new_download_and_checksum(tmp_path):
    result = _run_harness(tmp_path, "good")
    assert result["checked"]["status"] == "available"
    assert result["checked"]["update"]["version"] == "v2.1.0"
    assert result["exists"] is True
    assert result["hash"] == result["digest"]


def test_controlled_offline_check_is_fail_safe(tmp_path):
    result = _run_harness(tmp_path, "offline")
    assert result["status"] == "error"
    assert "offline" in result["error"]


def test_controlled_bad_checksum_removes_partial_download(tmp_path):
    result = _run_harness(tmp_path, "bad-checksum")
    assert "checksum" in result["error"]
    assert not any(name.endswith(".exe") or name.endswith(".tmp") for name in result["files"])


def test_controlled_interruption_removes_partial_download(tmp_path):
    result = _run_harness(tmp_path, "interrupted")
    assert "interruption" in result["error"]
    assert not any(name.endswith(".exe") or name.endswith(".tmp") for name in result["files"])
