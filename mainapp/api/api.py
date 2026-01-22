from flask import Blueprint, send_from_directory, request, jsonify, url_for, json
from pathlib import Path
from werkzeug.utils import secure_filename
from uuid import uuid4

apiapp = Blueprint("apiroutes", __name__)
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads" # path of upload directory
UPLOAD_DIR.mkdir(exist_ok = True) # check that upload dir exists

# serve uploaded audio files back to browser
@apiapp.get("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)

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
    (UPLOAD_DIR / f"{out_name}.json").write_text(json.dumps("phrase_id", phrase_id)) # write the phrase_id to the proper file

    out_path = UPLOAD_DIR / out_name # save file to disk
    f.save(out_path)

    return jsonify( # return a URL
        {
            "file_url": url_for("apiroutes.uploads", filename = out_name),
            "bytes_saved": out_path.stat().st_size
        }
    )