import { describe, expect, it } from 'vitest';
import {
  addDays,
  addMonths,
  balance,
  formatDate,
  isActiveDay,
  jstDateKey,
  legsOn,
  monthStats,
  todayKey,
  whoFor,
  type DaysMap,
  type Household,
} from './index';

const kid = (id: string, archived = false) => ({ id, name: id, school: '', archived });

/** 月〜金。上の子=a送り/b迎え、下の子=b送り/a迎え */
const patternV1 = Object.fromEntries(
  [1, 2, 3, 4, 5].map((w) => [
    w,
    { 'k1-drop': 'a', 'k1-pick': 'b', 'k2-drop': 'b', 'k2-pick': 'a' },
  ]),
) as Household['schedules'][number]['pattern'];

const house = (over: Partial<Household> = {}): Household => ({
  names: { a: 'ママ', b: 'パパ' },
  kids: [kid('k1'), kid('k2')],
  startDate: '2025-10-01',
  schedules: [{ from: '2025-10-01', weekdays: [1, 2, 3, 4, 5], pattern: patternV1 }],
  ...over,
});

describe('日付（JST）', () => {
  it('UTC 15:00 を境に JST の日付が進む', () => {
    expect(jstDateKey(new Date('2025-10-23T14:59:59Z'))).toBe('2025-10-23');
    expect(jstDateKey(new Date('2025-10-23T15:00:00Z'))).toBe('2025-10-24');
  });
  it('todayKey は引数の瞬間から JST の暦日を返す', () => {
    expect(todayKey(new Date('2025-12-31T15:30:00Z'))).toBe('2026-01-01');
  });
  it('addDays / addMonths は月・年をまたぐ', () => {
    expect(addDays('2025-10-31', 1)).toBe('2025-11-01');
    expect(addDays('2025-01-01', -1)).toBe('2024-12-31');
    expect(addMonths('2025-12', 1)).toBe('2026-01');
    expect(addMonths('2025-01', -1)).toBe('2024-12');
  });
  it('formatDate は曜日つき', () => {
    expect(formatDate('2025-10-24')).toBe('10/24(金)');
  });
});

describe('担当の決め方', () => {
  it('パターン通りに決まる（2025-10-24は金曜）', () => {
    const h = house();
    expect(whoFor(h, {}, '2025-10-24', 'k1', 'drop')).toBe('a');
    expect(whoFor(h, {}, '2025-10-24', 'k1', 'pick')).toBe('b');
    expect(legsOn(h, {}, '2025-10-24')).toHaveLength(4);
  });
  it('開始日より前は対象外', () => {
    expect(legsOn(house(), {}, '2025-09-30')).toEqual([]);
  });
  it('曜日外（土日）は送迎なし', () => {
    expect(isActiveDay(house(), {}, '2025-10-25')).toBe(false);
  });
  it('お休みの日は送迎なし', () => {
    const days: DaysMap = { '2025-10-24': { off: true } };
    expect(legsOn(house(), days, '2025-10-24')).toEqual([]);
  });
  it('日ごとの上書きがパターンに優先する', () => {
    const days: DaysMap = { '2025-10-24': { legs: { 'k1-drop': 'b' } } };
    expect(whoFor(house(), days, '2025-10-24', 'k1', 'drop')).toBe('b');
    expect(whoFor(house(), days, '2025-10-24', 'k1', 'pick')).toBe('b');
    expect(whoFor(house(), days, '2025-10-24', 'k2', 'drop')).toBe('b');
  });
  it('パターン版は適用開始日で切り替わり、過去は変わらない', () => {
    const v2 = Object.fromEntries(
      [1, 2, 3, 4, 5].map((w) => [
        w,
        { 'k1-drop': 'b', 'k1-pick': 'b', 'k2-drop': 'b', 'k2-pick': 'b' },
      ]),
    ) as Household['schedules'][number]['pattern'];
    const h = house({
      schedules: [
        { from: '2025-10-01', weekdays: [1, 2, 3, 4, 5], pattern: patternV1 },
        { from: '2025-10-20', weekdays: [1, 2, 3, 4], pattern: v2 },
      ],
    });
    expect(whoFor(h, {}, '2025-10-17', 'k1', 'drop')).toBe('a'); // 版1
    expect(whoFor(h, {}, '2025-10-20', 'k1', 'drop')).toBe('b'); // 版2の初日
    expect(isActiveDay(h, {}, '2025-10-17')).toBe(true); // 版1は金曜あり
    expect(isActiveDay(h, {}, '2025-10-24')).toBe(false); // 版2は金曜なし
  });
  it('archived の子は表示しない。ただし上書きが残る日は表示する', () => {
    const h = house({ kids: [kid('k1'), kid('k2', true)] });
    expect(legsOn(h, {}, '2025-10-24').map((l) => l.kid)).toEqual(['k1', 'k1']);
    const days: DaysMap = { '2025-10-24': { legs: { 'k2-drop': 'a' } } };
    const kids = legsOn(h, days, '2025-10-24').map((l) => l.kid);
    expect(kids).toEqual(['k1', 'k1', 'k2', 'k2']);
    expect(whoFor(h, days, '2025-10-24', 'k2', 'drop')).toBe('a');
  });
});

