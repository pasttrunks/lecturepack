# LecturePack Public Beta — 0.9.0-beta.1

Turn lecture videos into searchable transcripts, reviewed slides, study notes,
quizzes, flashcards, and exportable study materials.

**Works immediately:**
- ✓ Local lecture transcription
- ✓ Slide extraction and review
- ✓ Transcript editing and export
- ✓ Built-in quizzes and flashcards
- ✓ No account required

**Optional:**
- ○ Smart Study local AI (better chat, quizzes, flashcards — private, on your computer)
- ○ Online-fast transcription with your Groq key

---

## Install

1. Download **LecturePack-0.9.0-beta.1-Setup.exe** and run it. It installs per
   user (no administrator prompt), adds a Start Menu entry, and optionally a
   desktop shortcut.
2. Launch LecturePack. The core workflow is ready immediately — no account, no
   API key, no Ollama, no model download.

Advanced users can instead download **LecturePack-0.9.0-beta.1-Portable.zip**
and run `LecturePack.exe` from the extracted folder.

Verify your download against **LecturePack-0.9.0-beta.1-SHA256SUMS.txt**.

## Optional: Smart Study

Open **Study** (or Settings → Smart Study) and choose **Install Smart Study**
for better local chat, quizzes, and flashcards. Pick **Lightweight Study** or
**Balanced Study** (recommended for most computers). Smart Study runs privately
on your computer and is never required — Built-in Study always works.

## Beta disclosure

> This is a public beta. Keep copies of important source videos and exports.
> Please report processing, export, and interface issues.

## Known limitations

- **Clean-machine, packaged click-through, and Smart Study download matrix** are
  human/VM acceptance steps and are not claimed as validated in this build (see
  `docs/HANDOFF_PUBLIC_BETA_RELEASE.md`).
- Groq online transcription was validated live (both modes) with a real key;
  local↔online fallback is covered by the transcription-backend contract tests.
