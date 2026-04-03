# Arquitectura backend (código existente)

**Proyecto:** movie_recommendator  
**Ámbito:** FastAPI, LangGraph (`movie_assistant.py`), WebSocket (`ws_movies.py`), LiteLLM, prompts, CRUD conversaciones  
**Fecha:** 2026-04-03  
**Confianza:** ALTA (basada en lectura directa del repositorio)

## Vista actual (componentes y flujo)

| Capa | Ubicación | Rol |
|------|-----------|-----|
| App FastAPI | `application.py`, `api/v1/api.py` | Lifespan (`init_db`), CORS, montaje de routers bajo `/api/v1` |
| WS cine | `api/v1/endpoints/ws_movies.py` → `crud/ws_movies.py` | `GET ws` en `/api/v1/ws/movies`; protocolo tipado (`WSRequest` / `WSResponse`) |
| Grafo agente | `assistants/movie_assistant.py` | `StateGraph`: router → contextualize → retrieve → (generate_retrieve \| reask_user) o generate_general |
| LLM | LiteLLM vía `ChatOpenAI` | `settings.LiteLLMSettings.openai_base_url`; modelos lógicos `primary-llm` / `secondary-llm` en proxy |
| RAG | `services/retriever.py` | `HybridSearcher`: Qdrant híbrido (denso + disperso, RRF), rerank fastembed cross-encoder |
| Persistencia | `crud/conversation_crud.py` + entidades SQLModel | Conversaciones/mensajes; `content` vs `raw_content`; actualización diferida de `content` |
| Prompts | `app/prompts/*.py` + `__init__.py` | Textos aislados por intención (router, contextualize, generate, reask, summarize) |

Flujo resumido: el cliente envía mensajes por WebSocket; se persiste el mensaje de usuario; se carga un historial acotado desde Postgres; se ejecuta `app_graph.astream_events` para streaming y telemetría de nodos; al finalizar se guarda la respuesta del asistente y se lanza en segundo plano `summarize_question_background` para actualizar el `content` del mensaje de usuario (ahorro en turnos siguientes).

## Fortalezas

1. **Separación clara grafo / transporte / CRUD** — El grafo no conoce WebSocket; `ws_movies.py` orquesta DB, interrupciones y eventos. Facilita tests y otro front (p. ej. HTTP SSE) reutilizando `build_app()`.
2. **Observabilidad en cliente** — Uso de `astream_events` con filtrado por nodos (`GRAPH_NODES`), `node_start` / `node_end`, `node_output` con metadatos (decisión, `media_type`, recuentos, reescritura). Alineado con un panel tipo LangGraph en frontend.
3. **RAG con calidad explícita** — Umbral `RETRIEVAL_SCORE_THRESHOLD`, rama `reask_user` y límite `MAX_REASK_COUNT`; filtro Qdrant por `metadata.media_type`. Evita generar con contexto irrelevante.
4. **LiteLLM como fachada** — Un solo `base_url` + modelos alias; rotación de proveedores y claves sin tocar cada cadena LCEL.
5. **Prompts modulares** — Fácil versionar o A/B test por archivo sin mezclar lógica de grafo.
6. **Estado de sesión WS bien modelado** — `ChatSession` con cancelación cooperativa, tarea de contextualización en background y `skip_db` si el cliente se desconecta.

## Brechas (funcionales / de diseño)

- **Doble “contextualización”** — En el grafo: `contextualize_question` (historial + pregunta). Tras el turno: `summarize_question_background` sobre el texto crudo del usuario para persistir. Pueden divergir; no hay una única fuente de verdad documentada para “qué ve el modelo como pregunta usuario en histórico”.
- **Historial cargado vs ventana del grafo** — `_load_langchain_messages` usa `number_of_messages_to_contextualize`; el grafo usa la misma constante en `format_history`. Coherente hoy, pero el acoplamiento es implícito (mismo setting, distintos sitios).
- **Sin trazas estructuradas server-side** — `logging` clásico; no hay IDs de correlación estándar (más allá de `req_id` local) ni export a OpenTelemetry.
- **Tests del grafo y del WS** — No verificados en esta lectura; el archivo `ws_movies.py` es grande (~760 líneas) y concentra lógica crítica.

