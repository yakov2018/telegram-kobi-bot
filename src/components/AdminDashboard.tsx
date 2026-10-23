import React, { useState } from 'react';
import { useApp } from '../context/AppContext';
import { ROLE_NAMES, Role, User } from '../types';
import {
  Shield,
  Building,
  Users,
  Radio,
  Plus,
  Scale,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Send,
  Search,
  Lock,
  Unlock,
  Percent,
  Sliders,
  Crown,
  Sparkles,
  RefreshCw,
  Car,
  Calendar,
  Layers,
  ArrowRight,
} from 'lucide-react';
import { DispatcherPanel } from './DispatcherPanel';
import { DriverPanel } from './DriverPanel';

export const AdminDashboard: React.FC = () => {
  const {
    currentUser,
    users,
    stations,
    debts,
    orders,
    broadcasts,
    createStation,
    updateStation,
    updateUserRoleAndStation,
    chargeDriverDebt,
    updateDebt,
    deleteDebt,
    resolveDebtAppeal,
    sendBroadcast,
    resetToInitialData,
  } = useApp();

  // סעיף אבטחה קשיחה: אם המשתמש אינו מנהל מערכת, הקומפוננטה חוסמת גישה מיידית
  if (currentUser.role !== 'admin') {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-2xl p-6 text-center text-red-300 font-bold my-8">
        ⛔ גישה חסומה: פאנל ניהול המערכת מיועד אך ורק למנהלי מערכת מורשים (Super Admin).
      </div>
    );
  }

  const [activeTab, setActiveTab] = useState<'users' | 'system' | 'subscriptions' | 'stations' | 'appeals' | 'broadcast'>('users');
  const [simulationView, setSimulationView] = useState<'none' | 'dispatcher' | 'driver'>('none');
  const [searchUser, setSearchUser] = useState('');

  // Modals state for Stations, User Role & Station assignment, and Debts CRUD
  const [editStationModal, setEditStationModal] = useState<{
    isOpen: boolean;
    station_id: number;
    name: string;
    commission_percent: string;
  }>({
    isOpen: false,
    station_id: 0,
    name: '',
    commission_percent: '10.0',
  });

  const [editUserModal, setEditUserModal] = useState<{
    isOpen: boolean;
    user: User | null;
    role: Role | 'blocked';
    station_id: number;
    subscription_plan: string;
  }>({
    isOpen: false,
    user: null,
    role: 'user',
    station_id: 1,
    subscription_plan: 'free',
  });

  const [chargeDebtModal, setChargeDebtModal] = useState<{
    isOpen: boolean;
    driver_id: number;
    amount: string;
    reason: string;
    station_id: number;
    order_id: string;
  }>({
    isOpen: false,
    driver_id: 0,
    amount: '20',
    reason: 'עמלת נסיעה (🍓)',
    station_id: currentUser.station_id || 1,
    order_id: '',
  });

  const [editDebtModal, setEditDebtModal] = useState<{
    isOpen: boolean;
    debt_id: number;
    amount: string;
    reason: string;
    station_id: number;
    status: 'unpaid' | 'paid' | 'cancelled';
  }>({
    isOpen: false,
    debt_id: 0,
    amount: '0',
    reason: '',
    station_id: 1,
    status: 'unpaid',
  });

  // New station state
  const [stationName, setStationName] = useState('');
  const [stationComm, setStationComm] = useState('10.0');
  const [stationSuccess, setStationSuccess] = useState<string | null>(null);

  // Broadcast state
  const [broadcastText, setBroadcastText] = useState('');
  const [broadcastSuccess, setBroadcastSuccess] = useState<string | null>(null);

  // System Settings state
  const [defaultCommission, setDefaultCommission] = useState('10.0');
  const [autoFreezeThreshold, setAutoFreezeThreshold] = useState('500');
  const [freeTripsLimit, setFreeTripsLimit] = useState('3');
  const [cityAliasKey, setCityAliasKey] = useState('');
  const [cityAliasVal, setCityAliasVal] = useState('');
  const [settingsSuccess, setSettingsSuccess] = useState<string | null>(null);

  // Aliases list in memory for display
  const [customAliases, setCustomAliases] = useState<Array<{ alias: string; standard: string }>>([
    { alias: 'ים', standard: 'ירושלים' },
    { alias: 'בב', standard: 'בני ברק' },
    { alias: 'פת', standard: 'פתח תקווה' },
    { alias: 'תא', standard: 'תל אביב' },
    { alias: 'קס', standard: 'מודיעין עילית' },
    { alias: 'אשד', standard: 'אשדוד' },
    { alias: 'ב"ש', standard: 'בית שמש' },
  ]);

  const pendingAppeals = debts.filter((d) => d.appeal_status === 'pending');
  const openOrdersCount = orders.filter((o) => o.status === 'open').length;
  const activeDriversCount = users.filter((u) => u.role === 'user' && u.status === 'free' && !u.is_blocked).length;
  const totalDebtsSum = users.reduce((sum, u) => sum + (u.debt_balance || 0), 0);

  const filteredUsers = users.filter(
    (u) =>
      u.full_name.includes(searchUser) ||
      u.phone.includes(searchUser) ||
      u.user_id.toString().includes(searchUser)
  );

  const handleCreateStation = (e: React.FormEvent) => {
    e.preventDefault();
    if (!stationName.trim()) return;
    const comm = parseFloat(stationComm);
    if (isNaN(comm) || comm < 0) {
      setStationSuccess('⚠️ נא להזין אחוז עמלה תקין');
      setTimeout(() => setStationSuccess(null), 3000);
      return;
    }
    const newSt = createStation(stationName.trim(), comm);
    setStationName('');
    setStationComm('10.0');
    setStationSuccess(`✅ תחנה "${newSt.name}" (#${newSt.station_id}) נוצרה בהצלחה עם ${comm}% עמלה!`);
    setTimeout(() => setStationSuccess(null), 4000);
  };

  const handleSendBroadcast = (e: React.FormEvent) => {
    e.preventDefault();
    if (!broadcastText.trim()) return;
    const count = sendBroadcast(broadcastText.trim());
    setBroadcastText('');
    setBroadcastSuccess(`✅ הודעת Broadcast שודרה בהצלחה ל-${count} משתמשי המערכת!`);
    setTimeout(() => setBroadcastSuccess(null), 5000);
  };

  const handleSaveSettings = (e: React.FormEvent) => {
    e.preventDefault();
    setSettingsSuccess('✅ הגדרות המערכת הגלובליות נשמרו בהצלחה!');
    setTimeout(() => setSettingsSuccess(null), 4000);
  };

  const handleAddAlias = (e: React.FormEvent) => {
    e.preventDefault();
    if (!cityAliasKey.trim() || !cityAliasVal.trim()) return;
    setCustomAliases((prev) => [...prev, { alias: cityAliasKey.trim(), standard: cityAliasVal.trim() }]);
    setCityAliasKey('');
    setCityAliasVal('');
    setSettingsSuccess('✅ קיצור עיר חדש נוסף למילון ה-NLP של המערכת!');
    setTimeout(() => setSettingsSuccess(null), 3000);
  };

  // אבטחה קשיחה (Protected Component): חסימת כל משתמש שאינו מנהל מערכת (Super Admin)
  if (currentUser.role !== 'admin') {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6 text-center font-sans" dir="rtl">
        <div className="w-16 h-16 rounded-2xl bg-red-500/10 border border-red-500/30 flex items-center justify-center text-3xl mb-4 text-red-400">
          🚫
        </div>
        <h2 className="text-xl font-extrabold text-white mb-2">גישה חסומה</h2>
        <p className="text-sm text-slate-400 max-w-sm mb-6">
          פאנל ניהול המערכת (Super Admin) מוגבל למנהלי מערכת בלבד. אין לך הרשאות לצפות בדף זה.
        </p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans" dir="rtl">
      {/* Top Admin Sticky Bar */}
      <header className="sticky top-0 z-50 bg-slate-900/95 backdrop-blur-md border-b border-amber-500/30 p-3.5 shadow-lg shadow-amber-500/5">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-amber-500 via-amber-400 to-amber-600 flex items-center justify-center text-slate-950 font-black text-xl shadow-md">
              👑
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="font-extrabold text-base text-white tracking-wide flex items-center gap-1.5">
                  <span>פאנל מנהל ראשי</span>
                  <span className="text-[11px] bg-gradient-to-r from-amber-500 to-amber-600 text-slate-950 px-2 py-0.5 rounded-full font-black uppercase shadow-sm">
                    GOD MODE
                  </span>
                </h1>
                <span className="text-[11px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 px-2 py-0.5 rounded-md font-mono">
                  LIVE API SYNC
                </span>
              </div>
              <p className="text-xs text-slate-400">
                מחובר: <strong className="text-amber-300">{currentUser.full_name}</strong> (מזהה טלגרם: <span className="font-mono">{currentUser.user_id}</span>)
              </p>
            </div>
          </div>

          {/* Quick Simulation Mode Switcher */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400 hidden md:inline">תצוגת סימולטור:</span>
            <div className="flex bg-slate-950 p-1 rounded-xl border border-slate-800 text-xs">
              <button
                onClick={() => setSimulationView('none')}
                className={`px-3 py-1 rounded-lg font-bold transition ${
                  simulationView === 'none' ? 'bg-amber-500 text-slate-950' : 'text-slate-300 hover:text-white'
                }`}
              >
                פאנל ניהול
              </button>
              <button
                onClick={() => setSimulationView('dispatcher')}
                className={`px-3 py-1 rounded-lg font-bold transition ${
                  simulationView === 'dispatcher' ? 'bg-blue-600 text-white' : 'text-slate-300 hover:text-white'
                }`}
              >
                עמדת סדרן
              </button>
              <button
                onClick={() => setSimulationView('driver')}
                className={`px-3 py-1 rounded-lg font-bold transition ${
                  simulationView === 'driver' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:text-white'
                }`}
              >
                עמדת נהג
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Admin Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 space-y-6">
        {/* If simulating Dispatcher or Driver, render them with back button */}
        {simulationView === 'dispatcher' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between bg-blue-950/40 border border-blue-800/60 p-3 rounded-2xl text-xs text-blue-200">
              <span>תצוגת סימולציית סדרן (שיגור קריאות, חלוקה לנהגים ומעקב)</span>
              <button
                onClick={() => setSimulationView('none')}
                className="bg-blue-600 hover:bg-blue-500 text-white px-3 py-1 rounded-xl font-bold flex items-center gap-1"
              >
                <span>חזור לפאנל מנהל</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
            <DispatcherPanel />
          </div>
        )}

        {simulationView === 'driver' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between bg-emerald-950/40 border border-emerald-800/60 p-3 rounded-2xl text-xs text-emerald-200">
              <span>תצוגת סימולציית נהג (סטטוס פנוי/תפוס, אזורי פעילות וקבלת קריאות)</span>
              <button
                onClick={() => setSimulationView('none')}
                className="bg-emerald-600 hover:bg-emerald-500 text-white px-3 py-1 rounded-xl font-bold flex items-center gap-1"
              >
                <span>חזור לפאנל מנהל</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
            <DriverPanel />
          </div>
        )}

        {simulationView === 'none' && (
          <>
            {/* KPI Cards Strip */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
              <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 shadow-sm flex items-center justify-between">
                <div>
                  <span className="text-xs text-slate-400 block font-medium">סך הכל משתמשים ונהגים</span>
                  <span className="text-2xl font-black text-amber-400 mt-1 block">{users.length}</span>
                  <span className="text-[11px] text-emerald-400 mt-0.5 block">{activeDriversCount} פנויים לעבודה</span>
                </div>
                <div className="w-12 h-12 rounded-xl bg-amber-500/10 text-amber-400 flex items-center justify-center text-2xl font-bold border border-amber-500/20">
                  👥
                </div>
              </div>

              <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 shadow-sm flex items-center justify-between">
                <div>
                  <span className="text-xs text-slate-400 block font-medium">קריאות פתוחות כעת</span>
                  <span className="text-2xl font-black text-sky-400 mt-1 block">{openOrdersCount}</span>
                  <span className="text-[11px] text-slate-400 mt-0.5 block">סך הכל נסיעות: {users.reduce((acc, u) => acc + u.total_trips, 0)}</span>
                </div>
                <div className="w-12 h-12 rounded-xl bg-sky-500/10 text-sky-400 flex items-center justify-center text-2xl font-bold border border-sky-500/20">
                  🎫
                </div>
              </div>

              <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 shadow-sm flex items-center justify-between">
                <div>
                  <span className="text-xs text-slate-400 block font-medium">תחנות מורשות</span>
                  <span className="text-2xl font-black text-purple-400 mt-1 block">{stations.length}</span>
                  <span className="text-[11px] text-purple-300 mt-0.5 block">עמלה ממוצעת: 10%</span>
                </div>
                <div className="w-12 h-12 rounded-xl bg-purple-500/10 text-purple-400 flex items-center justify-center text-2xl font-bold border border-purple-500/20">
                  🏢
                </div>
              </div>

              <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 shadow-sm flex items-center justify-between">
                <div>
                  <span className="text-xs text-slate-400 block font-medium">חובות פתוחים במערכת</span>
                  <span className="text-2xl font-black text-red-400 mt-1 block">₪{totalDebtsSum.toFixed(2)}</span>
                  <span className="text-[11px] text-amber-400 mt-0.5 block">{pendingAppeals.length} ערעורים ממתינים</span>
                </div>
                <div className="w-12 h-12 rounded-xl bg-red-500/10 text-red-400 flex items-center justify-center text-2xl font-bold border border-red-500/20">
                  ⚖️
                </div>
              </div>
            </div>

            {/* Admin Tabs Bar - Explicit buttons requested by user */}
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-2 flex flex-wrap gap-2 shadow-sm">
              <button
                onClick={() => setActiveTab('users')}
                className={`flex-1 sm:flex-none py-2.5 px-4 rounded-xl text-xs font-bold transition flex items-center justify-center gap-2 ${
                  activeTab === 'users'
                    ? 'bg-amber-500 text-slate-950 shadow-md font-extrabold'
                    : 'bg-slate-950 text-slate-300 hover:text-white hover:bg-slate-800'
                }`}
              >
                <Users className="w-4 h-4" />
                <span>👥 ניהול משתמשים ({users.length})</span>
              </button>

              <button
                onClick={() => setActiveTab('system')}
                className={`flex-1 sm:flex-none py-2.5 px-4 rounded-xl text-xs font-bold transition flex items-center justify-center gap-2 ${
                  activeTab === 'system'
                    ? 'bg-amber-500 text-slate-950 shadow-md font-extrabold'
                    : 'bg-slate-950 text-slate-300 hover:text-white hover:bg-slate-800'
                }`}
              >
                <Sliders className="w-4 h-4" />
                <span>⚙️ הגדרות מערכת</span>
              </button>

              <button
                onClick={() => setActiveTab('subscriptions')}
                className={`flex-1 sm:flex-none py-2.5 px-4 rounded-xl text-xs font-bold transition flex items-center justify-center gap-2 ${
                  activeTab === 'subscriptions'
                    ? 'bg-amber-500 text-slate-950 shadow-md font-extrabold'
                    : 'bg-slate-950 text-slate-300 hover:text-white hover:bg-slate-800'
                }`}
              >
                <Crown className="w-4 h-4" />
                <span>💎 ניהול מנויים</span>
              </button>

              <button
                onClick={() => setActiveTab('stations')}
                className={`flex-1 sm:flex-none py-2.5 px-4 rounded-xl text-xs font-bold transition flex items-center justify-center gap-2 ${
                  activeTab === 'stations'
                    ? 'bg-amber-500 text-slate-950 shadow-md font-extrabold'
                    : 'bg-slate-950 text-slate-300 hover:text-white hover:bg-slate-800'
                }`}
              >
                <Building className="w-4 h-4" />
                <span>🏢 ניהול תחנות ({stations.length})</span>
              </button>

              <button
                onClick={() => setActiveTab('appeals')}
                className={`flex-1 sm:flex-none py-2.5 px-4 rounded-xl text-xs font-bold transition flex items-center justify-center gap-2 relative ${
                  activeTab === 'appeals'
                    ? 'bg-amber-500 text-slate-950 shadow-md font-extrabold'
                    : 'bg-slate-950 text-slate-300 hover:text-white hover:bg-slate-800'
                }`}
              >
                <Scale className="w-4 h-4" />
                <span>⚖️ ערעורי חובות</span>
                {pendingAppeals.length > 0 && (
                  <span className="bg-red-500 text-white text-[10px] px-1.5 py-0.2 rounded-full font-bold">
                    {pendingAppeals.length}
                  </span>
                )}
              </button>

              <button
                onClick={() => setActiveTab('broadcast')}
                className={`flex-1 sm:flex-none py-2.5 px-4 rounded-xl text-xs font-bold transition flex items-center justify-center gap-2 ${
                  activeTab === 'broadcast'
                    ? 'bg-amber-500 text-slate-950 shadow-md font-extrabold'
                    : 'bg-slate-950 text-slate-300 hover:text-white hover:bg-slate-800'
                }`}
              >
                <Radio className="w-4 h-4" />
                <span>📢 שידור Broadcast</span>
              </button>
            </div>

            {/* TAB 1: ניהול משתמשים (User Management) */}
            {activeTab === 'users' && (
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm space-y-4">
                <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
                  <div>
                    <h3 className="font-extrabold text-base text-white flex items-center gap-2">
                      <Users className="w-5 h-5 text-amber-400" />
                      <span>ניהול משתמשים, נהגים והרשאות God Mode</span>
                    </h3>
                    <p className="text-xs text-slate-400">
                      שנה תפקידים, שייך עובדים לתחנות, חסום נהגים או אפס הרשאות בלחיצה
                    </p>
                  </div>
                  <div className="w-full sm:w-72 relative">
                    <Search className="w-4 h-4 text-slate-400 absolute right-3 top-3 pointer-events-none" />
                    <input
                      type="text"
                      placeholder="חפש לפי שם, טלפון או ID..."
                      value={searchUser}
                      onChange={(e) => setSearchUser(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-700 rounded-xl pr-9 pl-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-amber-500"
                    />
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-right text-xs">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400">
                        <th className="py-2.5 px-3">משתמש</th>
                        <th className="py-2.5 px-3">מזהה ID</th>
                        <th className="py-2.5 px-3">טלפון</th>
                        <th className="py-2.5 px-3">רכב</th>
                        <th className="py-2.5 px-3">תפקיד</th>
                        <th className="py-2.5 px-3">תחנה</th>
                        <th className="py-2.5 px-3">חוב</th>
                        <th className="py-2.5 px-3 text-center">פעולות הרשאה</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {filteredUsers.map((u) => (
                        <tr key={u.user_id} className={`hover:bg-slate-800/40 transition ${u.is_blocked ? 'bg-red-950/20' : ''}`}>
                          <td className="py-3 px-3">
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-white">{u.full_name}</span>
                              {u.role === 'admin' && (
                                <span className="bg-amber-500/20 text-amber-300 border border-amber-500/30 text-[10px] px-1.5 py-0.2 rounded font-bold">
                                  ADMIN
                                </span>
                              )}
                              {u.is_blocked === 1 && (
                                <span className="bg-red-500/20 text-red-300 border border-red-500/30 text-[10px] px-1.5 py-0.2 rounded font-bold">
                                  חסום
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="py-3 px-3 font-mono text-slate-400">{u.user_id}</td>
                          <td className="py-3 px-3 font-mono text-slate-300">{u.phone}</td>
                          <td className="py-3 px-3 text-slate-300">{u.car_brand} {u.car_model}</td>
                          <td className="py-3 px-3">
                            <span className="px-2 py-0.5 rounded-lg bg-slate-800 text-slate-300 border border-slate-700 text-[11px] font-bold">
                              {ROLE_NAMES[u.role] || u.role}
                            </span>
                          </td>
                          <td className="py-3 px-3 text-slate-300">
                            תחנה #{u.station_id}
                          </td>
                          <td className="py-3 px-3 font-mono font-bold text-amber-400">
                            ₪{u.debt_balance.toFixed(2)}
                          </td>
                          <td className="py-3 px-3">
                            <div className="flex items-center justify-center gap-1.5 flex-wrap">
                              <button
                                title="ערוך תפקיד, שיוך לתחנה ומנוי"
                                onClick={() =>
                                  setEditUserModal({
                                    isOpen: true,
                                    user: u,
                                    role: u.role,
                                    station_id: u.station_id || 1,
                                    subscription_plan: (u as any).subscription_plan || 'free',
                                  })
                                }
                                className="bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold text-[11px] px-2.5 py-1 rounded-md shadow transition"
                              >
                                ✏️ ערוך שיוך
                              </button>
                              <button
                                title="הפוך לסדרן עם בחירת תחנה"
                                onClick={() =>
                                  setEditUserModal({
                                    isOpen: true,
                                    user: u,
                                    role: 'dispatcher',
                                    station_id: u.station_id || 1,
                                    subscription_plan: (u as any).subscription_plan || 'free',
                                  })
                                }
                                className="bg-blue-900/40 hover:bg-blue-800 text-blue-200 text-[10px] px-2 py-1 rounded-md border border-blue-700/50"
                              >
                                סדרן
                              </button>
                              <button
                                title="הפוך למנהל תחנה עם בחירת תחנה"
                                onClick={() =>
                                  setEditUserModal({
                                    isOpen: true,
                                    user: u,
                                    role: 'station_manager',
                                    station_id: u.station_id || 1,
                                    subscription_plan: (u as any).subscription_plan || 'free',
                                  })
                                }
                                className="bg-purple-900/40 hover:bg-purple-800 text-purple-200 text-[10px] px-2 py-1 rounded-md border border-purple-700/50"
                              >
                                מנהל תחנה
                              </button>
                              {u.is_blocked ? (
                                <button
                                  title="שחרר חסימה"
                                  onClick={() => updateUserRoleAndStation(u.user_id, 'user', u.station_id)}
                                  className="bg-emerald-900/40 hover:bg-emerald-800 text-emerald-200 text-[10px] px-2 py-1 rounded-md border border-emerald-700/50"
                                >
                                  שחרר
                                </button>
                              ) : (
                                <button
                                  title="חסום משתמש"
                                  onClick={() => updateUserRoleAndStation(u.user_id, 'blocked', u.station_id)}
                                  className="bg-red-900/40 hover:bg-red-800 text-red-200 text-[10px] px-2 py-1 rounded-md border border-red-700/50"
                                >
                                  חסימה
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* TAB 2: הגדרות מערכת (System Settings & NLP Aliases) */}
            {activeTab === 'system' && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Global Parameters */}
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm space-y-4">
                  <h3 className="font-extrabold text-base text-white flex items-center gap-2">
                    <Sliders className="w-5 h-5 text-amber-400" />
                    <span>הגדרות מערכת גלובליות</span>
                  </h3>
                  <p className="text-xs text-slate-400">
                    קביעת תקרת אכיפת חובות (Auto-Freeze), עמלות ברירת מחדל ומגבלות קריאות יומיות
                  </p>

                  {settingsSuccess && (
                    <div className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-xs text-emerald-300 font-bold">
                      {settingsSuccess}
                    </div>
                  )}

                  <form onSubmit={handleSaveSettings} className="space-y-4 text-xs">
                    <div>
                      <label className="text-slate-300 block mb-1.5 font-bold">אחוז עמלת ברירת מחדל לקריאות (%)</label>
                      <input
                        type="number"
                        step="0.5"
                        value={defaultCommission}
                        onChange={(e) => setDefaultCommission(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-amber-500"
                      />
                    </div>

                    <div>
                      <label className="text-slate-300 block mb-1.5 font-bold">תקרת הקפאת נהג אוטומטית (Auto-Freeze) בש"ח</label>
                      <input
                        type="number"
                        value={autoFreezeThreshold}
                        onChange={(e) => setAutoFreezeThreshold(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-amber-500"
                      />
                      <span className="text-[11px] text-slate-500 block mt-1">
                        נהג שצבר חוב מעל סכום זה לא יוכל להעביר סטטוס ל'פנוי' עד הסדרת החוב.
                      </span>
                    </div>

                    <div>
                      <label className="text-slate-300 block mb-1.5 font-bold">מגבלת נסיעות יומיות למנוי חינמי (Free Plan)</label>
                      <input
                        type="number"
                        value={freeTripsLimit}
                        onChange={(e) => setFreeTripsLimit(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-amber-500"
                      />
                    </div>

                    <button
                      type="submit"
                      className="w-full py-2.5 rounded-xl font-bold bg-amber-500 hover:bg-amber-400 text-slate-950 shadow-md transition"
                    >
                      שמור הגדרות מערכת
                    </button>
                  </form>
                </div>

                {/* NLP City Aliases Dictionary */}
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm space-y-4">
                  <h3 className="font-extrabold text-base text-white flex items-center gap-2">
                    <Sparkles className="w-5 h-5 text-amber-400" />
                    <span>מילון קיצורי ערים (NLP City Aliases)</span>
                  </h3>
                  <p className="text-xs text-slate-400">
                    מאגר הקיצורים שמאפשר לנהגים וסדרנים להקליד קיצורים המתורגמים אוטומטית לשמות ערים תקניים
                  </p>

                  <form onSubmit={handleAddAlias} className="flex gap-2 text-xs">
                    <input
                      type="text"
                      placeholder="קיצור (למשל: י-ם)"
                      value={cityAliasKey}
                      onChange={(e) => setCityAliasKey(e.target.value)}
                      className="w-1/3 bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-amber-500"
                    />
                    <input
                      type="text"
                      placeholder="שם עיר תקני (למשל: ירושלים)"
                      value={cityAliasVal}
                      onChange={(e) => setCityAliasVal(e.target.value)}
                      className="flex-1 bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-amber-500"
                    />
                    <button
                      type="submit"
                      className="bg-slate-800 hover:bg-slate-700 text-white font-bold px-4 py-2 rounded-xl border border-slate-700"
                    >
                      הוסף
                    </button>
                  </form>

                  <div className="max-h-64 overflow-y-auto space-y-1.5 p-2 bg-slate-950 rounded-xl border border-slate-800 text-xs">
                    {customAliases.map((a, i) => (
                      <div key={i} className="flex justify-between items-center py-1.5 px-3 bg-slate-900/60 rounded-lg">
                        <span className="font-mono font-bold text-amber-400">{a.alias}</span>
                        <span className="text-slate-400">➔</span>
                        <span className="text-white font-bold">{a.standard}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* TAB 3: ניהול מנויים (Subscription Plans) */}
            {activeTab === 'subscriptions' && (
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm space-y-6">
                <div>
                  <h3 className="font-extrabold text-base text-white flex items-center gap-2">
                    <Crown className="w-5 h-5 text-amber-400" />
                    <span>ניהול מנויים ומסלולי נהגים</span>
                  </h3>
                  <p className="text-xs text-slate-400">
                    שליטה במנויי VIP, מנוי בסיסי, תוקף מנויים ואכיפת מגבלת קריאות
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {/* Plan 1: Free */}
                  <div className="bg-slate-950 border border-slate-800 rounded-2xl p-4 space-y-3">
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-sm text-white">מנוי חינמי (Free)</span>
                      <span className="text-xs bg-slate-800 text-slate-300 px-2 py-0.5 rounded-full font-mono">0 ₪</span>
                    </div>
                    <ul className="text-xs text-slate-400 space-y-2">
                      <li className="flex items-center gap-1.5">
                        <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                        <span>מוגבל לעד 3 נסיעות ביום</span>
                      </li>
                      <li className="flex items-center gap-1.5">
                        <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                        <span>עמלת תחנה רגילה (10%)</span>
                      </li>
                      <li className="flex items-center gap-1.5">
                        <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                        <span>השהיית קפיצת קריאות של 15 שניות</span>
                      </li>
                    </ul>
                    <div className="pt-2 border-t border-slate-800 text-xs text-slate-400">
                      נהגים במסלול: <strong>{users.filter((u) => u.role === 'user').length}</strong>
                    </div>
                  </div>

                  {/* Plan 2: Basic */}
                  <div className="bg-slate-950 border border-slate-800 rounded-2xl p-4 space-y-3">
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-sm text-sky-400">מנוי בייסיק (Basic)</span>
                      <span className="text-xs bg-sky-950 text-sky-300 border border-sky-800 px-2 py-0.5 rounded-full font-mono">150 ₪/חודש</span>
                    </div>
                    <ul className="text-xs text-slate-300 space-y-2">
                      <li className="flex items-center gap-1.5">
                        <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                        <span>נסיעות ללא הגבלה יומית</span>
                      </li>
                      <li className="flex items-center gap-1.5">
                        <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                        <span>עמלה מופחתת של 8%</span>
                      </li>
                      <li className="flex items-center gap-1.5">
                        <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                        <span>השהייה מופחתת (5 שניות)</span>
                      </li>
                    </ul>
                    <button className="w-full py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-xl text-xs font-bold transition">
                      ערוך הגדרות מסלול
                    </button>
                  </div>

                  {/* Plan 3: VIP Master */}
                  <div className="bg-slate-950 border border-amber-500/40 rounded-2xl p-4 space-y-3 shadow-md shadow-amber-500/5">
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-sm text-amber-400 flex items-center gap-1">
                        <span>👑 מנוי VIP Master</span>
                      </span>
                      <span className="text-xs bg-amber-500/20 text-amber-300 border border-amber-500/30 px-2 py-0.5 rounded-full font-mono font-bold">350 ₪/חודש</span>
                    </div>
                    <ul className="text-xs text-slate-200 space-y-2">
                      <li className="flex items-center gap-1.5">
                        <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                        <span>קפיצת קריאות מיידית 0 שניות (עדיפות עליונה)</span>
                      </li>
                      <li className="flex items-center gap-1.5">
                        <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                        <span>עמלה מינימלית של 5% בלבד</span>
                      </li>
                      <li className="flex items-center gap-1.5">
                        <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                        <span>תג VIP מזהב בפרופיל</span>
                      </li>
                    </ul>
                    <button className="w-full py-2 bg-amber-500 hover:bg-amber-400 text-slate-950 rounded-xl text-xs font-bold transition">
                      שייך נהגים ל-VIP
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 4: ניהול תחנות ועמלות */}
            {activeTab === 'stations' && (
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                <div className="lg:col-span-5 bg-slate-900 rounded-2xl p-5 border border-slate-800 shadow-md">
                  <h3 className="font-bold text-base text-white mb-2 flex items-center gap-2">
                    <Plus className="w-4 h-4 text-amber-400" />
                    <span>פתיחת תחנה חדשה במערכת</span>
                  </h3>
                  <p className="text-xs text-slate-400 mb-4">
                    יצירת תחנת מוניות/משלוחים חדשה עם אחוז עמלה ייעודי לסדרנים ונהגים
                  </p>

                  {stationSuccess && (
                    <div className="mb-4 p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-xs text-emerald-300 font-bold">
                      {stationSuccess}
                    </div>
                  )}

                  <form onSubmit={handleCreateStation} className="space-y-4 text-xs">
                    <div>
                      <label className="text-slate-300 block mb-1 font-bold">שם התחנה החדשה</label>
                      <input
                        type="text"
                        placeholder="למשל: תחנת מרכז ירושלים"
                        value={stationName}
                        onChange={(e) => setStationName(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-amber-500"
                        required
                      />
                    </div>

                    <div>
                      <label className="text-slate-300 block mb-1 font-bold">אחוז עמלה לתחנה (%)</label>
                      <input
                        type="number"
                        step="0.5"
                        placeholder="10.0"
                        value={stationComm}
                        onChange={(e) => setStationComm(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-amber-500"
                        required
                      />
                    </div>

                    <button
                      type="submit"
                      className="w-full py-2.5 rounded-xl font-bold bg-amber-500 hover:bg-amber-400 text-slate-950 shadow transition"
                    >
                      צור תחנה עכשיו
                    </button>
                  </form>
                </div>

                <div className="lg:col-span-7 bg-slate-900 rounded-2xl p-5 border border-slate-800 shadow-md">
                  <h3 className="font-bold text-base text-white mb-3">תחנות קיימות במערכת ({stations.length})</h3>
                  <div className="space-y-3">
                    {stations.map((s) => (
                      <div key={s.station_id} className="p-3.5 bg-slate-950 rounded-xl border border-slate-800 flex justify-between items-center">
                        <div>
                          <span className="font-bold text-sm text-white">{s.name}</span>
                          <span className="text-xs text-slate-400 block">מזהה: #{s.station_id}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-mono font-bold text-amber-400 bg-amber-500/10 px-2.5 py-1 rounded-lg border border-amber-500/30">
                            {s.commission_percent}% עמלה
                          </span>
                          <button
                            onClick={() =>
                              setEditStationModal({
                                isOpen: true,
                                station_id: s.station_id,
                                name: s.name,
                                commission_percent: s.commission_percent.toString(),
                              })
                            }
                            className="text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1 rounded-lg border border-slate-700 transition font-bold"
                          >
                            ✏️ ערוך
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* TAB 5: ניהול חיובים וערעורים (CRUD) */}
            {activeTab === 'appeals' && (
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
                  <div>
                    <h3 className="font-extrabold text-base text-white flex items-center gap-2">
                      <Scale className="w-5 h-5 text-amber-400" />
                      <span>ניהול חיובים, עמלות (🍓) וערעורים ({debts.length})</span>
                    </h3>
                    <p className="text-xs text-slate-400 mt-0.5">
                      הוספת חיובים ידניים, שינוי סכומים, בחירת תחנה ושליחת התראה מיידית לנהג בטלגרם
                    </p>
                  </div>
                  <button
                    onClick={() =>
                      setChargeDebtModal({
                        isOpen: true,
                        driver_id: users.find((u) => u.role === 'user')?.user_id || users[0]?.user_id || 0,
                        amount: '20',
                        reason: 'עמלת נסיעה (🍓)',
                        station_id: currentUser.station_id || stations[0]?.station_id || 1,
                        order_id: '',
                      })
                    }
                    className="bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold text-xs px-4 py-2.5 rounded-xl shadow transition flex items-center justify-center gap-2 cursor-pointer"
                  >
                    <Plus className="w-4 h-4" />
                    <span>➕ הוסף חיוב לנהג (🍓)</span>
                  </button>
                </div>

                <div className="space-y-3">
                  {debts.length === 0 ? (
                    <div className="text-center py-8 text-slate-500 text-xs">
                      אין כרגע חיובים רשומים במערכת.
                    </div>
                  ) : (
                    debts.map((d) => {
                      const driverObj = users.find((u) => u.user_id === d.driver_id);
                      const stationObj = stations.find((s) => s.station_id === d.station_id);
                      return (
                        <div key={d.debt_id} className="p-3.5 bg-slate-950 rounded-xl border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs">
                          <div>
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="font-bold text-white">חיוב #{d.debt_id}</span>
                              {d.order_id ? (
                                <span className="text-slate-400 font-mono text-[11px]">(קריאה #{d.order_id})</span>
                              ) : null}
                              <span className="font-mono font-bold text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/30">
                                ₪{d.amount.toFixed(2)} (🍓)
                              </span>
                              <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${
                                d.status === 'unpaid' ? 'bg-red-500/20 text-red-300 border border-red-500/30' : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                              }`}>
                                {d.status === 'unpaid' ? 'לא שולם' : d.status === 'paid' ? 'שולם / זוכה' : 'בוטל'}
                              </span>
                              <span className="text-[11px] text-slate-300 bg-slate-800 px-2 py-0.5 rounded">
                                🏢 {stationObj ? stationObj.name : `תחנה #${d.station_id}`}
                              </span>
                            </div>
                            <p className="text-slate-300 text-[11px] mt-1.5">
                              נהג: <strong>{driverObj ? driverObj.full_name : `נהג ${d.driver_id}`}</strong> (מזהה: {d.driver_id}) • סיבה: {d.reason}
                            </p>
                            {d.appeal_reason && (
                              <p className="text-amber-300 text-[11px] mt-1.5 bg-amber-500/10 p-2 rounded-lg border border-amber-500/30">
                                ⚖️ <strong>נימוק ערעור הנהג:</strong> "{d.appeal_reason}"
                              </p>
                            )}
                          </div>
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <button
                              onClick={() =>
                                setEditDebtModal({
                                  isOpen: true,
                                  debt_id: d.debt_id,
                                  amount: d.amount.toString(),
                                  reason: d.reason,
                                  station_id: d.station_id,
                                  status: d.status as any,
                                })
                              }
                              className="bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold px-2.5 py-1.5 rounded-lg text-xs border border-slate-700 transition"
                            >
                              ✏️ ערוך
                            </button>
                            {d.status === 'unpaid' && (
                              <button
                                onClick={() => resolveDebtAppeal(d.debt_id, true)}
                                className="bg-emerald-600 hover:bg-emerald-500 text-white font-bold px-2.5 py-1.5 rounded-lg text-xs transition"
                              >
                                ✅ אשר ומחק חוב
                              </button>
                            )}
                            {d.appeal_status === 'pending' && (
                              <button
                                onClick={() => resolveDebtAppeal(d.debt_id, false)}
                                className="bg-red-900/40 hover:bg-red-800 text-red-200 font-bold px-2.5 py-1.5 rounded-lg text-xs border border-red-700/50 transition"
                              >
                                ❌ דחה ערעור
                              </button>
                            )}
                            <button
                              onClick={() => deleteDebt(d.debt_id)}
                              className="text-red-400 hover:text-red-300 bg-red-900/20 hover:bg-red-900/30 font-bold px-2.5 py-1.5 rounded-lg text-xs border border-red-800/40 transition"
                            >
                              🗑️ מחק
                            </button>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            )}

            {/* TAB 6: שידור Broadcast */}
            {activeTab === 'broadcast' && (
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm space-y-4">
                <h3 className="font-extrabold text-base text-white flex items-center gap-2">
                  <Radio className="w-5 h-5 text-amber-400" />
                  <span>שידור הודעת Broadcast גלובלית לכל המשתמשים</span>
                </h3>
                <p className="text-xs text-slate-400">
                  הודעה זו תוקפץ לכל הנהגים, הסדרנים ומנהלי התחנות במערכת ובבוט
                </p>

                {broadcastSuccess && (
                  <div className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-xs text-emerald-300 font-bold">
                    {broadcastSuccess}
                  </div>
                )}

                <form onSubmit={handleSendBroadcast} className="space-y-4 text-xs">
                  <textarea
                    rows={4}
                    placeholder="הקלד כאן את תוכן ההודעה הגלובלית..."
                    value={broadcastText}
                    onChange={(e) => setBroadcastText(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-xl p-3 text-white focus:outline-none focus:border-amber-500"
                    required
                  />
                  <button
                    type="submit"
                    className="w-full py-3 rounded-xl font-bold bg-amber-500 hover:bg-amber-400 text-slate-950 shadow-md transition flex items-center justify-center gap-2 text-sm"
                  >
                    <Send className="w-4 h-4" />
                    <span>שגר הודעה לכל המערכת</span>
                  </button>
                </form>
              </div>
            )}
          </>
        )}
      </main>

      {/* 1. Modal: עריכת תחנה קיימת (שם ועמלה) */}
      {editStationModal.isOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="font-extrabold text-base text-white flex items-center gap-2">
                <Building className="w-5 h-5 text-amber-400" />
                <span>עריכת תחנה #{editStationModal.station_id}</span>
              </h3>
              <button
                onClick={() => setEditStationModal((prev) => ({ ...prev, isOpen: false }))}
                className="text-slate-400 hover:text-white text-lg font-bold"
              >
                ✕
              </button>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                const comm = parseFloat(editStationModal.commission_percent);
                if (!editStationModal.name.trim() || isNaN(comm) || comm < 0) return;
                updateStation(editStationModal.station_id, editStationModal.name.trim(), comm);
                setEditStationModal((prev) => ({ ...prev, isOpen: false }));
              }}
              className="space-y-4 text-xs"
            >
              <div>
                <label className="text-slate-300 block mb-1 font-bold">שם התחנה</label>
                <input
                  type="text"
                  value={editStationModal.name}
                  onChange={(e) => setEditStationModal((prev) => ({ ...prev, name: e.target.value }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-amber-500"
                  required
                />
              </div>

              <div>
                <label className="text-slate-300 block mb-1 font-bold">אחוז עמלה (%)</label>
                <input
                  type="number"
                  step="0.1"
                  value={editStationModal.commission_percent}
                  onChange={(e) =>
                    setEditStationModal((prev) => ({ ...prev, commission_percent: e.target.value }))
                  }
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-amber-500"
                  required
                />
              </div>

              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setEditStationModal((prev) => ({ ...prev, isOpen: false }))}
                  className="flex-1 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold"
                >
                  ביטול
                </button>
                <button
                  type="submit"
                  className="flex-1 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold shadow"
                >
                  שמור שינויים
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 2. Modal: עריכת משתמש, תפקיד ושיוך לתחנה (סעיף 3ב) */}
      {editUserModal.isOpen && editUserModal.user && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="font-extrabold text-base text-white flex items-center gap-2">
                  <Users className="w-5 h-5 text-amber-400" />
                  <span>עריכת משתמש ושיוך לתחנה</span>
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  {editUserModal.user.full_name} (מזהה: {editUserModal.user.user_id})
                </p>
              </div>
              <button
                onClick={() => setEditUserModal((prev) => ({ ...prev, isOpen: false }))}
                className="text-slate-400 hover:text-white text-lg font-bold"
              >
                ✕
              </button>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                updateUserRoleAndStation(
                  editUserModal.user!.user_id,
                  editUserModal.role,
                  editUserModal.station_id,
                  editUserModal.subscription_plan
                );
                setEditUserModal((prev) => ({ ...prev, isOpen: false }));
              }}
              className="space-y-4 text-xs"
            >
              <div>
                <label className="text-slate-300 block mb-1 font-bold">תפקיד במערכת</label>
                <select
                  value={editUserModal.role}
                  onChange={(e) =>
                    setEditUserModal((prev) => ({ ...prev, role: e.target.value as any }))
                  }
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-amber-500"
                >
                  <option value="user">נהג / שליח (User)</option>
                  <option value="dispatcher">סדרן תחנה (Dispatcher)</option>
                  <option value="station_manager">מנהל תחנה (Station Manager)</option>
                  <option value="admin">מנהל מערכת ראשי (Admin God Mode)</option>
                  <option value="blocked">משתמש חסום (Blocked)</option>
                </select>
              </div>

              <div>
                <label className="text-slate-300 block mb-1 font-bold">
                  🏢 שיבוץ לתחנה (Station ID) - חובה לסדרנים ומנהלים
                </label>
                <select
                  value={editUserModal.station_id}
                  onChange={(e) =>
                    setEditUserModal((prev) => ({ ...prev, station_id: parseInt(e.target.value, 10) }))
                  }
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-amber-500 font-bold"
                >
                  {stations.map((s) => (
                    <option key={s.station_id} value={s.station_id}>
                      תחנה #{s.station_id} - {s.name} ({s.commission_percent}% עמלה)
                    </option>
                  ))}
                </select>
                <p className="text-[11px] text-slate-400 mt-1">
                  המשתמש יהיה משויך לתחנה זו וינהל/יראה קריאות של תחנה זו בלבד.
                </p>
              </div>

              <div>
                <label className="text-slate-300 block mb-1 font-bold">מסלול מנוי (Subscription)</label>
                <select
                  value={editUserModal.subscription_plan}
                  onChange={(e) =>
                    setEditUserModal((prev) => ({ ...prev, subscription_plan: e.target.value }))
                  }
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-amber-500"
                >
                  <option value="free">חינם (Free - עד 3 קריאות ליום ללא מנוי)</option>
                  <option value="basic">בסיסי (Basic - ללא הגבלת קריאות)</option>
                  <option value="vip">VIP (עדיפות שידור ופטור מעמלות ידניות)</option>
                </select>
              </div>

              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setEditUserModal((prev) => ({ ...prev, isOpen: false }))}
                  className="flex-1 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold"
                >
                  ביטול
                </button>
                <button
                  type="submit"
                  className="flex-1 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold shadow"
                >
                  שמור שיבוץ
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 3. Modal: הוספת חיוב לנהג (עמלת נסיעה / 🍓) עם בחירת תחנה והתראה בטלגרם (סעיף 4א, 4ג) */}
      {chargeDebtModal.isOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="font-extrabold text-base text-white flex items-center gap-2">
                  <span>🍓</span>
                  <span>הוספת חיוב / עמלה לנהג</span>
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  החיוב יירשם ביומן והנהג יקבל מיד התראה לפרטי בטלגרם עם כפתור ערעור
                </p>
              </div>
              <button
                onClick={() => setChargeDebtModal((prev) => ({ ...prev, isOpen: false }))}
                className="text-slate-400 hover:text-white text-lg font-bold"
              >
                ✕
              </button>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                const amt = parseFloat(chargeDebtModal.amount);
                if (!chargeDebtModal.driver_id || isNaN(amt) || amt <= 0) return;
                chargeDriverDebt(
                  chargeDebtModal.driver_id,
                  amt,
                  chargeDebtModal.reason.trim() || 'עמלת נסיעה (🍓)',
                  chargeDebtModal.station_id,
                  chargeDebtModal.order_id ? parseInt(chargeDebtModal.order_id, 10) : undefined
                );
                setChargeDebtModal((prev) => ({ ...prev, isOpen: false }));
              }}
              className="space-y-4 text-xs"
            >
              <div>
                <label className="text-slate-300 block mb-1 font-bold">בחר נהג לחיוב</label>
                <select
                  value={chargeDebtModal.driver_id}
                  onChange={(e) =>
                    setChargeDebtModal((prev) => ({ ...prev, driver_id: parseInt(e.target.value, 10) }))
                  }
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-amber-500 font-bold"
                  required
                >
                  <option value="">-- בחר נהג --</option>
                  {users.map((u) => (
                    <option key={u.user_id} value={u.user_id}>
                      {u.full_name} (מזהה {u.user_id}) - {ROLE_NAMES[u.role] || u.role} | חוב: ₪
                      {u.debt_balance.toFixed(2)}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-slate-300 block mb-1 font-bold">
                  🏢 שיוך לתחנה (סעיף 4א - בחירת תחנה מפורשת ולא תחנה 1)
                </label>
                <select
                  value={chargeDebtModal.station_id}
                  onChange={(e) =>
                    setChargeDebtModal((prev) => ({ ...prev, station_id: parseInt(e.target.value, 10) }))
                  }
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-amber-500 font-bold"
                  required
                >
                  {stations.map((s) => (
                    <option key={s.station_id} value={s.station_id}>
                      תחנה #{s.station_id} - {s.name} ({s.commission_percent}%)
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-slate-300 block mb-1 font-bold">סכום לחיוב (₪)</label>
                  <input
                    type="number"
                    step="0.5"
                    min="1"
                    value={chargeDebtModal.amount}
                    onChange={(e) => setChargeDebtModal((prev) => ({ ...prev, amount: e.target.value }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-amber-500 font-bold"
                    required
                  />
                </div>

                <div>
                  <label className="text-slate-300 block mb-1 font-bold">מספר קריאה (אופציונלי)</label>
                  <input
                    type="number"
                    placeholder="למשל 1005"
                    value={chargeDebtModal.order_id}
                    onChange={(e) => setChargeDebtModal((prev) => ({ ...prev, order_id: e.target.value }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-amber-500 font-mono"
                  />
                </div>
              </div>

              <div>
                <label className="text-slate-300 block mb-1 font-bold">סיבת החיוב / פירוט הנסיעה</label>
                <input
                  type="text"
                  placeholder="למשל: עמלת נסיעה 10% ירושלים-בני ברק"
                  value={chargeDebtModal.reason}
                  onChange={(e) => setChargeDebtModal((prev) => ({ ...prev, reason: e.target.value }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-amber-500"
                  required
                />
              </div>

              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setChargeDebtModal((prev) => ({ ...prev, isOpen: false }))}
                  className="flex-1 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold"
                >
                  ביטול
                </button>
                <button
                  type="submit"
                  className="flex-1 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold shadow flex items-center justify-center gap-1.5"
                >
                  <span>🍓</span>
                  <span>חייב ושלח התראה</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 4. Modal: עריכת חיוב קיים (CRUD - סעיף 4ב) */}
      {editDebtModal.isOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="font-extrabold text-base text-white flex items-center gap-2">
                <Scale className="w-5 h-5 text-amber-400" />
                <span>עריכת פרטי חיוב #{editDebtModal.debt_id}</span>
              </h3>
              <button
                onClick={() => setEditDebtModal((prev) => ({ ...prev, isOpen: false }))}
                className="text-slate-400 hover:text-white text-lg font-bold"
              >
                ✕
              </button>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                const amt = parseFloat(editDebtModal.amount);
                if (isNaN(amt) || amt < 0) return;
                updateDebt(editDebtModal.debt_id, {
                  amount: amt,
                  reason: editDebtModal.reason.trim(),
                  station_id: editDebtModal.station_id,
                  status: editDebtModal.status,
                });
                setEditDebtModal((prev) => ({ ...prev, isOpen: false }));
              }}
              className="space-y-4 text-xs"
            >
              <div>
                <label className="text-slate-300 block mb-1 font-bold">סכום החיוב (₪)</label>
                <input
                  type="number"
                  step="0.5"
                  value={editDebtModal.amount}
                  onChange={(e) => setEditDebtModal((prev) => ({ ...prev, amount: e.target.value }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-amber-500 font-bold"
                  required
                />
              </div>

              <div>
                <label className="text-slate-300 block mb-1 font-bold">תחנה מקושרת</label>
                <select
                  value={editDebtModal.station_id}
                  onChange={(e) =>
                    setEditDebtModal((prev) => ({ ...prev, station_id: parseInt(e.target.value, 10) }))
                  }
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-amber-500 font-bold"
                >
                  {stations.map((s) => (
                    <option key={s.station_id} value={s.station_id}>
                      תחנה #{s.station_id} - {s.name} ({s.commission_percent}%)
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-slate-300 block mb-1 font-bold">סיבת החיוב / פירוט</label>
                <input
                  type="text"
                  value={editDebtModal.reason}
                  onChange={(e) => setEditDebtModal((prev) => ({ ...prev, reason: e.target.value }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-amber-500"
                  required
                />
              </div>

              <div>
                <label className="text-slate-300 block mb-1 font-bold">סטטוס חיוב</label>
                <select
                  value={editDebtModal.status}
                  onChange={(e) =>
                    setEditDebtModal((prev) => ({ ...prev, status: e.target.value as any }))
                  }
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-amber-500"
                >
                  <option value="unpaid">לא שולם (חוב פעיל לנהג)</option>
                  <option value="paid">שולם / זוכה</option>
                  <option value="cancelled">בוטל (נמחק מחובות הנהג)</option>
                </select>
              </div>

              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setEditDebtModal((prev) => ({ ...prev, isOpen: false }))}
                  className="flex-1 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold"
                >
                  ביטול
                </button>
                <button
                  type="submit"
                  className="flex-1 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold shadow"
                >
                  עדכן חיוב
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
