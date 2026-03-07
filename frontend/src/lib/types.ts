export type UseCase = "movies" | "reviews" | "lightrag";

export interface MessageType {
  ID: number;
  ConversationID: number;
  Role: string;
  Content: string;
  RawContent: string;
  Thinking: string | null;
  ThinkingTime: number | null;
  CreatedAt: string;
}

export interface ConversationType {
  ID: number;
  Title: string;
  CreatedAt: string;
  UpdatedAt: string;
  Messages?: MessageType[];
}

