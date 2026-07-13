import re
import torch
import soundfile as sf
from transformers import VitsModel, AutoTokenizer

MODELS = {
    "bn": {
        "model_id": "facebook/mms-tts-ben",
        "model": None,
        "tokenizer": None,
    },
    "en": {
        "model_id": "facebook/mms-tts-eng",
        "model": None,
        "tokenizer": None,
    },
}

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def load_models(progress_callback=None):
    for lang, info in MODELS.items():
        model_id = info["model_id"]
        info["model"] = VitsModel.from_pretrained(model_id).to(DEVICE)
        info["tokenizer"] = AutoTokenizer.from_pretrained(model_id)
        if progress_callback:
            progress_callback(lang)


def chunk_text(text, lang="en"):
    if not text or not text.strip():
        return []

    text = text.strip()

    if lang == "bn":
        pattern = r'(?<=[।\?\!\.])\s*'
    else:
        pattern = r'(?<=[\?\!\.])\s*'

    chunks = re.split(pattern, text)
    chunks = [c.strip() for c in chunks if c.strip()]

    if not chunks:
        return [text]

    MIN_CHUNK_LEN = 20
    merged = []
    buffer = ""
    for chunk in chunks:
        if buffer and len(buffer) + len(chunk) < MIN_CHUNK_LEN:
            buffer = (buffer + " " + chunk).strip()
        elif buffer:
            merged.append(buffer)
            buffer = chunk
        else:
            buffer = chunk
    if buffer:
        merged.append(buffer)

    return merged if merged else [text]


def generate_wav(text, lang, chunk_path):
    m = MODELS[lang]
    inputs = m["tokenizer"](text, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        try:
            output = m["model"](**inputs).waveform
        except torch.cuda.OutOfMemoryError:
            temp_inputs = m["tokenizer"](text, return_tensors="pt").to("cpu")
            temp_model = m["model"].to("cpu")
            output = temp_model(**temp_inputs).waveform
            m["model"].to(DEVICE)

    sample_rate = m["model"].config.sampling_rate
    sf.write(chunk_path, output.squeeze().cpu().numpy(), sample_rate)
    return chunk_path