describe('月集計', () => {
  it('10月は平日23日 × 4担当。a と b は半々', () => {
    const s = monthStats(house(), {}, '2025-10', '2025-10-10');
    // 10/1(水)〜10/31(金) の平日は23日
    expect(s.a.total).toBe(46);
    expect(s.b.total).toBe(46);
    expect(s.a.drop + s.a.pick).toBe(s.a.total);
  });
  it('「今日まで」は今日を含む', () => {
    const s = monthStats(house(), {}, '2025-10', '2025-10-03'); // 水〜金の3日
    expect(s.a.done).toBe(6);
    expect(s.b.done).toBe(6);
  });
  it('開始日が月の途中なら、開始日より前は数えない', () => {
    const h = house({ startDate: '2025-10-27' });
    const s = monthStats(h, {}, '2025-10', '2025-10-31'); // 27〜31の5日
    expect(s.a.total + s.b.total).toBe(20);
  });
  it('お休みと上書きが反映され、子ども別にも集計される', () => {
    const days: DaysMap = {
      '2025-10-01': { off: true },
      '2025-10-02': { legs: { 'k1-drop': 'b' } },
    };
    const s = monthStats(house(), days, '2025-10', '2025-10-31');
    expect(s.a.total + s.b.total).toBe(22 * 4);
    expect(s.a.total).toBe(44 - 1);
    expect(s.kids['k1']).toEqual({ a: 21, b: 22 + 1 });
  });
  it('月またぎ：月末と月初が別の月に入る', () => {
    const oct = monthStats(house(), {}, '2025-10', '2025-12-31');
    const nov = monthStats(house(), {}, '2025-11', '2025-12-31');
    // 11月は平日20日
    expect(nov.a.total + nov.b.total).toBe(80);
    expect(oct.a.total + oct.b.total).toBe(92);
  });
  it('パターン変更をまたぐ月でも、過去分の回数は変わらない', () => {
    const v2 = Object.fromEntries(
      [1, 2, 3, 4, 5].map((w) => [
        w,
        { 'k1-drop': 'b', 'k1-pick': 'b', 'k2-drop': 'b', 'k2-pick': 'b' },
      ]),
    ) as Household['schedules'][number]['pattern'];
    const before = monthStats(house(), {}, '2025-10', '2025-10-31');
    const h2 = house({
      schedules: [
        ...house().schedules,
        { from: '2025-10-27', weekdays: [1, 2, 3, 4, 5], pattern: v2 },
      ],
    });
    const after = monthStats(h2, {}, '2025-10', '2025-10-31');
    // 10/27 より前の 18 日（10/1〜10/24の平日）は同じ。残り5日がすべて b になる
    expect(after.a.total).toBe(before.a.total - 10);
    expect(after.b.total).toBe(before.b.total + 10);
  });
  it('archived の子は、上書きがない日は数えない', () => {
    const h = house({ kids: [kid('k1'), kid('k2', true)] });
    const s = monthStats(h, {}, '2025-10', '2025-10-31');
    expect(s.a.total + s.b.total).toBe(46);
    expect(s.kids['k2']).toBeUndefined();
  });
});

describe('貸し借り', () => {
  const t = (from: 'a' | 'b', status: 'accepted' | 'pending', ret: boolean) => ({
    from,
    to: from === 'a' ? ('b' as const) : ('a' as const),
    ret: ret ? { date: '2025-10-24', kid: 'k1', leg: 'drop' as const } : null,
    status,
  });
  it('お返しなしで成立した分だけ数える', () => {
    expect(balance([t('b', 'accepted', false), t('b', 'accepted', false)])).toBe(2);
    expect(balance([t('a', 'accepted', false)])).toBe(-1);
  });
  it('お返しつき・返事待ちは数えない', () => {
    expect(balance([t('b', 'accepted', true), t('b', 'pending', false)])).toBe(0);
  });
  it('引き受け（take）は元の担当者への貸しになる', () => {
    // a の担当を b が引き受け: from=a, to=b → a が b に借り → 負
    expect(balance([{ from: 'a', to: 'b', ret: null, status: 'accepted' }])).toBe(-1);
  });
});
