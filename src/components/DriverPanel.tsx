import React, { useState, useEffect } from 'react';
import { useApp } from '../context/AppContext';
import {
  Car,
  MapPin,
  Clock,
  Send,
  Star,
  AlertOctagon,
  CheckCircle,
  HelpCircle,
  Trash2,
  DollarSign,
  Plus,
  Scale,
  ShieldAlert,
  Settings,
  Sparkles,
  X,
  Lock,
  MessageCircle,
} from 'lucide-react';
import { getIsraelCities } from '../utils/datasets';
import { AutocompleteInput } from './AutocompleteInput';

export const DriverPanel: React.FC = () => {
  const {
    currentUser,
    orders,
    debts,
    stations,
    getDriverCities,
    addDriverCity,
    removeDriverCity,
    clearDriverCities,
    toggleDriverStatus,
    submitOrderBid,
    acknowledgeDebt,
    submitDebtAppeal,
  } = useApp();

  const [allCities, setAllCities] = useState<string[]>([]);
  const [newCityInput, setNewCityInput] = useState('');
  const [feedback, setFeedback] = useState<string | null>(null);

  // Load Israel cities dataset for autocomplete
  useEffect(() => {
    getIsraelCities().then((cities) => setAllCities(cities || []));
  }, []);

  // ETA Modal state
  const [etaModal, setEtaModal] = useState<{
    isOpen: boolean;
    orderId: number;
    price: number;
    text: string;
  }>({
    isOpen: false,
    orderId: 0,
    price: 0,
    text: '',
  });
  const [etaMinutes, setEtaMinutes] = useState('10');

  // Appeal Modal state
  const [appealModal, setAppealModal] = useState<{
    isOpen: boolean;
    debtId: number;
    amount: number;
    reason: string;
  }>({
    isOpen: false,
    debtId: 0,
    amount: 0,
    reason: '',
  });
  const [appealText, setAppealText] = useState('');

  const driverCities = getDriverCities(currentUser?.user_id ?? 0);
  const driverDebts = (debts || []).filter((d) => d.driver_id === currentUser?.user_id);
  const unpaidDebts = driverDebts.filter((d) => d.status === 'unpaid');
  const isOverDebtLimit = Number(currentUser?.debt_balance || 0) > 500.0;

  // Open orders matching driver's cities (or all if none defined)
  const openMatchingOrders = (orders || []).filter((o) => {
    if (o?.status !== 'open') return false;
    if (driverCities.length === 0) return true;
    return driverCities.some((c) => (o?.text || '').includes(c) || (o?.origin_city || '').includes(c));
  });

  const handleStatusToggle = async () => {
    const res = await toggleDriverStatus();
    setFeedback(res.message);
    setTimeout(() => setFeedback(null), 4000);
  };

  const handleAddCity = (cityName: string) => {
    if (!cityName.trim()) return;
    addDriverCity(currentUser?.user_id ?? 0, cityName.trim());
    setNewCityInput('');
  };

  const handleTakeOrderClick = (order: any) => {
    if (currentUser?.status !== 'free') {
      setFeedback("⚠️ אתה בסטטוס תפוס! העבר ל'פנוי' בראש הדף קודם.");
      setTimeout(() => setFeedback(null), 4000);
      return;
    }
    if (isOverDebtLimit) {
      setFeedback('🚫 חשבונך מוקפא עקב חוב מעל 500 ש"ח!');
      setTimeout(() => setFeedback(null), 4000);
      return;
    }

    // אם הקריאה דורשת זמן או כוללת את המילה 'זמן' / 'דקות'
    setEtaModal({
      isOpen: true,
      orderId: order.order_id,
      price: order.price,
      text: order.text,
    });
  };

  const handleSubmitEta = (e: React.FormEvent) => {
    e.preventDefault();
    const minutes = parseInt(etaMinutes, 10);
    if (isNaN(minutes) || minutes <= 0) {
      setFeedback('⚠️ נא להזין מספר דקות הגיוני.');
      setTimeout(() => setFeedback(null), 3000);
      return;
    }

    const res = submitOrderBid(etaModal.orderId, currentUser?.user_id ?? 0, minutes);
    setEtaModal({ isOpen: false, orderId: 0, price: 0, text: '' });
    setFeedback(res.message);
    setTimeout(() => setFeedback(null), 5000);
  };

  const handleSubmitAppeal = (e: React.FormEvent) => {
    e.preventDefault();
    if (!appealText.trim()) return;

    submitDebtAppeal(appealModal.debtId, appealText.trim());
    setAppealModal({ isOpen: false, debtId: 0, amount: 0, reason: '' });
    setAppealText('');
    setFeedback('✅ בקשתך לביטול חיוב נשלחה לסדרן המפרסם!');
    setTimeout(() => setFeedback(null), 5000);
  };

  return (
    <div className="space-y-6">
      {/* Driver Status Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 sm:p-5 shadow-sm space-y-4">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-amber-500 to-amber-600 flex items-center justify-center text-slate-950 font-black text-2xl shadow-md">
              🚗
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base sm:text-lg font-extrabold text-white">{currentUser?.full_name || 'נהג'}</h2>
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-amber-300 font-bold flex items-center gap-1 font-mono">
                  <Star className="w-3 h-3 fill-amber-300" />
                  {Number(currentUser?.rating || 5.0).toFixed(1)} ({currentUser?.total_trips || 0} נסיעות)
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                רכב: <strong className="text-slate-200">{currentUser?.car_brand || 'רכב'} {currentUser?.car_model || ''}</strong> ({currentUser?.car_year || ''}) • {currentUser?.car_seats || 4} מקומות | טל: {currentUser?.phone || ''}
              </p>
            </div>
          </div>

          {/* Status Switcher & Debt Warning */}
          <div className="flex items-center gap-3 w-full md:w-auto">
            <button
              onClick={handleStatusToggle}
              className={`flex-1 md:flex-initial px-5 py-2.5 rounded-xl font-extrabold text-xs transition flex items-center justify-center gap-2 shadow cursor-pointer ${
                currentUser?.status === 'free'
                  ? 'bg-emerald-500 hover:bg-emerald-400 text-slate-950'
                  : 'bg-red-500/20 hover:bg-red-500/30 text-red-300 border border-red-500/30'
              }`}
            >
              <span className={`w-2.5 h-2.5 rounded-full ${currentUser?.status === 'free' ? 'bg-slate-950' : 'bg-red-400 animate-pulse'}`} />
              <span>{currentUser?.status === 'free' ? '🟢 פנוי לעבודה (קולט קריאות)' : '🔴 תפוס (עצור קריאות)'}</span>
            </button>

            <div className="bg-slate-950 px-3.5 py-2 rounded-xl border border-slate-800 text-center">
              <span className="text-[10px] text-slate-400 block font-semibold">חוב לתחנה</span>
              <span className={`text-sm font-extrabold font-mono ${isOverDebtLimit ? 'text-red-400 animate-pulse' : 'text-amber-400'}`}>
                ₪{Number(currentUser?.debt_balance || 0).toFixed(2)}
              </span>
            </div>
          </div>
        </div>

        {/* Auto-freeze warning if debt > 500 */}
        {isOverDebtLimit && (
          <div className="p-3 bg-red-500/15 border border-red-500/40 rounded-xl flex items-center gap-3 text-red-300 text-xs font-semibold">
            <ShieldAlert className="w-5 h-5 flex-shrink-0 text-red-400" />
            <div>
              <p className="font-bold text-red-200">🚫 חשבונך מוקפא עקב חובות (מעל 500 ש"ח)!</p>
              <p className="text-red-300/80 text-[11px]">
                נהג עם יתרת חוב מעל 500 ₪ לא יכול לעבור לסטטוס 'פנוי'. יש להסדיר תשלום מול התחנה או להגיש בקשה לביטול חיוב.
              </p>
            </div>
          </div>
        )}
      </div>

      {feedback && (
        <div className="bg-amber-500/15 border border-amber-500/40 text-amber-200 px-4 py-3 rounded-xl flex items-center justify-between text-xs font-semibold">
          <span>{feedback}</span>
          <button onClick={() => setFeedback(null)} className="text-amber-400 hover:text-white">✕</button>
        </div>
      )}

      {/* Grid: 1. Work Zones & Debts, 2. Available Orders Feed */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Work Zones & Debt Ledger (5 cols) */}
        <div className="lg:col-span-5 space-y-4">
          {/* Work Zones Card (📍 אזורי עבודה) */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-sm space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="font-bold text-sm text-white flex items-center gap-2">
                <MapPin className="w-4 h-4 text-amber-400" />
                <span>אזורי עבודה מוגדרים ({driverCities.length})</span>
              </h3>
              {driverCities.length > 0 && (
                <button
                  onClick={() => clearDriverCities(currentUser?.user_id ?? 0)}
                  className="text-xs text-red-400 hover:text-red-300 flex items-center gap-1 transition cursor-pointer"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>נקה הכל</span>
                </button>
              )}
            </div>

            <p className="text-xs text-slate-400 leading-relaxed">
              *קריאות מהערים האלו יקפצו אליך כשתהיה פנוי. (אם לא הוגדרו ערים, תקבל קריאות מכל הארץ).*
            </p>

            {/* Active City Chips */}
            <div className="flex flex-wrap gap-1.5 p-2 bg-slate-950 rounded-xl border border-slate-800 min-h-[44px] items-center">
              {driverCities.length === 0 ? (
                <span className="text-xs text-slate-500 italic px-2">
                  לא הוגדרו אזורים (מקבל קריאות מכל הארץ)
                </span>
              ) : (
                driverCities.map((city) => (
                  <span
                    key={city}
                    className="inline-flex items-center gap-1 bg-amber-500/10 text-amber-300 border border-amber-500/30 text-xs px-2.5 py-1 rounded-lg font-medium"
                  >
                    <span>{city}</span>
                    <button
                      onClick={() => removeDriverCity(currentUser?.user_id ?? 0, city)}
                      className="text-amber-400 hover:text-white"
                    >
                      ✕
                    </button>
                  </span>
                ))
              )}
            </div>

            {/* Add City Input */}
            <div className="flex gap-2">
              <div className="flex-1">
                <AutocompleteInput
                  suggestions={allCities}
                  value={newCityInput}
                  onChange={setNewCityInput}
                  onSelect={handleAddCity}
                  placeholder="הקלד עיר להוספה (למשל: ירושלים)..."
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-amber-500"
                />
              </div>
              <button
                onClick={() => handleAddCity(newCityInput)}
                className="px-3.5 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs transition flex items-center gap-1 cursor-pointer"
              >
                <Plus className="w-4 h-4" />
                <span>הוסף</span>
              </button>
            </div>
          </div>

          {/* Active Debts & Appeal Notice (סעיף 5: הודעת חיוב עם אישור חיוב וביטול חיוב) */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-sm space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="font-bold text-sm text-white flex items-center gap-2">
                <span>💳 חובות וחיובים פעילים</span>
              </h3>
              <span className="text-xs text-amber-400 font-bold font-mono">
                {unpaidDebts.length} חיובים פתוחים
              </span>
            </div>

            {unpaidDebts.length === 0 ? (
              <p className="text-xs text-slate-500 italic bg-slate-950 p-3 rounded-xl border border-slate-800 text-center">
                ✅ אין לך חובות פתוחים במערכת.
              </p>
            ) : (
              <div className="space-y-2.5 max-h-72 overflow-y-auto">
                {unpaidDebts.map((d) => {
                  const isLocked = d.is_locked === 1 || d.appeal_status === 'confirmed';
                  const isPendingAppeal = d.appeal_status === 'pending';

                  return (
                    <div
                      key={d.debt_id}
                      className="bg-slate-950 border border-slate-800 p-3 rounded-xl space-y-2 text-xs"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-extrabold text-amber-400 font-mono text-sm">
                          🍓 ₪{Number(d.amount).toFixed(2)}
                        </span>
                        <span className="text-[10px] text-slate-400 font-mono">
                          חיוב #{d.debt_id} {d.order_id ? `(קריאה #${d.order_id})` : ''}
                        </span>
                      </div>
                      <p className="text-slate-300 text-[11px]">{d.reason || 'עמלת נסיעה'}</p>

                      {/* Status badge */}
                      {isPendingAppeal && (
                        <div className="p-2 rounded-lg bg-purple-500/10 border border-purple-500/30 text-purple-300 text-[11px]">
                          ⚖️ בקשה לביטול חיוב בבדיקת הסדרן: "{d.appeal_reason}"
                        </div>
                      )}
                      {isLocked && (
                        <div className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-300 text-[10px] font-bold flex items-center gap-1">
                          <CheckCircle className="w-3 h-3" />
                          <span>החיוב אושר וננעל סופית</span>
                        </div>
                      )}

                      {/* Two Required Buttons: [אישור חיוב] / [בקשה לביטול חיוב] */}
                      {!isLocked && !isPendingAppeal && (
                        <div className="flex gap-2 pt-1">
                          <button
                            onClick={() => {
                              acknowledgeDebt(d.debt_id);
                              setFeedback('✅ החיוב אושר וננעל בהצלחה.');
                              setTimeout(() => setFeedback(null), 3000);
                            }}
                            className="flex-1 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-[11px] transition text-center cursor-pointer flex items-center justify-center gap-1"
                          >
                            <CheckCircle className="w-3 h-3" />
                            <span>אישור חיוב</span>
                          </button>
                          <button
                            onClick={() => {
                              setAppealModal({
                                isOpen: true,
                                debtId: d.debt_id,
                                amount: d.amount,
                                reason: d.reason,
                              });
                            }}
                            className="flex-1 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-amber-300 border border-slate-700 font-bold text-[11px] transition text-center cursor-pointer flex items-center justify-center gap-1"
                          >
                            <Scale className="w-3 h-3" />
                            <span>בקשה לביטול חיוב</span>
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Open Orders Feed (7 cols) */}
        <div className="lg:col-span-7 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-sm text-white flex items-center gap-2">
              <span>🚗 קריאות זמינות עבורך ({openMatchingOrders.length})</span>
            </h3>
            <span className="text-xs text-slate-400">
              {currentUser?.status === 'free' ? '🟢 קולט בזמן אמת' : '🔴 עצור (תפוס)'}
            </span>
          </div>

          {openMatchingOrders.length === 0 ? (
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 text-center text-slate-400">
              <div className="w-12 h-12 rounded-2xl bg-slate-800 flex items-center justify-center mx-auto mb-3 text-2xl">
                🚖
              </div>
              <p className="font-bold text-sm text-slate-300 mb-1">אין קריאות פעילות כרגע באזורים שלך</p>
              <p className="text-xs text-slate-500">
                קריאות חדשות שיפורסמו על ידי הסדרנים יופיעו כאן בזמן אמת.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {openMatchingOrders.map((order) => {
                const bids = order.bids || [];
                const myBid = bids.find((b) => b.driver_id === currentUser?.user_id);

                return (
                  <div
                    key={order.order_id}
                    className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-sm space-y-3"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-black text-amber-400 text-sm">#{order.order_id}</span>
                        <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-200 font-bold">
                          ₪{order.price}
                        </span>
                        {order.requires_eta && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 font-bold">
                            ⏱️ נדרש זמן הגעה (ETA)
                          </span>
                        )}
                      </div>
                      <span className="text-[11px] text-slate-500">
                        {order.origin_city ? `מ${order.origin_city}` : ''} {order.dest_city ? `➔ ${order.dest_city}` : ''}
                      </span>
                    </div>

                    {/* Order text - Customer phone hidden! */}
                    <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 text-xs text-slate-200 whitespace-pre-wrap font-sans">
                      {order.text}
                    </div>

                    {/* Action buttons: [בקשת נסיעה], [לשאלות בפרטי] */}
                    <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-1 border-t border-slate-800">
                      {myBid ? (
                        <div className="p-2 rounded-lg bg-purple-500/10 border border-purple-500/30 text-purple-300 text-xs font-semibold flex items-center gap-1.5">
                          <Clock className="w-3.5 h-3.5" />
                          <span>הגשת הצעה: {myBid.eta_minutes} דק' (ממתין לאישור סדרן)</span>
                        </div>
                      ) : (
                        <button
                          onClick={() => handleTakeOrderClick(order)}
                          className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold text-xs transition flex items-center justify-center gap-2 shadow cursor-pointer"
                        >
                          <Car className="w-4 h-4" />
                          <span>בקשת נסיעה</span>
                        </button>
                      )}

                      <a
                        href={`https://t.me/${order.publisher_username || 'kobi_erp_bot'}`}
                        target="_blank"
                        rel="noreferrer"
                        className="w-full sm:w-auto px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold text-xs transition flex items-center justify-center gap-1.5 border border-slate-700 cursor-pointer text-center"
                      >
                        <MessageCircle className="w-3.5 h-3.5" />
                        <span>לשאלות בפרטי</span>
                      </a>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* ETA Bid Modal (סעיף 4: כאשר לוחצים בקשת נסיעה, מזינים זמן הגעה בדקות) */}
      {etaModal.isOpen && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-5 shadow-2xl space-y-4">
            <h4 className="font-extrabold text-base text-white flex items-center gap-2">
              <Clock className="w-4 h-4 text-amber-400" />
              <span>הזנת זמן הגעה לקריאה #{etaModal.orderId} (₪{etaModal.price})</span>
            </h4>
            <p className="text-xs text-slate-400 bg-slate-950 p-2.5 rounded-xl border border-slate-800 whitespace-pre-wrap">
              {etaModal.text}
            </p>

            <form onSubmit={handleSubmitEta} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1.5">
                  ⏱️ כמה זמן ייקח לך להגיע למוצא? (במספר דקות):
                </label>
                <div className="flex gap-2">
                  {[5, 10, 15, 20, 30].map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => setEtaMinutes(m.toString())}
                      className={`flex-1 py-1.5 rounded-lg text-xs font-bold border transition cursor-pointer ${
                        etaMinutes === m.toString()
                          ? 'bg-amber-500 text-slate-950 border-amber-500'
                          : 'bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700'
                      }`}
                    >
                      {m} דק'
                    </button>
                  ))}
                </div>
                <input
                  type="number"
                  min="1"
                  max="120"
                  value={etaMinutes}
                  onChange={(e) => setEtaMinutes(e.target.value)}
                  className="mt-2 w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-amber-500 font-bold"
                />
              </div>

              <div className="flex gap-2 pt-1">
                <button
                  type="submit"
                  className="flex-1 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold text-xs transition shadow cursor-pointer"
                >
                  אישור ושליחת בקשה לסדרן
                </button>
                <button
                  type="button"
                  onClick={() => setEtaModal({ isOpen: false, orderId: 0, price: 0, text: '' })}
                  className="px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition cursor-pointer"
                >
                  ביטול
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Appeal Reason Modal (סעיף 5: הבוט מבקש מהנהג להקליד סיבה לביטול חיוב) */}
      {appealModal.isOpen && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-5 shadow-2xl space-y-4">
            <h4 className="font-extrabold text-base text-white flex items-center gap-2">
              <Scale className="w-4 h-4 text-amber-400" />
              <span>בקשה לביטול חיוב #{appealModal.debtId} (₪{appealModal.amount})</span>
            </h4>
            <p className="text-xs text-slate-400">
              הקלד את סיבת הבקשה. הסיבה תישלח לסדרן המפרסם לבחינת ביטול החיוב:
            </p>

            <form onSubmit={handleSubmitAppeal} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">
                  סיבת הביטול:
                </label>
                <textarea
                  value={appealText}
                  onChange={(e) => setAppealText(e.target.value)}
                  placeholder="למשל: הלקוח ביטל במקום / הנוסע לא הופיע / מחיר שגוי"
                  rows={3}
                  required
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl p-3 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-amber-500 resize-none font-sans"
                />
              </div>

              <div className="flex gap-2">
                <button
                  type="submit"
                  className="flex-1 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold text-xs transition shadow cursor-pointer"
                >
                  שגר בקשה לסדרן
                </button>
                <button
                  type="button"
                  onClick={() => setAppealModal({ isOpen: false, debtId: 0, amount: 0, reason: '' })}
                  className="px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition cursor-pointer"
                >
                  ביטול
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
