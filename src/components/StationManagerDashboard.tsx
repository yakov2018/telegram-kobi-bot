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
  Edit3,
} from 'lucide-react';

export const StationManagerDashboard: React.FC = () => {
  const {
    currentUser,
    stations,
    orders,
    debts,
    users,
    updateUserRoleAndStation,
    chargeDriverDebt,
    creditDriverDebt,
    updateDebt,
    deleteDebt,
    updateOrder,
    deleteOrder,
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

  const [activeTab, setActiveTab] = useState<'overview' | 'dispatchers' | 'orders' | 'debts' | 'appeals'>('overview');
  const [feedback, setFeedback] = useState<string | null>(null);

  // New dispatcher modal state
  const [isAddDispatcherModalOpen, setIsAddDispatcherModalOpen] = useState(false);
  const [selectedUserToAdd, setSelectedUserToAdd] = useState<number | null>(null);

  // Charge / Credit modal state
  const [chargeCreditModal, setChargeCreditModal] = useState<{
    isOpen: boolean;
    type: 'charge' | 'credit';
    driver_id: number;
    amount: string;
    reason: string;
    order_id: string;
  }>({
    isOpen: false,
    type: 'charge',
    driver_id: 0,
    amount: '20',
    reason: 'עמלת נסיעה (🍓)',
    order_id: '',
  });

  // Edit Debt modal state
  const [editDebtModal, setEditDebtModal] = useState<{
    isOpen: boolean;
    debt_id: number;
    amount: string;
    reason: string;
    status: 'unpaid' | 'paid' | 'cancelled';
  }>({
    isOpen: false,
    debt_id: 0,
    amount: '0',
    reason: '',
    status: 'unpaid',
  });

  // Edit Order modal state
  const [editOrderModal, setEditOrderModal] = useState<{
    isOpen: boolean;
    order_id: number;
    price: string;
    text: string;
    status: 'open' | 'assigned' | 'closed' | 'cancelled';
  }>({
    isOpen: false,
    order_id: 0,
    price: '',
    text: '',
    status: 'open',
  });

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
              ניהול קריאות, חיובים וזיכויים 🍏, צוות סדרנים וערעורים
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => refreshAllData()}
            className="p-2 rounded-xl bg-slate-800 text-slate-300 hover:text-white transition flex items-center gap-1.5 text-xs font-bold cursor-pointer"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>רענן</span>
          </button>
        </div>
      </div>

      {feedback && (
        <div className="bg-purple-500/15 border border-purple-500/40 text-purple-200 px-4 py-3 rounded-xl flex items-center justify-between text-xs font-semibold">
          <span>{feedback}</span>
          <button onClick={() => setFeedback(null)} className="text-purple-400 hover:text-white cursor-pointer">✕</button>
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
          onClick={() => setActiveTab('debts')}
          className={`px-3.5 py-2 rounded-xl transition cursor-pointer whitespace-nowrap flex items-center gap-1.5 ${
            activeTab === 'debts' ? 'bg-purple-600 text-white shadow' : 'bg-slate-900 text-slate-300 hover:text-white'
          }`}
        >
          <span>💳 חיובים וזיכויים ({stationDebts.length})</span>
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

      {/* Orders Tab: צפייה ועריכה חופשית של כל קריאות התחנה */}
      {activeTab === 'orders' && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 sm:p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-extrabold text-sm text-white">יומן קריאות של {currentStation.name} ({stationOrders.length})</h3>
            <span className="text-xs text-slate-400">באפשרותך לערוך או לבטל כל קריאה</span>
          </div>

          {stationOrders.length === 0 ? (
            <p className="text-xs text-slate-500 italic text-center py-4">אין קריאות רשומות בתחנה זו.</p>
          ) : (
            <div className="space-y-2.5 max-h-[500px] overflow-y-auto">
              {stationOrders.map((o) => {
                const statusColors = {
                  open: 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30',
                  assigned: 'bg-amber-500/10 text-amber-400 border border-amber-500/30',
                  closed: 'bg-purple-500/10 text-purple-400 border border-purple-500/30',
                  cancelled: 'bg-red-500/10 text-red-400 border border-red-500/30',
                  deleted: 'bg-red-500/10 text-red-400 border border-red-500/30',
                };
                const statusLabels = {
                  open: 'פתוחה לנהגים',
                  assigned: 'משוריינת לנהג',
                  closed: 'הושלמה ונסגרה',
                  cancelled: 'בוטלה',
                  deleted: 'נמחקה',
                };

                return (
                  <div key={o.order_id} className="bg-slate-950 border border-slate-800 p-3.5 rounded-xl text-xs space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-black text-amber-400">#{o.order_id}</span>
                        <span className="font-bold text-white text-sm">₪{o.price}</span>
                        <span className={`text-[10px] px-2 py-0.5 rounded font-bold ${statusColors[o.status] || 'bg-slate-800 text-slate-300'}`}>
                          {statusLabels[o.status] || o.status}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-slate-500">{o.created_at?.slice(0, 16)}</span>
                        <button
                          onClick={() => setEditOrderModal({
                            isOpen: true,
                            order_id: o.order_id,
                            price: String(o.price),
                            text: o.text,
                            status: o.status as any,
                          })}
                          className="p-1 rounded bg-slate-800 hover:bg-slate-700 text-amber-300 transition cursor-pointer"
                          title="ערוך קריאה"
                        >
                          <Edit3 className="w-3.5 h-3.5" />
                        </button>
                        {o.status !== 'cancelled' && (
                          <button
                            onClick={async () => {
                              await deleteOrder(o.order_id);
                              setFeedback(`🚫 קריאה #${o.order_id} בוטלה בהצלחה.`);
                              setTimeout(() => setFeedback(null), 3000);
                            }}
                            className="p-1 rounded bg-slate-800 hover:bg-red-500/20 text-slate-400 hover:text-red-400 transition cursor-pointer"
                            title="בטל קריאה"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </div>
                    <p className="text-slate-300 text-[11px] whitespace-pre-wrap">{o.text}</p>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Debts Tab: חיובים וזיכויים של התחנה */}
      {activeTab === 'debts' && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 sm:p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-extrabold text-sm text-white flex items-center gap-2">
                <span>💳 יומן חיובים וזיכויים 🍏 ({stationDebts.length})</span>
              </h3>
              <p className="text-xs text-slate-400">ניהול, עריכה, הוספת חיוב/זיכוי וביטול חובות של נהגים בתחנה</p>
            </div>
            <button
              onClick={() => setChargeCreditModal({
                isOpen: true,
                type: 'charge',
                driver_id: users.find((u) => u.role === 'user')?.user_id || 0,
                amount: '20',
                reason: 'עמלת נסיעה (🍓)',
                order_id: '',
              })}
              className="px-3.5 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs transition flex items-center gap-1.5 shadow cursor-pointer"
            >
              <Plus className="w-4 h-4" />
              <span>➕ חיוב / זיכוי נהג</span>
            </button>
          </div>

          {stationDebts.length === 0 ? (
            <p className="text-xs text-slate-500 italic text-center py-6">אין חיובים או זיכויים רשומים בתחנה זו.</p>
          ) : (
            <div className="space-y-2.5 max-h-[500px] overflow-y-auto">
              {stationDebts.map((d) => {
                const driver = users.find((u) => u.user_id === d.driver_id);
                const isCredit = (d.amount < 0) || (d as any).transaction_type === 'manual_credit' || d.reason?.includes('זיכוי');

                return (
                  <div key={d.debt_id} className="bg-slate-950 border border-slate-800 p-3.5 rounded-xl text-xs space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-slate-400">#{d.debt_id}</span>
                        <span className={`font-mono font-extrabold text-sm ${isCredit ? 'text-emerald-400' : 'text-amber-400'}`}>
                          {isCredit ? '🍏 זיכוי' : '🍓 חיוב'}: ₪{Math.abs(d.amount).toFixed(2)}
                        </span>
                        <span className={`text-[10px] px-2 py-0.5 rounded font-bold ${
                          d.status === 'paid' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30' :
                          d.status === 'cancelled' ? 'bg-red-500/10 text-red-400 border border-red-500/30' :
                          'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                        }`}>
                          {d.status === 'paid' ? 'שולם / זוכה' : d.status === 'cancelled' ? 'בוטל' : 'לא שולם'}
                        </span>
                        {d.appeal_status === 'pending' && (
                          <span className="text-[10px] px-2 py-0.5 rounded bg-red-500/20 text-red-300 font-bold">
                            ⏳ ערעור ממתין
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setEditDebtModal({
                            isOpen: true,
                            debt_id: d.debt_id,
                            amount: String(d.amount),
                            reason: d.reason || '',
                            status: d.status,
                          })}
                          className="p-1 rounded bg-slate-800 hover:bg-slate-700 text-amber-300 transition cursor-pointer"
                          title="ערוך פרטי חיוב/זיכוי"
                        >
                          <Edit3 className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={async () => {
                            await deleteDebt(d.debt_id);
                            setFeedback(`🗑️ חיוב #${d.debt_id} בוטל ונמחק בהצלחה.`);
                            setTimeout(() => setFeedback(null), 3000);
                          }}
                          className="p-1 rounded bg-slate-800 hover:bg-red-500/20 text-slate-400 hover:text-red-400 transition cursor-pointer"
                          title="מחק / בטל חיוב"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>

                    <div className="flex items-center justify-between text-slate-400 text-[11px]">
                      <span>
                        נהג: <strong className="text-white">{driver?.full_name || `ID ${d.driver_id}`}</strong> {driver?.phone ? `(${driver.phone})` : ''}
                      </span>
                      <span>{d.reason}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Appeals Tab */}
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
                        <span>בטל חיוב (זכה נהג 🍏)</span>
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

      {/* Charge / Credit Modal */}
      {chargeCreditModal.isOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-5 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h4 className="font-extrabold text-base text-white">
                {chargeCreditModal.type === 'credit' ? '🍏 זיכוי נהג בתחנה' : '🍓 חיוב נהג בעמלה'}
              </h4>
              <button
                onClick={() => setChargeCreditModal((prev) => ({ ...prev, isOpen: false }))}
                className="text-slate-400 hover:text-white cursor-pointer"
              >
                ✕
              </button>
            </div>

            <form
              onSubmit={async (e) => {
                e.preventDefault();
                let amt = parseFloat(chargeCreditModal.amount);
                if (!chargeCreditModal.driver_id || isNaN(amt) || amt === 0) return;

                const isCredit = chargeCreditModal.type === 'credit' || amt < 0;
                const finalAmt = Math.abs(amt);

                if (isCredit) {
                  await creditDriverDebt(
                    chargeCreditModal.driver_id,
                    finalAmt,
                    chargeCreditModal.reason.trim() || 'זיכוי נהג (🍏)',
                    myStationId
                  );
                  setFeedback(`🍏 הנהג זוכה ב-₪${finalAmt.toFixed(2)} בהצלחה!`);
                } else {
                  await chargeDriverDebt(
                    chargeCreditModal.driver_id,
                    finalAmt,
                    chargeCreditModal.reason.trim() || 'עמלת נסיעה (🍓)',
                    myStationId,
                    chargeCreditModal.order_id ? parseInt(chargeCreditModal.order_id, 10) : undefined
                  );
                  setFeedback(`🍓 הנהג חויב ב-₪${finalAmt.toFixed(2)} בהצלחה.`);
                }

                setChargeCreditModal((prev) => ({ ...prev, isOpen: false }));
                setTimeout(() => setFeedback(null), 4000);
              }}
              className="space-y-3.5 text-xs"
            >
              {/* Type Switcher */}
              <div className="flex gap-2 p-1 bg-slate-950 border border-slate-800 rounded-xl">
                <button
                  type="button"
                  onClick={() => setChargeCreditModal((prev) => ({ ...prev, type: 'charge', reason: 'עמלת נסיעה (🍓)' }))}
                  className={`flex-1 py-2 rounded-lg font-bold transition flex items-center justify-center gap-1.5 cursor-pointer ${
                    chargeCreditModal.type === 'charge' ? 'bg-amber-500 text-slate-950 shadow' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <span>🍓</span>
                  <span>חיוב עמלה</span>
                </button>
                <button
                  type="button"
                  onClick={() => setChargeCreditModal((prev) => ({ ...prev, type: 'credit', reason: 'זיכוי נהג (🍏)' }))}
                  className={`flex-1 py-2 rounded-lg font-bold transition flex items-center justify-center gap-1.5 cursor-pointer ${
                    chargeCreditModal.type === 'credit' ? 'bg-emerald-500 text-slate-950 shadow' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <span>🍏</span>
                  <span>זיכוי נהג</span>
                </button>
              </div>

              <div>
                <label className="text-slate-300 block mb-1 font-bold">בחר נהג</label>
                <select
                  value={chargeCreditModal.driver_id}
                  onChange={(e) => setChargeCreditModal((prev) => ({ ...prev, driver_id: Number(e.target.value) }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl p-2.5 text-white font-bold"
                  required
                >
                  <option value="">-- בחר נהג --</option>
                  {users.map((u) => (
                    <option key={u.user_id} value={u.user_id}>
                      {u.full_name} ({u.phone || 'ללא טלפון'}) | חוב: ₪{u.debt_balance.toFixed(2)}
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-slate-300 block mb-1 font-bold">סכום (₪)</label>
                  <input
                    type="number"
                    step="0.5"
                    placeholder="סכום (גם עם - לזיכוי)"
                    value={chargeCreditModal.amount}
                    onChange={(e) => {
                      const val = e.target.value;
                      if (val.startsWith('-')) {
                        setChargeCreditModal((prev) => ({
                          ...prev,
                          type: 'credit',
                          amount: val.replace('-', ''),
                          reason: prev.reason === 'עמלת נסיעה (🍓)' ? 'זיכוי נהג (🍏)' : prev.reason
                        }));
                      } else {
                        setChargeCreditModal((prev) => ({ ...prev, amount: val }));
                      }
                    }}
                    className="w-full bg-slate-950 border border-slate-700 rounded-xl p-2.5 text-white font-bold font-mono"
                    required
                  />
                </div>

                <div>
                  <label className="text-slate-300 block mb-1 font-bold">מספר קריאה (אופציונלי)</label>
                  <input
                    type="number"
                    placeholder="למשל 1005"
                    value={chargeCreditModal.order_id}
                    onChange={(e) => setChargeCreditModal((prev) => ({ ...prev, order_id: e.target.value }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-xl p-2.5 text-white font-mono"
                  />
                </div>
              </div>

              <div>
                <label className="text-slate-300 block mb-1 font-bold">סיבת הפעולה</label>
                <input
                  type="text"
                  placeholder={chargeCreditModal.type === 'credit' ? 'למשל: זיכוי בגין ביטול נסיעה' : 'למשל: עמלת נסיעה 10%'}
                  value={chargeCreditModal.reason}
                  onChange={(e) => setChargeCreditModal((prev) => ({ ...prev, reason: e.target.value }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl p-2.5 text-white"
                  required
                />
              </div>

              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setChargeCreditModal((prev) => ({ ...prev, isOpen: false }))}
                  className="flex-1 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold cursor-pointer"
                >
                  ביטול
                </button>
                <button
                  type="submit"
                  className={`flex-1 py-2.5 rounded-xl font-extrabold text-slate-950 shadow flex items-center justify-center gap-1.5 cursor-pointer ${
                    chargeCreditModal.type === 'credit' ? 'bg-emerald-500 hover:bg-emerald-400' : 'bg-amber-500 hover:bg-amber-400'
                  }`}
                >
                  <span>{chargeCreditModal.type === 'credit' ? '🍏' : '🍓'}</span>
                  <span>{chargeCreditModal.type === 'credit' ? 'אשר זיכוי 🍏' : 'אשר חיוב 🍓'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Debt Modal */}
      {editDebtModal.isOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-5 space-y-4 shadow-2xl text-xs">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h4 className="font-extrabold text-base text-white">עריכת חיוב/זיכוי #{editDebtModal.debt_id}</h4>
              <button onClick={() => setEditDebtModal((prev) => ({ ...prev, isOpen: false }))} className="text-slate-400 hover:text-white cursor-pointer">✕</button>
            </div>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                await updateDebt(editDebtModal.debt_id, {
                  amount: parseFloat(editDebtModal.amount),
                  reason: editDebtModal.reason,
                  status: editDebtModal.status,
                });
                setEditDebtModal((prev) => ({ ...prev, isOpen: false }));
                setFeedback(`✅ פרטי החיוב עודכנו בהצלחה.`);
                setTimeout(() => setFeedback(null), 3000);
              }}
              className="space-y-3"
            >
              <div>
                <label className="text-slate-300 block mb-1 font-bold">סכום (₪)</label>
                <input
                  type="number"
                  step="0.5"
                  value={editDebtModal.amount}
                  onChange={(e) => setEditDebtModal((prev) => ({ ...prev, amount: e.target.value }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl p-2.5 text-white font-mono font-bold"
                  required
                />
              </div>

              <div>
                <label className="text-slate-300 block mb-1 font-bold">סיבה</label>
                <input
                  type="text"
                  value={editDebtModal.reason}
                  onChange={(e) => setEditDebtModal((prev) => ({ ...prev, reason: e.target.value }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl p-2.5 text-white"
                  required
                />
              </div>

              <div>
                <label className="text-slate-300 block mb-1 font-bold">סטטוס חיוב</label>
                <select
                  value={editDebtModal.status}
                  onChange={(e) => setEditDebtModal((prev) => ({ ...prev, status: e.target.value as any }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl p-2.5 text-white"
                >
                  <option value="unpaid">לא שולם (unpaid)</option>
                  <option value="paid">שולם / זוכה (paid)</option>
                  <option value="cancelled">בוטל (cancelled)</option>
                </select>
              </div>

              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setEditDebtModal((prev) => ({ ...prev, isOpen: false }))}
                  className="flex-1 py-2.5 rounded-xl bg-slate-800 text-slate-300 font-bold cursor-pointer"
                >
                  ביטול
                </button>
                <button
                  type="submit"
                  className="flex-1 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold cursor-pointer"
                >
                  שמור שינויים
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Order Modal */}
      {editOrderModal.isOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-5 space-y-4 shadow-2xl text-xs">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h4 className="font-extrabold text-base text-white">עריכת קריאה #{editOrderModal.order_id}</h4>
              <button onClick={() => setEditOrderModal((prev) => ({ ...prev, isOpen: false }))} className="text-slate-400 hover:text-white cursor-pointer">✕</button>
            </div>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                await updateOrder(editOrderModal.order_id, {
                  price: parseFloat(editOrderModal.price),
                  text: editOrderModal.text,
                  status: editOrderModal.status,
                });
                setEditOrderModal((prev) => ({ ...prev, isOpen: false }));
                setFeedback(`✅ קריאה #${editOrderModal.order_id} עודכנה בהצלחה.`);
                setTimeout(() => setFeedback(null), 3000);
              }}
              className="space-y-3"
            >
              <div>
                <label className="text-slate-300 block mb-1 font-bold">מחיר קריאה (₪)</label>
                <input
                  type="number"
                  step="1"
                  value={editOrderModal.price}
                  onChange={(e) => setEditOrderModal((prev) => ({ ...prev, price: e.target.value }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl p-2.5 text-white font-mono font-bold"
                  required
                />
              </div>

              <div>
                <label className="text-slate-300 block mb-1 font-bold">תוכן הקריאה</label>
                <textarea
                  rows={4}
                  value={editOrderModal.text}
                  onChange={(e) => setEditOrderModal((prev) => ({ ...prev, text: e.target.value }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl p-2.5 text-white whitespace-pre-wrap"
                  required
                />
              </div>

              <div>
                <label className="text-slate-300 block mb-1 font-bold">סטטוס קריאה</label>
                <select
                  value={editOrderModal.status}
                  onChange={(e) => setEditOrderModal((prev) => ({ ...prev, status: e.target.value as any }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl p-2.5 text-white"
                >
                  <option value="open">פתוחה לנהגים (open)</option>
                  <option value="assigned">משוריינת לנהג (assigned)</option>
                  <option value="closed">הושלמה ונסגרה (closed)</option>
                  <option value="cancelled">בוטלה (cancelled)</option>
                </select>
              </div>

              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setEditOrderModal((prev) => ({ ...prev, isOpen: false }))}
                  className="flex-1 py-2.5 rounded-xl bg-slate-800 text-slate-300 font-bold cursor-pointer"
                >
                  ביטול
                </button>
                <button
                  type="submit"
                  className="flex-1 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold cursor-pointer"
                >
                  שמור שינויים
                </button>
              </div>
            </form>
          </div>
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
