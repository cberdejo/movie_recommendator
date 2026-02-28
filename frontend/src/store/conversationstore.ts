import { create } from "zustand";
import { ConversationType, MessageType } from "../lib/types";
import { apiFetch, SERVER_ENDPOINTS } from "../lib/api";

interface ConversationStore {
  // State
  conversations: ConversationType[];
  selectedConversation: ConversationType | null;
  messages: Record<number, MessageType[]>;
  isInitialLoading: boolean;
  isMessagesLoading: boolean;
  error: string | null;

  // Actions
  fetchInitialData: (useCase?: string) => Promise<void>;
  getConversation: (id: number) => Promise<void>;
  addMessageToConversation: (
    conversationId: number,
    message: MessageType
  ) => void;
  createNewConversation: (
    conversationId: number,
    firstMessage: MessageType
  ) => void;
  updateConversationTitle: (conversationId: number, title: string) => Promise<void>;
  updateMessageContent: (
    conversationId: number,
    messageId: number,
    content: string
  ) => void;
  updateMessageWithThinking: (
    conversationId: number,
    messageId: number,
    content: string,
    thinking: string | null,
    thinkingTime: number | null
  ) => void;
  setSelectedConversation: (conversation: ConversationType | null) => void;
  deleteConversation: (id: number) => Promise<void>;
}

