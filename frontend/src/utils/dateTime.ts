const BEIJING_TIME_ZONE = 'Asia/Shanghai';

type DateInput = Date | string | number | null | undefined;

const formatterDateTime = new Intl.DateTimeFormat('zh-CN', {
  timeZone: BEIJING_TIME_ZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});

const formatterTime = new Intl.DateTimeFormat('zh-CN', {
  timeZone: BEIJING_TIME_ZONE,
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});

const parseInput = (input: DateInput): Date | null => {
  if (input === null || input === undefined || input === '') {
    return null;
  }
  if (input instanceof Date) {
    return Number.isNaN(input.getTime()) ? null : input;
  }

  let normalized: string | number = input;
  if (typeof input === 'string') {
    const raw = input.trim();
    // Back-end frequently emits naive UTC timestamps (without trailing Z).
    // For consistent display, treat naive timestamps as UTC first.
    const hasTimezone = /[zZ]|[+-]\d{2}:\d{2}$/.test(raw);
    if (!hasTimezone && /^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(\.\d+)?$/.test(raw)) {
      normalized = `${raw.replace(' ', 'T')}Z`;
    } else {
      normalized = raw;
    }
  }

  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date;
};

const formatByParts = (date: Date, formatter: Intl.DateTimeFormat): string => {
  const parts = formatter.formatToParts(date);
  const map: Record<string, string> = {};
  parts.forEach((part) => {
    if (part.type !== 'literal') {
      map[part.type] = part.value;
    }
  });
  return `${map.year}-${map.month}-${map.day} ${map.hour}:${map.minute}:${map.second}`;
};

export const formatBeijingDateTime = (input: DateInput, fallback = '--'): string => {
  const date = parseInput(input);
  if (!date) return fallback;
  return `${formatByParts(date, formatterDateTime)} (北京时间)`;
};

export const formatBeijingTime = (input: DateInput, fallback = '--'): string => {
  const date = parseInput(input);
  if (!date) return fallback;
  const parts = formatterTime.formatToParts(date);
  const map: Record<string, string> = {};
  parts.forEach((part) => {
    if (part.type !== 'literal') {
      map[part.type] = part.value;
    }
  });
  return `${map.hour}:${map.minute}:${map.second}`;
};
