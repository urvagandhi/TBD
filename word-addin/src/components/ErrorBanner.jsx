export default function ErrorBanner({ message, onRetry }) {
  if (!message) return null;

  return (
    <div className="rounded-lg border border-red-800 bg-red-950/50 p-3">
      <p className="text-sm text-red-300">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-2 text-xs font-medium text-red-400 underline hover:text-red-300"
        >
          Try Again
        </button>
      )}
    </div>
  );
}
