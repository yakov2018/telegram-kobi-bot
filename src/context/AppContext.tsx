import React, { createContext, useContext, useState, useEffect } from 'react';
import { User, Station, Order, Debt, DriverCity, BotGroup, BroadcastMessage, Role } from '../types';
import {
  INITIAL_STATIONS,
  INITIAL_USERS,
  INITIAL_DRIVER_CITIES,
  INITIAL_ORDERS,
  INITIAL_DEBTS,
  INITIAL_BOT_GROUPS,
} from '../mockData';
import {
  cleanOrderText,
  extractOrderPrice,
  calculateCommission,
  calculateNewRating,
} from '../utils/orderUtils';

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
  toggleDriverStatus: (userId?: number) => { success: boolean; message: string; newStatus?: 'free' | 'busy' };
  addDriverCity: (userId: number, cityName: string) => void;
  removeDriverCity: (userId: number, cityName: string) => void;
  clearDriverCities: (userId: number) => void;
  getDriverCities: (userId: number) => string[];
  publishOrder: (
    rawText: string,
    destinationType: 'private' | 'groups',
    customPrice?: number
  ) => { order: Order; eligibleDriversCount: number };
  submitOrderBid: (orderId: number, driverId: number, etaMinutes: number) => { success: boolean; message: string };
  approveDriverOrder: (orderId: number, driverId: number) => { success: boolean; debtAmount: number };
  denyDriverOrder: (orderId: number, driverId: number) => void;
  rateDriver: (driverId: number, stars: number) => void;
  deleteOrder: (orderId: number) => void;
  submitDebtAppeal: (debtId: number, reason: string) => boolean;
  resolveDebtAppeal: (debtId: number, approve: boolean) => void;
  createStation: (name: string, commissionPercent: number) => Station;
  updateUserRoleAndStation: (targetId: number, newRole: Role | 'blocked', stationId: number) => void;
  sendBroadcast: (text: string) => number;
  resetToInitialData: () => void;
  isTelegramWebApp: boolean;
}

const AppContext = createContext<AppContextType | null>(null);

const STORAGE_PREFIX = 'kobi_erp_bot_';

