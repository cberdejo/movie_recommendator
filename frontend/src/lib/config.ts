import type { UseCase as BaseUseCase } from "./types";

export type UseCase = BaseUseCase;

const BACKEND_PORT = 8000;
const API_PATH = "/api/v1";
const WS_PATH = "/api/v1/ws/movies";

function getBackendHost(): string {
  if (typeof window !== "undefined" && window?.location?.hostname) {
    return window.location.hostname;
  }
  return "localhost";
}

function getHttpProtocol(): string {
  if (typeof window !== "undefined" && window?.location?.protocol === "https:") {
    return "https";
  }
  return "http";
}

function getWsProtocol(): string {
  return getHttpProtocol() === "https" ? "wss" : "ws";
}

// Base URL for the backend API (FastAPI).
// In the browser we use the same host as the page and port 8000 so Docker/any host works.
// Override with VITE_API_BASE in the frontend .env if needed.
export const API_BASE_URL =
  (import.meta as any).env?.VITE_API_BASE ||
  `${getHttpProtocol()}://${getBackendHost()}:${BACKEND_PORT}${API_PATH}`;

// Base URL for the WebSocket endpoint.
// Same host as the page in the browser so it works with docker compose without extra config.
// Override with VITE_WS_URL in the frontend .env if needed.
export const WEBSOCKET_URL =
  (import.meta as any).env?.VITE_WS_URL ||
  `${getWsProtocol()}://${getBackendHost()}:${BACKEND_PORT}${WS_PATH}`;

// For ahora solo usamos el caso de uso "movies".
export const getWebSocketUrl = (_useCase: UseCase): string => WEBSOCKET_URL;

export const getChatPath = (
  useCase: UseCase,
  conversationId?: number,
): string =>
  conversationId != null
    ? `/chat/${useCase}/${conversationId}`
    : `/chat/${useCase}`;

