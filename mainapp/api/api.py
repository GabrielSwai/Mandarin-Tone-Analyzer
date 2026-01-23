from flask import Blueprint, send_from_directory, request, jsonify, url_for
from pathlib import Path
from werkzeug.utils import secure_filename
from uuid import uuid4
import random # for random phrase selection
import json # for writing phrase_id sidecar metadata

apiapp = Blueprint("apiroutes", __name__)
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads" # path of upload directory
UPLOAD_DIR.mkdir(exist_ok = True) # check that upload dir exists
PHRASES = [ # tiny starter phrase bank (replace later w/ DB)
    {"phrase_id": "p001", "hanzi": "你好", "pinyin": "nǐ hǎo"},
    {"phrase_id": "p002", "hanzi": "谢谢", "pinyin": "xiè xie"},
    {"phrase_id": "p003", "hanzi": "中文", "pinyin": "zhōng wén"}
]

# serve uploaded audio files back to browser
@apiapp.get("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# get a random phrase from the phrase bank
@apiapp.get("/phrase")
def phrase():
    return jsonify(random.choice(PHRASES)) # return {phrase_id, hanzi, pinyin}

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