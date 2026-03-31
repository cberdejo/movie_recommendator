import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { useConversationStore } from "../store/conversationstore";
import wsService, { WSEventType } from "../service/ws";
import { MessageType } from "../lib/types";
import { useNavigate, useLocation } from "react-router-dom";
import { getWebSocketUrl, UseCase, getChatPath } from "../lib/config";

// ---------------------------------------------------------------------------
// Temp ID generator
// ---------------------------------------------------------------------------

let tempIdCounter = 0;
const generateTempId = () => {
  tempIdCounter = (tempIdCounter + 1) % 1000;
  return Date.now() * 1000 + tempIdCounter;
};

// ---------------------------------------------------------------------------
// Graph types
// ---------------------------------------------------------------------------

export type GraphNodeStatus = "idle" | "active" | "completed" | "error";

export interface GraphNodeState {
  id: string;
  status: GraphNodeStatus;
  output?: Record<string, any>;
}

export interface GraphState {
  isRunning: boolean;
  nodes: Record<string, GraphNodeState>;
  activeNode: string | null;
  executionPath: string[];
}

// Matches exactly the nodes in movie_assistant.py build_app()
const INITIAL_GRAPH_STATE: GraphState = {
  isRunning: false,
  nodes: {
    router: { id: "router", status: "idle" },
    retrieve: { id: "retrieve", status: "idle" },
    generate_retrieve: { id: "generate_retrieve", status: "idle" },
    generate_general: { id: "generate_general", status: "idle" },
    reask_user: { id: "reask_user", status: "idle" },
  },
  activeNode: null,
  executionPath: [],
};

// ---------------------------------------------------------------------------
// Context type
// ---------------------------------------------------------------------------

interface WebSocketContextType {
  isConnected: boolean;
  isThinking: boolean;
  isGenerating: boolean;
  currentThinking: string;
  finalThinking: string | null;
  graphState: GraphState;
  sendMessage: (message: string) => Promise<void>;
  startConversation: (message: string) => Promise<void>;
  resumeConversation: (conversationId: number) => Promise<void>;
  interruptGeneration: () => void;
  clearThinkingState: () => void;
}

const WebSocketContext = createContext<WebSocketContextType>({
  isConnected: false,
  isThinking: false,
  isGenerating: false,
  currentThinking: "",
  finalThinking: null,
  graphState: INITIAL_GRAPH_STATE,
  sendMessage: async () => { },
  startConversation: async () => { },
  resumeConversation: async () => { },
  interruptGeneration: () => { },
  clearThinkingState: () => { },
});

export const useWebSocket = () => useContext(WebSocketContext);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

interface WebSocketProviderProps {
  children: React.ReactNode;
}

