# Hybrid Rag Analysis
[![Python](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

![Qdrant](https://img.shields.io/badge/Qdrant-FF4B4B?style=for-the-badge&logo=qdrant&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![SentenceTransformers](https://img.shields.io/badge/SentenceTransformers-FFCC00?style=for-the-badge)
![LangGraph](https://img.shields.io/badge/LangGraph-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white)
![LightRag](https://img.shields.io/badge/LightRag-FF6B6B?style=for-the-badge)
![LiteLLM](https://img.shields.io/badge/LiteLLM-7C3AED?style=for-the-badge&logo=openai&logoColor=white)

## Table of Contents
- [Project Overview](#project-overview)
- [Project Structure](#project-structure)
- [Main Technologies Used](#main-technologies-used)
- [WebSocket](#websocket)
- [LiteLLM](#litellm)
- [Use cases](#use-cases)
- [How to run](#run)
- [Credits](#credits)
- [License](#license)


## Project Overview <a id="project-overview"></a>

**RAG** application for movie analysis and recommendation. The backend exposes a conversational assistant that combines:

- **Hybrid search** (dense + sparse) over reviews indexed in Qdrant, with optional re-ranking.
- **LangGraph** to orchestrate the assistant flow (search, context, generation).
- **LiteLLM** as a unified proxy to the LLM (Ollama by default; configurable to OpenAI, vLLM, etc.).
- **WebSockets** for streaming responses in real time to the frontend.

The frontend is a chat interface that connects to the backend via WebSocket, allowing users to converse with the assistant and receive movie recommendations with streaming responses.


## Project Structure <a id="project-structure"></a>

```
movie_recommendator/
├── backend/                    # API FastAPI + LangGraph + Qdrant
│   ├── src/app/
│   │   ├── api/v1/endpoints/   # REST and WebSocket routes
│   │   ├── assistants/         # Assistant (movie_assistant) and LangGraph flow
│   │   ├── core/config/        # Configuration (settings, Qdrant, etc.)
│   │   ├── crud/               # WebSocket logic and handlers (ws_movies)
│   │   ├── db/                 # Qdrant population (populate_movies_qdrant)
│   │   └── services/           # Hybrid retriever (retriever.py)
│   ├── litellm_config.yaml     # LiteLLM model configuration (see LiteLLM)
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/                   # Chat UI (React + Vite)
│   ├── src/
│   │   ├── components/chat/    # ChatView, ChatInput, Sidebar
│   │   ├── providers/          # WebSocketProvider
│   │   ├── lib/                # config, api, types
│   │   └── service/            # ws.ts (WebSocket client)
│   └── package.json
├── docker-compose.yml          # Qdrant, Postgres, Ollama, LiteLLM, backend
├── Justfile                    # Local commands (sync, run-backend, run-frontend)
└── README.md
```


## Main Technologies Used <a id="main-technologies-used"></a>

### Core Framework & Language
- **Python 3.13**: The main programming language used for the entire project, providing modern features and performance improvements.

### RAG & LLM Frameworks
- **LangChain**: A comprehensive framework for building applications with Large Language Models (LLMs). It provides abstractions and tools for chaining together different components like prompt templates, LLMs, vector stores, and memory systems to create sophisticated AI applications.

- **LangGraph**: An extension of LangChain that enables building stateful, multi-actor applications with LLMs. It allows you to create complex workflows and agentic systems by modeling applications as graphs where nodes represent steps and edges represent transitions, making it ideal for building advanced RAG pipelines with multiple decision points.

### Vector Database & Embeddings
- **Qdrant**: A high-performance vector database designed for similarity search and storing embeddings. It enables efficient retrieval of semantically similar documents and supports advanced filtering capabilities for hybrid search strategies.

### Infrastructure & Deployment
- **Docker**: Containerization platform used for packaging and deploying the application and its dependencies in a consistent, isolated environment.

### LLM & Protocol
- **MCP (Model Context Protocol)**: A protocol that enables standardized communication and context management between different components of AI systems, facilitating better integration and interoperability.


## WebSocket <a id="websocket"></a>

Real-time communication between the frontend and backend is done via **WebSockets**:

- **Backend**: FastAPI exposes a WebSocket endpoint (e.g. `/api/v1/ws/movies`) that accepts text messages with the user's content. The assistant processes the query (RAG + LangGraph), calls the LLM through LiteLLM and sends the response **in streaming** over the same WebSocket, chunk by chunk, so the user sees the text appear live.
- **Frontend**: A `WebSocketProvider` (React) maintains the connection and a service (`ws.ts`) handles opening the socket, sending messages and parsing incoming responses (e.g. typed messages such as content chunks or "done"). This allows the chat to display streaming without reloading the page.

Benefits in this project: low perceived latency, a single persistent connection and native support for progressively generated text streams.


## LiteLLM <a id="litellm"></a>

**[LiteLLM](https://github.com/BerriAI/litellm)** is a proxy that unifies access to multiple LLM providers behind an OpenAI-compatible API. In this project:

- The backend does not call Ollama (or OpenAI, vLLM, etc.) directly, but **LiteLLM** (by default on port 4000).
- LiteLLM translates requests to the configured provider's format and returns responses in a standard format, allowing you to **switch model or provider** without touching the backend code.
- Model configuration (names, routes, API base) is defined in **`backend/litellm_config.yaml`**. There you list the models (e.g. `primary-llm` → `ollama/llama3.1`, `secondary-llm` → `ollama/llama3.2:1b`) and the `api_base` (e.g. `http://ollama:11434`). To use another backend (vLLM, OpenAI, etc.) just edit that file: add or change entries in `model_list` and adjust `litellm_params` (`model`, `api_base`, api_key if applicable). The docker-compose includes Ollama for convenience, but LiteLLM allows replacing or complementing it with any compatible API.


## How to run <a id="run"></a>

### With Justfile (local)

1. **Backend dependencies**
   ```bash
   just sync
   ```

2. **Qdrant database and data**  
   You need Qdrant (and optionally Postgres) running. The easiest way with Docker is to use the compose and the `init` profile to populate Qdrant:
   ```bash
   docker compose up -d
   docker compose --profile init up
   ```
   The `init` profile starts the `qdrant-init` service, which runs the script to populate movies in Qdrant.

3. **Backend**
   ```bash
   just run-backend
   ```

4. **Frontend**
   ```bash
   just run-frontend
   ```

If you use models via Ollama (as in the compose example), make sure you have the models downloaded, for example:
```bash
docker exec -it ollama ollama pull llama3.1
docker exec -it ollama ollama pull llama3.2:1b
```

### With Docker (docker-compose)

1. **Start all services** (Qdrant, Postgres, Ollama, LiteLLM, backend):
   ```bash
   docker compose up -d
   ```

2. **Populate Qdrant** (movie index):
   ```bash
   docker compose --profile init up
   ```

3. Optional: download models in the Ollama container (see `ollama pull` commands above).

The `docker-compose` includes **Ollama** as the default LLM service. Thanks to **LiteLLM**, you can switch to another provider (vLLM, OpenAI, etc.) without modifying the backend: just edit **`backend/litellm_config.yaml`** (add/change models and `api_base` or api_key) and, if needed, add or replace the corresponding service in `docker-compose`. The backend will keep calling LiteLLM on port 4000.


## Credits <a id="credits"></a>

- **Frontend**: based on the [tiny-ollama-chat](https://github.com/anishgowda21/tiny-ollama-chat/tree/master) repository by **Anish Gowda**.
- **Retriever**: thanks to **[@davcamunezr](https://github.com/davcamunezr)** for help with the hybrid retriever in `backend/src/app/services/retriever.py`.


## 📄 License <a id="license"></a>

MIT – free to use, modify and distribute.
