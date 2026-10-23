import type { DateKey, Leg, LegKey, Slot } from './types';

const JST_OFFSET_MS = 9 * 60 * 60 * 1000;
export const WEEKDAY_LABELS = ['日', '月', '火', '水', '木', '金', '土'] as const;
export const LEG_LABELS: Record<Leg, string> = { drop: '送り', pick: '迎え' };

const pad = (n: number) => String(n).padStart(2, '0');

/** 日付キーを UTC の Date に（端末のタイムゾーンに依存させないため） */
const toUtc = (key: DateKey): Date => {
  const [y, m, d] = key.split('-').map(Number) as [number, number, number];
  return new Date(Date.UTC(y, m - 1, d));
};

const fromUtc = (d: Date): DateKey =>
  `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;

/** 瞬間（Date）を JST の暦日キーにする */
export function jstDateKey(instant: Date): DateKey {
  return fromUtc(new Date(instant.getTime() + JST_OFFSET_MS));
}

export const todayKey = (now: Date = new Date()): DateKey => jstDateKey(now);

export const weekdayOf = (key: DateKey): number => toUtc(key).getUTCDay();

export function addDays(key: DateKey, n: number): DateKey {
  const d = toUtc(key);
  d.setUTCDate(d.getUTCDate() + n);
  return fromUtc(d);
}

/** 'YYYY-MM' */
export const monthOf = (key: DateKey): string => key.slice(0, 7);

export function addMonths(month: string, n: number): string {
  const [y, m] = month.split('-').map(Number) as [number, number];
  const idx = y * 12 + (m - 1) + n;
  return `${Math.floor(idx / 12)}-${pad((idx % 12) + 1)}`;
}

export function daysInMonth(month: string): DateKey[] {
  const [y, m] = month.split('-').map(Number) as [number, number];
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return Array.from({ length: last }, (_, i) => `${month}-${pad(i + 1)}`);
}

/** 例: 10/24(金) */
export function formatDate(key: DateKey): string {
  const d = toUtc(key);
  return `${d.getUTCMonth() + 1}/${d.getUTCDate()}(${WEEKDAY_LABELS[d.getUTCDay()]})`;
}

export const monthLabel = (month: string): string => {
  const [y, m] = month.split('-').map(Number) as [number, number];
  return `${y}年${m}月`;
};

export const legKey = (kid: string, leg: Leg): LegKey => `${kid}-${leg}`;
export const other = (p: Slot): Slot => (p === 'a' ? 'b' : 'a');
