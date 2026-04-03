# Ops, calidad y seguridad (estado del repo)

**Proyecto:** movie_recommendator  
**Alcance:** Docker Compose, configuración, pruebas, CI, seguridad (API/WS), observabilidad  
**Fecha:** 2026-04-03  
**Confianza global:** **ALTA** para hallazgos basados en archivos del repo; **MEDIA** para recomendaciones de herramientas externas (no verificadas con Context7 en esta pasada).

---

## Historia de despliegue (deployment story)

- **Stack local/prototipo:** `docker-compose.yml` levanta **frontend** (Vite build + nginx en `:5173→80`), **backend** FastAPI (`:8000`), **Postgres 15** (healthcheck), **Qdrant**, **LiteLLM** (`ghcr.io/berriai/litellm:main-latest` + `backend/litellm_config.yaml` montado), **Ollama** (`:11434`). Perfil **`init`** con `qdrant-init` para poblar Qdrant vía `app.etl.populate_qdrant_movies`.
- **Build:** Backend multi-stage con **uv** y Python 3.13; frontend **Node 22** → artefacto estático en nginx. URLs del navegador se inyectan con build-args `VITE_API_BASE` / `VITE_WS_URL` (por defecto `localhost` en Dockerfile).
- **Gaps de producción:** no hay manifiestos K8s/Helm, compose sin `restart`/`resource limits` en la mayoría de servicios, imagen LiteLLM fijada a `main-latest` (etiqueta móvil), puertos de DB/vector/LLM expuestos al host (típico de dev). El backend arranca con `python -m app.main`, que ejecuta **uvicorn con `reload=True`** (`app/main.py`), poco adecuado para contenedor estable y con coste de CPU.
- **Automatización local:** `Justfile` con `sync`, `run-backend`, `run-frontend`, `check-backend` (**solo `ruff format --check`**, sin tests).

---

## Configuración y variables de entorno

- **Compose:** `env_file: ./.env` en varios servicios; backend recibe además `DATABASE_URI` construida en compose (sobreescribe/define conexión a `postgres`).
- **Plantilla:** `.env.example` documenta Qdrant, Postgres, backend host/port, `VITE_*`, `LITELLM_URL`. No lista todas las variables usadas en código (p. ej. modelos en `QdrantSettings`: `DENSE_MODEL_NAME`, `SPARSE_MODEL_NAME`, etc.).
- **Settings:** `pydantic-settings` + `BaseSettings` en `app/core/config/settings.py`; mezcla de defaults en clase y `os.getenv` en subclases (duplicidad posible con el modelo de settings).
- **Secretos:** ejemplo con contraseña placeholder. En `.gitignore` aparece `*.env` (puede no cubrir el archivo raíz `.env` según cómo se interprete el patrón); conviene confirmar que `.env` no se versiona.

---

## Pruebas y CI

| Área | Estado |
|------|--------|
| **Tests backend** | No hay `pytest` ni dependencias de test en `backend/pyproject.toml`; no se encontraron `test_*.py` / suites. |
| **Tests frontend** | `package.json` sin Vitest/Jest/Playwright; solo `build`, `lint`, `dev`, `preview`. |
| **CI** | **No existe** carpeta `.github/workflows` (ni otros CI detectados en raíz). |
| **Calidad estática** | Backend: **Ruff** (formato) en grupo `dev`. Frontend: **ESLint**. `check-backend` no ejecuta `ruff check` (lint), solo formato. |

**Conclusión:** el proyecto depende de ejecución manual y revisión; no hay red de seguridad regresiva automatizada.

---

## Postura de seguridad

- **API REST (`/api/v1/conversations/...`):** rutas usan `Depends(get_session)` pero **no hay autenticación/autorización** (sin JWT, API keys ni usuarios en el modelo `Conversation`). Cualquier cliente puede crear/listar/borrar conversaciones si alcanza el API.
- **WebSocket (`/api/v1/ws/movies`):** `await websocket.accept()` sin comprobación de token u origen; tras conectar, `resume_conversation` valida existencia y `use_case == "movies"` pero **no hay vínculo a identidad de usuario** — conocer o adivinar `convo_id` implica acceso a esa conversación.
- **CORS:** `allow_origins=["*"]` con `allow_credentials=True` en `application.py` — configuración permisiva y en la práctica problemática o inconsistente con políticas estrictas de navegador.
- **Superficie expuesta:** LiteLLM y Ollama en puertos accesibles desde el host en compose por defecto; en entornos compartidos requiere red interna/firewall o proxy con auth.
- **Dependencias:** LiteLLM/Ollama sin análisis de licencias/vulnerabilidades automatizado en repo.

---

## Observabilidad

- **Logging:** `logging` estándar a stdout, nivel **DEBUG** por defecto en `get_logger`; motor SQLAlchemy con **`echo=True`** en `db/session.py` (trazas SQL en logs — ruido y posible fuga de datos en texto).
- **Health:** `GET .../health/` comprueba API y LLM vía petición a endpoint de modelos de LiteLLM; no hay readiness separado de liveness ni chequeo de Postgres/Qdrant en ese endpoint.
- **Métricas/trazas:** no hay OpenTelemetry, Prometheus ni correlación de request-id en el código revisado.

---

## Fases sugeridas para roadmap (3–5)

1. **Fundamentos de calidad (CI + tests mínimos)**  
   Añadir workflow CI (p. ej. GitHub Actions): `uv run ruff check` + `ruff format --check`, tests **pytest** con `TestClient`/`httpx` para health y un flujo REST crítico; en frontend `npm run lint` + `npm run build`. Objetivo: fallo visible en PR.

2. **Endurecimiento de configuración y despliegue**  
   Documentar/envirolizar todas las variables; `reload=False` en contenedor; fijar versión de imagen LiteLLM; opcional `depends_on` + health del backend; reducir exposición de puertos en perfiles `dev` vs `prod`; límites de recursos en compose.

3. **Seguridad incremental**  
   CORS restringido por entorno; autenticación mínima (API key en proxy o en FastAPI) para REST/WS; considerar rate limiting; modelo de **usuario** o al menos secreto compartido por instancia si el producto sigue siendo single-tenant.

4. **Observabilidad operativa**  
   Niveles de log por `LOG_LEVEL`; desactivar `echo` SQL en prod; health extendido (DB, Qdrant); logs estructurados JSON opcional; métricas básicas (latencia WS, errores por código).

5. **(Opcional) Pruebas de integración / E2E**  
   Compose de test o job que levante servicios y ejecute pruebas de contrato contra API/WS; más adelante UI E2E si el chat es crítico comercialmente.

---

## Fuentes (evidencia en repo)

- `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`
- `backend/pyproject.toml`, `frontend/package.json`, `Justfile`
- `backend/src/app/application.py`, `main.py`, `core/config/settings.py`, `core/config/logger.py`, `db/session.py`
- `backend/src/app/api/v1/endpoints/ws_movies.py`, `crud/ws_movies.py` (aceptación WS)
- `backend/src/app/entities/conversation_model.py`, `api/v1/endpoints/conversations_routes.py`
- `backend/src/app/api/v1/endpoints/health.py`
- `.env.example`

---

## Brechas explícitas

- No se auditó `.gitignore` ni secretos reales en el entorno.
- No se ejecutaron escaneos de vulnerabilidades (`pip audit`, `npm audit`) en esta investigación.
- Recomendaciones de CI concretas (proveedor, matrices de Python/Node) quedan para la fase de planificación de roadmap.
