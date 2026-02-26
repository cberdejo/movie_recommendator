export const MessageSkeleton = () => {
  return (
    <div className="py-4 animate-pulse">
      <div className="max-w-4xl mx-auto px-4">
        {/* Role indicator */}
        <div className="w-16 h-4 bg-gray-800 rounded mb-2"></div>

        {/* Message content */}
        <div className="space-y-3">
          <div className="h-4 bg-gray-800 rounded w-3/4"></div>
          <div className="h-4 bg-gray-800 rounded w-1/2"></div>
        </div>
      </div>
    </div>
  );
};

export const ConversationSkeleton = () => {
  return (
    <div className="p-3 mx-2 mb-2 rounded-xl bg-gray-900 animate-pulse">
      <div className="flex justify-between items-start gap-2">
        <div className="flex-1 min-w-0 space-y-2">
          {/* Title Skeleton */}
          <div className="h-4 bg-gray-800 rounded w-3/4"></div>

          {/* Model Skeleton */}
          <div className="h-3 bg-gray-800 rounded w-1/2"></div>

          {/* Time Skeleton */}
          <div className="h-3 bg-gray-800 rounded w-1/4"></div>
        </div>

        {/* Delete Button Skeleton */}
        <div className="p-1.5 rounded-lg bg-gray-800">
          <div className="w-4 h-4 bg-gray-700 rounded-sm"></div>
        </div>
      </div>
    </div>
  );
};
