# Research: Data pipeline, Qdrant y RAG (código actual)

**Proyecto:** movie_recommendator  
**Alcance:** `backend/src/app/db`, `etl/`, `services/retriever.py`, uso en `assistants/movie_assistant.py`  
**Fecha:** 2026-04-03  
**Confianza:** **ALTA** para comportamiento implementado (lectura directa del repo); **MEDIA** para recomendaciones de producto.

---

## Resumen ejecutivo

El flujo de datos es **CSV → Polars (`media_dataset.load_unified`) → un `Document` por ítem (`semantic_chunking`) → índice Qdrant con vectores **dense** (FastEmbed/`sentence-transformers` por nombre de modelo) y **sparse** (Splade vía nombre de modelo), fusión **RRF** en consulta y **reranking** con cross-encoder (`fastembed` `TextCrossEncoder`). La app conversacional aplica un **filtro opcional por tipo de medio** y un **umbral de calidad** sobre la puntuación del reranker antes de generar o pedir aclaraciones.

Hay **desalineaciones importantes** entre lo que se indexa en el payload y lo que el retriever filtra, y el módulo `semantic_chunking` **no hace chunking semántico** (un ítem = un punto). No hay en el repo **evaluación sistemática de recuperación** ni trazabilidad de versiones de índice/dataset.

---

## Pipeline actual (hechos en código)

| Etapa | Ubicación | Comportamiento |
|--------|-----------|----------------|
| Descarga por defecto | `etl/populate_qdrant_movies._download_default_kaggle` | Kaggle Hub: `payamamanat/imbd-dataset`, `shivamb/netflix-shows`; reintentos; workaround temporal desactivando verificación SSL en env. |
| Unificación CSV | `etl/media_dataset.load_unified` | Dos esquemas (películas IMDb-style vs Netflix mixto); `glob` recursivo; `ignore_errors=True` en lectura. |
| Texto + metadata | `etl/semantic_chunking.build_semantic_documents_from_media_item` | Plantilla fija (título, tipo, director, géneros, reparto, duración, descripción). Metadata en payload anidado bajo `metadata`. |
| Creación colección | `services/retriever.HybridSearcher.create_collection` | Cosine en vector dense; sparse config por defecto de Qdrant. |
| Ingesta | `HybridSearcher.index` | `upsert` en lotes de **64**; IDs **UUID aleatorios** (sin idempotencia ni deduplicación por título). |
| Consulta | `HybridSearcher.search` | `FusionQuery(RRF)`; prefetch dense + sparse; `prefetch_limit` 15 → rerank → `final_limit` 5; scores: sigmoid del cross-encoder si `rerank=True`. |
| Orquestación RAG | `assistants/movie_assistant.retrieve` | Filtro Qdrant + umbral `RETRIEVAL_SCORE_THRESHOLD` (0.30) sobre mejor score. |

**PostgreSQL** (`db/init_db.py`, `session.py`) almacena conversaciones/mensajes; **no** es el almacén del corpus de películas.

---

## Palancas de calidad de recuperación

1. **Modelos (env):** `DENSE_MODEL_NAME`, `SPARSE_MODEL_NAME`, `RERANKER_MODEL_NAME` — impacto directo en recall/precisión y latencia. Existe `SEMANTIC_RERANKER_MODEL_NAME` en settings **sin uso** en `retriever.py` (deuda/config muerta).
2. **Híbrido RRF:** combina señal léxica (sparse) y semántica (dense); sensible a elección de modelo sparse (inglés vs multilingüe) frente a datos mixtos.
3. **Límites:** `prefetch_limit` / `final_limit` en `HybridSearcher` — tradeoff recall del pool vs coste del reranker.
4. **Reranking:** normalización sigmoid; el umbral de calidad en el asistente asume esta escala — requiere **calibración por colección** (comentario en código ya lo indica).
5. **Consulta:** contextualización previa (`contextualize_question`) cambia el texto de búsqueda vs pregunta cruda.
6. **Filtro `media_type`:** diseñado en `movie_assistant._build_media_filter` sobre `metadata.media_type`, pero el documento indexado usa **`metadata.type`** (y el campo **`media_type` en `load_unified` no coincide con el modelo `MediaItem`**, que solo define `type` — con `model_config` implícito pydantic v2, kwargs desconocidos se ignoran). **Riesgo:** filtro por `movie`/`series` **no coincide** con el esquema indexado o queda vacío para parte del dataset.
7. **Corpus por ítem:** descripciones largas no se segmentan; títulos/reparto repetidos en bloque único pueden diluir señal embedding frente a consultas cortas.

