import React, { useState, useEffect } from 'react';
import { useApp } from '../context/AppContext';
import { StationStats, Order, Debt, User, ROLE_NAMES } from '../types';
import {
  Building,
  TrendingUp,
  Radio,
  FileText,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Clock,
  DollarSign,
  UserCheck,
  Send,
  AtSign,
  Search,
  RefreshCw,
  Percent,
} from 'lucide-react';

export const StationManagerDashboard: React.FC = () => {
  const { currentUser, stations, orders, debts, users } = useApp();
  const [activeTab, setActiveTab] = useState<'overview' | 'dispatchers' | 'orders' | 'debts'>('overview');
  const [searchTerm, setSearchTerm] = useState('');
  const [feedback, setFeedback] = useState<string | null>(null);

  const myStationId = currentUser.station_id || 1;
  const currentStation = stations.find((s) => s.station_id === myStationId) || {
    station_id: myStationId,
    name: `תחנה #${myStationId}`,
    commission_percent: 10.0,
  };

  // Strictly filter data to this manager's station only!
  const stationOrders = orders.filter((o) => o.station_id === myStationId);
  const stationDebts = debts.filter((d) => d.station_id === myStationId);
  const stationDispatchers = users.filter(
    (u) => u.station_id === myStationId && (u.role === 'dispatcher' || u.role === 'station_manager')
  );

  // Compute station statistics
  const openCount = stationOrders.filter((o) => o.status === 'open').length;
  const assignedCount = stationOrders.filter((o) => o.status === 'assigned').length;
  const closedCount = stationOrders.filter((o) => o.status === 'closed').length;
  const cancelledCount = stationOrders.filter((o) => o.status === 'cancelled').length;
  const totalRevenue = stationOrders
    .filter((o) => o.status === 'closed')
    .reduce((acc, o) => acc + (o.price || 0), 0);
  const totalCommission = stationDebts
    .filter((d) => d.status !== 'cancelled')
    .reduce((acc, d) => acc + (d.amount || 0), 0);
  const pendingAppealsCount = stationDebts.filter((d) => d.appeal_status === 'pending').length;

  const showNotification = (msg: string) => {
    setFeedback(msg);
    setTimeout(() => setFeedback(null), 4000);
  };

  const handleResolveAppeal = async (debtId: number, approve: boolean) => {
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
        showNotification(
          approve ? '🍏 הערעור אושר בהצלחה! הנהג זוכה.' : '❌ הערעור נדחה והחיוב נותר בעינו.'
        );
      } else {
        showNotification(data.error || 'שגיאה בטיפול בערעור');
      }
    } catch {
      showNotification('שגיאת תקשורת עם השרת');
    }
  };

  // אבטחה קשיחה (Protected Component): חסימת כל מי שאינו מנהל תחנה או מנהל מערכת
  if (currentUser.role !== 'station_manager' && currentUser.role !== 'admin') {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6 text-center font-sans" dir="rtl">
        <div className="w-16 h-16 rounded-2xl bg-red-500/10 border border-red-500/30 flex items-center justify-center text-3xl mb-4 text-red-400">
          🚫
        </div>
        <h2 className="text-xl font-extrabold text-white mb-2">גישה חסומה</h2>
        <p className="text-sm text-slate-400 max-w-sm mb-6">
          פאנל ניהול התחנה מיועד למנהלי תחנות מורשים בלבד.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in text-slate-100">
      {/* Station Header */}
      <div className="bg-slate-900/90 rounded-2xl p-6 border border-slate-800 shadow-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr from-purple-600 to-indigo-600 flex items-center justify-center text-white font-extrabold text-2xl shadow-lg shadow-purple-500/20">
            🏢
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-black text-white">{currentStation.name}</h1>
              <span className="text-xs px-2.5 py-1 rounded-lg bg-purple-500/20 text-purple-300 border border-purple-500/30 font-bold">
                תחנה #{myStationId}
              </span>
              <span className="text-xs px-2.5 py-1 rounded-lg bg-amber-500/10 text-amber-300 border border-amber-500/30 font-semibold flex items-center gap-1">
                <Percent className="w-3 h-3" />
                {currentStation.commission_percent}% עמלה
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              פאנל ניהול תחנה ייעודי למנהל: <strong>{currentUser.full_name}</strong> | הרשאות מוגבלות לתחנה #{myStationId} בלבד
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 w-full md:w-auto">
          <div className="bg-slate-950/80 px-4 py-2 rounded-xl border border-slate-800 text-center flex-1 md:flex-initial">
            <span className="text-[11px] text-slate-400 block font-medium">עמלות שנצברו לתחנה</span>
            <span className="text-lg font-black text-emerald-400">₪{totalCommission.toFixed(2)}</span>
          </div>
        </div>
      </div>

      {feedback && (
        <div className="bg-amber-500/15 border border-amber-500/30 text-amber-300 px-4 py-3 rounded-xl flex items-center justify-between text-sm font-semibold animate-fade-in">
          <span>{feedback}</span>
          <button onClick={() => setFeedback(null)} className="text-amber-400 hover:text-white">✕</button>
        </div>
      )}

      {/* KPI Cards Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-3.5">
          <span className="text-[11px] text-slate-400 block font-medium">קריאות פתוחות</span>
          <span className="text-xl font-black text-amber-400">{openCount}</span>
        </div>
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-3.5">
          <span className="text-[11px] text-slate-400 block font-medium">משובצות בנסיעה</span>
          <span className="text-xl font-black text-blue-400">{assignedCount}</span>
        </div>
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-3.5">
          <span className="text-[11px] text-slate-400 block font-medium">הושלמו ונסגרו</span>
          <span className="text-xl font-black text-emerald-400">{closedCount}</span>
        </div>
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-3.5">
          <span className="text-[11px] text-slate-400 block font-medium">בוטלו</span>
          <span className="text-xl font-black text-red-400">{cancelledCount}</span>
        </div>
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-3.5">
          <span className="text-[11px] text-slate-400 block font-medium">סדרנים פעילים</span>
          <span className="text-xl font-black text-purple-400">{stationDispatchers.length}</span>
        </div>
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-3.5">
          <span className="text-[11px] text-slate-400 block font-medium">ערעורים ממתינים</span>
          <span className={`text-xl font-black ${pendingAppealsCount > 0 ? 'text-red-400 animate-pulse' : 'text-slate-400'}`}>
            {pendingAppealsCount}
          </span>
        </div>
      </div>

      {/* Tabs Navigation */}
      <div className="flex items-center gap-2 bg-slate-900/90 p-1.5 rounded-2xl border border-slate-800 overflow-x-auto">
        <button
          onClick={() => setActiveTab('overview')}
          className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 whitespace-nowrap ${
            activeTab === 'overview'
              ? 'bg-purple-600 text-white shadow'
              : 'text-slate-300 hover:text-white hover:bg-slate-800'
          }`}
        >
          <TrendingUp className="w-3.5 h-3.5" />
          <span>מבט על וסטטיסטיקות</span>
        </button>

        <button
          onClick={() => setActiveTab('dispatchers')}
          className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 whitespace-nowrap ${
            activeTab === 'dispatchers'
              ? 'bg-purple-600 text-white shadow'
              : 'text-slate-300 hover:text-white hover:bg-slate-800'
          }`}
        >
          <Radio className="w-3.5 h-3.5" />
          <span>סדרני התחנה ({stationDispatchers.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('orders')}
          className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 whitespace-nowrap ${
            activeTab === 'orders'
              ? 'bg-purple-600 text-white shadow'
              : 'text-slate-300 hover:text-white hover:bg-slate-800'
          }`}
        >
          <FileText className="w-3.5 h-3.5" />
          <span>קריאות התחנה ({stationOrders.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('debts')}
          className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 whitespace-nowrap ${
            activeTab === 'debts'
              ? 'bg-purple-600 text-white shadow'
              : 'text-slate-300 hover:text-white hover:bg-slate-800'
          }`}
        >
          <DollarSign className="w-3.5 h-3.5" />
          <span>עמלות וערעורים ({stationDebts.length})</span>
          {pendingAppealsCount > 0 && (
            <span className="bg-red-500 text-white text-[10px] px-1.5 py-0.2 rounded-full font-bold">
              {pendingAppealsCount}
            </span>
          )}
        </button>
      </div>

      {/* Tab 1: Overview */}
      {activeTab === 'overview' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 bg-slate-900/80 rounded-2xl p-5 border border-slate-800 space-y-4">
            <h3 className="font-bold text-white text-base flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-purple-400" />
              <span>ביצועי התחנה</span>
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 bg-slate-950/60 rounded-xl border border-slate-800">
                <span className="text-xs text-slate-400 block">סך מחזור נסיעות שנסגרו</span>
                <span className="text-2xl font-black text-white mt-1 block">₪{totalRevenue.toLocaleString()}</span>
                <span className="text-[11px] text-slate-500 mt-1 block">נסיעות שהושלמו בהצלחה</span>
              </div>
              <div className="p-4 bg-slate-950/60 rounded-xl border border-slate-800">
                <span className="text-xs text-slate-400 block">רווחי עמלות לתחנה ({currentStation.commission_percent}%)</span>
                <span className="text-2xl font-black text-emerald-400 mt-1 block">₪{totalCommission.toLocaleString()}</span>
                <span className="text-[11px] text-slate-500 mt-1 block">נגבו / חויבו ב-🍓</span>
              </div>
            </div>

            <div className="p-4 bg-purple-500/5 rounded-xl border border-purple-500/20 text-xs text-slate-300 leading-relaxed">
              💡 <strong>הערת ניהול:</strong> סדרני התחנה מנהלים ומשגרים קריאות מתוך כפתורי הצ'אט של הבוט בטלגרם. פאנל זה מאפשר לך, כמנהל התחנה, לפקח על פעילות הסדרנים, לעקוב אחר אחוזי הסגירה והעמלות, ולאשר/לסרב לבקשות ביטול חיובים (ערעורים).
            </div>
          </div>

          <div className="bg-slate-900/80 rounded-2xl p-5 border border-slate-800 space-y-4">
            <h3 className="font-bold text-white text-base flex items-center gap-2">
              <UserCheck className="w-4 h-4 text-amber-400" />
              <span>פרטי מנהל התחנה</span>
            </h3>
            <div className="space-y-2.5 text-xs">
              <div className="flex justify-between py-1.5 border-b border-slate-800">
                <span className="text-slate-400">שם מלא:</span>
                <span className="font-bold text-white">{currentUser.full_name}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-800">
                <span className="text-slate-400">מזהה טלגרם:</span>
                <span className="font-mono text-slate-300">{currentUser.user_id}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-800">
                <span className="text-slate-400">שם משתמש:</span>
                <span className="text-amber-300 font-bold">
                  {currentUser.telegram_username ? `@${currentUser.telegram_username}` : 'לא הוגדר'}
                </span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-800">
                <span className="text-slate-400">שיוך תחנה:</span>
                <span className="font-bold text-purple-300">{currentStation.name} (#{myStationId})</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Dispatchers */}
      {activeTab === 'dispatchers' && (
        <div className="bg-slate-900/80 rounded-2xl border border-slate-800 p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-white text-base flex items-center gap-2">
              <Radio className="w-4 h-4 text-purple-400" />
              <span>סדרני התחנה המשויכים (מי פרסם מה)</span>
            </h3>
            <span className="text-xs text-slate-400">{stationDispatchers.length} סדרנים רשומים</span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-right text-xs">
              <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="p-3">שם הסדרן</th>
                  <th className="p-3">שם משתמש בטלגרם (@username)</th>
                  <th className="p-3">טלפון</th>
                  <th className="p-3">קריאות שפורסמו</th>
                  <th className="p-3">תפקיד</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {stationDispatchers.map((d) => {
                  const publishedCount = stationOrders.filter((o) => o.publisher_id === d.user_id).length;
                  return (
                    <tr key={d.user_id} className="hover:bg-slate-800/40 transition">
                      <td className="p-3 font-bold text-white">{d.full_name}</td>
                      <td className="p-3">
                        {d.telegram_username ? (
                          <a
                            href={`https://t.me/${d.telegram_username}`}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1 text-purple-300 hover:text-purple-200 underline font-semibold"
                          >
                            <AtSign className="w-3 h-3" />
                            <span>{d.telegram_username}</span>
                          </a>
                        ) : (
                          <span className="text-slate-500 italic">אין שם משתמש</span>
                        )}
                      </td>
                      <td className="p-3 text-slate-300">{d.phone}</td>
                      <td className="p-3 font-extrabold text-amber-400">{publishedCount}</td>
                      <td className="p-3">
                        <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-blue-500/10 text-blue-300 border border-blue-500/30">
                          {ROLE_NAMES[d.role]}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 3: Station Orders */}
      {activeTab === 'orders' && (
        <div className="bg-slate-900/80 rounded-2xl border border-slate-800 p-5 space-y-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <h3 className="font-bold text-white text-base flex items-center gap-2">
              <FileText className="w-4 h-4 text-purple-400" />
              <span>יומן קריאות התחנה (#{myStationId})</span>
            </h3>
            <div className="relative w-full sm:w-64">
              <Search className="w-4 h-4 text-slate-400 absolute right-3 top-2.5" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="חיפוש קריאה לפי טקסט / עיר..."
                className="w-full bg-slate-950 border border-slate-800 rounded-xl pr-9 pl-3 py-1.5 text-xs text-white focus:outline-none focus:border-purple-500"
              />
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-right text-xs">
              <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="p-3">מזהה</th>
                  <th className="p-3">פרטי הנסיעה</th>
                  <th className="p-3">מחיר</th>
                  <th className="p-3">סדרן מפרסם</th>
                  <th className="p-3">נהג משובץ</th>
                  <th className="p-3">סטטוס</th>
                  <th className="p-3">תאריך</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {stationOrders
                  .filter((o) => !searchTerm || o.text.includes(searchTerm))
                  .map((o) => {
                    const pubUser = users.find((u) => u.user_id === o.publisher_id);
                    const driverUser = o.driver_id ? users.find((u) => u.user_id === o.driver_id) : null;
                    return (
                      <tr key={o.order_id} className="hover:bg-slate-800/40 transition">
                        <td className="p-3 font-mono font-bold text-slate-300">#{o.order_id}</td>
                        <td className="p-3 max-w-xs truncate text-white">{o.text}</td>
                        <td className="p-3 font-extrabold text-amber-400">₪{o.price}</td>
                        <td className="p-3">
                          <span className="font-semibold text-slate-200">
                            {pubUser ? pubUser.full_name : `סדרן #${o.publisher_id}`}
                          </span>
                          {pubUser?.telegram_username && (
                            <span className="text-[10px] text-purple-300 block">
                              @{pubUser.telegram_username}
                            </span>
                          )}
                        </td>
                        <td className="p-3 text-slate-300">
                          {driverUser ? driverUser.full_name : o.driver_id ? `נהג #${o.driver_id}` : '—'}
                        </td>
                        <td className="p-3">
                          <span
                            className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${
                              o.status === 'open'
                                ? 'bg-amber-500/10 text-amber-300 border border-amber-500/30'
                                : o.status === 'assigned'
                                ? 'bg-blue-500/10 text-blue-300 border border-blue-500/30'
                                : o.status === 'closed'
                                ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/30'
                                : 'bg-red-500/10 text-red-300 border border-red-500/30'
                            }`}
                          >
                            {o.status === 'open'
                              ? 'פתוחה'
                              : o.status === 'assigned'
                              ? 'משובצת'
                              : o.status === 'closed'
                              ? 'סגורה (חויבה)'
                              : 'בוטלה'}
                          </span>
                        </td>
                        <td className="p-3 text-slate-500 text-[10px]">
                          {new Date(o.created_at).toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' })}
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 4: Debts & Appeals */}
      {activeTab === 'debts' && (
        <div className="bg-slate-900/80 rounded-2xl border border-slate-800 p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-white text-base flex items-center gap-2">
              <DollarSign className="w-4 h-4 text-emerald-400" />
              <span>יומן חיובים, עמלות וערעורי נהגים לתחנה</span>
            </h3>
            <span className="text-xs text-slate-400">סה"כ {stationDebts.length} חיובים</span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-right text-xs">
              <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="p-3">מזהה חיוב</th>
                  <th className="p-3">קריאה</th>
                  <th className="p-3">נהג מחויב</th>
                  <th className="p-3">סכום עמלה (🍓)</th>
                  <th className="p-3">סטטוס חיוב</th>
                  <th className="p-3">סטטוס ערעור</th>
                  <th className="p-3 text-center">פעולות מנהל</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {stationDebts.map((d) => {
                  const driver = users.find((u) => u.user_id === d.driver_id);
                  return (
                    <tr key={d.debt_id} className="hover:bg-slate-800/40 transition">
                      <td className="p-3 font-mono font-bold text-slate-300">#{d.debt_id}</td>
                      <td className="p-3 font-mono text-purple-300">#{d.order_id}</td>
                      <td className="p-3 font-bold text-white">
                        {driver ? driver.full_name : `נהג #${d.driver_id}`}
                      </td>
                      <td className="p-3 font-extrabold text-amber-400">₪{d.amount.toFixed(2)} (🍓)</td>
                      <td className="p-3">
                        <span
                          className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${
                            d.status === 'paid'
                              ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/30'
                              : d.status === 'cancelled'
                              ? 'bg-slate-500/20 text-slate-400'
                              : 'bg-red-500/10 text-red-300 border border-red-500/30'
                          }`}
                        >
                          {d.status === 'paid' ? 'שולם' : d.status === 'cancelled' ? 'בוטל / זוכה' : 'ממתין לתשלום'}
                        </span>
                      </td>
                      <td className="p-3">
                        {d.appeal_status === 'pending' ? (
                          <div className="space-y-1">
                            <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 animate-pulse">
                              ערעור ממתין
                            </span>
                            {d.appeal_reason && (
                              <p className="text-[10px] text-slate-400 max-w-xs italic">
                                "{d.appeal_reason}"
                              </p>
                            )}
                          </div>
                        ) : d.appeal_status === 'approved' ? (
                          <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-emerald-500/10 text-emerald-300">
                            ערעור התקבל (🍏)
                          </span>
                        ) : d.appeal_status === 'rejected' ? (
                          <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-red-500/10 text-red-300">
                            ערעור נדחה
                          </span>
                        ) : d.appeal_status === 'confirmed' ? (
                          <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-blue-500/10 text-blue-300">
                            אושר ע"י הנהג
                          </span>
                        ) : (
                          <span className="text-slate-500">—</span>
                        )}
                      </td>
                      <td className="p-3 text-center">
                        {d.appeal_status === 'pending' && d.status !== 'cancelled' ? (
                          <div className="flex items-center justify-center gap-1.5">
                            <button
                              onClick={() => handleResolveAppeal(d.debt_id, true)}
                              className="px-2 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] font-bold transition flex items-center gap-1 shadow"
                              title="אשר ביטול חיוב (זיכוי הנהג 🍏)"
                            >
                              <span>🍏 אשר זיכוי</span>
                            </button>
                            <button
                              onClick={() => handleResolveAppeal(d.debt_id, false)}
                              className="px-2 py-1 rounded-lg bg-red-600/80 hover:bg-red-600 text-white text-[11px] font-bold transition flex items-center gap-1 shadow"
                              title="דחה ערעור"
                            >
                              <span>❌ דחה</span>
                            </button>
                          </div>
                        ) : (
                          <span className="text-slate-500 text-[11px]">ללא פעולה נדרשת</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
