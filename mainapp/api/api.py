from flask import Blueprint, send_from_directory, request, jsonify, url_for
from pathlib import Path
from werkzeug.utils import secure_filename
from uuid import uuid4
import random # for random phrase selection
import json # for writing phrase_id sidecar metadata
import time # for simple timestamps
import os
import re
import subprocess
import numpy as np
import parselmouth
import matplotlib
matplotlib.use("Agg") # force non-GUI backend so plots work inside Flask threads
import matplotlib.pyplot as plt
from urllib.parse import urlparse

apiapp = Blueprint("apiroutes", __name__)
ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts" # where plots + wavs go
ARTIFACT_DIR.mkdir(exist_ok = True) # ensure artifacts dir exists
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads" # path of upload directory
UPLOAD_DIR.mkdir(exist_ok = True) # check that upload dir exists
PHRASES = [ # tiny starter phrase bank (replace later w/ DB)
    {"phrase_id": "p001", "hanzi": "你好", "pinyin": "nǐ hǎo"},
    {"phrase_id": "p002", "hanzi": "谢谢", "pinyin": "xiè xie"},
    {"phrase_id": "p003", "hanzi": "中文", "pinyin": "zhōng wén"}
]
TONE_MARKS = { # very small tone-mark lookup for common vowel diacritics
    "ā":1,"á":2,"ǎ":3,"à":4,
    "ē":1,"é":2,"ě":3,"è":4,
    "ī":1,"í":2,"ǐ":3,"ì":4,
    "ō":1,"ó":2,"ǒ":3,"ò":4,
    "ū":1,"ú":2,"ǔ":3,"ù":4,
    "ǖ":1,"ǘ":2,"ǚ":3,"ǜ":4,
} # if none found -> neutral/unknown

# detect tone number from tone mark (super simple)
def tone_from_pinyin_syllable(syl):
    for ch in syl:
        if ch in TONE_MARKS:
            return TONE_MARKS[ch]
    return 5 # treat as neutral/unknown

# fetch phrase dict by phrase_id
def get_phrase_by_id(phrase_id):
    for ph in PHRASES:
        if ph["phrase_id"] == phrase_id:
            return ph
    return None

# split pinyin string into syllables
def pinyin_syllables(pinyin):
    return [s for s in pinyin.strip().split() if s]

# map "/uploads/xyz.webm" -> UPLOAD_DIR/"xyz.webm"
def file_url_to_path(file_url):
    path = urlparse(file_url).path # strip domain/query
    fname = Path(path).name # just the filename
    return UPLOAD_DIR / fname

# convert anything -> wav 16k mono
def ffmpeg_to_wav16k_mono(src_path, dst_path):
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src_path), "-ac", "1", "-ar", "16000", str(dst_path)],
        check = True,
        stdout = subprocess.DEVNULL,
        stderr = subprocess.DEVNULL
    )

# return time array + f0 array
def extract_f0(wav_path):
    snd = parselmouth.Sound(str(wav_path)) # load audio
    pitch = snd.to_pitch(time_step = 0.01, pitch_floor = 75, pitch_ceiling = 500) # basic pitch tracking
    t = pitch.xs() # time stamps
    f0 = pitch.selected_array["frequency"] # Hz; 0 where unvoiced
    f0 = np.where(f0 > 0, f0, np.nan) # replace 0 with NaN (for unvoiced)
    return t, f0, snd.duration

# return (score, label) for one syllable window
def score_window(f0_win, tone):
    x = f0_win[np.isfinite(f0_win)] # drop NaNs (e.g. unvoiced)
    if len(x) < 5: # if not enough voiced frames:
        return 20, "too unvoiced/no pitch"

    start = x[0]
    end = x[-1]
    minimum = np.min(x)

    # normalze using log base 2 so "relative change" is nicer than raw hertz
    slope = np.log2(end) - np.log2(start) # positive = rising, negative = falling
    rng = np.log2(np.max(x)) - np.log2(np.min(x)) # movement amount

    # tone "grading"
    if tone == 1:
        if abs(slope) < 0.05 and rng < 0.10:
            return 95, "ok (level)"
        return 60, "too much movement (tone 1 should be level)"
    if tone == 2:
        if slope > 0.08:
            return 95, "ok (rising)"
        return 55, "not rising enough (tone 2)"
    if tone == 4:
        if slope < -0.08:
            return 95, "ok (falling)"
        return 55, "not falling enough (tone 4)"
    if tone == 3:
        # check for dip (min noticeably below both ends)
        if (minimum < min(start, end) * 0.92) and rng > 0.10:
            return 90, "ok (dip)"
        return 55, "missing dip (tone 3-ish)"
    # tone 5 or unknown
    return 75, "neutral/unknown tone"

