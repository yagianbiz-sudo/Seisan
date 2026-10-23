import { legKey, weekdayOf } from './dates';
import type { DateKey, DaysMap, Household, Kid, Leg, ResolvedLeg, Schedule, Slot } from './types';

const LEGS: Leg[] = ['drop', 'pick'];

/** その日に有効な schedule（from <= 日付 の最後のもの）。なければ null */
export function scheduleFor(h: Household, date: DateKey): Schedule | null {
  let found: Schedule | null = null;
  for (const s of h.schedules) {
    if (s.from <= date) found = s;
  }
  return found;
}

/** 送迎がある日か（開始日前・曜日外・お休みは false） */
export function isActiveDay(h: Household, days: DaysMap, date: DateKey): boolean {
  if (date < h.startDate) return false;
  const s = scheduleFor(h, date);
  if (!s || !s.weekdays.includes(weekdayOf(date))) return false;
  return days[date]?.off !== true;
}

/** その日に表示する子ども：archived でないもの、または上書きが残っているもの */
export function kidsOn(h: Household, days: DaysMap, date: DateKey): Kid[] {
  const legs = days[date]?.legs;
  return h.kids.filter((k) => {
    if (!k.archived) return true;
    return !!legs && LEGS.some((leg) => legKey(k.id, leg) in legs);
  });
}

/** 1つの担当者を決める。上書き → パターン → 'a'（パターン未登録時の保険） */
export function whoFor(h: Household, days: DaysMap, date: DateKey, kidId: string, leg: Leg): Slot {
  const key = legKey(kidId, leg);
  const override = days[date]?.legs?.[key];
  if (override) return override;
  const s = scheduleFor(h, date);
  return s?.pattern[weekdayOf(date)]?.[key] ?? 'a';
}

/** その日の担当一覧（送迎なしの日は空） */
export function legsOn(h: Household, days: DaysMap, date: DateKey): ResolvedLeg[] {
  if (!isActiveDay(h, days, date)) return [];
  return kidsOn(h, days, date).flatMap((kid) =>
    LEGS.map((leg) => ({ date, kid: kid.id, leg, who: whoFor(h, days, date, kid.id, leg) })),
  );
}