const WebSocketProvider = ({ children }: WebSocketProviderProps) => {
  const navigate = useNavigate();
  const location = useLocation();

  // --- connection & generation state ---
  const [isConnected, setIsConnected] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const isGeneratingRef = useRef(false);

  // --- thinking state ---
  const [currentThinking, setCurrentThinking] = useState("");
  const [finalThinking, setFinalThinking] = useState<string | null>(null);
  const [thinkingStartTime, setThinkingStartTime] = useState<number | null>(null);
  const [thinkingEndTime, setThinkingEndTime] = useState<number | null>(null);

  // --- response streaming ---
  const responseContentRef = useRef<string>("");

  // --- active message tracking ---
  // Set on the first response_chunk (or after thinking_end if thinking exists).
  // Cleared on done.
  const activeMessageIdRef = useRef<number | null>(null);
  // Stores thinking content captured at thinking_end so response_chunk can attach it.
  const pendingThinkingRef = useRef<string>("");
  const pendingThinkingTimeRef = useRef<number | null>(null);

  // --- misc refs ---
  const currentUserMessageRef = useRef<string>("");

  // --- graph state ---
  const [graphState, setGraphState] = useState<GraphState>(INITIAL_GRAPH_STATE);

  // --- store ---
  const {
    fetchInitialData,
    error,
    selectedConversation,
    addMessageToConversation,
    createNewConversation,
    updateMessageContent,
    updateMessageWithThinking,
  } = useConversationStore();

  // ---------------------------------------------------------------------------
  // Routing helpers
  // ---------------------------------------------------------------------------

  const getUseCaseFromPath = useCallback((): UseCase => {
    if (location.pathname.startsWith("/chat/movies")) return "movies";
    if (location.pathname.startsWith("/chat/reviews")) return "reviews";
    if (location.pathname.startsWith("/chat/lightrag")) return "lightrag";
    return "movies";
  }, [location.pathname]);

  const useCase = getUseCaseFromPath();
  const isInChat = location.pathname.startsWith("/chat/");

  // ---------------------------------------------------------------------------
  // WebSocket connection lifecycle
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (!isInChat) {
      wsService.disconnect();
      setIsConnected(false);
      return;
    }

    const initializeUseCase = async () => {
      await fetchInitialData(useCase);
      const wsUrl = getWebSocketUrl(useCase);
      const connected = await wsService.connect(wsUrl);
      setIsConnected(connected);
    };

    initializeUseCase();

    return () => {
      wsService.disconnect();
    };
  }, [fetchInitialData, useCase, isInChat]);

  // ---------------------------------------------------------------------------
  // Helper: reset all generation state
  // ---------------------------------------------------------------------------

  const resetGenerationState = useCallback(() => {
    responseContentRef.current = "";
    activeMessageIdRef.current = null;
    pendingThinkingRef.current = "";
    pendingThinkingTimeRef.current = null;
    setIsThinking(false);
    setIsGenerating(false);
    isGeneratingRef.current = false;
    setThinkingStartTime(null);
    setThinkingEndTime(null);
  }, []);

  // ---------------------------------------------------------------------------
  // WebSocket event handlers
  // ---------------------------------------------------------------------------

  useEffect(() => {
    const eventHandlers: Record<WSEventType, (data: any) => void> = {

      // --- connection ---
      connected: () => {
        setIsConnected(true);
      },

      disconnected: () => {
        setIsConnected(false);
        resetGenerationState();
      },

      // --- thinking ---
      thinking_start: () => {
        setIsThinking(true);
        setIsGenerating(true);
        isGeneratingRef.current = true;
        setCurrentThinking("");
        setFinalThinking(null);
        setThinkingStartTime(Date.now());
        responseContentRef.current = "";
        activeMessageIdRef.current = null;
        pendingThinkingRef.current = "";
        pendingThinkingTimeRef.current = null;
      },

      thinking_chunk: (content: string) => {
        if (content) {
          setCurrentThinking((prev) => prev + content);
        }
      },

      // thinking_end: capture thinking content so the first response_chunk
      // can attach it when creating the assistant message.
      // We do NOT create the message here to avoid an empty-content flash.
      thinking_end: () => {
        const thinkingTime = thinkingStartTime
          ? (Date.now() - thinkingStartTime) / 1000
          : null;

        setIsThinking(false);
        setThinkingEndTime(Date.now());
        setFinalThinking(currentThinking);

        // Stash for response_chunk to pick up
        pendingThinkingRef.current = currentThinking;
        pendingThinkingTimeRef.current = thinkingTime;
      },

      // --- response streaming ---
      // First chunk: create the assistant message (with thinking if available).
      // Subsequent chunks: update the existing message.
      response_chunk: (content: string) => {
        setIsThinking(false);
        responseContentRef.current += content ?? "";

        if (!selectedConversation) return;

        if (!activeMessageIdRef.current) {
          // Create assistant message on first chunk
          const messageId = generateTempId();
          activeMessageIdRef.current = messageId;

          const assistantMessage: MessageType = {
            ID: messageId,
            ConversationID: selectedConversation.ID,
            Role: "assistant",
            Content: responseContentRef.current,
            RawContent: responseContentRef.current,
            Thinking: pendingThinkingRef.current || null,
            ThinkingTime: pendingThinkingTimeRef.current,
            CreatedAt: new Date().toISOString(),
          };

          addMessageToConversation(selectedConversation.ID, assistantMessage);
        } else {
          // Update content on subsequent chunks
          updateMessageContent(
            selectedConversation.ID,
            activeMessageIdRef.current,
            responseContentRef.current,
          );
        }
      },

      // --- response_done: finalise the assistant message and reset state ---
      response_done: () => {
        if (selectedConversation && activeMessageIdRef.current) {
          const thinkingTime =
            thinkingStartTime && thinkingEndTime
              ? (thinkingEndTime - thinkingStartTime) / 1000
              : pendingThinkingTimeRef.current;

          updateMessageWithThinking(
            selectedConversation.ID,
            activeMessageIdRef.current,
            responseContentRef.current,
            finalThinking || pendingThinkingRef.current || null,
            thinkingTime,
          );
        } else if (selectedConversation && responseContentRef.current && !activeMessageIdRef.current) {
          // Edge case: response_done arrived without any response_chunk (e.g. empty generation)
          // Nothing to persist on the frontend side.
        }

        resetGenerationState();
        setCurrentThinking("");
        setFinalThinking(null);
      },

      // --- conversation lifecycle ---
      conversation_started: (conversationId: any) => {
        if (!conversationId) return;

        const parsedId = Number(conversationId);
        if (!Number.isInteger(parsedId)) {
          console.warn("Invalid conversation ID for conversation_started:", conversationId);
          return;
        }

        const userMessage: MessageType = {
          ID: generateTempId(),
          ConversationID: parsedId,
          Role: "user",
          Content: currentUserMessageRef.current,
          RawContent: currentUserMessageRef.current,
          Thinking: null,
          ThinkingTime: null,
          CreatedAt: new Date().toISOString(),
        };

        createNewConversation(parsedId, userMessage);
        currentUserMessageRef.current = "";

        navigate(getChatPath(getUseCaseFromPath(), parsedId));
      },

      conversation_resumed: (conversationId: any) => {
        const parsedId = Number(conversationId);
        if (Number.isInteger(parsedId)) {
          console.log(`Conversation resumed: ${parsedId}`);
        } else {
          console.warn("conversation_resumed received without valid ID");
        }
      },

      // --- interrupt ---
      interrupt_ack: () => {
        resetGenerationState();
        setCurrentThinking("");
        setFinalThinking(null);
      },

      // --- graph events ---
      graph_start: () => {
        setGraphState({ ...INITIAL_GRAPH_STATE, isRunning: true });
      },

      graph_end: () => {
        setGraphState((prev) => ({ ...prev, isRunning: false, activeNode: null }));
      },

      node_start: (nodeName: string) => {
        if (!nodeName) return;
        setGraphState((prev) => ({
          ...prev,
          activeNode: nodeName,
          executionPath: [...prev.executionPath, nodeName],
          nodes: {
            ...prev.nodes,
            [nodeName]: {
              ...prev.nodes[nodeName],
              id: nodeName,
              status: "active",
            },
          },
        }));
      },

      node_end: (nodeName: string) => {
        if (!nodeName) return;
        setGraphState((prev) => ({
          ...prev,
          activeNode: prev.activeNode === nodeName ? null : prev.activeNode,
          nodes: {
            ...prev.nodes,
            [nodeName]: {
              ...prev.nodes[nodeName],
              status: "completed",
            },
          },
        }));
      },

      node_output: (rawContent: string) => {
        try {
          const data = JSON.parse(rawContent);
          const nodeName = data.node;
          if (!nodeName) return;
          const { node: _, ...outputData } = data;
          setGraphState((prev) => ({
            ...prev,
            nodes: {
              ...prev.nodes,
              [nodeName]: {
                ...prev.nodes[nodeName],
                output: { ...prev.nodes[nodeName]?.output, ...outputData },
              },
            },
          }));
        } catch {
          /* ignore parse errors */
        }
      },

      // --- errors ---
      error: (errorMsg: string) => {
        console.error("WS error:", errorMsg);
        resetGenerationState();
      },
    };

    Object.entries(eventHandlers).forEach(([event, handler]) => {
      wsService.addEventListener(event as WSEventType, handler);
    });

    return () => {
      Object.entries(eventHandlers).forEach(([event, handler]) => {
        wsService.removeEventListener(event as WSEventType, handler);
      });
    };
  }, [
    selectedConversation,
    currentThinking,
    finalThinking,
    thinkingStartTime,
    thinkingEndTime,
    addMessageToConversation,
    createNewConversation,
    updateMessageContent,
    updateMessageWithThinking,
    resetGenerationState,
    getUseCaseFromPath,
    navigate,
  ]);

  // ---------------------------------------------------------------------------
  // Public actions
  // ---------------------------------------------------------------------------

  const sendMessage = useCallback(
    async (message: string) => {
      if (!selectedConversation) {
        console.error("No active conversation");
        return;
      }

      // Optimistically add user message to the store
      const userMessage: MessageType = {
        ID: generateTempId(),
        ConversationID: selectedConversation.ID,
        Role: "user",
        Content: message,
        RawContent: message,
        Thinking: null,
        ThinkingTime: null,
        CreatedAt: new Date().toISOString(),
      };
      addMessageToConversation(selectedConversation.ID, userMessage);

      setIsThinking(true);
      setIsGenerating(true);
      isGeneratingRef.current = true;
      responseContentRef.current = "";

      const success = await wsService.sendMessage(selectedConversation.ID, message);
      if (!success) {
        console.error("Failed to send message");
        resetGenerationState();
      }
    },
    [selectedConversation, addMessageToConversation, resetGenerationState],
  );

  const startConversation = useCallback(
    async (message: string) => {
      currentUserMessageRef.current = message;
      setIsThinking(true);
      setIsGenerating(true);
      isGeneratingRef.current = true;
      responseContentRef.current = "";

      const success = await wsService.startConversation(message);
      if (!success) {
        console.error("Failed to start conversation");
        resetGenerationState();
      }
    },
    [resetGenerationState],
  );

  const resumeConversation = useCallback(async (conversationId: number) => {
    const success = await wsService.resumeConversation(conversationId);
    if (!success) {
      console.error("Failed to resume conversation");
    }
  }, []);

  const interruptGeneration = useCallback(() => {
    if (!isGeneratingRef.current) return;
    wsService.sendInterrupt();
  }, []);

  const clearThinkingState = useCallback(() => {
    setCurrentThinking("");
    setFinalThinking(null);
    setThinkingStartTime(null);
    setThinkingEndTime(null);
  }, []);

  // ---------------------------------------------------------------------------
  // Interrupt on page unload
  // ---------------------------------------------------------------------------

  useEffect(() => {
    const handleBeforeUnload = () => {
      if (isGeneratingRef.current) wsService.sendInterrupt();
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, []);

  // ---------------------------------------------------------------------------
  // Context value
  // ---------------------------------------------------------------------------

  const contextValue: WebSocketContextType = {
    isConnected,
    isThinking,
    isGenerating,
    currentThinking,
    finalThinking,
    graphState,
    sendMessage,
    startConversation,
    resumeConversation,
    interruptGeneration,
    clearThinkingState,
  };

  if (error) {
    return (
      <div className="h-screen flex items-center justify-center bg-gray-950 text-gray-200">
        <div className="text-center">
          <h2 className="text-xl font-semibold mb-2">Failed to load</h2>
          <p className="text-gray-400">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <WebSocketContext.Provider value={contextValue}>
      <div className="min-h-screen bg-gray-950">{children}</div>
    </WebSocketContext.Provider>
  );
};

export default WebSocketProvider;