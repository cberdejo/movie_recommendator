import ChatInput from "./ChatInput.tsx";
import MessageComponent from "./Message.tsx";
import { useEffect, useRef } from "react";
import { Menu } from "lucide-react";

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

 
  const selectedConversation = useConversationStore(
    (state) => state.selectedConversation
  );

  const setSelectedConversation = useConversationStore(
    (state) => state.setSelectedConversation
  );

  const isMessagesLoading = useConversationStore(
    (state) => state.isMessagesLoading
  );
  const isInitialLoading = useConversationStore(
    (state) => state.isInitialLoading
  );
  const getConversation = useConversationStore(
    (state) => state.getConversation
  );

  // Detect when user manually scrolls and prevent auto-scroll while they're interacting
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    let userScrollTimeout: NodeJS.Timeout;

    const handleScrollStart = () => {
      isUserScrollingRef.current = true;
      
      // Clear any existing timeout
      if (userScrollTimeout) {
        clearTimeout(userScrollTimeout);
      }
    };

    const handleScrollEnd = () => {
      // Set a timeout before clearing the user scrolling flag
      // This prevents auto-scroll from kicking in too soon
      userScrollTimeout = setTimeout(() => {
        isUserScrollingRef.current = false;
      }, 1000); // Wait 1 second after scrolling stops
    };

    // Use both mousedown and touchstart to detect when user begins scrolling
    container.addEventListener('mousedown', handleScrollStart);
    container.addEventListener('touchstart', handleScrollStart);
    
    // Use both mouseup and touchend to detect when user stops scrolling
    container.addEventListener('mouseup', handleScrollEnd);
    container.addEventListener('touchend', handleScrollEnd);

    return () => {
      container.removeEventListener('mousedown', handleScrollStart);
      container.removeEventListener('touchstart', handleScrollStart);
      container.removeEventListener('mouseup', handleScrollEnd);
      container.removeEventListener('touchend', handleScrollEnd);
      
      if (userScrollTimeout) {
        clearTimeout(userScrollTimeout);
      }
    };
  }, []);

  // Auto-scroll logic
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    // Get the ID of the last message (if any)
    const messages = selectedConversation?.Messages || [];
    const lastMessage = messages[messages.length - 1];
    const lastMessageId = lastMessage?.ID || null;
    
    // Determine if this is a new message or a different conversation
    const isNewMessage = lastMessageId !== lastMessageIdRef.current;
    const isNewConversation = id !== resumedIdRef.current;
    
    // Update the ref for next comparison
    lastMessageIdRef.current = lastMessageId;
    
    // Only auto-scroll if:
    // 1. User is not actively scrolling OR
    // 2. This is a completely new message OR
    // 3. We switched conversations
    if (!isUserScrollingRef.current || isNewMessage || isNewConversation) {
      // Use smooth scrolling for better user experience
      container.scrollTo({
        top: container.scrollHeight,
        behavior: 'smooth'
      });
    }
  }, [selectedConversation?.Messages, id, isThinking, currentThinking]);

  useEffect(() => {
    const loadConversation = async () => {
      if (!id) {
        setSelectedConversation(null);
        return;
      }

      await getConversation(id);
    };

    loadConversation();
  }, [id, getConversation, navigate, setSelectedConversation]);

  useEffect(() => {
    // Reset any thinking UI when conversation changes
    if (clearThinkingState) {
      clearThinkingState();
    }
  }, [id, clearThinkingState]);

  useEffect(() => {
    const tryResumeConversation = async () => {
      // Only try to resume if:
      // 1. We have an ID
      // 2. We're connected
      // 3. We haven't already resumed this exact ID
      // 4. We have a selected conversation loaded
      if (
        id &&
        isConnected &&
        resumedIdRef.current !== id &&
        selectedConversation
      ) {
        console.log(`Attempting to resume conversation: ${id}`);

        // Update the ref before the async call to prevent duplicates
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
      <div className="p-4 md:pl-14 border-b border-gray-800 flex items-center justify-center relative">
        {/* Mobile sidebar toggle */}
        <button
          type="button"
          className="absolute left-4 md:hidden p-2 rounded hover:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-purple-500"
          onClick={onToggleSidebar}
          aria-label="Abrir o cerrar la barra lateral de conversaciones"
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

        <h1 className="text-xl font-semibold text-gray-200 text-center">
          {id
            ? selectedConversation?.Title || "Chat"
            : useCase === "movies"
            ? "Movie Recommendations"
            : useCase === "reviews"
            ? "Review Analysis"
            : "LightRAG Chat"}
        </h1>

        {/* Connection status indicator */}
        <div className="absolute right-4 flex items-center gap-2">
          <span
            className={`h-2 w-2 rounded-full ${
              isConnected ? "bg-green-500" : "bg-red-500"
            }`}
            aria-label={isConnected ? "Conectado al servidor" : "Desconectado del servidor"}
          />
          <span className="hidden sm:inline text-xs text-gray-500">
            {isConnected ? "Connected" : "Disconnected"}
          </span>
        </div>
      </div>
      
      {/* Model Selector */}
      {/* {!id && (
        <div className="px-4 pt-4 pb-2 w-full flex justify-center border-b border-gray-800">
          <div className="w-full max-w-sm">
            <ModelSelector
              selectedModel={selectedModel || defaultModel}
              onModelSelect={(model) => {
                setSelectedModel(model);
              }}
            />
          </div>
        </div>
      )} */}

      {/* Messages or Welcome Screen */}
      <div 
        className="flex-1 overflow-y-auto" 
        ref={messagesContainerRef}
        onScroll={() => {
          // Mark that user is scrolling when they actively scroll
          isUserScrollingRef.current = true;
        }}
      >
        {id ? (
          // Show messages if we have a conversation ID (skeleton only on initial WS/data load)
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
          // Welcome screen when no conversation is selected
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