---

## Escalado y operación

- **Ingesta:** lotes de 64 y reintentos por batch en `populate_qdrant_movies`; recrear colección en cada corrida completa (`recreate=True`) — adecuado para dev, brusco para producción (downtime / pérdida de puntos si no hay snapshot).
- **IDs:** UUID por punto impide **updates incrementales** y deduplicación estable por clave de negocio (p. ej. título+fuente).
- **Consulta:** reranker en proceso por request sobre hasta `prefetch_limit` textos — cuello de botella CPU/memoria al subir concurrencia; sin cola ni GPU en el diseño actual.
- **Qdrant:** servicio único en Docker; sin sharding/replicación descrita en repo.
- **Kaggle:** dependencia de red y credenciales; workaround SSL debilita seguridad — solo aceptable como parche local documentado.

---

## Brechas de evaluación

- No hay suite de **métricas offline** (p. ej. nDCG@k, MRR, recall@k) ni conjunto de consultas golden.
- El umbral `RETRIEVAL_SCORE_THRESHOLD` es **mágico** sin histogramas ni A/B en código.
- No hay logging estructurado de **query → ids → scores** para análisis post hoc.
- No hay contrato explícito de **calidad de datos** tras `ignore_errors=True` en CSV (filas corruptas silenciosas).

---

## Elementos de roadmap sugeridos (3–5)

1. **Corregir contrato de payload y ETL:** alinear `MediaItem` / `load_unified` / `build_semantic_documents_from_media_item` / `_build_media_filter` (un solo nombre de campo canónico, p. ej. `media_type`, y valores `movie` | `series`); añadir pruebas que fallen si el filtro no matchea puntos reales.
2. **Ingesta idempotente y evolutiva:** claves deterministas en Qdrant (hash de fuente+id o título normalizado), modo incremental sin `recreate=True` obligatorio, y opcionalmente deduplicación entre los dos CSV.
3. **Chunking y enriquecimiento opcional:** para sinopsis largas, trocear con solapamiento o campos separados (p. ej. “facts” vs “plot”); evaluar impacto con un set fijo de queries antes de desplegar.
4. **Evaluación de recuperación:** 20–50 preguntas etiquetadas con títulos esperados; script que ejecute `HybridSearcher.search` y reporte métricas; recalibrar `RETRIEVAL_SCORE_THRESHOLD` con datos.
5. **Rendimiento en producción:** perfilar latencia reranker (batch interno, modelo más pequeño, o desactivar rerank en rutas de baja calidad requerida); revisar uso o eliminación de `SEMANTIC_RERANKER_MODEL_NAME`; endurecer descarga Kaggle (CA bundles / imagen base) en lugar de desactivar verificación SSL.

---

## Referencias en repo

- `backend/src/app/services/retriever.py` — colección, indexación, búsqueda híbrida, rerank.
- `backend/src/app/etl/populate_qdrant_movies.py`, `media_dataset.py`, `semantic_chunking.py` — ETL y texto.
- `backend/src/app/core/config/settings.py` — modelos y `chunk_size` (usado como default de batch CLI, no como tamaño de trozo de texto).
- `backend/src/app/assistants/movie_assistant.py` — filtro, umbral, flujo LangGraph.
