const JOURNALS = [
  "APA 7th Edition",
  "IEEE",
  "Springer",
  "Vancouver",
  "Chicago",
];

export default function JournalSelector({ value, onChange, disabled }) {
  return (
    <div className="space-y-2">
      <label className="block text-sm font-medium text-gray-300">
        Target Journal Style
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
      >
        <option value="">Select a style...</option>
        {JOURNALS.map((j) => (
          <option key={j} value={j}>
            {j}
          </option>
        ))}
      </select>
    </div>
  );
}
