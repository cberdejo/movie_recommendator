import { Trash2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { ConversationType } from "../../lib/types.ts";
import { getRelativeTime } from "../../lib/utils.ts";
import { UseCase, getChatPath } from "../../lib/config.ts";

type ConversationItemProps = {
  conversation: Pick<ConversationType, "ID" | "Title" |   "UpdatedAt">;
  onDelete: (id: number) => void;
  selectedConversationID: number;
  useCase?: UseCase;
  onSelect?: () => void; // Added callback for when conversation is selected
};

const ConversationItem = ({
  conversation,
  onDelete,
  selectedConversationID,
  useCase = "movies",
  onSelect
}: ConversationItemProps) => {
  const navigate = useNavigate();

  return (
    <div
      onClick={() => {
        navigate(getChatPath(useCase, conversation.ID));
        // If onSelect is provided, call it (used to close sidebar on mobile)
        if (onSelect) {
          onSelect();
        }
      }}
      className={`p-3 mx-2 mb-2 rounded-xl hover:bg-gray-800 cursor-pointer transition-colors duration-200 ${
        selectedConversationID === conversation.ID
          ? " bg-gray-800"
          : " bg-gray-900"
      }`}
    >
      <div className="flex justify-between items-start gap-2">
        <div className="flex-1 min-w-0">
          <h3 className="font-medium text-sm text-gray-200 truncate">
            {conversation.Title}
          </h3>
          <p className="text-gray-500 text-xs">
            {getRelativeTime(conversation.UpdatedAt)}
          </p>
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete(conversation.ID);
          }}
          className="p-1.5 hover:bg-gray-700 rounded-lg transition-colors duration-200"
          aria-label="Delete conversation"
        >
          <Trash2 className="w-4 h-4 text-gray-400" />
        </button>
      </div>
    </div>
  );
};

export default ConversationItem;
