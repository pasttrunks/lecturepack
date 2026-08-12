/* Pre-baked REAL output of LecturePack running on demo_lecture.mp4.
   Shipped as a script, not JSON: the renderer is loaded over file://,
   where fetch() of a sibling file is blocked by web security. A script
   tag is not, so the demo cannot fail to load its own data. */
window.LP_DEMO_DATA = {
  "_provenance": "Real output of LecturePack's own pipeline on app/assets/demo/demo_lecture.mp4 (Polar Bears, 00:10). Slide frames extracted at the timestamps the slide detector selected; transcript lines are the Whisper output; concept, flashcard and quiz content is what Study generated from this lecture. Baked so the demo is instant, offline and deterministic — see docs/DECISIONS.md AD-47.",
  "source": {
    "name": "polar_bears.mp4",
    "duration": "00:10",
    "resolution": "1280x720"
  },
  "slides": [
    {
      "img": "slide_01.png",
      "t": "00:01.5",
      "title": "Polar Bear Secrets",
      "kept": true
    },
    {
      "img": "slide_02.png",
      "t": "00:09.5",
      "title": "The Stealth Chonk",
      "kept": true
    }
  ],
  "lines": [
    {
      "t": "00:00.0",
      "text": "Behold the polar bear. Its fur is not white but transparent. Beneath it, their skin is black.",
      "active": true
    },
    {
      "t": "00:07.6",
      "text": "They are actually marine mammals.",
      "active": false
    }
  ],
  "concepts": [
    {
      "term": "Transparent fur, black skin",
      "note": "Its fur is not white but transparent. Beneath it, their skin is black.",
      "t": "00:00"
    },
    {
      "term": "Marine mammals",
      "note": "Polar bears are classified as marine mammals.",
      "t": "00:08"
    }
  ],
  "card": {
    "q": "Is polar-bear fur actually white?",
    "a": "No — it is transparent. The skin beneath it is black."
  },
  "quiz": {
    "q": "Why are polar bears classed as marine mammals?",
    "options": [
      "They spend their lives dependent on the sea and sea ice",
      "They have gills",
      "They are related to seals",
      "They cannot survive on land"
    ],
    "answer": 0
  }
};
