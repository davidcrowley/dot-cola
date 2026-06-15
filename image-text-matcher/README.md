# DOT COLA Label Matcher by David Crowley

## Code Repository
https://github.com/davidcrowley/dot-cola

## Public Web Site
https://dot-cola.crowleyexperiment.com

Configurable in the .env file:
- u: testadmin
- p: testadmin
- api: x-api-key = test-api-key

## Description
Image Text Matcher is a proof-of-concept COLA label review app. It stores
submissions in PostgreSQL, queues them in the database, processes each job with a
single FastAPI-owned background worker, runs local PaddleOCR, and writes durable
`ProcessResult` records.

The OCR and matching pipeline is local-only. The service does not call cloud
OCR, SaaS APIs, hosted AI endpoints, or external image-processing services
during request handling or background processing.

## Vision, Approach

- The submitted data and images are already in the COLA system; therefore, I see this app to be a companion to COLA.
  - Ideally, COLA would push submissions objects into this app, or this app would check COLA for updates and pull.
  - In this case, the restfull API would be used to process and evaluate COLA submissions:
    - POST to /api/submissions - single object, or an array of objects
- The app GUI can also be used to create new submissions and, of course, manage the process as this is the best way to test the app.
- Because the app can accept an array of submission objects, I decided a worker queue would be the best way to process the submissions.
  - Once a submission is created, it is pushed into a queue, the worker pulls it off the queue and processes it for approval.
- Each submission can be edited and re-submitted.  Submissions have many Results.

## Assumptions, Compromises
### Images
- When using the GUI to create a new submission, you can upload an image or pull from the library.
- When using the API to create a new submission, you must put the path to an image in the existing library.
  - This relates to my assumption/vision that the app would pull from existing images in COLA and only need a reference to an image.
### Queue Performance
- In a production system I would use Redis and something like Celery to manage the queue, spin up multiple workers, and scale the workers as needed.
- In this case we use a single background worker.
### Matching Performance
- We could improve matching by:
  - Iterating more with the matching algorithm / logic, but I like where we got in the time
  - Using a 2nd model (like gpt-5.5) to search for items that were not found by the first model.
  - Generally, I was happy with Paddle OCR results, and it achieved the tasks well enough without any other dependencies.
### GUI
- It is ugly. That bothers me, but I thought time was better spent on functionality.
### Auth
- I kept it super simple. Single user, configurable in the .env file.
## Tools
- I use a Jetbrains IDE. with their AI Assistant plugin (access to claude, codex, etc)
- Used Codex 5.5 high and medium for this project.
- I deployed on DigitalOcean's virtual server - Ubuntu 24 LTS, wiht NGINX as a reverse proxy to the Docker container.
- Other components are exposed below.
## Project Structure

```text
app/
  api/
  db/
  schemas/
  services/
  worker/
  main.py
  models.py
  ocr/
  matching/
  utils/
alembic/
tests/
data/
sample_requests/
docker-compose.yml
```

## Local Quick Start

Docker Compose is the recommended runtime for local evaluation. It runs the
FastAPI app, background worker, migration job, and PostgreSQL in containers.

```bash
cd image-text-matcher
cp .env.example .env
docker compose up --build
```

Open the app at `http://localhost:8000/gui`. The default credentials in
`.env.example` are:

- username: `testadmin`
- password: `testadmin`

Services:

- `web`: FastAPI application and background queue worker on `http://localhost:8000`
- `db`: PostgreSQL on `localhost:5432`
- `migrate`: one-off Alembic migration job that runs before `web` starts

Important details:

- Queue state lives in PostgreSQL. There is no Redis or Celery service.
- Image input and processed output are mounted from `./data/images` and `./data/processed`.
- PaddleOCR models are cached in the `paddleocr_cache` named volume at `/root/.paddleocr`.
  The first OCR job may download the models; keep network access available for that initial run.
- To warm the model cache before processing queue items, run:
  `docker compose exec web python -c "from app.ocr.engine import PaddleOCREngine; PaddleOCREngine()"`.
- Protected API routes accept either the browser login session cookie or the `X-API-Key` header.
  Set `API_KEY` in `.env`, then use the `/docs` Authorize button or send `X-API-Key: <your key>`.

Health check:

```bash
curl http://localhost:8000/health
```

Stop the stack:

```bash
docker compose down
```

Stop it and remove database/model volumes:

```bash
docker compose down -v
```

The helper scripts provide the same common operations:

```bash
./scripts/shutdown.sh
./scripts/reset-state.sh
```

What the scripts do:

- `scripts/shutdown.sh`: stops Docker Compose services for this project.
- `scripts/reset-state.sh`: prompts for confirmation, stops Docker Compose, removes Compose volumes, and removes files from `data/images` and `data/processed` while keeping tracked `.gitkeep` placeholders.

Legacy direct OCR endpoint:

```bash
curl -X POST "http://localhost:8000/analyze-image" \
  -F "image=@sample.jpg" \
  -F 'targets_json=["ACME-4491","Inspection Passed","Serial Number","06/10/2026"]' \
  -F "match_threshold=85"
```

## Running Tests

Unit tests avoid live OCR execution. They cover schema validation, alias
handling, submission creation, queue bookkeeping, admin pause state, worker queue
polling, and matching helpers.

```bash
cd image-text-matcher
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools
python -m pip install -r requirements.txt
python -m pytest -q
```

## API

`POST /analyze-image` remains available as a direct OCR/matching endpoint.

The management API routes below require authentication. Browser users can log in
through `/gui`; API clients should use the `X-API-Key` header with the value from
the `API_KEY` environment variable.

Phase 2 adds:

- `POST /submissions`
- `GET /submissions`
- `GET /submissions/{submission_id}`
- `PATCH /submissions/{submission_id}`
- `DELETE /submissions/{submission_id}`
- `GET /submissions/{submission_id}/process-results`
- `GET /process-results/{process_result_id}`
- `GET /queue`
- `POST /queue/{submission_id}`
- `DELETE /queue/{submission_id}`
- `DELETE /queue`
- `GET /admin/processing-status`
- `POST /admin/processing/pause`
- `POST /admin/processing/resume`

Submissions store a single image path only. Images can be uploaded through the GUI or `/images/upload`, and referenced files live in the mounted image volume, typically under `/data/images`.
