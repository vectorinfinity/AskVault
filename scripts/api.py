# api.py
import os
import logging
import threading
from pathlib import Path
from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from flask_cors import CORS

from search import retrieve
from augment import build_prompt
from generate import generate_answer
from pipeline import run_pipeline

# -----------------------------
# Logging
# -----------------------------
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/api.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# -----------------------------
# Load env
# -----------------------------
load_dotenv()

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "5000"))
API_DEBUG = os.getenv("API_DEBUG", "false").lower() == "true"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
UPLOAD_FOLDER = PROJECT_ROOT / "pdfs"
MAX_UPLOAD_SIZE = 50 * 1024 * 1024
UPLOAD_FOLDER.mkdir(exist_ok=True)

processing_lock = threading.Lock()
processing_status = {"state": "idle", "filename": None, "message": "No document is processing."}

# -----------------------------
# Flask app
# -----------------------------
app = Flask(__name__, template_folder="../frontend", static_folder="../frontend/static")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE
CORS(app)


@app.route("/")
def index():
    return render_template("index.html")

# -----------------------------
# Helper: standard error response
# -----------------------------
def error_response(message, status_code=400):
    logger.warning(f"Error response {status_code}: {message}")
    return jsonify({
        "success": False,
        "error": message,
        "answer": None,
        "sources": []
    }), status_code


def _safe_pdf_filename(filename):
    safe_name = secure_filename(filename or "")
    if not safe_name or not safe_name.lower().endswith(".pdf"):
        return None
    return safe_name


def _process_pdf(pdf_path, filename):
    global processing_status
    try:
        succeeded = run_pipeline(str(pdf_path), filename)
        with processing_lock:
            processing_status = {
                "state": "completed" if succeeded else "failed",
                "filename": filename,
                "message": "Document is ready to query." if succeeded else "Processing failed. Check logs/pipeline.log.",
            }
    except Exception:
        logger.exception("Unexpected background processing error for %s", filename)
        with processing_lock:
            processing_status = {"state": "failed", "filename": filename, "message": "Processing failed. Check logs/pipeline.log."}


@app.route("/upload-pdf", methods=["POST"])
def upload_pdf():
    uploaded_file = request.files.get("file")
    if not uploaded_file or not uploaded_file.filename:
        return error_response("Choose a PDF file to upload")

    filename = _safe_pdf_filename(uploaded_file.filename)
    if not filename:
        return error_response("Only PDF files can be uploaded")

    destination = UPLOAD_FOLDER / filename
    if destination.exists():
        return error_response("A PDF with this name already exists. Rename it and try again.", 409)

    try:
        uploaded_file.save(destination)
    except OSError as error:
        logger.error("Could not save uploaded PDF %s: %s", filename, error)
        return error_response("Could not save the uploaded PDF", 500)

    logger.info("Uploaded PDF: %s", filename)
    return jsonify({"success": True, "filename": filename, "message": "PDF uploaded. You can now process it."}), 201


@app.route("/process-pdf", methods=["POST"])
def process_pdf():
    global processing_status
    data = request.get_json(silent=True) or {}
    filename = _safe_pdf_filename(data.get("filename")) if isinstance(data, dict) else None
    if not filename:
        return error_response("A valid PDF filename is required")

    pdf_path = UPLOAD_FOLDER / filename
    if not pdf_path.is_file():
        return error_response("Uploaded PDF was not found", 404)

    with processing_lock:
        if processing_status["state"] == "processing":
            return error_response("Another PDF is already processing. Please wait for it to finish.", 409)
        processing_status = {"state": "processing", "filename": filename, "message": "Extracting, chunking, and indexing the PDF…"}

    threading.Thread(target=_process_pdf, args=(pdf_path, filename), daemon=True).start()
    logger.info("Started processing PDF: %s", filename)
    return jsonify({"success": True, **processing_status}), 202


@app.route("/process-status", methods=["GET"])
def process_status():
    with processing_lock:
        return jsonify({"success": True, **processing_status})

# -----------------------------
# Health check endpoint
# lets APEX / ops team verify API is alive
# -----------------------------
@app.route("/health", methods=["GET"])
def health():
    logger.info("Health check called")
    return jsonify({
        "status": "ok",
        "service": "RAG API"
    }), 200

# -----------------------------
# Main Q&A endpoint
# APEX will call this with a question
# -----------------------------
@app.route("/ask", methods=["POST"])
def ask():
    # -----------------------------
    # Parse and validate request
    # -----------------------------
    data = request.get_json(silent=True)

    if not isinstance(data, dict) or not data:
        return error_response("Request body must be valid JSON")

    question = data.get("question", "")
    if not isinstance(question, str):
        return error_response("'question' must be a string")
    question = question.strip()
    top_k = data.get("top_k", 5)

    if not question:
        return error_response("'question' field is required and cannot be empty")

    if type(top_k) is not int or top_k < 1 or top_k > 20:
        return error_response("'top_k' must be an integer between 1 and 20")

    logger.info(f"Received question: '{question}' | top_k: {top_k}")

    # -----------------------------
    # Step 1 — Retrieve
    # -----------------------------
    try:
        top_results = retrieve(question, top_k)
    except Exception as e:
        logger.error(f"Retrieval failed: {e}")
        return error_response("Retrieval step failed — please try again", 500)

    if not top_results:
        logger.warning(f"No results found for: '{question}'")
        return jsonify({
            "success": True,
            "answer": "I could not find any relevant information in the documents for your question.",
            "sources": [],
            "chunk_count": 0
        }), 200

    # -----------------------------
    # Step 2 — Augment
    # -----------------------------
    try:
        augmented = build_prompt(question, top_results)
    except Exception as e:
        logger.error(f"Augmentation failed: {e}")
        return error_response("Augmentation step failed — please try again", 500)

    # -----------------------------
    # Step 3 — Generate
    # -----------------------------
    try:
        result = generate_answer(augmented["prompt"])
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        return error_response("Generation step failed — please try again", 500)

    if not result["success"]:
        logger.error(f"Generation returned failure for: '{question}'")
        return error_response("Model failed to generate a response — please try again", 500)

    # -----------------------------
    # Build response
    # -----------------------------
    sources = [
        {"filename": filename, "section": section}
        for filename, section in augmented["sources"]
    ]

    response = {
        "success": True,
        "answer": result["answer"],
        "sources": sources,
        "chunk_count": augmented["chunk_count"],
        "model": result["model"],
        "truncated": augmented["truncated"]
    }

    logger.info(f"Successfully answered: '{question}' | Sources: {len(sources)}")

    return jsonify(response), 200

# -----------------------------
# 404 handler
# -----------------------------
@app.errorhandler(404)
def not_found(e):
    return error_response("Endpoint not found", 404)

# -----------------------------
# 405 handler
# -----------------------------
@app.errorhandler(405)
def method_not_allowed(e):
    return error_response("Method not allowed on this endpoint", 405)


@app.errorhandler(413)
def file_too_large(e):
    return error_response("PDF is too large. Maximum file size is 50 MB.", 413)

# -----------------------------
# 500 handler
# -----------------------------
@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Unhandled server error: {e}")
    return error_response("Internal server error", 500)

# -----------------------------
# Run
# -----------------------------
if __name__ == "__main__":
    logger.info(f"Starting RAG API on {API_HOST}:{API_PORT}")
    app.run(
        host=API_HOST,
        port=API_PORT,
        debug=API_DEBUG
    )
