export type Role = 'admin' | 'station_manager' | 'dispatcher' | 'user';

export const ROLE_NAMES: Record<Role, string> = {
  admin: 'מנהל מערכת',
  station_manager: 'מנהל תחנה',
  dispatcher: 'סדרן',
  user: 'נהג / שליח',
};

export const CAR_BRANDS = [
  'יונדאי',
  'טויוטה',
  'קיה',
  'סקודה',
  'שברולט',
  'פולקסווגן',
  'אחר (הקלדה ידנית)',
];

export interface User {
  user_id: number;
  full_name: string;
  phone: string;
  birth_year: number;
  car_brand: string;
  car_model: string;
  car_year: number;
  car_seats: number;
  status: 'free' | 'busy';
  role: Role;
  station_id: number;
  rating: number; // default 5.0
  total_trips: number;
  is_blocked: number; // 0 or 1
  debt_balance: number; // e.g. 0.0
  sub_expiry?: string | null;
}

export interface Station {
  station_id: number;
  name: string;
  commission_percent: number; // default 10.0
}

export interface DriverBid {
  driver_id: number;
  driver_name: string;
  rating: number;
  car_brand: string;
  car_model: string;
  car_seats: number;
  eta_minutes: number;
  submitted_at: string;
}

export interface Order {
  order_id: number;
  text: string;
  price: number;
  publisher_id: number;
  station_id: number;
  driver_id: number | null;
  status: 'open' | 'closed' | 'deleted';
  created_at: string;
  destination_type?: 'private' | 'groups';
  bids?: DriverBid[];
  rating_given?: number;
}

export interface Debt {
  debt_id: number;
  order_id: number;
  driver_id: number;
  station_id: number;
  amount: number;
  status: 'unpaid' | 'paid' | 'cancelled';
  reason: string;
  appeal_reason?: string;
  appeal_status?: 'none' | 'pending' | 'approved' | 'rejected';
}

export interface DriverCity {
  user_id: number;
  city_name: string;
}

export interface BotGroup {
  group_id: number;
  group_name: string;
}

export interface BroadcastMessage {
  id: string;
  text: string;
  sender_name: string;
  created_at: string;
}
