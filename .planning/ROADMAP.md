# Roadmap: movie_recommendator

## Overview

Este roadmap prioriza **corrección del contrato de datos RAG** y **seguridad** antes de invertir en automatización (CI/tests), **rendimiento operativo** del backend y, por último, **pulido de producto** en el chat. Las fases están acotadas para ser entregables verificables; la visión consolidada está en [research/SUMMARY.md](./research/SUMMARY.md) y el detalle por ámbito en los cuatro informes bajo `.planning/research/`.

## Phases

- [ ] **Phase 1: Integridad del corpus y contrato RAG** — Payload, ETL y filtros alineados con Qdrant.
- [ ] **Phase 2: Seguridad y gobernanza de acceso** — API/WS y CORS con postura mínima defendible.
- [ ] **Phase 3: Calidad de ingeniería y operaciones** — CI, pruebas regresivas, despliegue y observabilidad básica.
- [ ] **Phase 4: Rendimiento y evolución del RAG** — Async, parametrización, evaluación/calibración e ingesta evolutiva.
- [ ] **Phase 5: Experiencia de producto (chat)** — Errores visibles, accesibilidad y estados de carga coherentes.

## Phase Details

### Phase 1: Integridad del corpus y contrato RAG

**Goal:** La búsqueda y los filtros reflejan un **único contrato** entre ETL, payload en Qdrant y el asistente; no hay campos “fantasma” ni filtros que no matcheen puntos reales.

**Depends on:** Nada (primera fase).

**Temas / investigación:** `DATA_RAG.md` (contrato payload, `media_type` vs `metadata.type`, `MediaItem`/`load_unified`); brechas de calidad de datos (`ignore_errors`); `ARCHITECTURE_BACKEND.md` (filtro en `movie_assistant` coherente con índice).

**Success Criteria** (qué debe ser cierto al cerrar):

1. Un usuario (o prueba automatizada) puede ejecutar una consulta con filtro por tipo de medio (`movie` / `series`) y **obtener resultados coherentes** con el tipo elegido, no un conjunto vacío por desalineación de esquema.
2. Existe **documentación o pruebas** que fallen si el campo canónico de tipo en el documento indexado y el filtro del retriever divergen (p. ej. tests contra payload real o fixtures que representen el índice).
3. Las filas corruptas o esquemas inconsistentes en CSV **no pasan silenciosamente**: hay política explícita (rechazo, métrica o log estructurado) acorde al nivel de entorno.

**Plans:** TBD

Plans:

- [ ] 01-01: Unificar contrato `MediaItem` / `load_unified` / `semantic_chunking` / `_build_media_filter` (un nombre y valores canónicos).
- [ ] 01-02: Pruebas de regresión del filtro frente a documentos representativos en Qdrant (o mocks del payload).
- [ ] 01-03: Política de calidad en ingestión CSV (comportamiento ante errores documentado e implementado).

---

### Phase 2: Seguridad y gobernanza de acceso

**Goal:** Quien use la API REST y el WebSocket **no puede actuar como anónimo ilimitado** en despliegues expuestos; CORS y superficie de red siguen una política acotada por entorno.

**Depends on:** Phase 1 (recomendado: corregir contrato RAG antes de endurecer acceso a conversaciones que dependen del mismo backend; no bloquea técnicamente el diseño de auth mínima).

**Temas / investigación:** `OPS_QUALITY.md` (REST sin auth, WS sin token/origen, CORS `*` + credentials, LiteLLM/Ollama expuestos); `ARCHITECTURE_BACKEND.md` (riesgo por `convo_id` adivinable, extensión de protocolo WS).

**Success Criteria:**

1. Las rutas REST de conversaciones exigen **autenticación o secreto compartido** acorde al modelo de despliegue (p. ej. API key por instancia o cabecera validada en FastAPI), documentado en `.env.example`.
2. El handshake de `GET /api/v1/ws/movies` valida **el mismo mecanismo** (o uno equivalente) antes de aceptar la conexión o antes de operaciones sensibles.
3. CORS queda **restringido por lista de orígenes** configurable en producción; no se mantiene `allow_origins=["*"]` con `allow_credentials=True` en el perfil de despliegue real.
4. (Opcional pero deseable en la misma fase si aplica) Política documentada para **exposición de puertos** (solo perfiles dev vs prod en `docker-compose.yml` o equivalente).

