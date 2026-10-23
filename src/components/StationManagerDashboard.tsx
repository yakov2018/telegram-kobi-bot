import React, { useState } from 'react';
import { useApp } from '../context/AppContext';
import { User, Order, Debt, Station, ROLE_NAMES, Role } from '../types';
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
  Search,
  RotateCcw,
  Percent,
  Plus,
  Trash2,
  Scale,
} from 'lucide-react';

export const StationManagerDashboard: React.FC = () => {
  const {
    currentUser,
    stations,
    orders,
    debts,
    users,
    updateUserRoleAndStation,
    resolveDebtAppeal,
    refreshAllData,
  } = useApp();

  // Role guard: Only station_manager or admin
  if (currentUser.role !== 'station_manager' && currentUser.role !== 'admin') {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-2xl p-6 text-center text-red-300 font-bold my-8">
        ⛔ גישה חסומה: פאנל ניהול תחנה מיועד אך ורק למנהלי תחנה מורשים.
      </div>
    );
  }

  const [activeTab, setActiveTab] = useState<'overview' | 'dispatchers' | 'orders' | 'appeals'>('overview');
  const [searchTerm, setSearchTerm] = useState('');
  const [feedback, setFeedback] = useState<string | null>(null);

  // New dispatcher modal state
  const [isAddDispatcherModalOpen, setIsAddDispatcherModalOpen] = useState(false);
  const [selectedUserToAdd, setSelectedUserToAdd] = useState<number | null>(null);

  const myStationId = currentUser.station_id || 1;
  const currentStation = (stations || []).find((s) => s.station_id === myStationId) || {
    station_id: myStationId,
    name: `תחנה #${myStationId}`,
    commission_percent: 10.0,
  };

  // Strictly filter data to this manager's station only
  const stationOrders = (orders || []).filter((o) => o?.station_id === myStationId);
  const stationDebts = (debts || []).filter((d) => d?.station_id === myStationId);
  const stationDispatchers = (users || []).filter(
    (u) => u?.station_id === myStationId && (u?.role === 'dispatcher' || u?.role === 'station_manager')
  );

  // Station Stats
  const openCount = stationOrders.filter((o) => o?.status === 'open').length;
  const assignedCount = stationOrders.filter((o) => o?.status === 'assigned').length;
  const closedCount = stationOrders.filter((o) => o?.status === 'closed').length;
  const cancelledCount = stationOrders.filter((o) => o?.status === 'cancelled').length;

  const totalRevenue = stationOrders
    .filter((o) => o?.status === 'closed')
    .reduce((acc, o) => acc + (o?.price || 0), 0);

  const totalCommission = stationDebts
    .filter((d) => d?.status !== 'cancelled')
    .reduce((acc, d) => acc + (d?.amount || 0), 0);

  const pendingAppeals = stationDebts.filter((d) => d?.appeal_status === 'pending');

  const handleResolveAppeal = async (debtId: number, approve: boolean) => {
    const ok = await resolveDebtAppeal(debtId, approve);
    if (ok) {
      setFeedback(approve ? '🍏 החיוב בוטל והנהג זוכה במלואו!' : '❌ הבקשה לביטול חיוב נדחתה.');
      setTimeout(() => setFeedback(null), 4000);
    }
  };

  const handleAddDispatcher = async () => {
    if (!selectedUserToAdd) return;
    await updateUserRoleAndStation(selectedUserToAdd, 'dispatcher', myStationId);
    setIsAddDispatcherModalOpen(false);
    setSelectedUserToAdd(null);
    setFeedback('✅ סדרן נוסף בהצלחה לתחנה!');
    setTimeout(() => setFeedback(null), 4000);
  };

  const handleRemoveDispatcher = async (userId: number) => {
    if (userId === currentUser.user_id) {
      setFeedback('⚠️ לא ניתן להסיר את עצמך.');
      setTimeout(() => setFeedback(null), 3000);
      return;
    }
    await updateUserRoleAndStation(userId, 'user', myStationId);
    setFeedback('✅ הסדרן הוסר מהתחנה והוחזר למעמד נהג.');
    setTimeout(() => setFeedback(null), 4000);
  };

  const driversAvailableToAdd = (users || []).filter(
    (u) => u.role === 'user' && u.is_blocked === 0
  );

  return (
    <div className="space-y-6">
      {/* Station Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 sm:p-5 shadow-sm flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-2xl bg-purple-600/20 border border-purple-500/30 flex items-center justify-center text-purple-400 text-xl font-bold">
            🏢
          </div>
          <div>
            <h2 className="font-extrabold text-base sm:text-lg text-white flex items-center gap-2">
              <span>פאנל ניהול: {currentStation.name}</span>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-300 border border-purple-500/30 font-mono font-bold">
                {currentStation.commission_percent}% עמלת תחנה
              </span>
            </h2>
            <p className="text-xs text-slate-400">
              ניהול צוות סדרנים, צפייה בסטטיסטיקות התחנה וטיפול בערעורי חיובים
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => refreshAllData()}
            className="p-2 rounded-xl bg-slate-800 text-slate-300 hover:text-white transition flex items-center gap-1.5 text-xs font-bold"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>רענן</span>
          </button>
        </div>
      </div>

      {feedback && (
        <div className="bg-purple-500/15 border border-purple-500/40 text-purple-200 px-4 py-3 rounded-xl flex items-center justify-between text-xs font-semibold">
          <span>{feedback}</span>
          <button onClick={() => setFeedback(null)} className="text-purple-400 hover:text-white">✕</button>
        </div>
      )}

      {/* Sub Tabs */}
      <div className="flex gap-2 border-b border-slate-800 pb-2 text-xs font-bold overflow-x-auto">
        <button
          onClick={() => setActiveTab('overview')}
          className={`px-3.5 py-2 rounded-xl transition cursor-pointer whitespace-nowrap ${
            activeTab === 'overview' ? 'bg-purple-600 text-white shadow' : 'bg-slate-900 text-slate-300 hover:text-white'
          }`}
        >
          📊 מבט על וסטטיסטיקות
        </button>
        <button
          onClick={() => setActiveTab('dispatchers')}
          className={`px-3.5 py-2 rounded-xl transition cursor-pointer whitespace-nowrap ${
            activeTab === 'dispatchers' ? 'bg-purple-600 text-white shadow' : 'bg-slate-900 text-slate-300 hover:text-white'
          }`}
        >
          👥 צוות סדרנים ({stationDispatchers.length})
        </button>
        <button
          onClick={() => setActiveTab('orders')}
          className={`px-3.5 py-2 rounded-xl transition cursor-pointer whitespace-nowrap ${
            activeTab === 'orders' ? 'bg-purple-600 text-white shadow' : 'bg-slate-900 text-slate-300 hover:text-white'
          }`}
        >
          📋 קריאות התחנה ({stationOrders.length})
        </button>
        <button
          onClick={() => setActiveTab('appeals')}
          className={`px-3.5 py-2 rounded-xl transition cursor-pointer whitespace-nowrap flex items-center gap-1.5 ${
            activeTab === 'appeals' ? 'bg-purple-600 text-white shadow' : 'bg-slate-900 text-slate-300 hover:text-white'
          }`}
        >
          <Scale className="w-3.5 h-3.5" />
          <span>ערעורים וביטולי חיוב</span>
          {pendingAppeals.length > 0 && (
            <span className="w-5 h-5 rounded-full bg-red-500 text-white text-[10px] flex items-center justify-center font-mono">
              {pendingAppeals.length}
            </span>
          )}
        </button>
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
            <div className="bg-slate-900 border border-slate-800 p-4 rounded-2xl space-y-1">
              <span className="text-xs text-slate-400">סה"כ קריאות בתחנה</span>
              <p className="text-xl sm:text-2xl font-black text-white font-mono">{stationOrders.length}</p>
              <div className="text-[11px] text-slate-500">
                {openCount} פתוחות • {closedCount} נסגרו
              </div>
            </div>

            <div className="bg-slate-900 border border-slate-800 p-4 rounded-2xl space-y-1">
              <span className="text-xs text-slate-400">מחזור נסיעות שנסגרו</span>
              <p className="text-xl sm:text-2xl font-black text-amber-400 font-mono">₪{totalRevenue.toFixed(0)}</p>
              <div className="text-[11px] text-slate-500">
                לפי {closedCount} קריאות שהושלמו
              </div>
            </div>

            <div className="bg-slate-900 border border-slate-800 p-4 rounded-2xl space-y-1">
              <span className="text-xs text-slate-400">עמלות תחנה שנרשמו</span>
              <p className="text-xl sm:text-2xl font-black text-emerald-400 font-mono">₪{totalCommission.toFixed(2)}</p>
              <div className="text-[11px] text-slate-500">
                לפי {currentStation.commission_percent}% עמלה
              </div>
            </div>

            <div className="bg-slate-900 border border-slate-800 p-4 rounded-2xl space-y-1">
              <span className="text-xs text-slate-400">צוות סדרנים ומנהלים</span>
              <p className="text-xl sm:text-2xl font-black text-purple-400 font-mono">{stationDispatchers.length}</p>
              <div className="text-[11px] text-slate-500">
                {pendingAppeals.length} ערעורים ממתינים
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Dispatchers Team Tab */}
      {activeTab === 'dispatchers' && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 sm:p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-extrabold text-sm text-white">
              צוות הסדרנים של {currentStation.name} ({stationDispatchers.length})
            </h3>
            <button
              onClick={() => setIsAddDispatcherModalOpen(true)}
              className="px-3 py-1.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs transition flex items-center gap-1.5 shadow cursor-pointer"
            >
              <Plus className="w-4 h-4" />
              <span>הוסף סדרן לתחנה</span>
            </button>
          </div>

          <div className="space-y-2">
            {stationDispatchers.map((disp) => {
              const ordersCount = stationOrders.filter((o) => o.publisher_id === disp.user_id).length;
              return (
                <div
                  key={disp.user_id}
                  className="bg-slate-950 border border-slate-800 p-3 rounded-xl flex items-center justify-between gap-3 text-xs"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-purple-500/10 text-purple-400 flex items-center justify-center font-bold">
                      👤
                    </div>
                    <div>
                      <strong className="text-white text-sm">{disp.full_name}</strong>
                      <p className="text-[11px] text-slate-400">
                        @{disp.telegram_username || 'אין'} | טל: {disp.phone || 'אין'} | תפקיד: {ROLE_NAMES[disp.role]}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <span className="text-[11px] text-slate-400">
                      פרסם: <strong className="text-white font-mono">{ordersCount}</strong> קריאות
                    </span>
                    {disp.user_id !== currentUser.user_id && (
                      <button
                        onClick={() => handleRemoveDispatcher(disp.user_id)}
                        className="p-1.5 rounded-lg bg-slate-800 hover:bg-red-500/20 text-slate-400 hover:text-red-400 transition cursor-pointer"
                        title="הסר סדרן מהתחנה"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Orders Tab */}
      {activeTab === 'orders' && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 sm:p-5 shadow-sm space-y-4">
          <h3 className="font-extrabold text-sm text-white">יומן קריאות של {currentStation.name}</h3>
          {stationOrders.length === 0 ? (
            <p className="text-xs text-slate-500 italic text-center py-4">אין קריאות רשומות בתחנה זו.</p>
          ) : (
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {stationOrders.map((o) => (
                <div key={o.order_id} className="bg-slate-950 border border-slate-800 p-3 rounded-xl text-xs space-y-1.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-amber-400">#{o.order_id}</span>
                      <span className="font-bold text-white">₪{o.price}</span>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                        {o.status}
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-500">{o.created_at?.slice(0, 10)}</span>
                  </div>
                  <p className="text-slate-300 text-[11px] whitespace-pre-wrap">{o.text}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Appeals Tab (סעיף 5: [בטל חיוב] / [סרב לביטול]) */}
      {activeTab === 'appeals' && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 sm:p-5 shadow-sm space-y-4">
          <h3 className="font-extrabold text-sm text-white flex items-center gap-2">
            <Scale className="w-4 h-4 text-amber-400" />
            <span>בקשות לביטול חיוב וערעורים ({pendingAppeals.length} ממתינים)</span>
          </h3>

          {pendingAppeals.length === 0 ? (
            <div className="bg-slate-950 p-6 rounded-xl border border-slate-800 text-center text-slate-500 text-xs">
              ✅ אין בקשות ביטול חיוב ממתינות לבדיקה כרגע.
            </div>
          ) : (
            <div className="space-y-3">
              {pendingAppeals.map((debt) => {
                const driver = users.find((u) => u.user_id === debt.driver_id);
                return (
                  <div
                    key={debt.debt_id}
                    className="bg-slate-950 border border-slate-800 p-4 rounded-xl space-y-3 text-xs"
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <strong className="text-white text-sm">{driver?.full_name || `נהג #${debt.driver_id}`}</strong>
                        <span className="text-slate-400 text-[11px] block">
                          חיוב #{debt.debt_id} {debt.order_id ? `(קריאה #${debt.order_id})` : ''} | עמלה: ₪{debt.amount}
                        </span>
                      </div>
                      <span className="text-base font-extrabold text-amber-400 font-mono">
                        🍓 ₪{debt.amount}
                      </span>
                    </div>

                    <div className="p-3 bg-purple-500/10 border border-purple-500/30 rounded-xl text-purple-200">
                      <span className="font-bold block text-purple-300 mb-1">✍️ סיבת הבקשה שהקליד הנהג:</span>
                      "{debt.appeal_reason || 'לא פורטה סיבה'}"
                    </div>

                    <div className="flex gap-2 pt-1">
                      <button
                        onClick={() => handleResolveAppeal(debt.debt_id, true)}
                        className="flex-1 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold transition flex items-center justify-center gap-1 shadow cursor-pointer"
                      >
                        <CheckCircle className="w-3.5 h-3.5" />
                        <span>בטל חיוב (זכה נהג)</span>
                      </button>
                      <button
                        onClick={() => handleResolveAppeal(debt.debt_id, false)}
                        className="flex-1 py-2 rounded-xl bg-red-600 hover:bg-red-500 text-white font-bold transition flex items-center justify-center gap-1 shadow cursor-pointer"
                      >
                        <XCircle className="w-3.5 h-3.5" />
                        <span>סרב לביטול (השאר חיוב)</span>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Add Dispatcher Modal */}
      {isAddDispatcherModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-5 shadow-2xl space-y-4">
            <h4 className="font-extrabold text-base text-white">
              הוספת סדרן לתחנה: {currentStation.name}
            </h4>
            <p className="text-xs text-slate-400">
              בחר נהג להענקה של הרשאת סדרן בתחנה שלך:
            </p>

            <select
              value={selectedUserToAdd || ''}
              onChange={(e) => setSelectedUserToAdd(Number(e.target.value))}
              className="w-full bg-slate-950 border border-slate-700 rounded-xl p-2.5 text-xs text-white focus:outline-none focus:border-purple-500"
            >
              <option value="">בחר נהג מהרשימה...</option>
              {driversAvailableToAdd.map((u) => (
                <option key={u.user_id} value={u.user_id}>
                  {u.full_name} ({u.phone || 'ללא טלפון'})
                </option>
              ))}
            </select>

            <div className="flex gap-2 pt-2">
              <button
                type="button"
                onClick={handleAddDispatcher}
                disabled={!selectedUserToAdd}
                className="flex-1 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-bold text-xs transition cursor-pointer"
              >
                אישור והוספת סדרן
              </button>
              <button
                type="button"
                onClick={() => setIsAddDispatcherModalOpen(false)}
                className="px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition cursor-pointer"
              >
                ביטול
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