## Señales de deuda técnica

| Señal | Evidencia | Riesgo |
|-------|-----------|--------|
| Singletons a import | `llm_primary`, `llm_secondary`, `searcher`, `app_graph` en módulos | Dificulta inyección de dependencias y tests con mocks; acoplado al proceso worker |
| `TypedDict` vs campos devueltos | `contextualize_question` devuelve `rewrote` no declarado en `AgentState` | Inconsistencia de tipos; herramientas estáticas pueden quejarse o ignorar campos |
| Rerank síncrono en `async def search` | `self.reranker.rerank(...)` en `retriever.py` | Bloqueo del event loop bajo carga; latencia acumulada por request WS |
| `logging.basicConfig` en `movie_assistant.py` | Configura root al importar | Puede chocar con la política de logging de la app (`get_logger` en WS) |
| CORS `allow_origins=["*"]` + `allow_credentials=True` | `application.py` | Patrón problemático en navegadores; revisar antes de producción |
| Umbral y modelos “mágicos” | Constantes y nombres de modelo en código / `.env` | Sin capa de configuración por entorno para experimentos (threshold, límites prefetch/final) |

## Puntos de extensión (dónde enganchar)

- **Nodos y aristas** — `build_app()` en `movie_assistant.py`: nuevos nodos (p. ej. herramientas TMDB, caché de embeddings, guardrails).
- **Router** — `router_node` + `ROUTER_PROMPT`: nuevas intenciones o ramas sin rediseñar todo el grafo.
- **Retriever** — `HybridSearcher.search`: otros filtros de payload, distintos límites, desactivar rerank por flag, otro fusionado.
- **Protocolo WS** — Nuevos `type` en `WSRequest`/`WSResponse` y ramas en `ws_handler_movies` (p. ej. feedback thumbs, selección de modelo).
- **CRUD** — `conversation_crud`: metadatos por mensaje (tokens, latencias), soft-delete, multi-tenant.
- **Config** — `settings.py`: nuevos campos Pydantic para parametrizar el grafo y el retriever.

## Direcciones concretas para fases de roadmap (3–5)

1. **Inyección de dependencias y capa de “assistant runtime”** — Factorizar `build_app(llm_router, llm_gen, searcher)` (o factory) y evitar singletons globales; permitir tests del grafo y del handler WS con doubles. Incluir estado inicial del grafo tipado de forma explícita (o `Annotated` con reducers) para alinear `AgentState` con lo que devuelven los nodos.

2. **Rendimiento del retriever en async** — Ejecutar rerank CPU-bound en `asyncio.to_thread` o proceso/worker dedicado; parametrizar `prefetch_limit` / `final_limit` y el umbral de calidad vía settings con métricas (p50/p95 de latencia por nodo).

3. **Observabilidad y coste** — Trazas por `conversation_id` / `req_id`, logging estructurado unificado, y contadores de tokens o llamadas (LiteLLM suele facilitar esto en proxy) para presupuestos y alertas.

4. **Unificar o documentar el pipeline de “pregunta persistida”** — Decidir si el histórico debe reflejar la salida de `contextualize_question`, de `summarize_question_background`, o ambas con campos distintos; reducir sorpresas en calidad RAG entre turnos.

5. **Contrato WS y resiliencia** — Versionar el protocolo de eventos, tests de integración para interrupciones y reconexión, y límites (tamaño de mensaje, rate limit por conexión) para operación estable.

## Referencias en código

- Grafo y LLM: `backend/src/app/assistants/movie_assistant.py`
- WebSocket y streaming: `backend/src/app/crud/ws_movies.py`
- Búsqueda: `backend/src/app/services/retriever.py`
- Config: `backend/src/app/core/config/settings.py`
- LiteLLM proxy: `backend/litellm_config.yaml` (definición de modelos alias)
- CRUD: `backend/src/app/crud/conversation_crud.py`
