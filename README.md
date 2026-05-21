# Axon

## Run with Docker

This repository includes a `docker-compose.yml` for the AXON orchestrator and its helper services.

### 1) Start with Docker Compose

From `AXON-SERVER`:

```bash
cd /home/arjuna-automationsoftware/frappe-bench/apps/AXON-SERVER
docker compose up --build
```

This will start:
- `orchestrator` on host port `8004`
- `wiki` on host port `8002`
- `arxiv` on host port `8003`
- `ddgs` on host port `8005`
- `ollama` as a model server

### 2) Open the UI

Open in your browser:

- `http://localhost:8004/docs`

This is the FastAPI Swagger UI for the AXON API.

### 3) Query AXON

Use the `/v1/query` endpoint in the UI, or call it directly:

```bash
curl -X POST http://localhost:8004/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "Tell me about Agnikul Cosmos launch vehicle"}'
```

### 4) Important Ollama note

The compose file mounts a host path for Ollama models.
If the path in `docker-compose.yml` does not exist on your machine, update it to a valid local model directory before starting.

For example, set the `ollama` volume to a directory that contains your Ollama model files.
