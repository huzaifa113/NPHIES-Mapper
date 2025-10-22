# Mapper Project — Production-ready

This repository contains a production-ready mapper (Python FastAPI) and a Node/Express bridge.

## Quick start (Python)
```bash
python -m venv venv
source venv/bin/activate    # Windows: .\venv\Scripts\activate
pip install -r requirements.txt
uvicorn mapper_service_final:app --reload --port 8000
```

Open http://localhost:8000/docs for interactive API docs.

## Node Bridge
```bash
cd node-interface
npm install
node server.js
```

## Run tests
```bash
./run_tests.sh
```

Notes:
- Production environment should use MTOM/XOP for document attachments instead of embedding base64 in XML.
- You can set PY_BASE env var for Node to forward to remote Python server.
