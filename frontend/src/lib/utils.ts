export function getRelativeTime(isoDate: string): string {
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) return "";

  const now = new Date();
  const diffInSeconds = Math.round((date.getTime() - now.getTime()) / 1000);

  const divisions: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 60 * 60 * 24 * 365],
    ["month", 60 * 60 * 24 * 30],
    ["day", 60 * 60 * 24],
    ["hour", 60 * 60],
    ["minute", 60],
    ["second", 1],
  ];

  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

  let unit: Intl.RelativeTimeFormatUnit = "second";
  let value = diffInSeconds;

  for (const [candidateUnit, secondsInUnit] of divisions) {
    if (Math.abs(diffInSeconds) >= secondsInUnit || candidateUnit === "second") {
      unit = candidateUnit;
      value = Math.round(diffInSeconds / secondsInUnit);
      break;
    }
  }

  return rtf.format(value, unit);
}

