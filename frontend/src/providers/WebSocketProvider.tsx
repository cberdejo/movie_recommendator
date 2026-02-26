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

let tempIdCounter = 0;
const generateTempId = () => {
  tempIdCounter = (tempIdCounter + 1) % 1000;
  return Date.now() * 1000 + tempIdCounter;
};

interface WebSocketContextType {
  isConnected: boolean;
  isThinking: boolean;
  currentThinking: string;
  finalThinking: string | null;
  sendMessage: (message: string) => Promise<void>;
  startConversation: (message: string) => Promise<void>;
  resumeConversation: (conversationId: number) => Promise<void>;
  clearThinkingState: () => void;
}

const WebSocketContext = createContext<WebSocketContextType>({
  isConnected: false,
  isThinking: false,
  currentThinking: "",
  finalThinking: null,
  sendMessage: async () => {},
  startConversation: async () => {},
  resumeConversation: async () => {},
  clearThinkingState: () => {},
});

export const useWebSocket = () => useContext(WebSocketContext);

interface WebSocketProviderProps {
  children: React.ReactNode;
}

const WebSocketProvider = ({ children }: WebSocketProviderProps) => {
  const navigate = useNavigate();
  const location = useLocation();
  const [isConnected, setIsConnected] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [thinkingStartTime, setThinkingStartTime] = useState<number | null>(
    null
  );
  const [thinkingEndTime, setThinkingEndTime] = useState<number | null>(null);
  const [finalThinking, setFinalThinking] = useState<string | null>(null);
  const [currentThinking, setCurrentThinking] = useState("");
  const [currentResponse, setCurrentResponse] = useState("");
  const currentUserMessageRef = useRef<string>("");
  const activeMessageIdRef = useRef<number | null>(null);
  const responseContentRef = useRef<string>("");

  const {
    fetchInitialData,
    error,
    selectedConversation,
    addMessageToConversation,
    createNewConversation,
    updateMessageContent,
    updateMessageWithThinking,
  } = useConversationStore();

  // Determine use case from location
  const getUseCaseFromPath = (): UseCase => {
    if (location.pathname.startsWith("/chat/movies")) return "movies";
    if (location.pathname.startsWith("/chat/reviews")) return "reviews";
    if (location.pathname.startsWith("/chat/lightrag")) return "lightrag";
    return "movies"; // default
  };

  useEffect(() => {
    const useCase = getUseCaseFromPath();
    
    // Only connect if we're in a use case route (not on landing page)
    if (useCase && location.pathname.startsWith("/chat/")) {
      const initializeUseCase = async () => {
        await fetchInitialData(useCase);
        const wsUrl = getWebSocketUrl(useCase);
        const connected = await wsService.connect(wsUrl);
        setIsConnected(connected);
      };

      initializeUseCase();

      // Cleanup on unmount or route change
      return () => {
        wsService.disconnect();
      };
    } else {
      // Disconnect if we're not in a use case route
      wsService.disconnect();
      setIsConnected(false);
    }
  }, [fetchInitialData, location.pathname]);

  useEffect(() => {
    const eventHandlers: Record<WSEventType, (data: any) => void> = {
      connected: () => {
        setIsConnected(true);
      },
      disconnected: () => {
        setIsConnected(false);
      },
      thinking_start: () => {
        setIsThinking(true);
        setCurrentThinking("");
        setThinkingStartTime(Date.now());
        setFinalThinking(null);
        responseContentRef.current = "";
      },
      thinking_chunk: (content) => {
        if (content) {
          setCurrentThinking((prev) => prev + content);
        }
      },
      thinking_end: () => {
        setIsThinking(false);
        setThinkingEndTime(Date.now());
        setFinalThinking(currentThinking);
        if (selectedConversation && currentThinking) {
          const messageId = generateTempId();
          activeMessageIdRef.current = messageId;

          const thinkingTimeInSeconds = thinkingStartTime
            ? (Date.now() - thinkingStartTime) / 1000
            : null;

          const initialMessage: MessageType = {
            ID: messageId,
            ConversationID: selectedConversation.ID,
            Role: "assistant",
            Content: "", // Empty content initially - will be filled by response chunks
            RawContent: "",
            Thinking: currentThinking,
            ThinkingTime: thinkingTimeInSeconds,
            CreatedAt: new Date().toISOString(),
          };

          addMessageToConversation(selectedConversation.ID, initialMessage);
        }
      },
      conversation_started: (conversationId) => {
        if (conversationId) {
          const parsedConversationId = Number(conversationId);
          if (!Number.isInteger(parsedConversationId)) {
            console.warn(
              "Invalid conversation ID received for conversation_started:",
              conversationId
            );
            return;
          }

          const userMessage: MessageType = {
            ID: generateTempId(),
            ConversationID: parsedConversationId,
            Role: "user",
            Content: currentUserMessageRef.current,
            RawContent: currentUserMessageRef.current,
            Thinking: null,
            ThinkingTime: null,
            CreatedAt: new Date().toISOString(),
          };

          createNewConversation(
            parsedConversationId,
            userMessage
          );

          currentUserMessageRef.current = "";

          const useCase = getUseCaseFromPath();
          navigate(getChatPath(useCase, parsedConversationId));
        }
      },
      conversation_resumed: (conversationId) => {
        const parsedConversationId = Number(conversationId);
        if (Number.isInteger(parsedConversationId)) {
          console.log(
            `Successfully resumed conversation: ${parsedConversationId}`
          );
        } else {
          console.warn(
            "Received conversation_resumed event without conversation ID"
          );
        }
      },
      response_chunk: (content) => {
        setIsThinking(false);
        responseContentRef.current += content ?? "";
        setCurrentResponse(responseContentRef.current);

        if (selectedConversation) {
          if (!activeMessageIdRef.current) {
            const messageId = generateTempId();
            activeMessageIdRef.current = messageId;
            const assistantMessage: MessageType = {
              ID: messageId,
              ConversationID: selectedConversation.ID,
              Role: "assistant",
              Content: responseContentRef.current,
              RawContent: responseContentRef.current,
              Thinking: currentThinking,
              ThinkingTime: thinkingStartTime
                ? (Date.now() - thinkingStartTime) / 1000
                : null,
              CreatedAt: new Date().toISOString(),
            };
            addMessageToConversation(selectedConversation.ID, assistantMessage);
          } else {
            updateMessageContent(
              selectedConversation.ID,
              activeMessageIdRef.current,
              responseContentRef.current
            );
          }
        }
      },

      response_done: () => {
        if (currentResponse && selectedConversation) {
          const thinkingTimeInSeconds =
            thinkingStartTime && thinkingEndTime
              ? (thinkingEndTime - thinkingStartTime) / 1000
              : null;

          console.log(`Thinking time: ${thinkingTimeInSeconds}s`);

          // If we already created a streaming message, just update it with final content
          if (activeMessageIdRef.current) {
            // Update the message with final content and thinking
            updateMessageWithThinking(
              selectedConversation.ID,
              activeMessageIdRef.current,
              currentResponse,
              finalThinking || currentThinking || null,
              thinkingTimeInSeconds
            );

            // Reset active message ID
            activeMessageIdRef.current = null;
          } else {
            // Create new message if we didn't stream (fallback)
            const assistantMessage: MessageType = {
              ID: generateTempId(),
              ConversationID: selectedConversation.ID,
              Role: "assistant",
              Content: currentResponse,
              RawContent: currentResponse,
              Thinking: finalThinking || currentThinking || null,
              ThinkingTime: thinkingTimeInSeconds,
              CreatedAt: new Date().toISOString(),
            };

            addMessageToConversation(selectedConversation.ID, assistantMessage);
          }

        }

        // Reset state
        setCurrentResponse("");
        responseContentRef.current = "";
        activeMessageIdRef.current = null;
        setThinkingStartTime(null);
        setThinkingEndTime(null);
      },
      error: (errorMsg) => {
        console.error(`Error: ${errorMsg}`);
        setIsThinking(false);
        responseContentRef.current = "";
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
    currentResponse,
    addMessageToConversation,
    createNewConversation,
    isThinking,
    navigate,
  ]);

  const sendMessage = useCallback(
    async (message: string) => {
      if (!selectedConversation) {
        console.error("No active conversation");
        return;
      }

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
      responseContentRef.current = "";

      const success = await wsService.sendMessage(
        selectedConversation.ID,
        message,
      );

      if (!success) {
        console.error("Failed to send message");
        setIsThinking(false);
      }
    },
    [selectedConversation, addMessageToConversation]
  );

  const startConversation = useCallback(
    async (message: string) => {
      currentUserMessageRef.current = message;
      setIsThinking(true);
      responseContentRef.current = "";

      const success = await wsService.startConversation(message);

      if (!success) {
        console.error("Failed to start conversation");
        setIsThinking(false);
      }
    },
    []
  );

  const resumeConversation = useCallback(async (conversationId: number) => {
    console.log(`Resuming conversation: ${conversationId}`);
    const success = await wsService.resumeConversation(conversationId);

    if (!success) {
      console.error("Failed to resume conversation");
    }
  }, []);

  const clearThinkingState = useCallback(() => {
    setCurrentThinking("");
    setFinalThinking(null);
    setThinkingStartTime(null);
    setThinkingEndTime(null);
  }, []);

  const contextValue: WebSocketContextType = {
    isConnected,
    isThinking,
    currentThinking,
    finalThinking,
    sendMessage,
    startConversation,
    resumeConversation,
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
