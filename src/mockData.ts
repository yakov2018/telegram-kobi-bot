import { User, Station, Order, Debt, DriverCity, BotGroup } from './types';

// תחנות ברירת מחדל ראשונית (מתעדכן מיד מ-deliveries_stations)
export const INITIAL_STATIONS: Station[] = [
  {
    station_id: 1,
    name: 'תחנה ראשית',
    commission_percent: 10.0,
  },
];

// אין נתוני דמה! כל המשתמשים נטענים בלעדית ממסד הנתונים בענן דרך /api/auth ו-/api/users
export const INITIAL_USERS: User[] = [];

// אין ערי דמה! כל ערי הנהג נטענות בלעדית מ-deliveries_driver_cities
export const INITIAL_DRIVER_CITIES: DriverCity[] = [];

// אין קריאות דמה! נטענות ישירות מ-deliveries_orders
export const INITIAL_ORDERS: Order[] = [];

// אין חובות דמה! נטענים ישירות מ-deliveries_debts
export const INITIAL_DEBTS: Debt[] = [];

export const INITIAL_BOT_GROUPS: BotGroup[] = [];
