# Real context-aware transcription — Egypt lecture excerpt (29:18–35:21)

Model: `ggml-base.en.bin` (CPU). Audio: 6:03, 16 kHz mono, derived from the
original m4v (original never modified). This excerpt is an embedded
pyramid-construction educational video within the lecture.

## Runs & elapsed time

| Run | Prompt | Elapsed |
|-----|--------|---------|
| base.en, no context | — | 67.4 s |
| base.en, generic Egypt prompt | Tutankhamun, Abu Simbel, King Tut, … (not spoken here) | 72.0 s |
| base.en, targeted prompt | Mark Lehner, dolerite, Giza, Nile, Pythagoras, … | 52.4 s |

> small.en was **not** run: it is not present locally and the task did not
> authorize downloading a model.

## Reference for representative difficult lines

I cannot listen to the audio, so this is **not** a listened human transcript; it
is a domain-knowledge reference for a few representative lines (both terms are
verifiable facts, not guesses): the Egyptologist is **Mark Lehner**, and the rock
used for pounding is **dolerite**.

| # | base.en output (all three runs) | Correct |
|---|---------------------------------|---------|
| 1 | "Egyptologists like **Mark Lainer**" | Mark **Lehner** |
| 2 | "heavy **dolarite** hammer stones" | **dolerite** |
| 3 | "round **dolarite** ball bearings" | **dolerite** |
| 4 | "**Barrying** wood rails" | **Burying** |
| 5 | "**Wedding** with the right amount of water" | **Wetting** |
| 6 | "a quarry team of **12 to 1500** workers" | **1,200 to 1,500** |

## Effect of the context prompt

**Negligible for these errors.** "Mark Lainer" and "dolarite" persisted in **all
three** runs — including the targeted run whose prompt literally contained "Mark
Lehner" and "dolerite". whisper.cpp's `--prompt` biases the decoder's prior but
did not change these outputs for base.en on this audio.

- Proper-name errors fixed by prompt: **0 / 2**
- Technical-term errors fixed by prompt: **0**
- No new hallucinated words were introduced by the prompt.

## Effect of Context Repair (post-hoc, deterministic, offline)

With approved names `[Mark Lehner, dolerite, Giza, Nile, Pythagoras]`, the
deterministic Context Repair provider proposed **3 corrections** on the real
normalized transcript (raw hash `40bc59d19a0b`, unchanged throughout):

```
seg 48  dolarite hammer stones      -> dolerite hammer stones      (conf 0.75)
seg 70  round dolarite ball bearings -> round dolerite ball bearings (conf 0.75)
seg 75  Egyptologists like Mark Lainer -> Egyptologists like Mark Lehner (conf 0.75)
```

Accept-one / reject-one was exercised: the accepted correction appears in the
user-approved projection (`corrected.json`), the normalized layer is untouched,
and the raw content hash is unchanged — proving reversibility and raw immutability.

## Honest conclusion

No claim of "perfect transcription". Automatic base.en transcription makes
consistent, identifiable errors; the Whisper prompt is a weak remedy for specific
names; post-hoc Context Repair proposes the right fixes but only applies them when
the user accepts. Uncertainty stays visible and under user control.