# main analysis: per-syllable scores + plot
def analyze_and_plot(wav_path, phrase):
    t, f0, dur = extract_f0(wav_path) # compute pitch track
    syls = pinyin_syllables(phrase["pinyin"]) # list syllables
    tones = [tone_from_pinyin_syllable(s) for s in syls] # tone numbers per syllable

    n = max(1, len(syls)) # number of windows
    edges = np.linspace(0, dur, n + 1) # uniform segmentation

    syllable_results = []
    bad_spans = []

    for i in range(n):
        a, b = edges[i], edges[i + 1] # window bounds
        mask = (t >= a) & (t < b) # f0 samples inside window
        score, label = score_window(f0[mask], tones[i]) # compute score + label

        syllable_results.append({
            "idx": i,
            "syllable": syls[i],
            "tone": tones[i],
            "score": int(score),
            "label": label,
            "t0": float(a),
            "t1": float(b),
        })

        if score < 70: # threshold for "bad" syllable highlight
            bad_spans.append((a, b))

    overall = int(round(np.mean([s["score"] for s in syllable_results]))) # overall score

    # plot f0 + highlight bad spans
    fig = plt.figure(figsize = (8, 3)) # wide, short
    ax = fig.add_subplot(111)
    ax.plot(t, f0, linewidth = 1) # pitch track

    for (a, b) in bad_spans:
        ax.axvspan(a, b, alpha = 0.25) # highlight mistakes

    ax.set_xlabel("time (s)")
    ax.set_ylabel("f0 (Hz)")
    ax.set_title(f'{phrase["hanzi"]}   ({phrase["pinyin"]})   score={overall}')

    fig.tight_layout()

    return overall, syllable_results, fig

# serve uploaded audio files back to browser
@apiapp.get("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# serve uploaded artifacts back to browser
@apiapp.get("/artifacts/<run_id>/<path:filename>")
def artifact(run_id, filename):
    return send_from_directory(ARTIFACT_DIR / run_id, filename) # serve plot.png, etc.

# get a random phrase from the phrase bank
@apiapp.get("/phrase")
def phrase():
    return jsonify(random.choice(PHRASES)) # return {phrase_id, hanzi, pinyin}

# compare recording to DB
@apiapp.post("/compare")
def compare():
    data = request.get_json(force = True) # read JSON body
    phrase_id = data.get("phrase_id", "") # grab phrase_id
    file_url = data.get("file_url", "") # grab last uploaded file_url

    phrase = get_phrase_by_id(phrase_id) # lookup phrase info
    if not phrase:
        return jsonify({"error": "unknown phrase_id"}), 400

    src_path = file_url_to_path(file_url) # map url -> disk file path
    if not src_path.exists():
        return jsonify({"error": "audio file not found on server"}), 404

    run_id = f"{int(time.time())}_{uuid4().hex[:8]}" # unique id for artifacts
    out_dir = ARTIFACT_DIR / run_id # per-compare artifacts folder
    out_dir.mkdir(exist_ok = True) # ensure folder exists

    wav_path = out_dir / "user.wav" # normalized audio location
    plot_path = out_dir / "plot.png" # plot image location

    ffmpeg_to_wav16k_mono(src_path, wav_path) # convert audio to wav 16k mono
    overall, syllables, fig = analyze_and_plot(wav_path, phrase) # analyze + build plot
    fig.savefig(plot_path, dpi = 160) # save the plot
    plt.close(fig) # avoid matplotlib memory buildup

    return jsonify({
        "phrase_id": phrase_id,
        "file_url": file_url,
        "score": overall,
        "syllables": syllables,
        "plot_url": url_for("apiroutes.artifact", run_id = run_id, filename = "plot.png"), # serve plot
    })

# upload endpoint
@apiapp.post("/upload")
def upload():
    if "audio" not in request.files:
        return jsonify({"error": "missing form field: audio"}), 400
    
    f = request.files["audio"]
    if not f.filename: # ensure browser doesn't come with empty filename
        return jsonify({"error": "empty filename"}), 400
    
    ext = Path(f.filename).suffix.lower() or ".webm" # extract file extension; default to `.webm`

    base = secure_filename(Path(f.filename).stem)[:40] or "rec" # create base name for disk readability; `secure_filename` strips weird chars

    out_name = f"{uuid4().hex}__{base}{ext}" # create unique filenames

    phrase_id = request.form.get("phrase_id", "") # initialize `phrase_id` var
    (UPLOAD_DIR / f"{out_name}.json").write_text( # write phrase_id metadata next to audio file
        json.dumps({"phrase_id": phrase_id}, ensure_ascii = False, indent = 2)
    )

    out_path = UPLOAD_DIR / out_name
    f.save(out_path) # save file to disk

    return jsonify( # return a URL
        {
            "file_url": url_for("apiroutes.uploads", filename = out_name),
            "bytes_saved": out_path.stat().st_size
        }
    )