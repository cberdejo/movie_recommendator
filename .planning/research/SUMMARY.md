# Síntesis de investigación — movie_recommendator

**Fecha:** 2026-04-03  
**Propósito:** Vista unificada para roadmap y priorización; fusiona cuatro informes de ámbito (backend, frontend, datos/RAG, ops).

---

## Resumen ejecutivo

El producto es un **asistente de cine** con **FastAPI + WebSocket**, **LangGraph** (router → contextualize → retrieve → generar o re-preguntar), **RAG híbrido en Qdrant** (denso + disperso, RRF, rerank) y **frontend React/Vite** con streaming, panel de diagnóstico alineado con el grafo y persistencia de layout. La arquitectura actual es **coherente y extensible** (separación grafo / transporte / CRUD, prompts modulales, LiteLLM como fachada), pero el conjunto se comporta hoy como **prototipo maduro**: hay riesgos de **contrato de datos en RAG**, **seguridad y CORS**, **operación tipo desarrollo** y **experiencia silenciosa ante errores**.

La recomendación integrada es **fijar contratos antes de escalar**: alinear **payload Qdrant ↔ filtro `media_type` ↔ ETL**; definir **política de errores** visible en el cliente y **rollback** de mensajes optimistas; introducir **CI mínima** (lint + build + unos tests) y **endurecimiento incremental** (auth mínima, CORS por entorno, `reload=False`, imagen LiteLLM fijada, logs sin SQL en prod). En paralelo, **desbloquear async del rerank** y **unificar o documentar** el pipeline “pregunta que ve el modelo” vs “pregunta persistida” para evitar sorpresas entre turnos.

Los mayores retornos de inversión están en **corrección del filtro RAG**, **fundamentos de calidad (CI + tests)** y **superficie de seguridad**; el frontend ya tiene buenas bases de streaming y panel — el gap principal es **observabilidad percibida por el usuario** y **accesibilidad** en el flujo principal.

---

## Temas transversales

| Tema | Manifiesto en |
|------|----------------|
| **Contratos explícitos** | Payload Qdrant vs `_build_media_filter`; eventos WS frontend ↔ backend; `AgentState` vs campos devueltos por nodos; histórico vs contextualize + summarize. |
| **“Dev en producción”** | Uvicorn `reload`, LiteLLM `main-latest`, puertos expuestos, sin CI, logs DEBUG y `echo` SQL, CORS `*`. |
| **Calidad sin medición** | Sin suite RAG offline; umbral de retrieval “mágico”; sin trazas estructuradas server-side ni correlación. |
| **Resiliencia percibida** | WS: errores solo en consola; mensajes optimistas sin rollback; grafo UI posiblemente obsoleto tras fallos. |
| **Rendimiento bajo carga** | Rerank síncrono en `async` search; pool prefetch + rerank por request sin cola. |

---

## Registro de riesgos priorizado (top 8)

| # | Riesgo | Impacto | Mitigación inmediata (dirección) |
|---|--------|---------|----------------------------------|
| 1 | **Sin autenticación/autorización** en REST y WS; acceso por conocimiento de `conversation_id`. | Alto (filtración de datos, abuso) | API key / proxy auth; modelo usuario o tenant; validar origen WS. |
| 2 | **Desalineación `metadata.type` vs `metadata.media_type`** y kwargs ignorados en `MediaItem` → filtro RAG incorrecto o vacío. | Alto (respuestas basadas en contexto erróneo) | Unificar campo y valores; tests que fallen si el filtro no matchea puntos reales. |
| 3 | **CORS `allow_origins=["*"]` + `allow_credentials=True`**. | Alto (postura de seguridad / compatibilidad navegador) | Orígenes por env; revisar antes de producción. |
| 4 | **Errores de red/WS “silenciosos”**; mensaje optimista queda sin rollback ni CTA. | Medio-alto (pérdida de confianza, tickets falsos) | Capa unificada de errores/toasts; política explícita; reintentar / marcar no enviado. |
| 5 | **Rerank CPU bloqueando event loop** en retriever async. | Medio-alto (latencia p95, degradación bajo concurrencia) | `asyncio.to_thread` / worker; flags y límites configurables. |
| 6 | **Ausencia de CI y tests** (backend sin pytest; frontend sin Vitest/E2E). | Medio (regresiones no detectadas) | Workflow mínimo: ruff check+format, lint+build, tests REST críticos. |
| 7 | **Observabilidad y ruido operativo** (DEBUG por defecto, SQL `echo=True`, sin correlación/trazas). | Medio (coste, fugas en logs, debugging difícil) | `LOG_LEVEL` por env; quitar echo en prod; IDs de correlación; health DB/Qdrant. |
| 8 | **Ingesta Qdrant**: UUID aleatorios, `recreate=True`, sin idempotencia; SSL Kaggle desactivado en workaround. | Medio (downtime, datos duplicados, riesgo en descarga) | IDs deterministas; modo incremental; endurecer SSL/credenciales. |

---

## Recomendaciones consolidadas (temas de roadmap)

1. **Contrato de datos RAG** — Alinear ETL, `MediaItem`, documentos y filtro del asistente; eliminar config muerta (`SEMANTIC_RERANKER_MODEL_NAME` sin uso) o integrarla; evaluación offline ligera (20–50 queries) y recalibración del umbral.
2. **Runtime del asistente** — Inyección de dependencias / factory del grafo; estado del grafo tipado alineado con nodos; async seguro para rerank; parametrizar umbrales y límites vía settings con métricas.
3. **Experiencia y confiabilidad en cliente** — Errores visibles, reconexión anunciada, rollback optimista; `aria-live` / `prefers-reduced-motion`; refactor estable de listeners en `WebSocketProvider`.
4. **Ops y seguridad** — CI; contenedor sin reload; LiteLLM versionado; CORS y auth mínima; rate limits razonables; compose con límites y perfiles dev/prod.
5. **Un solo relato de “pregunta del usuario”** — Documentar o unificar contextualize vs summarize en persistencia para coherencia RAG multi-turno.
6. **Contrato WS versionado** — Tests de interrupción/reconexión; límites de mensaje y rate por conexión.

---

## Documentos fuente

| Documento | Contenido principal |
|-----------|---------------------|
| [ARCHITECTURE_BACKEND.md](./ARCHITECTURE_BACKEND.md) | Grafo LangGraph, WS, retriever, fortalezas, deuda (singletons, async rerank, doble contextualización). |
| [FRONTEND_UX.md](./FRONTEND_UX.md) | Streaming, LangGraph panel, gaps a11y/errores, riesgos de estado y WS. |
| [DATA_RAG.md](./DATA_RAG.md) | Pipeline CSV→Qdrant, híbrido RRF, bug de filtro `media_type`, ingestión y evaluación. |
| [OPS_QUALITY.md](./OPS_QUALITY.md) | Docker, CI ausente, seguridad API/WS, logging, health, fases sugeridas. |

---

## Confianza y brechas

- **Alta** en descripción del código y del repo (cuatro informes basados en lectura directa).
- **Media** en priorización de producto y elección exacta de herramientas CI/observabilidad (no verificadas con ejecución en esta síntesis).
- **Brechas para validar en planificación:** política de usuarios/tenants; volumen y SLA de concurrencia; idioma principal del corpus vs modelos sparse/dense.
