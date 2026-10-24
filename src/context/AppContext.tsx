import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { User, Station, Order, Debt, DriverCity, BotGroup, BroadcastMessage, Role, DriverBid } from '../types';
import { calculateCommission } from '../utils/orderUtils';

export const ADMIN_IDS = [8644923212, 552821474];

export interface DriverStatusResult {
  success: boolean;
  message: string;
  newStatus?: 'free' | 'busy';
}

export interface PublishOrderResult {
  success: boolean;
  orderId?: number;
  order: Order;
  eligibleDriversCount: number;
  error?: string;
}

interface AppContextType {
  currentUser: User;
  users: User[];
  stations: Station[];
  orders: Order[];
  debts: Debt[];
  driverCities: DriverCity[];
  botGroups: BotGroup[];
  broadcasts: BroadcastMessage[];
  switchUser: (userId: number) => void;
  registerUser: (data: {
    full_name: string;
    phone: string;
    birth_year: number;
    car_brand: string;
    car_model: string;
    car_year: number;
    car_seats: number;
  }) => User;
  toggleDriverStatus: (userId?: number) => DriverStatusResult;
  addDriverCity: (userId: number, cityName: string) => Promise<void>;
  removeDriverCity: (userId: number, cityName: string) => Promise<void>;
  clearDriverCities: (userId: number) => Promise<void>;
  getDriverCities: (userId: number) => string[];
  publishOrder: (
    payloadOrText:
      | string
      | {
          rawText?: string;
          text?: string;
          price?: number;
          destinationType?: 'private' | 'groups' | 'all' | 'zone_and_groups' | 'groups_only' | 'zone_only' | 'manual';
          requiresEta?: boolean;
          originCity?: string;
          destCity?: string;
          clientPhone?: string;
        },
    legacyDestType?: any,
    legacyPrice?: number
  ) => Promise<PublishOrderResult>;
  submitOrderBid: (orderId: number, driverId: number, etaMinutes: number) => { success: boolean; message: string };
  approveDriverOrder: (orderId: number, driverId: number) => { success: boolean; debtAmount: number; clientPhone?: string; message: string };
  denyDriverOrder: (orderId: number, driverId: number) => void;
  closeAndChargeOrder: (orderId: number, driverId: number, customCommission?: number) => { success: boolean; debtAmount: number };
  republishOrder: (orderId: number) => void;
  cancelOrder: (orderId: number) => void;
  manualCloseOrder: (payload: {
    text: string;
    price: number;
    driverId: number;
    stationId: number;
    clientPhone?: string;
    commissionPercent?: number;
  }) => Promise<{ success: boolean; orderId?: number; debtAmount?: number; error?: string }>;
  rateDriver: (driverId: number, stars: number) => void;
  deleteOrder: (orderId: number) => void;
  acknowledgeDebt: (debtId: number) => void;
  submitDebtAppeal: (debtId: number, reason: string) => boolean;
  resolveDebtAppeal: (debtId: number, approve: boolean) => Promise<boolean>;
  createStation: (name: string, commissionPercent: number) => Station;
  updateStation: (stationId: number, name: string, commissionPercent: number) => Promise<boolean>;
  updateUserRoleAndStation: (targetId: number, newRole: Role | 'blocked', stationId: number, subscriptionPlan?: string) => Promise<void>;
  chargeDriverDebt: (driverId: number, amount: number, reason: string, stationId: number, orderId?: number) => Promise<void>;
  updateDebt: (debtId: number, updates: { amount?: number; reason?: string; station_id?: number; status?: 'unpaid' | 'paid' | 'cancelled' }) => Promise<void>;
  deleteDebt: (debtId: number) => Promise<void>;
  sendBroadcast: (text: string) => Promise<number>;
  refreshAllData: () => Promise<void>;
  resetToInitialData: () => Promise<void>;
  isTelegramWebApp: boolean;
  isAuthLoading: boolean;
  isAuthenticated: boolean;
  authError: string | null;
}

const AppContext = createContext<AppContextType | null>(null);

