import React, { useRef, KeyboardEvent, ChangeEvent } from "react";
import TextareaAutosize from "react-textarea-autosize";
import { Send } from "lucide-react";
import { useWebSocket } from "../../providers/WebSocketProvider";

interface ChatInputProps {
  conversationId?: number;
}

const ChatInput = ({ conversationId }: ChatInputProps) => {
  const [input, setInput] = React.useState("");
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { isConnected, isThinking, sendMessage, startConversation } =
    useWebSocket();

  const handleSubmit = async () => {
    if (!input.trim() || isSubmitting || !isConnected || isThinking) return;

    setIsSubmitting(true);

    try {
      if (conversationId) {
        await sendMessage(input);
      } else {
        await startConversation(input);
      }
      setInput("");
    } catch (error) {
      console.error("Failed to send message:", error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
  };

  const isDisabled =
    !isConnected || isSubmitting || !input.trim() || isThinking;

  return (
    <div className="border-t border-gray-800 bg-gray-950 p-4">
      <div className="max-w-4xl mx-auto">
        <div className="relative flex flex-col gap-2">


          {/* Input area */}
          <div className="relative flex items-start">
            <TextareaAutosize
              ref={textareaRef}
              value={input}
              onChange={handleChange}
              onKeyDown={handleKeyDown}
              placeholder="Send a message..."
              className="w-full resize-none bg-gray-800 text-gray-200 rounded-lg px-4 py-3 pr-16 focus:outline-none focus:ring-1 focus:ring-purple-500 placeholder-gray-400"
              minRows={1}
              maxRows={5}
            />
            <button
              onClick={handleSubmit}
              className={`absolute right-2 bottom-2.5 p-1.5 rounded-lg transition-colors ${input.trim()
                  ? "bg-purple-600 hover:bg-purple-500 text-white"
                  : "bg-gray-700 text-gray-400 cursor-not-allowed"
                }`}
              disabled={isDisabled}
              aria-label="Enviar mensaje"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>

          <div className="text-xs text-gray-500">
            Press Shift + Enter for new line
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatInput;