export const useConversationStore = create<ConversationStore>((set, get) => ({
  conversations: [],
  selectedConversation: null,
  messages: {} as Record<number, MessageType[]>,
  isInitialLoading: false,
  isMessagesLoading: false,
  error: null,

  fetchInitialData: async (useCase?: string) => {
    if (get().isInitialLoading) return;
    set({ isInitialLoading: true, error: null });
    try {
      console.log("Initial data fetching", useCase);
      const url = useCase 
        ? `${SERVER_ENDPOINTS.conversations}?use_case=${useCase}`
        : SERVER_ENDPOINTS.conversations;
      const data = await apiFetch<unknown>(url);
      const list = Array.isArray(data)
        ? data
        : (data && typeof data === "object" && "conversations" in data
            ? (data as { conversations: ConversationType[] }).conversations
            : []);

      set({
        conversations: Array.isArray(list) ? list : [],
        isInitialLoading: false,
      });
    } catch (error) {
      set({
        error:
          error instanceof Error
            ? error.message
            : "Failed to fetch initial data",
        isInitialLoading: false,
      });
    }
  },

  getConversation: async (id: number) => {
    set({ isMessagesLoading: true, error: null });
    console.log("GOT ID in STORE", id);

    try {
      const existingConversation = get().conversations.find(
        (conv) => conv.ID === id
      );

      if (existingConversation) {
        if (get().messages[id]) {
          set({
            selectedConversation: {
              ...existingConversation,
              Messages: get().messages[id],
            },
            isMessagesLoading: false,
          });
          return;
        }
      }

      const conversationWithMessages: ConversationType = await apiFetch(
        `${SERVER_ENDPOINTS.conversations}/${id}`
      );

      set((state) => ({
        selectedConversation: conversationWithMessages,
        messages: {
          ...state.messages,
          [id]: conversationWithMessages.Messages || [],
        },
        isMessagesLoading: false,
      }));
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Failed to fetch conversation";
      const isNotFoundError = errorMessage.includes("not found");

      set({
        isMessagesLoading: false,
        selectedConversation: null,
        error: isNotFoundError ? null : errorMessage,
      });

      throw error;
    }
  },

  addMessageToConversation: (conversationId: number, message: MessageType) => {
    set((state) => {
      const existingConversation = state.conversations.find(
        (conv) => conv.ID === conversationId
      );

      if (!existingConversation) {
        console.error(`Conversation ${conversationId} not found`);
        return state;
      }

      const updateSelectedConversation =
        state.selectedConversation?.ID === conversationId
          ? {
              ...state.selectedConversation,
              Messages: [
                ...(state.selectedConversation.Messages || []),
                message,
              ],
            }
          : state.selectedConversation;

      const existingMessages = state.messages[conversationId] || [];
      const updatedMessages = {
        ...state.messages,
        [conversationId]: [...existingMessages, message],
      };

      const updatedConversations = state.conversations.map((conv) =>
        conv.ID === conversationId
          ? { ...conv, UpdatedAt: message.CreatedAt }
          : conv
      );

      return {
        messages: updatedMessages,
        selectedConversation: updateSelectedConversation,
        conversations: updatedConversations,
      };
    });
  },

  createNewConversation: (
    conversationId: number,
    firstMessage: MessageType
  ) => {
    set((state) => {
      const defaultTitle =
        firstMessage.Content.slice(0, 30) +
        (firstMessage.Content.length > 30 ? "..." : "");

      const newConversation: ConversationType = {
        ID: conversationId,
        Title: defaultTitle,
        CreatedAt: firstMessage.CreatedAt,
        UpdatedAt: firstMessage.CreatedAt,
        Messages: [firstMessage],
      };

      const updatesConversations = [newConversation, ...state.conversations];

      return {
        conversations: updatesConversations,
        selectedConversation: newConversation,
        messages: {
          ...state.messages,
          [conversationId]: [firstMessage],
        },
      };
    });
  },

  updateConversationTitle: async (conversationId: number, title: string) => {
    const trimmed = title.trim();
    if (!trimmed) return;
    await apiFetch(
      `${SERVER_ENDPOINTS.conversations}/${conversationId}`,
      {
        method: "PATCH",
        body: JSON.stringify({ title: trimmed }),
      }
    );
    set((state) => {
      const updatedConversations = state.conversations.map((conv) =>
        conv.ID === conversationId ? { ...conv, Title: trimmed } : conv
      );
      const updateSelectedConversation =
        state.selectedConversation?.ID === conversationId
          ? { ...state.selectedConversation, Title: trimmed }
          : state.selectedConversation;
      return {
        conversations: updatedConversations,
        selectedConversation: updateSelectedConversation,
      };
    });
  },

  updateMessageContent: (
    conversationId: number,
    messageId: number,
    content: string
  ) => {
    set((state) => {
      // If conversation isn't selected or doesn't match, do nothing
      if (state.selectedConversation?.ID !== conversationId) {
        return state;
      }

      // Update message in selected conversation
      const updatedMessages =
        state.selectedConversation.Messages?.map((msg) =>
          msg.ID === messageId
            ? { ...msg, Content: content, RawContent: content }
            : msg
        ) || [];

      // Update in messages cache
      const cachedMessages = state.messages[conversationId] || [];
      const updatedCachedMessages = cachedMessages.map((msg) =>
        msg.ID === messageId
          ? { ...msg, Content: content, RawContent: content }
          : msg
      );

      return {
        selectedConversation: {
          ...state.selectedConversation,
          Messages: updatedMessages,
          UpdatedAt: new Date().toISOString(),
        },
        messages: {
          ...state.messages,
          [conversationId]: updatedCachedMessages,
        },
        // Update the conversation in the list for timestamp
        conversations: state.conversations.map((conv) =>
          conv.ID === conversationId
            ? { ...conv, UpdatedAt: new Date().toISOString() }
            : conv
        ),
      };
    });
  },

  // Update a message with final content and thinking information
  updateMessageWithThinking: (
    conversationId: number,
    messageId: number,
    content: string,
    thinking: string | null,
    thinkingTime: number | null
  ) => {
    set((state) => {
      // If conversation isn't selected or doesn't match, do nothing
      if (state.selectedConversation?.ID !== conversationId) {
        return state;
      }

      // Update message in selected conversation
      const updatedMessages =
        state.selectedConversation.Messages?.map((msg) =>
          msg.ID === messageId
            ? {
                ...msg,
                Content: content,
                RawContent: content,
                Thinking: thinking || null,
                ThinkingTime: thinkingTime,
              }
            : msg
        ) || [];

      // Update in messages cache
      const cachedMessages = state.messages[conversationId] || [];
      const updatedCachedMessages = cachedMessages.map((msg) =>
        msg.ID === messageId
          ? {
              ...msg,
              Content: content,
              RawContent: content,
              Thinking: thinking || null,
              ThinkingTime: thinkingTime,
            }
          : msg
      );

      return {
        selectedConversation: {
          ...state.selectedConversation,
          Messages: updatedMessages,
          UpdatedAt: new Date().toISOString(),
        },
        messages: {
          ...state.messages,
          [conversationId]: updatedCachedMessages,
        },
        // Update the conversation in the list for timestamp
        conversations: state.conversations.map((conv) =>
          conv.ID === conversationId
            ? { ...conv, UpdatedAt: new Date().toISOString() }
            : conv
        ),
      };
    });
  },
  deleteConversation: async (id: number) => {
    set({ error: null });

    try {
      await apiFetch(`${SERVER_ENDPOINTS.conversations}/${id}`, {
        method: "DELETE",
      });

      set((state) => ({
        conversations: state.conversations.filter((conv) => conv.ID !== id),
        messages: Object.fromEntries(
          Object.entries(state.messages).filter(
            ([key]) => Number(key) !== id
          )
        ) as Record<number, MessageType[]>,

        selectedConversation:
          state.selectedConversation?.ID === id
            ? null
            : state.selectedConversation,
      }));
    } catch (error) {
      set({
        error:
          error instanceof Error
            ? error.message
            : "Failed to delete conversation",
      });
      throw error;
    }
  },

  setSelectedConversation: (conversation) => {
    set({ selectedConversation: conversation });
  },


}));
