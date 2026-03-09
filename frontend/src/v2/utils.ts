import { formatBeijingDateTime } from '@/utils/dateTime';

export const ACTIVE_STATUSES = [
  'pending',
  'running',
  'analyzing',
  'debating',
  'judging',
  'waiting',
  'retrying',
  'waiting_review',
  'waiting_resume',
];

export const TERMINAL_STATUSES = ['resolved', 'completed', 'closed', 'failed', 'cancelled'];

export const isActiveStatus = (status?: string): boolean => ACTIVE_STATUSES.includes(String(status || '').toLowerCase());

export const asRecord = (value: unknown): Record<string, unknown> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  return value as Record<string, unknown>;
};

export const asStringArray = (value: unknown): string[] => {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item || '').trim()).filter(Boolean);
};

export const parseTimestamp = (value?: string): number | null => {
  if (!value) return null;
  const ts = Date.parse(value);
  return Number.isFinite(ts) ? ts : null;
};

export const formatDuration = (start?: string, end?: string): string => {
  const startTs = parseTimestamp(start);
  const endTs = parseTimestamp(end);
  if (!startTs || !endTs || endTs <= startTs) return '--';
  const totalSeconds = Math.floor((endTs - startTs) / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}小时${minutes}分${seconds}秒`;
  if (minutes > 0) return `${minutes}分${seconds}秒`;
  return `${seconds}秒`;
};

export const formatSessionWindow = (createdAt?: string, updatedAt?: string): string => {
  const left = formatBeijingDateTime(createdAt, '--');
  const right = formatBeijingDateTime(updatedAt, '--');
  return `${left} -> ${right}`;
};

export const pickToneByStatus = (status?: string): 'brand' | 'teal' | 'amber' | 'red' => {
  const normalized = String(status || '').toLowerCase();
  if (['resolved', 'completed', 'closed'].includes(normalized)) return 'teal';
  if (['failed', 'cancelled'].includes(normalized)) return 'red';
  if (['waiting', 'retrying'].includes(normalized)) return 'amber';
  return 'brand';
};

export const compactText = (value: unknown, max = 160): string => {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (!text) return '--';
  return text.length > max ? `${text.slice(0, max - 1)}...` : text;
};

export const uniqueStrings = (items: Array<string | null | undefined>): string[] => {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of items) {
    const value = String(item || '').trim();
    if (!value || seen.has(value)) continue;
    seen.add(value);
    out.push(value);
  }
  return out;
};