const GUEST_USER: User = {
  user_id: 0,
  full_name: 'טוען נתונים...',
  phone: '',
  birth_year: 2000,
  car_brand: '',
  car_model: '',
  car_year: 2024,
  car_seats: 4,
  status: 'busy',
  role: 'user',
  station_id: 1,
  rating: 5.0,
  total_trips: 0,
  is_blocked: 0,
  debt_balance: 0.0,
  subscription_plan: 'free',
};

export const AppProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [currentUser, setCurrentUser] = useState<User>(GUEST_USER);
  const [users, setUsers] = useState<User[]>([]);
  const [stations, setStations] = useState<Station[]>([
    { station_id: 1, name: 'תחנה ראשית', commission_percent: 10.0, is_active: true }
  ]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [debts, setDebts] = useState<Debt[]>([]);
  const [driverCities, setDriverCities] = useState<DriverCity[]>([]);
  const [botGroups, setBotGroups] = useState<BotGroup[]>([]);
  const [broadcasts, setBroadcasts] = useState<BroadcastMessage[]>([]);

  const [isTelegramWebApp, setIsTelegramWebApp] = useState<boolean>(false);
  const [isAuthLoading, setIsAuthLoading] = useState<boolean>(true);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [authError, setAuthError] = useState<string | null>(null);

  // מרענן את כלל נתוני המערכת מה-Backend
  const refreshAllData = useCallback(async () => {
    try {
      const [resStations, resOrders, resDebts, resUsers, resCities] = await Promise.all([
        fetch('/api/stations').then((r) => r.json()).catch((e) => {
          console.error('🚨 [API /api/stations Fetch Error]:', e);
          return { ok: true, stations: [] };
        }),
        fetch('/api/orders').then((r) => r.json()).catch((e) => {
          console.error('🚨 [API /api/orders Fetch Error]:', e);
          return { ok: true, orders: [] };
        }),
        fetch('/api/debts').then((r) => r.json()).catch((e) => {
          console.error('🚨 [API /api/debts Fetch Error]:', e);
          return { ok: true, debts: [] };
        }),
        fetch('/api/users').then((r) => r.json()).catch((e) => {
          console.error('🚨 [API /api/users Fetch Error]:', e);
          return { ok: true, users: [] };
        }),
        fetch('/api/driver/all_cities').then((r) => r.json()).catch((e) => {
          console.error('🚨 [API /api/driver/all_cities Fetch Error]:', e);
          return { ok: true, cities: [] };
        }),
      ]);

      if (resStations.ok && Array.isArray(resStations.stations) && resStations.stations.length > 0) {
        setStations(resStations.stations.map((s: any) => ({
          station_id: Number(s.station_id),
          name: s.name,
          commission_percent: Number(s.commission_percent || 10.0),
          is_active: s.is_active !== undefined ? Boolean(s.is_active) : true,
        })));
      }

      if (resOrders.ok && Array.isArray(resOrders.orders)) {
        setOrders(resOrders.orders.map((o: any) => ({
          order_id: Number(o.order_id),
          text: o.text || '',
          raw_text: o.raw_text || o.text || '',
          price: Number(o.price || 0),
          publisher_id: Number(o.publisher_id || 0),
          station_id: Number(o.station_id || 1),
          driver_id: o.driver_id ? Number(o.driver_id) : null,
          status: o.status || 'open',
          created_at: o.created_at || new Date().toISOString(),
          destination_type: o.destination_type || 'all',
          requires_eta: Boolean(o.requires_eta),
          origin_city: o.origin_city || '',
          dest_city: o.dest_city || '',
          client_phone: o.client_phone || '',
          bids: Array.isArray(o.bids) ? o.bids : [],
        })));
      }

      if (resDebts.ok && Array.isArray(resDebts.debts)) {
        setDebts(resDebts.debts.map((d: any) => ({
          debt_id: Number(d.debt_id),
          order_id: Number(d.order_id || 0),
          driver_id: Number(d.driver_id),
          station_id: Number(d.station_id || 1),
          amount: Number(d.amount || 0),
          status: d.status || 'unpaid',
          reason: d.reason || '',
          appeal_status: d.appeal_status || 'none',
          appeal_reason: d.appeal_reason || '',
          publisher_username: d.publisher_username || '',
          is_locked: Number(d.is_locked || 0),
          created_at: d.created_at,
        })));
      }

      if (resUsers.ok && Array.isArray(resUsers.users)) {
        const parsedUsers: User[] = resUsers.users.map((u: any) => ({
          user_id: Number(u.user_id),
          full_name: u.full_name || 'משתמש',
          telegram_username: u.telegram_username || '',
          phone: u.phone || '',
          birth_year: Number(u.birth_year || 1995),
          car_brand: u.car_brand || '',
          car_model: u.car_model || '',
          car_year: Number(u.car_year || 0),
          car_seats: Number(u.car_seats || 4),
          status: u.status || 'busy',
          role: ADMIN_IDS.includes(Number(u.user_id)) ? 'admin' : (u.role === 'admin' ? 'user' : (u.role || 'user')),
          station_id: Number(u.station_id || 1),
          rating: Number(u.rating || 5.0),
          total_trips: Number(u.total_trips || 0),
          is_blocked: ADMIN_IDS.includes(Number(u.user_id)) ? 0 : (u.is_blocked ? 1 : 0),
          debt_balance: Number(u.debt_balance || 0),
          subscription_plan: u.subscription_plan || 'free',
        }));
        setUsers(parsedUsers);
      }

      if (resCities.ok && Array.isArray(resCities.cities)) {
        setDriverCities(resCities.cities.map((c: any) => ({
          user_id: Number(c.user_id),
          city_name: String(c.city_name),
        })));
      }
    } catch (err) {
      console.error('🚨 [refreshAllData Global Error]:', err);
    }
  }, []);

  // אימות מול שרת ה-API עם initData של טלגרם
  useEffect(() => {
    let initDataStr = '';
    let tgUser: any = null;

    const tg = (window as any).Telegram?.WebApp;
    if (tg) {
      try {
        setIsTelegramWebApp(true);
        initDataStr = tg.initData || '';
        tgUser = tg.initDataUnsafe?.user || null;
      } catch (err) {
        console.error('🚨 [Telegram WebApp Init Error]:', err);
      }
    }

    let urlUserId: number | undefined = undefined;
    try {
      const q = new URLSearchParams(window.location.search).get('user_id');
      if (q && !isNaN(Number(q))) urlUserId = Number(q);
    } catch {}

    const payloadUserId = tgUser?.id ? Number(tgUser.id) : urlUserId;

    fetch('/api/auth', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Telegram-Init-Data': initDataStr,
      },
      body: JSON.stringify({
        initData: initDataStr,
        user_id: payloadUserId,
        user: tgUser,
      }),
    })
      .then(async (res) => {
        const data = await res.json();
        const incomingUser = data.user_data || data.user;
        if (res.ok && data.ok && incomingUser) {
          const isServerAdmin = ADMIN_IDS.includes(Number(incomingUser.user_id)) || data.role === 'admin' || incomingUser.role === 'admin';
          const userRole: Role = isServerAdmin
            ? 'admin'
            : (incomingUser.role === 'admin' ? 'user' : (incomingUser.role || data.role || 'user'));

          const serverUser: User = {
            user_id: Number(incomingUser.user_id),
            full_name: incomingUser.full_name || 'משתמש',
            telegram_username: incomingUser.telegram_username || tgUser?.username || '',
            phone: incomingUser.phone || '',
            birth_year: Number(incomingUser.birth_year || 1995),
            car_brand: incomingUser.car_brand || '',
            car_model: incomingUser.car_model || '',
            car_year: Number(incomingUser.car_year || 0),
            car_seats: Number(incomingUser.car_seats || 4),
            status: incomingUser.status || 'busy',
            role: userRole,
            station_id: Number(incomingUser.station_id || 1),
            rating: Number(incomingUser.rating || 5.0),
            total_trips: Number(incomingUser.total_trips || 0),
            is_blocked: isServerAdmin ? 0 : (incomingUser.is_blocked ? 1 : 0),
            debt_balance: Number(incomingUser.debt_balance || 0.0),
            subscription_plan: incomingUser.subscription_plan || 'free',
          };

          setCurrentUser(serverUser);
          setIsAuthenticated(true);
          setAuthError(null);

          if (data.stations && Array.isArray(data.stations) && data.stations.length > 0) {
            setStations(data.stations.map((s: any) => ({
              station_id: Number(s.station_id),
              name: s.name,
              commission_percent: Number(s.commission_percent || 10.0),
            })));
          }

          if (Array.isArray(data.cities)) {
            const freshCities = data.cities.map((cityName: string) => ({
              user_id: serverUser.user_id,
              city_name: cityName,
            }));
            setDriverCities((prev) => [
              ...prev.filter((dc) => dc.user_id !== serverUser.user_id),
              ...freshCities,
            ]);
          }

          refreshAllData();
        } else {
          setIsAuthenticated(false);
          setAuthError(data.error || 'אימות ה-Mini App נכשל מול הבוט בטלגרם.');
        }
      })
      .catch((err) => {
        console.error('🚨 [Auth API Exception]:', err);
        setIsAuthenticated(false);
        setAuthError('שגיאת תקשורת באימות מול השרת. פתח מחדש מתוך הטלגרם.');
      })
      .finally(() => {
        setIsAuthLoading(false);
        try {
          const tgObj = (window as any).Telegram?.WebApp;
          if (tgObj) {
            tgObj.ready();
            tgObj.expand();
          }
        } catch (e) {
          console.error('🚨 [Telegram WebApp ready error]:', e);
        }
      });
  }, [refreshAllData]);

  // סנכרון ערי נהג מקומיות
  const getDriverCities = (userId: number): string[] => {
    return driverCities.filter((dc) => dc.user_id === userId).map((dc) => dc.city_name);
  };

  const addDriverCity = async (userId: number, cityName: string) => {
    try {
      const res = await fetch('/api/driver/cities/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, city_name: cityName }),
      });
      const data = await res.json();
      if (data.ok) {
        setDriverCities((prev) => [...prev.filter((c) => !(c.user_id === userId && c.city_name === cityName)), { user_id: userId, city_name: cityName }]);
      }
    } catch (err) {
      console.error('🚨 [addDriverCity Error]:', err);
    }
  };

  const removeDriverCity = async (userId: number, cityName: string) => {
    try {
      const res = await fetch('/api/driver/cities/remove', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, city_name: cityName }),
      });
      const data = await res.json();
      if (data.ok) {
        setDriverCities((prev) => prev.filter((c) => !(c.user_id === userId && c.city_name === cityName)));
      }
    } catch (err) {
      console.error('🚨 [removeDriverCity Error]:', err);
    }
  };

  const clearDriverCities = async (userId: number) => {
    try {
      const res = await fetch('/api/driver/cities/clear', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId }),
      });
      const data = await res.json();
      if (data.ok) {
        setDriverCities((prev) => prev.filter((c) => c.user_id !== userId));
      }
    } catch (err) {
      console.error('🚨 [clearDriverCities Error]:', err);
    }
  };

  // Toggle driver status (synchronous UI response + background server sync)
  const toggleDriverStatus = (userId?: number): DriverStatusResult => {
    const targetId = userId ?? currentUser.user_id;
    const targetUser = users.find((u) => u.user_id === targetId) || currentUser;
    const newStatus: 'free' | 'busy' = targetUser.status === 'free' ? 'busy' : 'free';

    if (newStatus === 'free' && Number(targetUser.debt_balance || 0) > 500) {
      return { success: false, message: '🚫 חשבונך מוקפא עקב חוב מעל 500 ש"ח! הסדר חוב מול התחנה.' };
    }

    // Update state immediately
    setCurrentUser((prev) => (prev.user_id === targetId ? { ...prev, status: newStatus } : prev));
    setUsers((prev) => prev.map((u) => (u.user_id === targetId ? { ...u, status: newStatus } : u)));

    // Sync in background
    fetch('/api/driver/status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: targetId, status: newStatus }),
    }).catch((err) => console.error('🚨 [toggleDriverStatus Sync Error]:', err));

    return {
      success: true,
      newStatus,
      message: newStatus === 'free' ? '🟢 סטטוס עודכן ל-פנוי לקריאות' : '🔴 סטטוס עודכן ל-תפוס (עצור קריאות)',
    };
  };

  // Switch user (available only to admin)
  const switchUser = (userId: number) => {
    if (currentUser.role !== 'admin') return;
    const found = users.find((u) => u.user_id === userId);
    if (found) {
      setCurrentUser(found);
    }
  };

  // Register user fallback
  const registerUser = (data: {
    full_name: string;
    phone: string;
    birth_year: number;
    car_brand: string;
    car_model: string;
    car_year: number;
    car_seats: number;
  }): User => {
    const newId = Math.floor(100000 + Math.random() * 900000);
    const newUser: User = {
      user_id: newId,
      full_name: data.full_name,
      phone: data.phone,
      birth_year: data.birth_year,
      car_brand: data.car_brand,
      car_model: data.car_model,
      car_year: data.car_year,
      car_seats: data.car_seats,
      status: 'busy',
      role: 'user',
      station_id: 1,
      rating: 5.0,
      total_trips: 0,
      is_blocked: 0,
      debt_balance: 0.0,
      subscription_plan: 'free',
    };
    setUsers((prev) => [...prev, newUser]);
    return newUser;
  };

  // Publish order supporting both object and positional calling signatures
  const publishOrder = async (
    payloadOrText:
      | string
      | {
          rawText?: string;
          text?: string;
          price?: number;
          destinationType?: 'private' | 'groups' | 'all' | 'zone_and_groups' | 'groups_only' | 'zone_only' | 'manual';
          requiresEta?: boolean;
          originCity?: string;
          destCity?: string;
          clientPhone?: string;
        },
    legacyDestType?: any,
    legacyPrice?: number
  ): Promise<PublishOrderResult> => {
    let rawText = '';
    let price = 0;
    let destinationType = 'all';
    let requiresEta = false;
    let originCity = '';
    let destCity = '';
    let clientPhone = '';

    if (typeof payloadOrText === 'string') {
      rawText = payloadOrText;
      destinationType = legacyDestType || 'all';
      price = Number(legacyPrice || 0);
    } else {
      rawText = payloadOrText.rawText || payloadOrText.text || '';
      price = Number(payloadOrText.price || 0);
      destinationType = payloadOrText.destinationType || 'all';
      requiresEta = Boolean(payloadOrText.requiresEta);
      originCity = payloadOrText.originCity || '';
      destCity = payloadOrText.destCity || '';
      clientPhone = payloadOrText.clientPhone || '';
    }

    const fallbackOrder: Order = {
      order_id: Math.floor(1000 + Math.random() * 9000),
      text: rawText,
      price,
      publisher_id: currentUser.user_id,
      station_id: currentUser.station_id || 1,
      driver_id: null,
      status: 'open',
      created_at: new Date().toISOString(),
      destination_type: destinationType as any,
      requires_eta: requiresEta,
      origin_city: originCity,
      dest_city: destCity,
      client_phone: clientPhone,
      bids: [],
    };

    try {
      const res = await fetch('/api/orders/publish', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          raw_text: rawText,
          price,
          publisher_id: currentUser.user_id,
          station_id: currentUser.station_id || 1,
          destination_type: destinationType,
          requires_eta: requiresEta ? 1 : 0,
          origin_city: originCity,
          dest_city: destCity,
          client_phone: clientPhone,
        }),
      });
      const data = await res.json();
      if (data.ok) {
        const createdOrder: Order = {
          ...fallbackOrder,
          order_id: data.order_id || fallbackOrder.order_id,
        };
        setOrders((prev) => [createdOrder, ...prev]);
        refreshAllData();
        return {
          success: true,
          orderId: createdOrder.order_id,
          order: createdOrder,
          eligibleDriversCount: data.eligible_drivers || 0,
        };
      }
      return {
        success: false,
        order: fallbackOrder,
        eligibleDriversCount: 0,
        error: data.error || 'שגיאה בפרסום',
      };
    } catch (err: any) {
      console.error('🚨 [publishOrder Error]:', err);
      return {
        success: false,
        order: fallbackOrder,
        eligibleDriversCount: 0,
        error: 'שגיאת תקשורת עם השרת',
      };
    }
  };

  // Bidding and order interactions
  const submitOrderBid = (orderId: number, driverId: number, etaMinutes: number) => {
    const driver = users.find((u) => u.user_id === driverId) || currentUser;
    const newBid: DriverBid = {
      driver_id: driverId,
      driver_name: driver.full_name || 'נהג',
      telegram_username: driver.telegram_username,
      driver_phone: driver.phone,
      rating: driver.rating || 5.0,
      car_brand: driver.car_brand || '',
      car_model: driver.car_model || '',
      car_year: driver.car_year,
      car_seats: driver.car_seats || 4,
      eta_minutes: etaMinutes,
      submitted_at: new Date().toISOString(),
      status: 'pending',
    };

    setOrders((prev) =>
      prev.map((o) => {
        if (o.order_id === orderId) {
          const existingBids = o.bids || [];
          const updatedBids = [...existingBids.filter((b) => b.driver_id !== driverId), newBid];
          return { ...o, bids: updatedBids };
        }
        return o;
      })
    );

    return {
      success: true,
      message: `✅ בקשתך לקריאה #${orderId} עם זמן הגעה של ${etaMinutes} דק' נשלחה לסדרן!`,
    };
  };

  const approveDriverOrder = (orderId: number, driverId: number) => {
    const order = orders.find((o) => o.order_id === orderId);
    const station = stations.find((s) => s.station_id === (order?.station_id || currentUser.station_id)) || {
      station_id: 1,
      name: 'תחנה ראשית',
      commission_percent: 10.0,
    };
    const debtAmount = calculateCommission(order?.price || 0, station.commission_percent);

    setOrders((prev) =>
      prev.map((o) => {
        if (o.order_id === orderId) {
          return {
            ...o,
            status: 'assigned',
            driver_id: driverId,
            bids: (o.bids || []).map((b) => ({
              ...b,
              status: b.driver_id === driverId ? 'accepted' : 'rejected',
            })),
          };
        }
        return o;
      })
    );

    return {
      success: true,
      debtAmount,
      clientPhone: order?.client_phone,
      message: `✅ הנסיעה ננעלה על הנהג! פרטי הלקוח מוכנים להעברה.`,
    };
  };

  const denyDriverOrder = (orderId: number, driverId: number) => {
    setOrders((prev) =>
      prev.map((o) => {
        if (o.order_id === orderId) {
          return {
            ...o,
            bids: (o.bids || []).map((b) => (b.driver_id === driverId ? { ...b, status: 'rejected' } : b)),
          };
        }
        return o;
      })
    );
  };

  const closeAndChargeOrder = (orderId: number, driverId: number, customCommission?: number) => {
    const order = orders.find((o) => o.order_id === orderId);
    const station = stations.find((s) => s.station_id === (order?.station_id || currentUser.station_id)) || {
      station_id: 1,
      name: 'תחנה ראשית',
      commission_percent: 10.0,
    };
    const debtAmount = customCommission !== undefined ? customCommission : calculateCommission(order?.price || 0, station.commission_percent);

    chargeDriverDebt(driverId, debtAmount, `עמלת נסיעה #${orderId} (${station.name})`, station.station_id, orderId);

    setOrders((prev) =>
      prev.map((o) => (o.order_id === orderId ? { ...o, status: 'closed', driver_id: driverId } : o))
    );

    return { success: true, debtAmount };
  };

  const republishOrder = (orderId: number) => {
    setOrders((prev) =>
      prev.map((o) => (o.order_id === orderId ? { ...o, status: 'open', driver_id: null, bids: [] } : o))
    );
  };

  const cancelOrder = (orderId: number) => {
    setOrders((prev) =>
      prev.map((o) => (o.order_id === orderId ? { ...o, status: 'cancelled' } : o))
    );
  };

  // Manual close directly on driver
  const manualCloseOrder = async (payload: {
    text: string;
    price: number;
    driverId: number;
    stationId: number;
    clientPhone?: string;
    commissionPercent?: number;
  }) => {
    try {
      const commRate = payload.commissionPercent || 10.0;
      const debtAmount = calculateCommission(payload.price, commRate);

      const res = await fetch('/api/orders/publish', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          raw_text: payload.text,
          price: payload.price,
          publisher_id: currentUser.user_id,
          station_id: payload.stationId,
          destination_type: 'manual',
          client_phone: payload.clientPhone || '',
        }),
      });
      const data = await res.json();
      const orderId = data.order_id || Math.floor(2000 + Math.random() * 5000);

      await chargeDriverDebt(payload.driverId, debtAmount, `סגירה ידנית קריאה #${orderId}`, payload.stationId, orderId);

      refreshAllData();
      return { success: true, orderId, debtAmount };
    } catch (err: any) {
      console.error('🚨 [manualCloseOrder Error]:', err);
      return { success: false, error: 'שגיאה בסגירה ידנית' };
    }
  };

  const rateDriver = (driverId: number, stars: number) => {
    setUsers((prev) =>
      prev.map((u) => {
        if (u.user_id === driverId) {
          const trips = (u.total_trips || 0) + 1;
          const newRating = Number((((u.rating || 5.0) * (trips - 1) + stars) / trips).toFixed(1));
          return { ...u, rating: newRating, total_trips: trips };
        }
        return u;
      })
    );
  };

  const deleteOrder = (orderId: number) => {
    setOrders((prev) => prev.filter((o) => o.order_id !== orderId));
  };

  // Debt operations
  const acknowledgeDebt = (debtId: number) => {
    setDebts((prev) =>
      prev.map((d) => (d.debt_id === debtId ? { ...d, is_locked: 1, appeal_status: 'confirmed' } : d))
    );
  };

  const submitDebtAppeal = (debtId: number, reason: string): boolean => {
    setDebts((prev) =>
      prev.map((d) =>
        d.debt_id === debtId
          ? { ...d, appeal_status: 'pending', appeal_reason: reason }
          : d
      )
    );
    return true;
  };

  const resolveDebtAppeal = async (debtId: number, approve: boolean): Promise<boolean> => {
    try {
      const res = await fetch('/api/debts/resolve_appeal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          debt_id: debtId,
          approved: approve,
          manager_id: currentUser.user_id,
        }),
      });
      const data = await res.json();
      if (data.ok) {
        setDebts((prev) =>
          prev.map((d) => {
            if (d.debt_id === debtId) {
              return {
                ...d,
                status: approve ? 'cancelled' : d.status,
                appeal_status: approve ? 'approved' : 'rejected',
              };
            }
            return d;
          })
        );
        refreshAllData();
        return true;
      }
      return false;
    } catch (err) {
      console.error('🚨 [resolveDebtAppeal Error]:', err);
      return false;
    }
  };

  const chargeDriverDebt = async (
    driverId: number,
    amount: number,
    reason: string,
    stationId: number,
    orderId?: number
  ) => {
    try {
      const res = await fetch('/api/debts/charge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          driver_id: driverId,
          amount,
          reason,
          station_id: stationId,
          order_id: orderId,
        }),
      });
      const data = await res.json();
      if (data.ok) {
        refreshAllData();
      }
    } catch (err) {
      console.error('🚨 [chargeDriverDebt Error]:', err);
    }
  };

  const updateDebt = async (debtId: number, updates: { amount?: number; reason?: string; station_id?: number; status?: 'unpaid' | 'paid' | 'cancelled' }) => {
    try {
      await fetch('/api/debts/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ debt_id: debtId, ...updates }),
      });
      refreshAllData();
    } catch (err) {
      console.error('🚨 [updateDebt Error]:', err);
    }
  };

  const deleteDebt = async (debtId: number) => {
    try {
      await fetch('/api/debts/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ debt_id: debtId }),
      });
      refreshAllData();
    } catch (err) {
      console.error('🚨 [deleteDebt Error]:', err);
    }
  };

  // Station CRUD (returns Station synchronously for instant UI responsiveness)
  const createStation = (name: string, commissionPercent: number): Station => {
    const tempId = Math.floor(100 + Math.random() * 900);
    const newStation: Station = {
      station_id: tempId,
      name,
      commission_percent: commissionPercent,
      is_active: true,
    };
    setStations((prev) => [...prev, newStation]);

    // Send to backend in background
    fetch('/api/stations/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, commission_percent: commissionPercent }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.ok && data.station_id) {
          setStations((prev) =>
            prev.map((s) => (s.station_id === tempId ? { ...s, station_id: data.station_id } : s))
          );
        }
      })
      .catch((err) => console.error('🚨 [createStation Server Error]:', err));

    return newStation;
  };

  const updateStation = async (stationId: number, name: string, commissionPercent: number): Promise<boolean> => {
    try {
      const res = await fetch('/api/stations/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ station_id: stationId, name, commission_percent: commissionPercent }),
      });
      const data = await res.json();
      if (data.ok) {
        setStations((prev) =>
          prev.map((s) =>
            s.station_id === stationId ? { ...s, name, commission_percent: commissionPercent } : s
          )
        );
        return true;
      }
      return false;
    } catch (err) {
      console.error('🚨 [updateStation Error]:', err);
      return false;
    }
  };

  // User management
  const updateUserRoleAndStation = async (
    targetId: number,
    newRole: Role | 'blocked',
    stationId: number,
    subscriptionPlan?: string
  ) => {
    try {
      await fetch('/api/users/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: targetId,
          role: newRole,
          station_id: stationId,
          subscription_plan: subscriptionPlan,
        }),
      });
      setUsers((prev) =>
        prev.map((u) => {
          if (u.user_id === targetId) {
            const actualRole = newRole === 'blocked' ? u.role : newRole;
            const isBlocked = newRole === 'blocked' ? 1 : 0;
            return {
              ...u,
              role: actualRole,
              is_blocked: isBlocked,
              station_id: stationId,
              subscription_plan: subscriptionPlan || u.subscription_plan,
            };
          }
          return u;
        })
      );
      if (currentUser.user_id === targetId) {
        setCurrentUser((prev) => ({
          ...prev,
          role: newRole === 'blocked' ? prev.role : newRole,
          is_blocked: newRole === 'blocked' ? 1 : 0,
          station_id: stationId,
          subscription_plan: subscriptionPlan || prev.subscription_plan,
        }));
      }
    } catch (err) {
      console.error('🚨 [updateUserRoleAndStation Error]:', err);
    }
  };

  const sendBroadcast = async (text: string): Promise<number> => {
    try {
      const res = await fetch('/api/broadcast', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      const data = await res.json();
      const newB: BroadcastMessage = {
        id: 'bc_' + Date.now(),
        text,
        sender_name: currentUser.full_name || 'מנהל מערכת',
        created_at: new Date().toISOString(),
      };
      setBroadcasts((prev) => [newB, ...prev]);
      return data.count || users.length;
    } catch (err) {
      console.error('🚨 [sendBroadcast Error]:', err);
      return 0;
    }
  };

  return (
    <AppContext.Provider
      value={{
        currentUser,
        users,
        stations,
        orders,
        debts,
        driverCities,
        botGroups,
        broadcasts,
        switchUser,
        registerUser,
        toggleDriverStatus,
        addDriverCity,
        removeDriverCity,
        clearDriverCities,
        getDriverCities,
        publishOrder,
        submitOrderBid,
        approveDriverOrder,
        denyDriverOrder,
        closeAndChargeOrder,
        republishOrder,
        cancelOrder,
        manualCloseOrder,
        rateDriver,
        deleteOrder,
        acknowledgeDebt,
        submitDebtAppeal,
        resolveDebtAppeal,
        createStation,
        updateStation,
        updateUserRoleAndStation,
        chargeDriverDebt,
        updateDebt,
        deleteDebt,
        sendBroadcast,
        refreshAllData,
        resetToInitialData: refreshAllData,
        isTelegramWebApp,
        isAuthLoading,
        isAuthenticated,
        authError,
      }}
    >
      {children}
    </AppContext.Provider>
  );
};

export const useApp = () => {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error('useApp must be used within an AppProvider');
  }
  return context;
};
