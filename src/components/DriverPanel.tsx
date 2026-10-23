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
} from 'lucide-react';
import { getIsraelCities, getVehicleBrandsAndModels } from '../utils/datasets';
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
    submitDebtAppeal,
    updateUserRoleAndStation,
  } = useApp();

  const [allCities, setAllCities] = useState<string[]>([]);
  const [vehicleData, setVehicleData] = useState<Record<string, string[]>>({});
  const [newCityInput, setNewCityInput] = useState('');

  // Load datasets on mount
  useEffect(() => {
    getIsraelCities().then((cities) => setAllCities(cities));
    getVehicleBrandsAndModels().then((data) => setVehicleData(data));
  }, []);

  // Vehicle Profile Modal state
  const [isVehicleModalOpen, setIsVehicleModalOpen] = useState(false);
  const [vehicleForm, setVehicleForm] = useState({
    car_brand: currentUser.car_brand || '',
    car_model: currentUser.car_model || '',
    car_year: currentUser.car_year || new Date().getFullYear(),
    car_seats: currentUser.car_seats || 4,
  });
  const [isSavingProfile, setIsSavingProfile] = useState(false);

  const [etaModal, setEtaModal] = useState<{ isOpen: boolean; orderId: number; price: number; text: string }>({
    isOpen: false,
    orderId: 0,
    price: 0,
    text: '',
  });
  const [etaMinutes, setEtaMinutes] = useState('10');

  const [appealModal, setAppealModal] = useState<{ isOpen: boolean; debtId: number; amount: number; reason: string }>({
    isOpen: false,
    debtId: 0,
    amount: 0,
    reason: '',
  });
  const [appealText, setAppealText] = useState('');

  const [feedback, setFeedback] = useState<string | null>(null);

  const driverCities = getDriverCities(currentUser.user_id);
  const driverDebts = debts.filter((d) => d.driver_id === currentUser.user_id && d.status === 'unpaid');
  const isOverDebtLimit = currentUser.debt_balance > 500.0;

  // Open orders matching driver's cities
  const matchingOrders = orders.filter((o) => {
    if (o.status !== 'open') return false;
    if (driverCities.length === 0) return true; // gets all if no cities defined
    return driverCities.some((c) => o.text.includes(c));
  });

  const handleStatusToggle = () => {
    const res = toggleDriverStatus();
    setFeedback(res.message);
    setTimeout(() => setFeedback(null), 5000);
  };

  const handleAddCity = (cityName: string) => {
    if (!cityName.trim()) return;
    addDriverCity(currentUser.user_id, cityName.trim());
    setNewCityInput('');
  };

  const handleSubmitEta = (e: React.FormEvent) => {
    e.preventDefault();
    const minutes = parseInt(etaMinutes, 10);
    if (isNaN(minutes) || minutes <= 0) {
      setFeedback('⚠️ נא להזין מספר דקות הגיוני.');
      setTimeout(() => setFeedback(null), 3000);
      return;
    }

    const res = submitOrderBid(etaModal.orderId, currentUser.user_id, minutes);
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
    setFeedback('✅ הערעור נשלח להנהלת המערכת לבדיקה. תקבל עדכון בקרוב.');
    setTimeout(() => setFeedback(null), 5000);
  };

  return (
    <div className="space-y-6">
      {/* Driver Status Banner */}
      <div className="bg-slate-800/90 rounded-2xl p-5 border border-slate-700 shadow-lg">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr from-amber-500 to-amber-600 flex items-center justify-center text-slate-950 font-extrabold text-2xl shadow-lg">
              🚗
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-extrabold text-white">{currentUser.full_name}</h2>
                <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-900 border border-slate-700 text-amber-300 font-semibold flex items-center gap-1">
                  <Star className="w-3 h-3 fill-amber-300" />
                  {currentUser.rating.toFixed(1)} ({currentUser.total_trips} נסיעות)
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-1">
                רכב: <strong className="text-slate-200">{currentUser.car_brand} {currentUser.car_model}</strong> ({currentUser.car_year}) • {currentUser.car_seats} מקומות | טל: {currentUser.phone}
              </p>
            </div>
          </div>

          {/* Status Switcher & Debt Warning */}
          <div className="flex items-center gap-3 w-full md:w-auto">
            <button
              onClick={handleStatusToggle}
              className={`flex-1 md:flex-initial px-5 py-3 rounded-xl font-extrabold text-sm transition flex items-center justify-center gap-2 shadow-md cursor-pointer ${
                currentUser.status === 'free'
                  ? 'bg-emerald-500 hover:bg-emerald-400 text-slate-950'
                  : 'bg-red-500/20 hover:bg-red-500/30 text-red-300 border border-red-500/30'
              }`}
            >
              <span className={`w-3 h-3 rounded-full ${currentUser.status === 'free' ? 'bg-slate-950' : 'bg-red-400 animate-pulse'}`} />
              <span>{currentUser.status === 'free' ? '🟢 פנוי לעבודה (קולט קריאות)' : '🔴 תפוס (עצור קריאות)'}</span>
            </button>

            <div className="bg-slate-900 px-4 py-2.5 rounded-xl border border-slate-700 text-center">
              <span className="text-[11px] text-slate-400 block">חוב לתחנה</span>
              <span className={`text-base font-extrabold ${isOverDebtLimit ? 'text-red-400 animate-bounce' : 'text-amber-400'}`}>
                ₪{currentUser.debt_balance.toFixed(2)}
              </span>
            </div>
          </div>
        </div>

        {/* Auto-freeze banner if debt > 500 */}
        {isOverDebtLimit && (
          <div className="mt-4 p-3.5 bg-red-500/15 border border-red-500/40 rounded-xl flex items-center gap-3 text-red-300 text-xs font-semibold">
            <ShieldAlert className="w-5 h-5 flex-shrink-0 text-red-400" />
            <div>
              <p className="font-bold text-red-200">
                🚫 חשבונך מוקפא עקב חובות (מעל 500 ש"ח)!
              </p>
              <p className="text-red-300/80">
                לפי נהלי הבוט (סעיף 5/276), נהג עם יתרת חוב מעל 500 ₪ לא יכול לעבור לסטטוס 'פנוי'. יש להסדיר את התשלום מול הנהלת התחנה או להגיש ערעור.
              </p>
            </div>
          </div>
        )}
      </div>

      {feedback && (
        <div className="bg-amber-500/15 border border-amber-500/40 text-amber-300 px-4 py-3 rounded-xl flex items-center justify-between text-sm font-medium animate-fade-in">
          <span>{feedback}</span>
          <button onClick={() => setFeedback(null)} className="text-amber-400 hover:text-white">
            ✕
          </button>
        </div>
      )}

      {/* Grid: 1. Work Zones (📍 אזורי עבודה), 2. Incoming Calls, 3. Debts & Appeals */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Work Zones & Profile (5 cols) */}
        <div className="lg:col-span-5 space-y-6">
          {/* Work Zones Card (📍 אזורי עבודה) */}
          <div className="bg-slate-800/90 rounded-2xl p-5 border border-slate-700 shadow-md">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-bold text-base text-white flex items-center gap-2">
                <MapPin className="w-4 h-4 text-amber-400" />
                <span>אזורי עבודה מוגדרים</span>
              </h3>
              {driverCities.length > 0 && (
                <button
                  onClick={() => clearDriverCities(currentUser.user_id)}
                  className="text-xs text-red-400 hover:text-red-300 flex items-center gap-1 transition"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>נקה הכל</span>
                </button>
              )}
            </div>

            <p className="text-xs text-slate-400 mb-3 leading-relaxed">
              *רק קריאות מהערים האלו יקפצו אליך כשתהיה פנוי. (אם לא מוגדרות ערים, תקבל את כל הקריאות).*
            </p>

            {/* Active City Chips */}
            <div className="flex flex-wrap gap-2 mb-4 min-h-[40px] p-2.5 bg-slate-900/80 rounded-xl border border-slate-800">
              {driverCities.length === 0 ? (
                <span className="text-xs text-slate-500 italic py-1">
                  לא הוגדרו אזורים (מקבל קריאות מכל הארץ)
                </span>
              ) : (
                driverCities.map((city) => (
                  <span
                    key={city}
                    className="inline-flex items-center gap-1.5 bg-amber-500/10 text-amber-300 border border-amber-500/30 text-xs px-2.5 py-1 rounded-lg font-medium"
                  >
                    <span>{city}</span>
                    <button
                      onClick={() => removeDriverCity(currentUser.user_id, city)}
                      className="text-amber-400 hover:text-white"
                    >
                      ✕
                    </button>
                  </span>
                ))
              )}
            </div>

            {/* Add Custom City */}
            <div className="flex gap-2 mb-4">
              <input
                type="text"
                value={newCityInput}
                onChange={(e) => setNewCityInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAddCity(newCityInput)}
                placeholder="הקלד עיר להוספה (למשל: בית שמש)"
                className="flex-1 bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-amber-500"
              />
              <button
                type="button"
                onClick={() => handleAddCity(newCityInput)}
                className="bg-slate-700 hover:bg-slate-600 text-white text-xs font-bold px-3 py-2 rounded-xl transition flex items-center gap-1"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>הוסף</span>
              </button>
            </div>
          </div>

          {/* Debts & Appeals (💳 חיובים וערעורים - סעיף 5) */}
          <div className="bg-slate-800/90 rounded-2xl p-5 border border-slate-700 shadow-md">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-bold text-base text-white flex items-center gap-2">
                <Scale className="w-4 h-4 text-amber-400" />
                <span>חיובים וערעורים פתוחים ({driverDebts.length})</span>
              </h3>
            </div>

            {driverDebts.length === 0 ? (
              <div className="text-center p-6 bg-slate-900/60 rounded-xl border border-slate-800">
                <CheckCircle className="w-8 h-8 text-emerald-400 mx-auto mb-1.5" />
                <p className="text-xs text-slate-300 font-bold">אין לך חובות פתוחים במערכת!</p>
                <p className="text-[11px] text-slate-500 mt-0.5">כל העמלות מסודרות מול התחנה.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {driverDebts.map((d) => (
                  <div
                    key={d.debt_id}
                    className="bg-slate-900/90 border border-slate-700 rounded-xl p-3.5 flex flex-col justify-between gap-2.5"
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="text-xs font-bold text-white flex items-center gap-2">
                          <span>חיוב #{d.debt_id}</span>
                          <span className="text-slate-400 font-normal">עבור קריאה #{d.order_id}</span>
                        </div>
                        <div className="text-[11px] text-slate-400 mt-0.5">
                          תחנה #{d.station_id} • {d.reason}
                        </div>
                      </div>
                      <span className="text-sm font-extrabold text-amber-400 bg-slate-800 px-2.5 py-1 rounded-lg">
                        ₪{d.amount.toFixed(2)}
                      </span>
                    </div>

                    {d.appeal_status === 'pending' ? (
                      <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-2 text-[11px] text-amber-300">
                        ⚖️ <strong>ערעור נשלח להנהלה:</strong> "{d.appeal_reason}" (ממתין להכרעה)
                      </div>
                    ) : d.appeal_status === 'rejected' ? (
                      <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-2 text-[11px] text-red-300">
                        ❌ <strong>ערעור נדחה:</strong> החיוב נשאר בעינו ויש להסדירו מול התחנה.
                      </div>
                    ) : (
                      <button
                        onClick={() =>
                          setAppealModal({
                            isOpen: true,
                            debtId: d.debt_id,
                            amount: d.amount,
                            reason: d.reason,
                          })
                        }
                        className="text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white py-1.5 px-3 rounded-lg border border-slate-700 transition flex items-center justify-center gap-1.5"
                      >
                        <Scale className="w-3.5 h-3.5 text-amber-400" />
                        <span>ערעור / בקשת ביטול</span>
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Live Matching Calls Feed (7 cols) */}
        <div className="lg:col-span-7 bg-slate-800/90 rounded-2xl p-5 border border-slate-700 shadow-md flex flex-col">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-bold text-base text-white flex items-center gap-2">
                <Clock className="w-4 h-4 text-emerald-400" />
                <span>קריאות זמינות עבורך ({matchingOrders.length})</span>
              </h3>
              <p className="text-xs text-slate-400">
                מסונן לפי אזורי העבודה שלך ומצב פנוי
              </p>
            </div>

            {currentUser.status !== 'free' && (
              <span className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 px-2.5 py-1 rounded-lg">
                ⚠️ אתה בסטטוס תפוס
              </span>
            )}
          </div>

          {matchingOrders.length === 0 ? (
            <div className="bg-slate-900/60 rounded-xl p-12 text-center border border-slate-800 my-auto">
              <Car className="w-12 h-12 text-slate-600 mx-auto mb-2" />
              <p className="text-sm font-bold text-slate-300">אין קריאות חדשות באזורי הפעילות שלך כרגע</p>
              <p className="text-xs text-slate-500 mt-1">
                כאשר סדרן ישגר קריאה לאחד מהאזורים שלך, היא תופיע כאן מיד.
              </p>
            </div>
          ) : (
            <div className="space-y-4 overflow-y-auto max-h-[620px] pr-1">
              {matchingOrders.map((order) => {
                const myBid = (order.bids || []).find((b) => b.driver_id === currentUser.user_id);
                return (
                  <div
                    key={order.order_id}
                    className="bg-slate-900/90 border border-slate-700/80 rounded-xl p-4.5 transition hover:border-slate-600"
                  >
                    <div className="flex items-center justify-between mb-2.5">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold font-mono bg-amber-500/10 text-amber-400 border border-amber-500/30 px-2.5 py-0.5 rounded-lg">
                          קריאה #{order.order_id}
                        </span>
                        <span className="text-xs text-slate-400">
                          {new Date(order.created_at).toLocaleTimeString('he-IL', {
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </span>
                      </div>
                      <span className="text-base font-extrabold text-emerald-400 bg-slate-800 px-3 py-1 rounded-lg border border-slate-700">
                        ₪{order.price}
                      </span>
                    </div>

                    <p className="text-sm text-slate-200 mb-4 bg-slate-950/70 p-3 rounded-xl border border-slate-800 leading-relaxed font-sans">
                      {order.text}
                    </p>

                    <div className="flex items-center justify-between pt-2 border-t border-slate-800">
                      {myBid ? (
                        <div className="flex items-center gap-2 text-xs font-semibold text-amber-300 bg-amber-500/10 px-3 py-1.5 rounded-lg border border-amber-500/30">
                          <Clock className="w-3.5 h-3.5" />
                          <span>
                            הגשת הצעה: {myBid.eta_minutes} דקות (ממתין לאישור סדרן)
                          </span>
                        </div>
                      ) : (
                        <button
                          onClick={() => {
                            if (currentUser.status !== 'free') {
                              setFeedback("⚠️ אתה בסטטוס תפוס! העבר ל'פנוי' בראש הדף קודם.");
                              setTimeout(() => setFeedback(null), 4000);
                              return;
                            }
                            if (isOverDebtLimit) {
                              setFeedback('🚫 חשבונך מוקפא עקב חובות (מעל 500 ש"ח)!');
                              setTimeout(() => setFeedback(null), 4000);
                              return;
                            }
                            setEtaModal({
                              isOpen: true,
                              orderId: order.order_id,
                              price: order.price,
                              text: order.text,
                            });
                          }}
                          className="w-full sm:w-auto bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold text-xs px-5 py-2.5 rounded-xl transition flex items-center justify-center gap-2 shadow cursor-pointer"
                        >
                          <Car className="w-4 h-4" />
                          <span>🚗 קח קריאה (הזן זמן הגעה)</span>
                        </button>
                      )}

                      <span className="text-[11px] text-slate-500">
                        {(order.bids || []).length} נהגים מתמודדים
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* ETA Bid Modal (סעיף OrderFlow.waiting_driver_eta) */}
      {etaModal.isOpen && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 shadow-2xl">
            <h4 className="text-base font-bold text-white mb-2 flex items-center gap-2">
              <Clock className="w-4 h-4 text-amber-400" />
              <span>בקשה לקריאה #{etaModal.orderId} (₪{etaModal.price})</span>
            </h4>
            <p className="text-xs text-slate-400 mb-4 bg-slate-950 p-2.5 rounded-lg border border-slate-800">
              {etaModal.text}
            </p>

            <form onSubmit={handleSubmitEta} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                  ⏱️ כמה זמן עד להגעה למוצא? (במספר דקות):
                </label>
                <div className="flex gap-2">
                  {[5, 8, 10, 15, 20].map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => setEtaMinutes(m.toString())}
                      className={`flex-1 py-1.5 rounded-lg text-xs font-bold border transition ${
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
                  className="mt-3 w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500"
                />
              </div>

              <div className="flex gap-3">
                <button
                  type="submit"
                  className="flex-1 bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold py-2.5 rounded-xl transition text-xs"
                >
                  שלח בקשה לסדרן
                </button>
                <button
                  type="button"
                  onClick={() => setEtaModal({ isOpen: false, orderId: 0, price: 0, text: '' })}
                  className="px-4 bg-slate-800 hover:bg-slate-700 text-slate-300 py-2.5 rounded-xl transition text-xs"
                >
                  ביטול
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Appeal Debt Modal (סעיף DebtFlow.waiting_dispute_reason) */}
      {appealModal.isOpen && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 shadow-2xl">
            <h4 className="text-base font-bold text-white mb-2 flex items-center gap-2">
              <Scale className="w-4 h-4 text-amber-400" />
              <span>ערעור על חיוב #{appealModal.debtId} (₪{appealModal.amount})</span>
            </h4>
            <p className="text-xs text-slate-400 mb-4">
              מדוע אתה מבקש לבטל את החיוב הזה? הסיבה תישלח לבדיקת הנהלת המערכת.
            </p>

            <form onSubmit={handleSubmitAppeal} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                  סיבת הערעור:
                </label>
                <textarea
                  value={appealText}
                  onChange={(e) => setAppealText(e.target.value)}
                  placeholder="למשל: הלקוח ביטל במקום / הנוסע לא הופיע / מחיר שגוי"
                  rows={3}
                  required
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl p-3 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-amber-500 resize-none"
                />
              </div>

              <div className="flex gap-3">
                <button
                  type="submit"
                  className="flex-1 bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold py-2.5 rounded-xl transition text-xs"
                >
                  שגר ערעור להנהלה
                </button>
                <button
                  type="button"
                  onClick={() => setAppealModal({ isOpen: false, debtId: 0, amount: 0, reason: '' })}
                  className="px-4 bg-slate-800 hover:bg-slate-700 text-slate-300 py-2.5 rounded-xl transition text-xs"
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
