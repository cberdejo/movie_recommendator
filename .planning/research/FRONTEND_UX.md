# Investigación: Frontend y UX (chat React/Vite)

**Alcance:** `frontend/src` — UI de chat, `WebSocketProvider`, `LangGraphPanel`, streaming, accesibilidad, errores.  
**Fecha:** 2026-04-03  
**Confianza:** **ALTA** (lectura directa del código); recomendaciones de producto **MEDIA** (criterio habitual de la industria).

---

## Fortalezas actuales

1. **Arquitectura de streaming bien pensada** — `WebSocketProvider` separa *thinking* (`thinking_chunk` / `thinking_end`) de la respuesta (`response_chunk` / `response_done`), usa `pendingThinkingRef` para adjuntar el pensamiento al primer chunk del asistente y evita un “flash” de mensaje vacío. El buffer `responseContentRef` + `activeMessageIdRef` encaja con actualizaciones incrementales en Zustand.

2. **Panel LangGraph coherente con el backend** — `INITIAL_GRAPH_STATE` y `NODE_DEFS` están alineados con el grafo del asistente; estados visuales (`idle` / `active` / `completed` / `error`), `node_output` parseado y trazas (`executionPath`, “Trace Log”) dan una UX de diagnóstico clara y con buen diseño visual (tema oscuro, jerarquía tipográfica).

3. **Layout y persistencia de preferencias** — `Chat.tsx` combina sidebar, chat central y panel derecho redimensionables, con anchos y visibilidad en `localStorage`; en `<768px` colapsa paneles y usa overlay para la sidebar.

4. **Rendimiento del hilo de mensajes** — `Message.tsx` hace *lazy* de `react-markdown`, registra solo lenguajes necesarios de highlight.js y ofrece copiar código; reduce carga inicial frente a cargar todo el stack markdown de entrada.

5. **Detalles de UX en chat** — Auto-scroll con respeto al scroll manual del usuario; guardas de condición de carrera al cargar conversación nueva mientras hay stream activo; barra de progreso en carga inicial; indicador de conexión; interrupción de generación y `beforeunload` que envía interrupt.

6. **A11y parcial pero presente** — Varios controles con `aria-label` (sidebar móvil, título, enviar/detener, toggles de paneles); botón “Thought process” con `aria-expanded`.

---

## Brechas (gaps)

| Área | Observación |
|------|-------------|
| **Errores WebSocket** | El handler `error` en el provider solo hace `console.error` y `resetGenerationState`; no hay mensaje visible, código de error ni acción de reintento. |
| **Fallos al enviar** | Tras `sendMessage` / `startConversation`, si `wsService.send*` devuelve `false`, se resetea estado pero el mensaje de usuario optimista **permanece** en el store sin rollback ni aviso. |
| **Carga de mensajes** | En `ChatView`, `isMessagesLoading` renderiza `null` → posible pantalla vacía breve sin *skeleton* ni texto. |
| **Errores de conversación** | `getConversation` puede dejar `error` en el store y `selectedConversation: null`; la vista no muestra un bloque de error dedicado (solo el pantallazo global del provider si `error` viene de `fetchInitialData`). |
| **LangGraphPanel** | Botón cerrar sin `aria-label`; el panel es mayormente decorativo para lectores de pantalla (nodos como `div` sin roles/región viva). |
| **Redimensionado** | *Handles* solo con ratón; sin alternativa teclado ni anuncio para SR. |
| **Movimiento** | Animaciones `pulse` / `bounce` / `animate-progress` sin comprobar `prefers-reduced-motion`. |
| **Markdown + HTML** | Bloques de código con `dangerouslySetInnerHTML` tras highlight.js: asunción de confianza en el contenido del modelo (riesgo si el pipeline cambia). |
| **i18n** | Mezcla EN/ES en `aria-label` y copy de UI. |

---

## Riesgos

1. **UX “silenciosa” ante fallos de red** — Usuario puede creer que el mensaje se envió o que la IA “no respondió” cuando el WS falló o el envío no tuvo éxito.

2. **Complejidad del `useEffect` del provider** — El registro de listeners depende de muchos valores (`currentThinking`, `finalThinking`, etc.); favorece re-suscripciones frecuentes y hace más difícil razonar sobre cierres (*closures*) en eventos encadenados (*thinking_end* vs último *thinking_chunk*). Conviene vigilar duplicados de listeners y condiciones de carrera en pruebas E2E.

3. **Estado del grafo** — Tras errores de nodo o desincronización con el backend, no hay reset explícito del grafo salvo `graph_start` / `graph_end`; la UI podría mostrar un camino obsoleto si el servidor se recupera de forma distinta.

4. **Accesibilidad en flujo principal** — El hilo de mensajes no usa `role="log"` / `aria-live` para anunciar nuevos fragmentos de streaming; usuarios con SR pueden no percibir la respuesta en tiempo real.

---

## Mejoras recomendadas para roadmap (5)

1. **Capa unificada de errores y toasts** — Superficie visible para: fallo de conexión/reconexión agotada, `WS error`, fallo al `send`, y errores de `getConversation` (con CTA “Reintentar” / “Volver al inicio”). Incluir rollback o marca de “no enviado” en mensajes optimistas.

2. **Streaming accesible** — Región con `aria-live="polite"` (o estrategia equivalente) para el contenido del asistente en curso; respetar `prefers-reduced-motion` en indicadores de *thinking* y progreso.

3. **Panel LangGraph a11y + modo compacto** — `aria-label` en cerrar; opcional `role="region"` + `aria-labelledby`; atajo de teclado para abrir/cerrar; modo colapsado solo con lista de nodos para pantallas estrechas.

4. **Higiene del WebSocketProvider** — Refactor a registro estable de listeners (refs para handlers) o capa tipo “reducer” para eventos WS; reduce riesgo de bugs y facilita pruebas. Documentar contrato de eventos frente al backend.

5. **Estados de carga explícitos** — *Skeleton* o mensaje cuando `isMessagesLoading`; indicador “reconectando…” cuando `wsService` reintenta; opcional banner si `lightrag` u otro *use case* está incompleto.

---

## Archivos de referencia (lectura rápida)

- `frontend/src/providers/WebSocketProvider.tsx` — contexto WS, streaming, grafo, pantalla “Failed to load”.
- `frontend/src/components/chat/ChatView.tsx` — lista de mensajes, *thinking*, scroll, carga.
- `frontend/src/components/chat/LangGraphPanel.tsx` — visualización del grafo.
- `frontend/src/components/chat/ChatInput.tsx` — envío, interrupt.
- `frontend/src/components/chat/Message.tsx` — markdown, thinking colapsable.
- `frontend/src/pages/Chat.tsx` — layout tres columnas, *localStorage*.
- `frontend/src/service/ws.ts` — conexión, reconexión, eventos.

---

## Lista de comprobación para el roadmap

- [ ] Definir política de errores (usuario vs consola).
- [ ] Definir comportamiento ante mensaje optimista fallido.
- [ ] Auditoría a11y focalizada (chat + paneles + teclado).
- [ ] Criterios de aceptación E2E para reconexión y streaming interrumpido.
