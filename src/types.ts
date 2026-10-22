export type Role = 'admin' | 'station_manager' | 'dispatcher' | 'user';

export const ROLE_NAMES: Record<Role, string> = {
  admin: 'מנהל מערכת (God Mode)',
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
  'מאזדה',
  'אחר (הקלדה ידנית)',
];

export interface User {
  user_id: number;
  full_name: string;
  telegram_username?: string;
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
  subscription_plan?: string;
}

export interface Station {
  station_id: number;
  name: string;
  commission_percent: number; // default 10.0
  is_active?: boolean;
}

export interface DriverBid {
  bid_id?: number;
  order_id?: number;
  driver_id: number;
  driver_name: string;
  telegram_username?: string;
  driver_phone?: string;
  rating: number;
  car_brand: string;
  car_model: string;
  car_year?: number;
  car_seats: number;
  eta_minutes?: number;
  eta_text?: string;
  submitted_at: string;
  status?: 'pending' | 'accepted' | 'rejected';
}

export interface Order {
  order_id: number;
  text: string;
  raw_text?: string;
  price: number;
  publisher_id: number;
  publisher_name?: string;
  publisher_username?: string;
  station_id: number;
  station_name?: string;
  driver_id: number | null;
  assigned_driver_name?: string;
  status: 'open' | 'assigned' | 'closed' | 'cancelled' | 'deleted';
  created_at: string;
  destination_type?: 'private' | 'groups' | 'all';
  requires_eta?: boolean;
  origin_city?: string;
  dest_city?: string;
  client_phone?: string;
  commission_amount?: number;
  bids?: DriverBid[];
  rating_given?: number;
}

export interface Debt {
  debt_id: number;
  order_id: number;
  driver_id: number;
  driver_name?: string;
  station_id: number;
  station_name?: string;
  amount: number;
  status: 'unpaid' | 'paid' | 'cancelled';
  reason: string;
  appeal_reason?: string;
  appeal_status?: 'none' | 'pending' | 'approved' | 'rejected' | 'confirmed';
  publisher_username?: string;
  created_at?: string;
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

export interface StationStats {
  station_id: number;
  station_name: string;
  commission_percent: number;
  total_orders: number;
  open_orders: number;
  assigned_orders: number;
  closed_orders: number;
  cancelled_orders: number;
  total_revenue: number;
  total_commission: number;
  dispatchers: Array<{
    user_id: number;
    full_name: string;
    telegram_username: string;
    role: Role;
    orders_published: number;
  }>;
}
