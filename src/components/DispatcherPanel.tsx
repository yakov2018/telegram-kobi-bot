import React, { useState } from 'react';
import { useApp } from '../context/AppContext';
import { cleanOrderText, extractOrderPrice } from '../utils/orderUtils';
import {
  Send,
  Sparkles,
  DollarSign,
  Users,
  Clock,
  Trash2,
  CheckCircle,
  XCircle,
  Star,
  MapPin,
  Car,
  AlertTriangle,
} from 'lucide-react';

export const DispatcherPanel: React.FC = () => {
  const {
    currentUser,
    orders,
    stations,
    users,
    driverCities,
    botGroups,
    publishOrder,
    approveDriverOrder,
    denyDriverOrder,
    rateDriver,
    deleteOrder,
  } = useApp();

  if (currentUser.role !== 'dispatcher' && currentUser.role !== 'station_manager' && currentUser.role !== 'admin') {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-2xl p-6 text-center text-red-300 font-bold my-8">
        ⛔ גישה חסומה: עמדת הסדרן מיועדת אך ורק לסדרנים ומנהלי תחנות מורשים.
      </div>
    );
  }

  const [rawText, setRawText] = useState('');
  const [destType, setDestType] = useState<'private' | 'groups'>('private');
  const [feedbackMsg, setFeedbackMsg] = useState<string | null>(null);

  // Rating modal state after driver approval
  const [ratingModal, setRatingModal] = useState<{
    isOpen: boolean;
    orderId: number;
    driverId: number;
    driverName: string;
    debtAmount: number;
  }>({
    isOpen: false,
    orderId: 0,
    driverId: 0,
    driverName: '',
    debtAmount: 0,
  });

  const currentStation = stations.find((s) => s.station_id === currentUser.station_id) || stations[0];

  // Real-time text cleaning & price extraction preview
  const cleanedPreview = cleanOrderText(rawText);
  const detectedPrice = extractOrderPrice(cleanedPreview);

  // Filter open orders for current dispatcher's station (or all if admin)
  const stationOrders = orders.filter((o) => {
    if (currentUser.role === 'admin') return o.status === 'open';
    return o.status === 'open' && o.station_id === currentUser.station_id;
  });

  // Calculate matching drivers for preview
  const matchingDriversCount = users.filter((u) => {
    if (u.role !== 'user' || u.status !== 'free' || u.is_blocked || u.debt_balance > 500) {
      return false;
    }
    const cities = driverCities.filter((dc) => dc.user_id === u.user_id).map((dc) => dc.city_name);
    if (cities.length === 0) return true;
    return cities.some((c) => cleanedPreview.includes(c));
  }).length;

  const handlePublish = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rawText.trim()) return;

    if (detectedPrice <= 0) {
      setFeedbackMsg('⚠️ המערכת לא זיהתה מחיר. נא לכלול מחיר בספרות (למשל: 100 ש"ח)');
      setTimeout(() => setFeedbackMsg(null), 4000);
      return;
    }

    setFeedbackMsg('⏳ משגר קריאה ומאתר נהגים פנויים באזורי היעד...');
    const currentText = rawText;
    setRawText('');
    const res = await publishOrder(currentText, destType, detectedPrice);
    setFeedbackMsg(
      destType === 'private'
        ? `✅ קריאה #${res.order.order_id} שוגרה בהצלחה ל-${res.eligibleDriversCount} נהגים פנויים באזורי היעד!`
        : `✅ קריאה #${res.order.order_id} שוגרה בהצלחה ל-${botGroups.length} קבוצות חיצוניות!`
    );
    setTimeout(() => setFeedbackMsg(null), 6000);
  };

  const handleApproveDriver = (orderId: number, driverId: number) => {
    const driver = users.find((u) => u.user_id === driverId);
    const res = approveDriverOrder(orderId, driverId);
    if (res.success) {
      // Open rating dialog like bot.py rate_kb
      setRatingModal({
        isOpen: true,
        orderId,
        driverId,
        driverName: driver ? driver.full_name : 'נהג',
        debtAmount: res.debtAmount,
      });
    }
  };

  const handleRate = (stars: number) => {
    rateDriver(ratingModal.driverId, stars);
    setRatingModal((prev) => ({ ...prev, isOpen: false }));
    setFeedbackMsg(`⭐ דירגת את הנהג ב-${stars} כוכבים. נרשמה עמלה של ₪${ratingModal.debtAmount} לתחנה.`);
    setTimeout(() => setFeedbackMsg(null), 4000);
  };

  return (
    <div className="space-y-6">
      {/* Station Banner */}
      <div className="bg-slate-800/80 rounded-2xl p-5 border border-slate-700/80 shadow-lg flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-amber-400 font-bold text-sm">
            <span>📢 עמדת סדרן פעילה</span>
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          </div>
          <h2 className="text-xl font-extrabold text-white mt-1">
            {currentStation.name} • ניהול ושיגור קריאות בזמן אמת
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            עמלת תחנה מוגדרת: <strong className="text-amber-400">{currentStation.commission_percent}%</strong> |
            סדרן מחובר: <strong className="text-slate-200">{currentUser.full_name}</strong>
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="bg-slate-900/90 px-4 py-2 rounded-xl border border-slate-700 text-center">
            <span className="text-xs text-slate-400 block">קריאות פתוחות כעת</span>
            <span className="text-lg font-bold text-amber-400">{stationOrders.length}</span>
          </div>
          <div className="bg-slate-900/90 px-4 py-2 rounded-xl border border-slate-700 text-center">
            <span className="text-xs text-slate-400 block">נהגים פנויים באונליין</span>
            <span className="text-lg font-bold text-emerald-400">
              {users.filter((u) => u.role === 'user' && u.status === 'free' && !u.is_blocked).length}
            </span>
          </div>
        </div>
      </div>

      {feedbackMsg && (
        <div className="bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 px-4 py-3 rounded-xl flex items-center justify-between animate-fade-in text-sm font-medium">
          <span>{feedbackMsg}</span>
          <button onClick={() => setFeedbackMsg(null)} className="text-emerald-400 hover:text-white">
            ✕
          </button>
        </div>
      )}

      {/* Grid: Order Publisher & Live Status */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Order Publisher (📢 פרסם קריאה) */}
        <div className="lg:col-span-5 bg-slate-800/90 rounded-2xl p-6 border border-slate-700 shadow-md flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-base text-white flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-amber-400" />
                <span>פרסום קריאה חדשה</span>
              </h3>
              <span className="text-[11px] text-slate-400 bg-slate-900 px-2 py-1 rounded-md border border-slate-700">
                ניקוי חצים וקיצורים אוטומטי
              </span>
            </div>

            <form onSubmit={handlePublish} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                  הדבק או הקלד פרטי קריאה:
                </label>
                <textarea
                  value={rawText}
                  onChange={(e) => setRawText(e.target.value)}
                  placeholder="לדוגמה: מודיעין עילית (נתיבות שלום) -> ירושלים (רוממה), 3 נוסעים, 180 שח"
                  rows={4}
                  className="w-full bg-slate-900 border border-slate-700 rounded-xl p-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-amber-500 transition resize-none"
                />
              </div>

              {/* Cleaning & Price Realtime Preview */}
              {rawText && (
                <div className="bg-slate-950/70 p-3.5 rounded-xl border border-slate-800 space-y-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400 font-medium">טקסט מנוקה (כפי שיופץ):</span>
                    <span className="text-amber-400 font-bold flex items-center gap-1">
                      <DollarSign className="w-3.5 h-3.5" />
                      מחיר שזוהה: ₪{detectedPrice}
                    </span>
                  </div>
                  <div className="text-slate-200 bg-slate-900/80 p-2.5 rounded-lg border border-slate-800 break-words font-mono text-[13px]">
                    {cleanedPreview || '(הקלד טקסט)'}
                  </div>
                </div>
              )}

              {/* Destination selector: Drivers Private vs External Groups */}
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-2">
                  לאן לשגר את הקריאה?
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setDestType('private')}
                    className={`p-3 rounded-xl border text-right transition flex flex-col justify-between ${
                      destType === 'private'
                        ? 'bg-amber-500/10 border-amber-500 text-white shadow-sm'
                        : 'bg-slate-900/80 border-slate-700 text-slate-300 hover:bg-slate-800'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-bold text-xs">לנהגים בפרטי</span>
                      <Users className="w-4 h-4 text-amber-400" />
                    </div>
                    <span className="text-[11px] text-slate-400">
                      סינון חכם לפי עיר וסטטוס פנוי ({matchingDriversCount} נהגים מתאימים)
                    </span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setDestType('groups')}
                    className={`p-3 rounded-xl border text-right transition flex flex-col justify-between ${
                      destType === 'groups'
                        ? 'bg-amber-500/10 border-amber-500 text-white shadow-sm'
                        : 'bg-slate-900/80 border-slate-700 text-slate-300 hover:bg-slate-800'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-bold text-xs">לקבוצות (חיצוני)</span>
                      <Send className="w-4 h-4 text-blue-400" />
                    </div>
                    <span className="text-[11px] text-slate-400">
                      שיגור ל-{botGroups.length} קבוצות בוט טלגרם מוגדרות
                    </span>
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={!rawText.trim() || detectedPrice <= 0}
                className="w-full bg-amber-500 hover:bg-amber-400 disabled:opacity-50 disabled:cursor-not-allowed text-slate-950 font-extrabold py-3 rounded-xl transition flex items-center justify-center gap-2 shadow-lg shadow-amber-500/20 cursor-pointer"
              >
                <Send className="w-4 h-4" />
                <span>שגר קריאה עכשיו ({detectedPrice > 0 ? `₪${detectedPrice}` : 'ללא מחיר'})</span>
              </button>
            </form>
          </div>
        </div>

        {/* Right Column: Live Open Orders & Driver ETA Bids (📋 מצב קריאות) */}
        <div className="lg:col-span-7 bg-slate-800/90 rounded-2xl p-6 border border-slate-700 shadow-md">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-bold text-base text-white flex items-center gap-2">
                <Clock className="w-4 h-4 text-blue-400" />
                <span>מצב קריאות פתוחות ({stationOrders.length})</span>
              </h3>
              <p className="text-xs text-slate-400">
                מעקב בזמן אמת, אישור מתמודדים, גביית עמלה ודירוג
              </p>
            </div>
          </div>

          {stationOrders.length === 0 ? (
            <div className="bg-slate-900/60 rounded-xl p-10 text-center border border-slate-800">
              <CheckCircle className="w-10 h-10 text-emerald-400 mx-auto mb-2" />
              <p className="text-sm font-bold text-slate-200">אין קריאות פתוחות לתחנה שלך כרגע</p>
              <p className="text-xs text-slate-400 mt-1">כל הקריאות שובצו או נמחקו בהצלחה.</p>
            </div>
          ) : (
            <div className="space-y-4 max-h-[580px] overflow-y-auto pr-1">
              {stationOrders.map((order) => {
                const bids = order.bids || [];
                return (
                  <div
                    key={order.order_id}
                    className="bg-slate-900/90 border border-slate-700/80 rounded-xl p-4.5 transition hover:border-slate-600"
                  >
                    {/* Header */}
                    <div className="flex items-start justify-between gap-3 mb-2.5">
                      <div className="flex items-center gap-2">
                        <span className="bg-amber-500/10 text-amber-400 border border-amber-500/30 text-xs px-2.5 py-1 rounded-lg font-bold font-mono">
                          🎫 קריאה #{order.order_id}
                        </span>
                        <span className="text-xs text-slate-400">
                          {new Date(order.created_at).toLocaleTimeString('he-IL', {
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </span>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="text-base font-extrabold text-white bg-slate-800 px-3 py-1 rounded-lg border border-slate-700">
                          ₪{order.price}
                        </span>
                        <button
                          onClick={() => deleteOrder(order.order_id)}
                          title="מחק קריאה (נלקחה מחוץ לבוט)"
                          className="text-slate-400 hover:text-red-400 p-1.5 rounded-lg hover:bg-slate-800 transition"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>

                    {/* Order Text */}
                    <p className="text-sm text-slate-200 mb-3 bg-slate-950/60 p-3 rounded-lg border border-slate-800/80 leading-relaxed font-sans">
                      {order.text}
                    </p>

                    {/* Incoming Bids / Candidates Section */}
                    <div className="border-t border-slate-800 pt-3">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                          <Car className="w-3.5 h-3.5 text-amber-400" />
                          <span>נהגים שהגישו בקשה וזמן הגעה ({bids.length}):</span>
                        </span>
                        {bids.length === 0 && (
                          <span className="text-[11px] text-slate-500 animate-pulse">
                            ממתין להצעות נהגים...
                          </span>
                        )}
                      </div>

                      {bids.length > 0 ? (
                        <div className="space-y-2">
                          {bids.map((bid) => (
                            <div
                              key={bid.driver_id}
                              className="bg-slate-800/90 border border-slate-700 rounded-lg p-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                            >
                              <div>
                                <div className="flex items-center gap-2">
                                  <span className="font-bold text-xs text-white">
                                    {bid.driver_name}
                                  </span>
                                  <span className="text-xs text-amber-400 flex items-center gap-0.5 font-bold">
                                    <Star className="w-3 h-3 fill-amber-400" />
                                    {bid.rating.toFixed(1)}
                                  </span>
                                  <span className="text-[11px] text-slate-400 bg-slate-900 px-2 py-0.5 rounded">
                                    {bid.car_brand} {bid.car_model} ({bid.car_seats} מקומות)
                                  </span>
                                </div>
                                <div className="text-xs text-emerald-400 font-semibold mt-1 flex items-center gap-1">
                                  <Clock className="w-3.5 h-3.5" />
                                  <span>זמן הגעה למוצא: {bid.eta_minutes} דקות</span>
                                </div>
                              </div>

                              <div className="flex items-center gap-2 self-end sm:self-auto">
                                <button
                                  onClick={() => handleApproveDriver(order.order_id, bid.driver_id)}
                                  className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold px-3 py-1.5 rounded-lg transition flex items-center gap-1.5 shadow"
                                >
                                  <CheckCircle className="w-3.5 h-3.5" />
                                  <span>אשר נהג (גבה עמלה)</span>
                                </button>
                                <button
                                  onClick={() => denyDriverOrder(order.order_id, bid.driver_id)}
                                  className="bg-slate-700 hover:bg-red-500/20 hover:text-red-300 text-slate-300 text-xs px-2.5 py-1.5 rounded-lg transition"
                                >
                                  דחה
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-xs text-slate-500 italic bg-slate-950/40 p-2.5 rounded-lg text-center">
                          טרם הוגשו הצעות. הנהגים הפנויים באזורי היעד מקבלים התראה כעת.
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Driver Rating Modal (1-5 כוכבים לפי סעיף 20) */}
      {ratingModal.isOpen && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 text-center shadow-2xl space-y-4">
            <div className="w-12 h-12 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center mx-auto">
              <CheckCircle className="w-6 h-6" />
            </div>

            <div>
              <h4 className="text-lg font-bold text-white">
                הקריאה נסגרה על הנהג {ratingModal.driverName}!
              </h4>
              <p className="text-xs text-slate-400 mt-1">
                נרשמה עמלת תחנה אוטומטית של <strong className="text-amber-400">₪{ratingModal.debtAmount}</strong> בחוב הנהג.
              </p>
            </div>

            <div className="bg-slate-800/80 p-4 rounded-xl border border-slate-700">
              <p className="text-sm font-semibold text-slate-200 mb-3">
                איך הנהג/הרכב נראה לך? דרג עכשיו:
              </p>
              <div className="flex items-center justify-center gap-2">
                {[1, 2, 3, 4, 5].map((stars) => (
                  <button
                    key={stars}
                    onClick={() => handleRate(stars)}
                    className="p-2.5 bg-slate-900 hover:bg-amber-500/20 border border-slate-700 hover:border-amber-400 rounded-xl text-amber-400 flex flex-col items-center gap-1 transition group"
                  >
                    <Star className="w-5 h-5 fill-amber-400 group-hover:scale-110 transition" />
                    <span className="text-xs font-bold text-white">{stars}</span>
                  </button>
                ))}
              </div>
            </div>

            <button
              onClick={() => setRatingModal((prev) => ({ ...prev, isOpen: false }))}
              className="text-xs text-slate-400 hover:text-white"
            >
              דלג על דירוג כעת
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
