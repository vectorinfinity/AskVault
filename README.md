# AskVault — Private Local LLM Search for HR Management

AskVault is a privacy-first HR knowledge platform that lets authorized users search internal HR documents with plain-language questions. It uses Retrieval-Augmented Generation (RAG), Oracle Vector Search, and locally hosted Ollama models to return grounded answers with source citations.

Questions and documents stay within the organization’s environment. After the required software and models have been installed, answering and document processing run locally without sending HR content to an external AI API.

## HR use cases

- Search employee handbooks, leave policies, benefits guides, compliance material, and internal procedures.
- Answer questions such as “What documents are needed for parental leave?” or “What is the travel reimbursement policy?”
- Upload a PDF from the web interface, process it, and search it immediately after indexing completes.
- Verify responses through the original document name and section reference.

## How it works

```text
HR PDF uploaded through the web app
              |
              v
Text extraction + OCR for scanned pages
              |
              v
Section-aware chunking
              |
              v
Local nomic-embed-text embeddings (Ollama)
              |
              v
Oracle Database 23ai vector store
              |
              v
Hybrid semantic + keyword retrieval
              |
              v
Local Qwen LLM answer with source citations
```

## Key features

- **Local LLM search:** `qwen2.5:1.5b` runs through Ollama on the local environment.
- **Private RAG workflow:** documents, embeddings, and answers remain in organization-controlled systems.
- **Offline operation:** no external model API is required after installation and model download.
- **PDF upload and processing:** upload from the frontend, then run extraction, chunking, and ingestion with one button.
- **Hybrid retrieval:** Oracle vector similarity search is combined with keyword scoring for more relevant results.
- **Source citations:** answers include the document name and section used as context.
- **Scanned-PDF support:** Tesseract OCR processes image-based PDFs.
- **Automatic ingestion option:** a watcher can process PDFs placed directly in the `pdfs/` folder.

## Technology stack

| Component | Technology |
| --- | --- |
| Backend API | Flask, Flask-CORS |
| Frontend | HTML, CSS, JavaScript |
| Local LLM | Qwen 2.5 1.5B through Ollama |
| Embeddings | `nomic-embed-text` through Ollama |
| Vector database | Oracle Database 23ai Vector Search |
| PDF extraction | PyMuPDF and pdfplumber |
| OCR | Tesseract OCR and pdf2image/Poppler |
| File monitoring | Watchdog |

## Prerequisites

- Python 3.9 or newer
- Oracle Database 23ai with Vector Search enabled
- [Ollama](https://ollama.com/download)
- Tesseract OCR and Poppler if scanned PDFs must be supported

Download the local models once:

```cmd
ollama pull nomic-embed-text
ollama pull qwen2.5:1.5b
```

## Installation

Open Command Prompt in the project folder:

```cmd
cd /d D:\RAGchatbot\AskVault-main\AskVault-main
python -m venv venv
venv\Scripts\activate
```

Install the Python dependencies:

```cmd
pip install -r requirements.txt
python -c "import nltk; nltk.download('stopwords')"
```

Create `.env` in the project root. Do not commit this file.

```env
# Oracle database
DB_USER=your_oracle_username
DB_PASSWORD=your_oracle_password
DB_DSN=your_oracle_connection_string

# Flask application
API_HOST=0.0.0.0
API_PORT=5000
API_DEBUG=false

# OCR paths on Windows
EXTRACT_TESSERACT=C:\Program Files\Tesseract-OCR\tesseract.exe
EXTRACT_POPPLER_PATH=C:\path\to\poppler\Library\bin

# Document chunking
CHUNK_MAX_SIZE=1000
CHUNK_OVERLAP=20
CHUNK_MIN_SIZE=100

# Answer generation
GENERATE_MIN_ANS_LEN=1
GENERATE_MAX_ANS_LEN=5000
```

Create the vector table in Oracle:

```sql
CREATE TABLE pdf_chunks (
    id          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    filename    VARCHAR2(200),
    chunk_text  CLOB,
    embedding   VECTOR(768, FLOAT32, DENSE),
    chunk_id    NUMBER,
    domain      VARCHAR2(50),
    section     VARCHAR2(200)
);
```

## Run the web application

Start Ollama in one Command Prompt window:

```cmd
ollama serve
```

In another window, open the project folder and start Flask:

```cmd
cd /d D:\RAGchatbot\AskVault-main\AskVault-main
venv\Scripts\activate
python scripts\api.py
```

Open [http://localhost:5000](http://localhost:5000).

1. Select **Choose PDF** and select an HR PDF.
2. Select **Upload PDF**.
3. Select **Process PDF** and wait for “Document is ready to query.”
4. Ask an HR question in the question box.

The processing button runs the existing extract → chunk → embed → Oracle ingestion pipeline in the background. One document is processed at a time.

## Alternative: automatic folder ingestion

Run the watcher in a separate Command Prompt window:

```cmd
cd /d D:\RAGchatbot\AskVault-main\AskVault-main
venv\Scripts\activate
python scripts\pipeline.py
```

Place PDFs in `pdfs/`. Successfully processed files move to `pdfs/processed/`; failures move to `pdfs/failed/`.

## Ask questions from the terminal

With Ollama and Oracle running:

```cmd
cd /d D:\RAGchatbot\AskVault-main\AskVault-main
venv\Scripts\activate
python scripts\generate.py
```

Enter a question and the number of document chunks to retrieve.

## API endpoints

Base URL: `http://localhost:5000`

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/health` | `GET` | Checks whether the API is running. |
| `/ask` | `POST` | Answers a question from indexed documents. |
| `/upload-pdf` | `POST` | Uploads one PDF file; maximum size is 50 MB. |
| `/process-pdf` | `POST` | Starts background processing for an uploaded PDF. |
| `/process-status` | `GET` | Returns the current PDF-processing status. |

Example question request:

```json
{
  "question": "What is the leave policy for new employees?",
  "top_k": 5
}
```

## Project structure

```text
AskVault/
├── frontend/                 # Web interface
├── scripts/
│   ├── api.py                # Flask API and PDF upload/process routes
│   ├── pipeline.py           # Extract → chunk → ingest workflow
│   ├── extract.py            # PDF extraction and OCR
│   ├── chunking.py           # Section-based chunking
│   ├── ingestion.py          # Embedding and Oracle ingestion
│   ├── search.py             # Hybrid retrieval
│   ├── augment.py            # Prompt construction
│   └── generate.py           # Local LLM answer generation
├── pdfs/                     # Local uploaded PDFs (ignored by Git)
├── texts/                    # Generated extracted text (ignored by Git)
├── chunks/                   # Generated chunks (ignored by Git)
├── logs/                     # Local application logs (ignored by Git)
├── .env                      # Local secrets (ignored by Git)
└── README.md
```

## Privacy and GitHub safety

Do not commit `.env`, uploaded HR PDFs, generated chunks, logs, Oracle Wallet files, database dumps, or employee information. The supplied `.gitignore` excludes these local and sensitive files.

When deploying AskVault beyond a local prototype, add authentication, role-based access controls, encrypted storage, document retention rules, audit logging, and a security review appropriate for your organization.

## License

This project is released under the [MIT License](LICENSE).