**Plans:** TBD

Plans:

- [ ] 02-01: Auth mínima REST + validación en WS alineada con el modelo single-tenant/multi-tenant elegido.
- [ ] 02-02: CORS y variables de entorno por perfil (`application.py`, documentación).
- [ ] 02-03: Revisión de superficie compose (red interna, perfiles) según entorno objetivo.

---

### Phase 3: Calidad de ingeniería y operaciones

**Goal:** Cambios en backend y frontend **rompen el CI** si rompen formato, lint o build; el contenedor backend es apropiado para ejecución estable; salud y logs no filtran ruido crítico en producción.

**Depends on:** Phase 2 (la seguridad ya define el “contrato” de cómo se prueba el sistema expuesto; puede iniciarse en paralelo con Phase 2 solo para CI sin E2E auth si se acuerda explícitamente).

**Temas / investigación:** `OPS_QUALITY.md` (sin pytest/CI, `ruff` solo format, `reload=True` en contenedor, LiteLLM `main-latest`, health sin Postgres/Qdrant, `echo=True` SQL, `LOG_LEVEL` DEBUG); `ARCHITECTURE_BACKEND.md` (tests grafo/WS deseables).

**Success Criteria:**

1. Un workflow de CI ejecuta **al menos**: `ruff check` + `ruff format --check` en backend, **pytest** con cobertura de un endpoint crítico (p. ej. health) y rutas REST acotadas; en frontend `npm run lint` y `npm run build`.
2. La imagen/servicio backend en compose usa **`reload=False`** (o equivalente) para el modo contenedor estable descrito en documentación.
3. El endpoint de salud (o uno complementario) refleja **disponibilidad de Postgres y Qdrant** cuando el producto los requiere para operar.
4. En el perfil de producción, **no** se imprimen todas las sentencias SQL (`echo` desactivado) y el nivel de log es **configurable** sin reconstruir imagen.

**Plans:** TBD

Plans:

- [ ] 03-01: Workflow CI (p. ej. GitHub Actions) + pytest mínimo + ampliar `Justfile` / scripts locales.
- [ ] 03-02: Ajustes Docker/compose: reload, versión fija LiteLLM opcional, límites/recursos según necesidad.
- [ ] 03-03: Health extendido y política de logging por entorno (`health.py`, `db/session.py`, `logger`).

---

### Phase 4: Rendimiento y evolución del RAG

**Goal:** El camino crítico de búsqueda **no bloquea el event loop** bajo carga razonable; híper-parámetros y umbral de recuperación son **ajustables** y, cuando sea posible, **calibrados** con evidencia; la ingesta puede evolucionar sin recrear ciegamente todo el índice.

**Depends on:** Phase 1 (contrato de payload); **recomendado** después de Phase 3 para medir con CI/health estable.

**Temas / investigación:** `DATA_RAG.md` (rerank síncrono, UUID sin idempotencia, evaluación offline, umbral mágico, `SEMANTIC_RERANKER_MODEL_NAME` sin uso, SSL Kaggle); `ARCHITECTURE_BACKEND.md` (async rerank, parametrización prefetch/final/threshold, inyección de dependencias para tests).

**Success Criteria:**

1. La operación CPU-intensiva del reranker **no bloquea** el bucle asyncio del request (p. ej. `asyncio.to_thread`, worker o patrón equivalente verificable bajo prueba de carga ligera).
2. `prefetch_limit`, `final_limit` y umbral de calidad de recuperación son **configurables vía settings** y están documentados en `.env.example`.
3. Existe un **conjunto pequeño de consultas etiquetadas** (20–50) y un script o job que reporte métricas básicas (p. ej. recall@k / MRR) para guiar el ajuste del umbral.
4. Hay un plan ejecutado de **IDs deterministas o deduplicación** en ingesta, o modo incremental documentado, que permita actualizar el índice sin `recreate=True` obligatorio en el flujo operativo objetivo.

