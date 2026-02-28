import ChatInput from "./ChatInput.tsx";
import MessageComponent from "./Message.tsx";
import { useEffect, useRef, useState } from "react";
import { Menu, Pencil } from "lucide-react";

import { useNavigate } from "react-router-dom";
import { useConversationStore } from "../../store/conversationstore.ts";
import { MessageSkeleton } from "../loaders/skeleton";
import { useWebSocket } from "../../providers/WebSocketProvider.tsx";
import { UseCase } from "../../lib/config.ts";

interface ChatViewProps {
  id?: number;
  useCase?: UseCase;
  onToggleSidebar?: () => void;
  isSidebarOpen?: boolean;
}

const ChatView = ({
  id,
  useCase = "movies",
  onToggleSidebar,
}: ChatViewProps) => {
  const navigate = useNavigate();
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const resumedIdRef = useRef<number | null>(null);
  const isUserScrollingRef = useRef(false);
  const lastMessageIdRef = useRef<number | null>(null);
  
  const {
    isThinking,
    currentThinking,
    clearThinkingState,
    resumeConversation,
    isConnected,
  } = useWebSocket();

  const selectedConversation = useConversationStore((state) => state.selectedConversation);
  const setSelectedConversation = useConversationStore((state) => state.setSelectedConversation);
  const isMessagesLoading = useConversationStore((state) => state.isMessagesLoading);
  const isInitialLoading = useConversationStore((state) => state.isInitialLoading);
  const getConversation = useConversationStore((state) => state.getConversation);
  const updateConversationTitle = useConversationStore((state) => state.updateConversationTitle);

  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [editTitleValue, setEditTitleValue] = useState("");
  const titleInputRef = useRef<HTMLInputElement>(null);

  // --- NUEVOS REFS PARA SOLUCIONAR LA CONDICIÓN DE CARRERA ---
  const isThinkingRef = useRef(isThinking);
  const prevIdRef = useRef<number | undefined>(undefined);

  // Mantenemos el ref sincronizado con el estado real de isThinking
  useEffect(() => {
    isThinkingRef.current = isThinking;
  }, [isThinking]);
  // -----------------------------------------------------------

  useEffect(() => {
    if (isEditingTitle) {
      setEditTitleValue(selectedConversation?.Title ?? "");
      titleInputRef.current?.focus();
    }
  }, [isEditingTitle, selectedConversation?.Title]);

  const handleSaveTitle = async () => {
    if (!id || !editTitleValue.trim()) {
      setIsEditingTitle(false);
      return;
    }
    try {
      await updateConversationTitle(id, editTitleValue.trim());
    } finally {
      setIsEditingTitle(false);
    }
  };

  // Detect when user manually scrolls
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    let userScrollTimeout: NodeJS.Timeout;

    const handleScrollStart = () => {
      isUserScrollingRef.current = true;
      if (userScrollTimeout) clearTimeout(userScrollTimeout);
    };

    const handleScrollEnd = () => {
      userScrollTimeout = setTimeout(() => {
        isUserScrollingRef.current = false;
      }, 1000);
    };

    container.addEventListener('mousedown', handleScrollStart);
    container.addEventListener('touchstart', handleScrollStart);
    container.addEventListener('mouseup', handleScrollEnd);
    container.addEventListener('touchend', handleScrollEnd);

    return () => {
      container.removeEventListener('mousedown', handleScrollStart);
      container.removeEventListener('touchstart', handleScrollStart);
      container.removeEventListener('mouseup', handleScrollEnd);
      container.removeEventListener('touchend', handleScrollEnd);
      if (userScrollTimeout) clearTimeout(userScrollTimeout);
    };
  }, []);

  // Auto-scroll logic
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    const messages = selectedConversation?.Messages || [];
    const lastMessage = messages[messages.length - 1];
    const lastMessageId = lastMessage?.ID || null;

    const isNewMessage = lastMessageId !== lastMessageIdRef.current;
    const isNewConversation = id !== resumedIdRef.current;

    lastMessageIdRef.current = lastMessageId;

    if (!isUserScrollingRef.current || isNewMessage || isNewConversation) {
      container.scrollTo({
        top: container.scrollHeight,
        behavior: 'smooth'
      });
    }
  }, [selectedConversation?.Messages, id, isThinking, currentThinking]);

  // --- EFFECT 1 : LOAD CONVERSATION ---
  useEffect(() => {
    const loadConversation = async () => {
      if (!id) {
        setSelectedConversation(null);
        prevIdRef.current = id;
        return;
      }

      // if we are coming from the welcome screen (undefined) to the new ID just created
      const isNewChatStarting = prevIdRef.current === undefined;

      // GUARD: If we are "thinking" (the WS started the stream) and we just created the chat, 
      // BLOCK the REST request to not overwrite the Zustand store.
      if (isThinkingRef.current && isNewChatStarting) {
        console.log("Ignoring DB fetch to not overwrite the active WS stream.");
        prevIdRef.current = id;
        return;
      }

      await getConversation(id);
      prevIdRef.current = id;
    };

    loadConversation();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, getConversation, navigate, setSelectedConversation]);

  // --- EFFECT 2 : CLEAR THINKING ---
  useEffect(() => {
    // Reset any thinking UI when conversation changes, 
    // BUT only if we are not in full streaming of the new chat.
    if (clearThinkingState && !isThinkingRef.current) {
      clearThinkingState();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, clearThinkingState]);

  // Try Resume Conversation
  useEffect(() => {
    const tryResumeConversation = async () => {
      if (
        id &&
        isConnected &&
        resumedIdRef.current !== id &&
        selectedConversation
      ) {
        resumedIdRef.current = id;
        try {
          await resumeConversation(id);
        } catch (error) {
          console.error("Failed to resume conversation:", error);
        }
      }
    };

    tryResumeConversation();
  }, [id, isConnected, selectedConversation, resumeConversation]);


  return (
    <div className="h-full flex flex-col">
      {/* Header with centered title for better mobile experience */}
      <div className="p-4 md:pl-10 border-b border-gray-800 flex items-center justify-center relative">
        {/* Mobile sidebar toggle */}
        <button
          type="button"
          className="absolute left-4 md:hidden p-2 rounded hover:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-purple-500"
          onClick={onToggleSidebar}
          aria-label="Open or close the conversation sidebar"
        >
          <Menu className="w-5 h-5 text-gray-200" />
        </button>

        {isInitialLoading && (
          <div className="absolute top-0 left-0 right-0">
            <div className="h-1 bg-purple-500/20">
              <div className="h-1 bg-purple-600 animate-progress"></div>
            </div>
          </div>
        )}

        <div className="flex-1 flex items-center justify-center min-w-0">
          {id && selectedConversation && isEditingTitle ? (
            <input
              ref={titleInputRef}
              type="text"
              value={editTitleValue}
              onChange={(e) => setEditTitleValue(e.target.value)}
              onBlur={handleSaveTitle}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSaveTitle();
                if (e.key === "Escape") {
                  setEditTitleValue(selectedConversation?.Title ?? "");
                  setIsEditingTitle(false);
                }
              }}
              className="w-full max-w-md px-2 py-1 text-xl font-semibold text-gray-200 bg-gray-800 border border-gray-600 rounded focus:outline-none focus:ring-2 focus:ring-purple-500"
              aria-label="Conversation name"
            />
          ) : (
            <button
              type="button"
              onClick={() => id && selectedConversation && setIsEditingTitle(true)}
              className="group flex items-center justify-center gap-2 text-xl font-semibold text-gray-200 text-center hover:text-purple-400 focus:outline-none focus:ring-2 focus:ring-purple-500 rounded px-2"
              aria-label="Change conversation name"
            >
              {id
                ? selectedConversation?.Title || "Chat"
                : useCase === "movies"
                  ? "Movie Recommendations"
                  : useCase === "reviews"
                    ? "Review Analysis"
                    : "LightRAG Chat"}
              {id && selectedConversation && (
                <Pencil className="w-4 h-4 opacity-0 group-hover:opacity-70 transition-opacity" />
              )}
            </button>
          )}
        </div>

        {/* Connection status indicator */}
        <div className="absolute right-4 flex items-center gap-2">
          <span
            className={`h-2 w-2 rounded-full ${isConnected ? "bg-green-500" : "bg-red-500"}`}
            aria-label={isConnected ? "Connected to server" : "Disconnected from server"}
          />
          <span className="hidden sm:inline text-xs text-gray-500">
            {isConnected ? "Connected" : "Disconnected"}
          </span>
        </div>
      </div>

      {/* Messages or Welcome Screen */}
      <div
        className="flex-1 overflow-y-auto"
        ref={messagesContainerRef}
        onScroll={() => {
          isUserScrollingRef.current = true;
        }}
      >
        {id ? (
          isInitialLoading ? (
            <>
              <MessageSkeleton />
              <MessageSkeleton />
              <MessageSkeleton />
            </>
          ) : isMessagesLoading ? (
            null
          ) : (
            <>
              {selectedConversation?.Messages?.map((message) => (
                <MessageComponent key={message.ID} message={message} />
              ))}

              {/* Show thinking section */}
              {isThinking && (
                <div className="py-4 bg-gray-900/50">
                  <div className="max-w-4xl mx-auto px-4">
                    <div className="mb-1 text-xs font-medium text-gray-500">
                      Assistant
                    </div>
                    <div className="text-gray-300">
                      {currentThinking ? (
                        <div className="text-gray-400 text-sm">
                          <div className="mb-2 flex items-center gap-2">
                            <div className="flex gap-1">
                              <div className="w-2 h-2 bg-purple-500 rounded-full animate-pulse"></div>
                              <div
                                className="w-2 h-2 bg-purple-500 rounded-full animate-pulse"
                                style={{ animationDelay: "300ms" }}
                              ></div>
                              <div
                                className="w-2 h-2 bg-purple-500 rounded-full animate-pulse"
                                style={{ animationDelay: "600ms" }}
                              ></div>
                            </div>
                            <span className="text-xs font-medium text-purple-400">
                              Thinking...
                            </span>
                          </div>
                          <div className="pl-5 py-2 border-l-2 border-purple-800/30 text-sm text-gray-400 bg-purple-900/10 rounded-r-md">
                            {currentThinking}
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2">
                          <div className="flex gap-1">
                            <div
                              className="w-2 h-2 bg-purple-500 rounded-full animate-bounce"
                              style={{ animationDelay: "0ms" }}
                            ></div>
                            <div
                              className="w-2 h-2 bg-purple-500 rounded-full animate-bounce"
                              style={{ animationDelay: "300ms" }}
                            ></div>
                            <div
                              className="w-2 h-2 bg-purple-500 rounded-full animate-bounce"
                              style={{ animationDelay: "600ms" }}
                            ></div>
                          </div>
                          <span className="text-sm text-gray-400">
                            Thinking...
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </>
          )
        ) : (
          <div className="h-full flex flex-col items-center justify-center px-4 text-center">
            <div className="mb-8 text-5xl">
              {useCase === "movies" ? "🎬" : useCase === "reviews" ? "💬" : "✨"}
            </div>
            <h1 className="text-3xl font-bold text-gray-200 mb-4">
              {useCase === "movies"
                ? "Movie Recommendations"
                : useCase === "reviews"
                  ? "Review Analysis"
                  : "LightRAG Chat"}
            </h1>
            <p className="text-gray-400 max-w-md mb-8">
              {useCase === "movies"
                ? "Ask for movie recommendations! The system uses semantic search with cosine distance to find relevant matches."
                : useCase === "reviews"
                  ? "Paste a customer review to analyze sentiment, extract key points, and generate a response."
                  : "This use case is currently under development."}
            </p>
            <div className="flex flex-col items-center">
              <p className="text-gray-500 text-sm mb-2">Features:</p>
              <ul className="text-gray-400 text-sm text-left">
                <li className="flex items-center mb-1">
                  <span className={`mr-2 ${useCase === "movies" ? "text-purple-500" : useCase === "reviews" ? "text-blue-500" : "text-green-500"}`}>•</span> Real-time streaming responses
                </li>
                <li className="flex items-center mb-1">
                  <span className={`mr-2 ${useCase === "movies" ? "text-purple-500" : useCase === "reviews" ? "text-blue-500" : "text-green-500"}`}>•</span> View AI thinking process
                </li>
                <li className="flex items-center mb-1">
                  <span className={`mr-2 ${useCase === "movies" ? "text-purple-500" : useCase === "reviews" ? "text-blue-500" : "text-green-500"}`}>•</span> Chat history and conversation management
                </li>
              </ul>
            </div>
          </div>
        )}
      </div>

      <ChatInput conversationId={id} />
    </div>
  );
};

export default ChatView;