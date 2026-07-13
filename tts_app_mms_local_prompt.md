# Build Prompt: Local Offline Bangla/English TTS App (Facebook MMS-TTS)

You are building a **fully offline** desktop Text-to-Speech app in Python with a CustomTkinter GUI, using **Facebook's MMS-TTS** models (no cloud API, no API key, no internet needed after first model download). This is a new, standalone project — not a modification of any prior gTTS/Azure version.

## 1. Model

| Language | Model ID (HuggingFace) |
|---|---|
| Bangla | `facebook/mms-tts-ben` |
| English | `facebook/mms-tts-eng` |

- Architecture: VITS (single-speaker per model). **No male/female voice choice** — each model is one fixed voice. Note this limitation in the UI (disable/hide voice-gender selector, or gray it out with a tooltip explaining MMS-TTS is single-voice).
- Output: raw waveform tensor + sample rate (typically 16kHz) — not an mp3 directly. Must be converted to a file.

## 2. Tech stack

| Concern | Library | Why |
|---|---|---|
| Model + inference | `transformers` (`VitsModel`, `AutoTokenizer`) | Official HF integration for MMS-TTS |
| Tensor/audio backend | `torch` | Required by transformers; use CUDA if available, else CPU |
| Waveform → file | `soundfile` (write `.wav`) | Simple, no ffmpeg dependency for wav |
| wav → mp3 (only if user clicks "Save as MP3") | `pydub` + ffmpeg | Same as before, only needed for the optional export step |
| GUI | `customtkinter` | Same as prior versions |
| Playback | `pygame.mixer` | Same proven approach — `get_busy()` polling, instant pause via direct `.pause()` call |
| Concurrency | `threading` + `queue.Queue` | Keep UI responsive during model inference |

Install: `pip install transformers torch soundfile pydub customtkinter pygame`

## 3. Model loading — do this once, not per chunk

```python
from transformers import VitsModel, AutoTokenizer
import torch

device = "cuda" if torch.cuda.is_available() else "cpu"

models = {
    "bn": {"model": VitsModel.from_pretrained("facebook/mms-tts-ben").to(device),
           "tokenizer": AutoTokenizer.from_pretrained("facebook/mms-tts-ben")},
    "en": {"model": VitsModel.from_pretrained("facebook/mms-tts-eng").to(device),
           "tokenizer": AutoTokenizer.from_pretrained("facebook/mms-tts-eng")},
}
```

- Load both models **at app startup** (a loading splash/progress label is fine — first run downloads weights, ~100-200MB per language, cached afterward by HF in `~/.cache/huggingface`).
- Never call `from_pretrained` inside the generation loop — reload cost per chunk would kill performance.
- Detect and log which device (`cuda`/`cpu`) is active; show it somewhere in the UI (e.g. status bar) since CPU inference is noticeably slower.

## 4. Generation function

```python
def generate_wav(text, lang, chunk_path):
    m = models[lang]
    inputs = m["tokenizer"](text, return_tensors="pt").to(device)
    with torch.no_grad():
        output = m["model"](**inputs).waveform
    sample_rate = m["model"].config.sampling_rate
    soundfile.write(chunk_path, output.squeeze().cpu().numpy(), sample_rate)
```

- Wrap in try/except: catch OOM (`torch.cuda.OutOfMemoryError`) separately from generic errors — on OOM, fall back to CPU for that chunk rather than crashing.
- No network error handling needed here (unlike gTTS/Azure) — inference is local. Simplify the pipeline accordingly (see §5).

## 5. Pipeline: generation + playback (carry over the proven design)

Since inference is now CPU/GPU-bound (not network I/O-bound like the old gTTS/Azure versions), thread-pool parallelism for generation gives little benefit and risks GPU memory contention — **run generation on a single background thread**, sequentially, feeding a bounded playback queue:

```
Generation Thread (single)                    Playback Thread (long-lived)
   for each chunk:                                loop:
     generate_wav(chunk) → queue.put()  ────►        item = queue.get()
     (blocks if queue full, maxsize=3)                pygame.mixer.music.load(item)
                                                       pygame.mixer.music.play()
                                                       while get_busy(): sleep(0.05)
                                                          check pause/stop each tick
```

- `queue.Queue(maxsize=3)` — same bounded-lookahead approach as before, so playback of chunk 1 starts as soon as it's ready while chunk 2 generates in the background.
- Text chunking: same sentence-boundary split (`.`, `?`, `!`, Bangla `।`), merge tiny fragments, skip chunking entirely for short input (single mp3/wav, no queue overhead).

## 6. Pause/Resume — get this right from the start

- Pause/Resume button calls `pygame.mixer.music.pause()`/`.unpause()` **directly and immediately** on click (main thread, no flag delay).
- Maintain a persistent `is_paused` flag that the **playback loop also checks before loading each new chunk** (`while is_paused: sleep(0.05)` before `.load()`/`.play()`) — this is critical so pause holds across chunk boundaries, not just within whatever chunk happened to be playing at click-time.
- Stop: clear the queue, `pygame.mixer.music.stop()`, reset generation thread.

## 7. UI elements (CustomTkinter)

| Element | Behavior |
|---|---|
| Multi-line text box | Paste-friendly |
| Language toggle | EN / BN |
| Device status label | Shows "Running on: GPU" or "Running on: CPU" |
| Speak button | Generate + play, temp files auto-deleted after playback |
| Save as MP3/WAV button | Generate all chunks, merge, save dialog, no autoplay |
| Stop / Pause-Resume | As specified above |
| Progress label | "Generating chunk 3/12 · Playing chunk 2/12" |
| First-run model download indicator | Progress bar or spinner while HF downloads weights (first launch only) |

## 8. File & cleanup policy

- Temp `.wav` files in `tempfile.mkdtemp()`, deleted after playback (Speak mode) or after merge (Save mode).
- Merge for "Save" uses `pydub.AudioSegment` concatenation, exported as `.mp3` (needs ffmpeg on PATH) or `.wav` (no ffmpeg needed) — offer both formats in the save dialog.

## 9. Explicit notes / limitations to surface to the user in-app
- No voice selection (single fixed voice per language) — mention this in a tooltip/about section so it's not mistaken for a bug.
- No emotion/prosody control (VITS output is flat, more natural than gTTS/espeak but not expressive like Azure/ElevenLabs).
- Fully offline after first model download — no character limits, no API costs, no internet dependency at runtime.
- First launch will be slow (model download); subsequent launches load from local cache.

## 10. File structure

```
tts_app_local/
├── main.py
├── gui.py
├── tts_engine.py        # model loading, generate_wav(), chunk_text()
├── audio_player.py       # playback thread, queue, pause/stop logic
├── requirements.txt
```