**Plans:** TBD

Plans:

- [ ] 04-01: Rerank async + parametrización retriever/assistant vía `settings.py`.
- [ ] 04-02: Suite mínima de evaluación offline + recalibración de `RETRIEVAL_SCORE_THRESHOLD`.
- [ ] 04-03: Ingesta idempotente/incremental y limpieza de config muerta (`SEMANTIC_RERANKER_MODEL_NAME` o su uso).

---

### Phase 5: Experiencia de producto (chat)

**Goal:** El usuario **ve** fallos de red, envío fallido y carga de conversación; el streaming es más **accesible**; el panel LangGraph sigue siendo útil sin sacrificar a11y básica.

**Depends on:** Phase 3 (CI facilita regresión de UI); puede solaparse con Phase 4 si los equipos de trabajo son secuenciales en una sola persona (orden sugerido: tras estabilidad backend).

**Temas / investigación:** `FRONTEND_UX.md` (`WebSocketProvider.tsx`, `ChatView.tsx`, `LangGraphPanel.tsx`, `Message.tsx`, `Chat.tsx`, `ws.ts`).

**Success Criteria:**

1. Ante fallo de WebSocket, reconexión agotada o error del servidor, el usuario ve **mensaje o toast** con acción (reintentar / volver), no solo estado silencioso o consola.
2. Si el envío por WS falla, el mensaje optimista queda **marcado como no enviado** o se revierte, con copy claro.
3. Durante `isMessagesLoading` la UI muestra **skeleton o mensaje** explícito, no pantalla vacía prolongada.
4. El contenido del asistente en streaming se anuncia de forma razonable para tecnologías asistivas (**`aria-live`** u patrón equivalente) y las animaciones respetan **`prefers-reduced-motion`** donde aplica.
5. Controles críticos del panel LangGraph (p. ej. cerrar) tienen **etiquetas accesibles**; se documenta el contrato de eventos WS frente al backend para futuras pruebas E2E.

**Plans:** TBD

Plans:

- [ ] 05-01: Capa unificada de errores/toasts + rollback optimista (`WebSocketProvider`, store).
- [ ] 05-02: Estados de carga en `ChatView` + indicador de reconexión en `ws.ts` / provider.
- [ ] 05-03: A11y streaming y motion; mejoras `LangGraphPanel` y checklist focalizada.

---

## Progress

**Execution order:** Phases 1 → 2 → 3 → 4 → 5 (Phase 3 puede iniciar en paralelo con Phase 2 solo si se acuerda alcance de CI sin E2E completo).

**Dependencias resumidas:**

| Phase | Depende de |
|-------|------------|
| 1 | — |
| 2 | 1 (recomendado) |
| 3 | 2 (ideal); paralelo parcial posible |
| 4 | 1; idealmente tras 3 |
| 5 | 3 (ideal); puede tras 4 en calendario de una persona |

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Integridad RAG | 0/3 | Not started | - |
| 2. Seguridad | 0/3 | Not started | - |
| 3. Calidad / ops | 0/3 | Not started | - |
| 4. Rendimiento RAG | 0/3 | Not started | - |
| 5. UX chat | 0/3 | Not started | - |

---

## Trazabilidad temática (investigación → fase)

| Documento | Temas cubiertos principalmente en |
|-----------|-------------------------------------|
| `research/SUMMARY.md` | Vista transversal (riesgos y prioridades) |
| `research/DATA_RAG.md` | 1, 4 |
| `research/OPS_QUALITY.md` | 2, 3 |
| `research/ARCHITECTURE_BACKEND.md` | 1, 2, 3, 4 |
| `research/FRONTEND_UX.md` | 5 |

Cuando exista `.planning/REQUIREMENTS.md` con IDs formales, añadir aquí una tabla `REQ → Phase` y mantener cobertura 1:1.