export const AppProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // Initialize state from localStorage or mock defaults
  const [users, setUsers] = useState<User[]>(() => {
    const saved = localStorage.getItem(STORAGE_PREFIX + 'users');
    return saved ? JSON.parse(saved) : INITIAL_USERS;
  });

  const [currentUserId, setCurrentUserId] = useState<number>(() => {
    const saved = localStorage.getItem(STORAGE_PREFIX + 'current_user_id');
    return saved ? JSON.parse(saved) : 8644923212; // Default to Admin
  });

  const [stations, setStations] = useState<Station[]>(() => {
    const saved = localStorage.getItem(STORAGE_PREFIX + 'stations');
    return saved ? JSON.parse(saved) : INITIAL_STATIONS;
  });

  const [orders, setOrders] = useState<Order[]>(() => {
    const saved = localStorage.getItem(STORAGE_PREFIX + 'orders');
    return saved ? JSON.parse(saved) : INITIAL_ORDERS;
  });

  const [debts, setDebts] = useState<Debt[]>(() => {
    const saved = localStorage.getItem(STORAGE_PREFIX + 'debts');
    return saved ? JSON.parse(saved) : INITIAL_DEBTS;
  });

  const [driverCities, setDriverCities] = useState<DriverCity[]>(() => {
    const saved = localStorage.getItem(STORAGE_PREFIX + 'driver_cities');
    return saved ? JSON.parse(saved) : INITIAL_DRIVER_CITIES;
  });

  const [botGroups] = useState<BotGroup[]>(INITIAL_BOT_GROUPS);

  const [broadcasts, setBroadcasts] = useState<BroadcastMessage[]>(() => {
    const saved = localStorage.getItem(STORAGE_PREFIX + 'broadcasts');
    return saved
      ? JSON.parse(saved)
      : [
          {
            id: 'b1',
            text: 'ברוכים הבאים למערכת ה-ERP המתקדמת לניהול תחנות מוניות ומשלוחים!',
            sender_name: 'הנהלת המערכת',
            created_at: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
          },
        ];
  });

  // Sync to localStorage
  useEffect(() => {
    localStorage.setItem(STORAGE_PREFIX + 'users', JSON.stringify(users));
  }, [users]);

  useEffect(() => {
    localStorage.setItem(STORAGE_PREFIX + 'current_user_id', JSON.stringify(currentUserId));
  }, [currentUserId]);

  useEffect(() => {
    localStorage.setItem(STORAGE_PREFIX + 'stations', JSON.stringify(stations));
  }, [stations]);

  useEffect(() => {
    localStorage.setItem(STORAGE_PREFIX + 'orders', JSON.stringify(orders));
  }, [orders]);

  useEffect(() => {
    localStorage.setItem(STORAGE_PREFIX + 'debts', JSON.stringify(debts));
  }, [debts]);

  useEffect(() => {
    localStorage.setItem(STORAGE_PREFIX + 'driver_cities', JSON.stringify(driverCities));
  }, [driverCities]);

  useEffect(() => {
    localStorage.setItem(STORAGE_PREFIX + 'broadcasts', JSON.stringify(broadcasts));
  }, [broadcasts]);

  const [isTelegramWebApp, setIsTelegramWebApp] = useState<boolean>(false);

  const ADMIN_IDS = [8644923212, 552821474];

  // וידוא מוחלט שרשומות מנהלי המערכת מקבלות תמיד תפקיד admin
  useEffect(() => {
    setUsers((prev) => {
      let changed = false;
      const updated = prev.map((u) => {
        if (ADMIN_IDS.includes(u.user_id) && u.role !== 'admin') {
          changed = true;
          return { ...u, role: 'admin' as Role, is_blocked: 0 };
        }
        return u;
      });
      return changed ? updated : prev;
    });
  }, []);

  // Auto-detect Telegram WebApp environment & Authenticate via REST API
  useEffect(() => {
    const tg = (window as any).Telegram?.WebApp;
    if (tg) {
      try {
        tg.ready();
        tg.expand();
        setIsTelegramWebApp(true);

        const tgUser = tg.initDataUnsafe?.user;
        const userNumId = tgUser?.id ? Number(tgUser.id) : null;
        const isAdmin = userNumId ? ADMIN_IDS.includes(userNumId) : false;

        if (userNumId) {
          const fullName = [tgUser.first_name, tgUser.last_name].filter(Boolean).join(' ') || tgUser.username || `מנהל טלגרם ${userNumId}`;
          setUsers((prev) => {
            const exists = prev.find((u) => u.user_id === userNumId);
            if (!exists) {
              const newTgDriver: User = {
                user_id: userNumId,
                full_name: fullName,
                phone: '0500000000',
                birth_year: 1995,
                car_brand: 'טויוטה',
                car_model: 'קורולה',
                car_year: 2022,
                car_seats: 5,
                status: 'free',
                role: isAdmin ? 'admin' : 'user',
                station_id: 1,
                rating: 5.0,
                total_trips: 0,
                is_blocked: 0,
                debt_balance: 0.0,
              };
              return [...prev, newTgDriver];
            } else if (isAdmin && exists.role !== 'admin') {
              return prev.map((u) => (u.user_id === userNumId ? { ...u, role: 'admin', is_blocked: 0 } : u));
            }
            return prev;
          });
          setCurrentUserId(userNumId);
        }

        // שליחת initData לאימות קריפטוגרפי וסנכרון תפקיד מול שרת ה-API
        fetch('/api/auth', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            initData: tg.initData || '',
            user_id: userNumId,
            dev_user_id: userNumId,
          }),
        })
          .then((res) => res.json())
          .then((data) => {
            if (data.ok && data.user) {
              const isServerAdmin = ADMIN_IDS.includes(Number(data.user.user_id)) || data.user.role === 'admin';
              const serverUser: User = {
                user_id: Number(data.user.user_id),
                full_name: data.user.full_name,
                phone: data.user.phone || '0500000000',
                birth_year: data.user.birth_year || 1995,
                car_brand: data.user.car_brand || 'טויוטה',
                car_model: data.user.car_model || 'קורולה',
                car_year: data.user.car_year || 2022,
                car_seats: data.user.car_seats || 5,
                status: data.user.status || 'free',
                role: isServerAdmin ? 'admin' : (data.user.role || 'user'),
                station_id: data.user.station_id || 1,
                rating: Number(data.user.rating || 5.0),
                total_trips: Number(data.user.total_trips || 0),
                is_blocked: isServerAdmin ? 0 : (data.user.is_blocked ? 1 : 0),
                debt_balance: Number(data.user.debt_balance || 0.0),
              };

              setUsers((prev) => {
                const idx = prev.findIndex((u) => u.user_id === serverUser.user_id);
                if (idx >= 0) {
                  const updated = [...prev];
                  updated[idx] = serverUser;
                  return updated;
                }
                return [...prev, serverUser];
              });
              setCurrentUserId(serverUser.user_id);

              if (data.stations && Array.isArray(data.stations) && data.stations.length > 0) {
                setStations(
                  data.stations.map((s: any) => ({
                    station_id: Number(s.station_id),
                    name: s.name,
                    commission_percent: Number(s.commission_percent),
                  }))
                );
              }
            }
          })
          .catch((err) => {
            console.warn('API /api/auth sync note:', err);
          });
      } catch (err) {
        console.warn('Telegram WebApp init note:', err);
      }
    }
  }, []);

  // Current active user
  const currentUser = users.find((u) => u.user_id === currentUserId) || users[0];

  const switchUser = (userId: number) => {
    const found = users.find((u) => u.user_id === userId);
    if (found) {
      setCurrentUserId(userId);
    }
  };

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
    };

    setUsers((prev) => [...prev, newUser]);
    setCurrentUserId(newId);
    return newUser;
  };

  // Toggle driver free/busy status with Auto-Freeze debt check (bot.py line 276)
  const toggleDriverStatus = (userId?: number) => {
    const targetId = userId ?? currentUserId;
    const user = users.find((u) => u.user_id === targetId);

    if (!user) {
      return { success: false, message: 'משתמש לא נמצא.' };
    }

    if (user.is_blocked) {
      return { success: false, message: '❌ חשבונך נחסם ע"י הנהלת המערכת.' };
    }

    // Auto-Freeze rule: Debt balance > 500 NIS
    if (user.debt_balance > 500.0) {
      return {
        success: false,
        message: '🚫 חשבונך מוקפא עקב חובות (מעל 500 ש"ח)! לא תוכל לקבל קריאות עד הסדרת החוב.',
      };
    }

    const newStatus: 'free' | 'busy' = user.status === 'free' ? 'busy' : 'free';

    setUsers((prev) =>
      prev.map((u) => (u.user_id === targetId ? { ...u, status: newStatus } : u))
    );

    const message =
      newStatus === 'free'
        ? '🟢 אתה כעת פנוי לעבודה (קריאות באזורים שלך יקפצו)!'
        : '🔴 עצרת קריאות (סטטוס תפוס).';

    return { success: true, message, newStatus };
  };

  const getDriverCities = (userId: number): string[] => {
    return driverCities.filter((dc) => dc.user_id === userId).map((dc) => dc.city_name);
  };

  const addDriverCity = (userId: number, cityName: string) => {
    const trimmed = cityName.trim();
    if (!trimmed) return;
    setDriverCities((prev) => {
      if (prev.some((dc) => dc.user_id === userId && dc.city_name === trimmed)) {
        return prev;
      }
      return [...prev, { user_id: userId, city_name: trimmed }];
    });
  };

  const removeDriverCity = (userId: number, cityName: string) => {
    setDriverCities((prev) =>
      prev.filter((dc) => !(dc.user_id === userId && dc.city_name === cityName))
    );
  };

  const clearDriverCities = (userId: number) => {
    setDriverCities((prev) => prev.filter((dc) => dc.user_id !== userId));
  };

  // Publish order with text cleaning and driver matching
  const publishOrder = (
    rawText: string,
    destinationType: 'private' | 'groups',
    customPrice?: number
  ) => {
    const cleaned = cleanOrderText(rawText);
    const price = customPrice !== undefined ? customPrice : extractOrderPrice(cleaned);
    const newOrderId = Math.max(1000, ...orders.map((o) => o.order_id)) + 1;

    const newOrder: Order = {
      order_id: newOrderId,
      text: cleaned,
      price: price,
      publisher_id: currentUser.user_id,
      station_id: currentUser.station_id || 1,
      driver_id: null,
      status: 'open',
      created_at: new Date().toISOString(),
      destination_type: destinationType,
      bids: [],
    };

    // Calculate eligible drivers matching city & status & debt <= 500
    let eligibleCount = 0;
    if (destinationType === 'private') {
      const freeDrivers = users.filter(
        (u) =>
          u.role === 'user' &&
          u.status === 'free' &&
          !u.is_blocked &&
          u.debt_balance <= 500
      );

      eligibleCount = freeDrivers.filter((driver) => {
        const userCities = driverCities
          .filter((dc) => dc.user_id === driver.user_id)
          .map((dc) => dc.city_name);
        if (userCities.length === 0) return true; // gets all if no cities set
        return userCities.some((c) => cleaned.includes(c));
      }).length;
    } else {
      eligibleCount = botGroups.length;
    }

    setOrders((prev) => [newOrder, ...prev]);

    return { order: newOrder, eligibleDriversCount: eligibleCount };
  };

  // Driver submits ETA bid for an order
  const submitOrderBid = (orderId: number, driverId: number, etaMinutes: number) => {
    const order = orders.find((o) => o.order_id === orderId);
    const driver = users.find((u) => u.user_id === driverId);

    if (!order || order.status !== 'open') {
      return { success: false, message: '❌ איחרת! הקריאה כבר נתפסה או בוטלה.' };
    }

    if (!driver) {
      return { success: false, message: 'נהג לא נמצא.' };
    }

    if (driver.status !== 'free') {
      return { success: false, message: '⚠️ אתה בסטטוס תפוס! העבר ל-פנוי קודם.' };
    }

    const newBid = {
      driver_id: driver.user_id,
      driver_name: driver.full_name,
      rating: driver.rating,
      car_brand: driver.car_brand,
      car_model: driver.car_model,
      car_seats: driver.car_seats,
      eta_minutes: etaMinutes,
      submitted_at: new Date().toISOString(),
    };

    setOrders((prev) =>
      prev.map((o) => {
        if (o.order_id === orderId) {
          const currentBids = o.bids || [];
          const exists = currentBids.some((b) => b.driver_id === driverId);
          const updatedBids = exists
            ? currentBids.map((b) => (b.driver_id === driverId ? newBid : b))
            : [...currentBids, newBid];
          return { ...o, bids: updatedBids };
        }
        return o;
      })
    );

    return {
      success: true,
      message: '⏳ הבקשה וזמן ההגעה נשלחו בהצלחה לסדרן. ממתין לאישור...',
    };
  };

  // Dispatcher approves driver for order
  const approveDriverOrder = (orderId: number, driverId: number) => {
    const order = orders.find((o) => o.order_id === orderId);
    if (!order || order.status !== 'open') {
      return { success: false, debtAmount: 0 };
    }

    const station = stations.find((s) => s.station_id === order.station_id) || stations[0];
    const commPercent = station ? station.commission_percent : 10.0;
    const debtAmount = calculateCommission(order.price, commPercent);

    // 1. Close order
    setOrders((prev) =>
      prev.map((o) =>
        o.order_id === orderId ? { ...o, status: 'closed', driver_id: driverId } : o
      )
    );

    // 2. Add debt record if commission > 0
    if (debtAmount > 0) {
      const newDebtId = Math.max(500, ...debts.map((d) => d.debt_id)) + 1;
      const newDebt: Debt = {
        debt_id: newDebtId,
        order_id: orderId,
        driver_id: driverId,
        station_id: order.station_id,
        amount: debtAmount,
        status: 'unpaid',
        reason: `עמלה ${commPercent}%`,
        appeal_status: 'none',
      };
      setDebts((prev) => [newDebt, ...prev]);
    }

    // 3. Update driver debt_balance and total_trips
    setUsers((prev) =>
      prev.map((u) => {
        if (u.user_id === driverId) {
          return {
            ...u,
            debt_balance: Math.round((u.debt_balance + debtAmount) * 100) / 100,
            total_trips: u.total_trips + 1,
          };
        }
        return u;
      })
    );

    return { success: true, debtAmount };
  };

  // Dispatcher denies driver bid
  const denyDriverOrder = (orderId: number, driverId: number) => {
    setOrders((prev) =>
      prev.map((o) => {
        if (o.order_id === orderId && o.bids) {
          return { ...o, bids: o.bids.filter((b) => b.driver_id !== driverId) };
        }
        return o;
      })
    );
  };

  // Dispatcher rates driver (1-5 stars)
  const rateDriver = (driverId: number, stars: number) => {
    setUsers((prev) =>
      prev.map((u) => {
        if (u.user_id === driverId) {
          const newRating = calculateNewRating(u.rating, u.total_trips, stars);
          return { ...u, rating: newRating };
        }
        return u;
      })
    );
  };

  // Dispatcher deletes open order
  const deleteOrder = (orderId: number) => {
    setOrders((prev) =>
      prev.map((o) => (o.order_id === orderId ? { ...o, status: 'deleted' } : o))
    );
  };

  // Driver submits appeal on debt
  const submitDebtAppeal = (debtId: number, reason: string) => {
    setDebts((prev) =>
      prev.map((d) => {
        if (d.debt_id === debtId) {
          return {
            ...d,
            appeal_reason: reason,
            appeal_status: 'pending',
          };
        }
        return d;
      })
    );
    return true;
  };

  // Admin resolves appeal
  const resolveDebtAppeal = (debtId: number, approve: boolean) => {
    const debt = debts.find((d) => d.debt_id === debtId);
    if (!debt) return;

    if (approve && debt.status === 'unpaid') {
      // Cancel debt and deduct from driver balance
      setDebts((prev) =>
        prev.map((d) =>
          d.debt_id === debtId
            ? { ...d, status: 'cancelled', appeal_status: 'approved' }
            : d
        )
      );

      setUsers((prev) =>
        prev.map((u) => {
          if (u.user_id === debt.driver_id) {
            const newBal = Math.max(0, Math.round((u.debt_balance - debt.amount) * 100) / 100);
            return { ...u, debt_balance: newBal };
          }
          return u;
        })
      );
    } else {
      // Reject appeal - debt remains
      setDebts((prev) =>
        prev.map((d) =>
          d.debt_id === debtId ? { ...d, appeal_status: 'rejected' } : d
        )
      );
    }
  };

  // Admin creates new station
  const createStation = (name: string, commissionPercent: number): Station => {
    const newStationId = Math.max(1, ...stations.map((s) => s.station_id)) + 1;
    const newStation: Station = {
      station_id: newStationId,
      name,
      commission_percent: commissionPercent,
    };
    setStations((prev) => [...prev, newStation]);
    return newStation;
  };

  // Admin God Mode: Update user role and station assignment
  const updateUserRoleAndStation = (
    targetId: number,
    newRole: Role | 'blocked',
    stationId: number
  ) => {
    const isBlocked = newRole === 'blocked' ? 1 : 0;
    const roleToSave: Role = newRole === 'blocked' ? 'user' : newRole;

    setUsers((prev) =>
      prev.map((u) =>
        u.user_id === targetId
          ? {
              ...u,
              role: roleToSave,
              station_id: stationId,
              is_blocked: isBlocked,
            }
          : u
      )
    );
  };

  // Admin broadcast to all users
  const sendBroadcast = (text: string): number => {
    const newMsg: BroadcastMessage = {
      id: 'b_' + Date.now(),
      text,
      sender_name: currentUser.full_name,
      created_at: new Date().toISOString(),
    };
    setBroadcasts((prev) => [newMsg, ...prev]);
    return users.length;
  };

  // Reset to initial mock data
  const resetToInitialData = () => {
    localStorage.clear();
    setUsers(INITIAL_USERS);
    setCurrentUserId(8644923212);
    setStations(INITIAL_STATIONS);
    setOrders(INITIAL_ORDERS);
    setDebts(INITIAL_DEBTS);
    setDriverCities(INITIAL_DRIVER_CITIES);
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
        rateDriver,
        deleteOrder,
        submitDebtAppeal,
        resolveDebtAppeal,
        createStation,
        updateUserRoleAndStation,
        sendBroadcast,
        resetToInitialData,
        isTelegramWebApp,
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
