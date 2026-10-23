/** 保護者のスロット。v1は2人固定。 */
export type Slot = 'a' | 'b';
export type Leg = 'drop' | 'pick';
/** 'YYYY-MM-DD'（Asia/Tokyo の暦日） */
export type DateKey = string;
/** `${kidId}-drop` | `${kidId}-pick` */
export type LegKey = string;

export interface Kid {
  id: string;
  name: string;
  school: string;
  archived: boolean;
}

export interface Schedule {
  /** 適用開始日 */
  from: DateKey;
  /** 0=日 … 6=土 */
  weekdays: number[];
  pattern: Record<number, Record<LegKey, Slot>>;
}

export interface Household {
  names: Record<Slot, string>;
  kids: Kid[];
  /** 適用開始日の昇順。末尾が最新 */
  schedules: Schedule[];
  startDate: DateKey;
}

export interface DayDoc {
  legs?: Record<LegKey, Slot>;
  off?: boolean;
}

export type DaysMap = Record<DateKey, DayDoc | undefined>;

export interface LegRef {
  date: DateKey;
  kid: string;
  leg: Leg;
}

export interface ResolvedLeg extends LegRef {
  who: Slot;
}

export type TradeStatus = 'pending' | 'accepted' | 'declined' | 'cancelled' | 'expired';

export interface TradeLike {
  from: Slot;
  to: Slot;
  ret: LegRef | null;
  status: TradeStatus;
}
