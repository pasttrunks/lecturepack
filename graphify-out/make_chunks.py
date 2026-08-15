import json
from pathlib import Path
from collections import defaultdict

detect = json.loads(Path('graphify-out/.graphify_detect.json').read_text(encoding='utf-8'))
docs = list(detect['files'].get('document', []))
imgs = list(detect['files'].get('image', []))

docdirs = defaultdict(list)
for d in docs: docdirs[str(Path(d).parent)].append(d)
chunks = []
for d, fl in sorted(docdirs.items()):
    for i in range(0, len(fl), 22):
        chunks.append(('doc', fl[i:i+22]))
imgdirs = defaultdict(list)
for m in imgs: imgdirs[str(Path(m).parent)].append(m)
for d, fl in sorted(imgdirs.items()):
    for i in range(0, len(fl), 10):
        chunks.append(('image', fl[i:i+10]))

root = r'C:\Users\marsh\Documents\LecturePack-worktrees\release-polish'
out = root + r'\graphify-out'
spec = root + r'\graphify-out\extraction-spec.md'
manifest = []
for n, (t, fl) in enumerate(chunks):
    chunk_path = rf'{out}\.graphify_chunk_{n:02d}.json'
    file_list = '\n'.join(fl)
    # write a manifest per chunk for subagent reading
    Path(rf'{out}\.graphify_chunklist_{n:02d}.txt').write_text('\n'.join(fl), encoding='utf-8')
    prompt = Path(spec).read_text(encoding='utf-8')
    prompt = prompt.replace('FILE_LIST', file_list)
    prompt = prompt.replace('CHUNK_NUM', str(n))
    prompt = prompt.replace('TOTAL_CHUNKS', str(len(chunks)))
    prompt = prompt.replace('CHUNK_PATH', chunk_path)
    Path(rf'{out}\.graphify_chunkprompt_{n:02d}.txt').write_text(prompt, encoding='utf-8')
    manifest.append({'id': n, 'type': t, 'n': len(fl), 'chunk_path': chunk_path,
                     'chunklist': rf'{out}\.graphify_chunklist_{n:02d}.txt',
                     'chunkprompt': rf'{out}\.graphify_chunkprompt_{n:02d}.txt'})
Path('graphify-out/.graphify_chunks_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print('wrote', len(manifest), 'chunk manifests')