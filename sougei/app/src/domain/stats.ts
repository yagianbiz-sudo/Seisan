import { daysInMonth } from './dates';
import { legsOn } from './assignment';
import type { DateKey, DaysMap, Household, Slot, TradeLike } from './types';

export interface SlotCount {
  total: number;
  /** 今日まで（今日を含む） */
  done: number;
  drop: number;
  pick: number;
}

export interface MonthStats {
  month: string;
  a: SlotCount;
  b: SlotCount;
  kids: Record<string, Record<Slot, number>>;
}

const zero = (): SlotCount => ({ total: 0, done: 0, drop: 0, pick: 0 });

/** 月ごとの送迎回数（子ども1人 × 送り or 迎え を1回） */
export function monthStats(h: Household, days: DaysMap, month: string, today: DateKey): MonthStats {
  const out: MonthStats = { month, a: zero(), b: zero(), kids: {} };
  for (const date of daysInMonth(month)) {
    for (const l of legsOn(h, days, date)) {
      const p = out[l.who];
      p.total++;
      p[l.leg]++;
      if (date <= today) p.done++;
      const k = (out.kids[l.kid] ??= { a: 0, b: 0 });
      k[l.who]++;
    }
  }
  return out;
}

/**
 * 貸し借り。正なら b が a に借りがある。
 * accepted かつ お返しなし のトレード1件ごとに、from が to に借り1回。
 */
export function balance(trades: readonly TradeLike[]): number {
  let n = 0;
  for (const t of trades) {
    if (t.status === 'accepted' && t.ret === null) n += t.from === 'b' ? 1 : -1;
  }
  return n;
}
