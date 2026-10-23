import React, { useState } from 'react';
import { useApp } from '../context/AppContext';
import { parseOrderNLP, calculateCommission } from '../utils/orderUtils';
import { Order, User, DriverBid } from '../types';
import {
  Send,
  Clock,
  Trash2,
  CheckCircle,
  XCircle,
  Star,
  MapPin,
  Car,
  AlertTriangle,
  Phone,
  Shield,
  RotateCcw,
  UserCheck,
  Search,
  DollarSign,
  Copy,
  ExternalLink,
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
    closeAndChargeOrder,
    republishOrder,
    cancelOrder,
    manualCloseOrder,
    rateDriver,
    deleteOrder,
  } = useApp();

  const [rawText, setRawText] = useState('');
  const [selectedCustomPrice, setSelectedCustomPrice] = useState<number | null>(null);
  const [isEditingAfterWarning, setIsEditingAfterWarning] = useState(false);
  const [feedbackMsg, setFeedbackMsg] = useState<string | null>(null);

  // Manual close modal state
  const [manualCloseModal, setManualCloseModal] = useState<{
    isOpen: boolean;
    orderText: string;
    orderPrice: number;
    clientPhone: string;
    selectedDriverId: number | null;
    customCommissionPercent: number;
  }>({
    isOpen: false,
    orderText: '',
    orderPrice: 0,
    clientPhone: '',
    selectedDriverId: null,
    customCommissionPercent: 10.0,
  });

  const [driverSearchQuery, setDriverSearchQuery] = useState('');

  // Rating modal state
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

  // Role guard: Only dispatcher, station_manager, or admin
  if (currentUser.role !== 'dispatcher' && currentUser.role !== 'station_manager' && currentUser.role !== 'admin') {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-2xl p-6 text-center text-red-300 font-bold my-8">
        ⛔ גישה חסומה: עמדת הסדרן מיועדת אך ורק לסדרנים ומנהלי תחנות מורשים.
      </div>
    );
  }

  const currentStation = (stations || []).find((s) => s.station_id === currentUser.station_id) || {
    station_id: currentUser.station_id || 1,
    name: 'תחנה ראשית',
    commission_percent: 10.0,
  };

  // Run NLP on the text
  const nlp = parseOrderNLP(rawText, currentStation.name, currentUser.full_name);
  const effectivePrice = selectedCustomPrice !== null ? selectedCustomPrice : nlp.selectedPrice;

  // Filter open and assigned orders for this station (or all if admin)
  const myStationOrders = (orders || []).filter((o) => {
    if (currentUser.role === 'admin') return o.status !== 'deleted';
    return o.station_id === currentUser.station_id && o.status !== 'deleted';
  });

  const openOrders = myStationOrders.filter((o) => o.status === 'open' || o.status === 'assigned');

  // Matching drivers for preview
  const matchingDriversCount = (users || []).filter((u) => {
    if (u.role !== 'user' || u.status !== 'free' || u.is_blocked || Number(u.debt_balance || 0) > 500) {
      return false;
    }
    const cities = (driverCities || []).filter((dc) => dc.user_id === u.user_id).map((dc) => dc.city_name);
    if (cities.length === 0) return true;
    return cities.some((c) => nlp.cleanedText.includes(c));
  }).length;

  const handleRouteAction = async (
    destinationType: 'all' | 'zone_and_groups' | 'groups_only' | 'zone_only' | 'manual'
  ) => {
    if (!rawText.trim()) {
      setFeedbackMsg('⚠️ נא להקליד טקסט נסיעה');
      setTimeout(() => setFeedbackMsg(null), 3000);
      return;
    }

    if (effectivePrice <= 0) {
      setFeedbackMsg('⚠️ לא זוהה מחיר. נא להזין מחיר בספרות או לבחור מחירון.');
      setTimeout(() => setFeedbackMsg(null), 4000);
      return;
    }

    if (destinationType === 'manual') {
      setManualCloseModal({
        isOpen: true,
        orderText: nlp.cleanedText,
        orderPrice: effectivePrice,
        clientPhone: nlp.clientPhone,
        selectedDriverId: null,
        customCommissionPercent: currentStation.commission_percent,
      });
      return;
    }

    setFeedbackMsg('⏳ משגר קריאה ומנתב לפי בחירתך...');
    const res = await publishOrder({
      rawText,
      price: effectivePrice,
      destinationType,
      requiresEta: nlp.requiresEta,
      originCity: nlp.originCity,
      destCity: nlp.destCity,
      clientPhone: nlp.clientPhone,
    });

    if (res.success) {
      setRawText('');
      setSelectedCustomPrice(null);
      setFeedbackMsg(`✅ קריאה #${res.orderId} שוגרה בהצלחה (${destinationType})!`);
    } else {
      setFeedbackMsg(res.error || 'שגיאה בשיגור הקריאה');
    }
    setTimeout(() => setFeedbackMsg(null), 5000);
  };

  const handleConfirmManualClose = async () => {
    if (!manualCloseModal.selectedDriverId) {
      setFeedbackMsg('⚠️ נא לבחור נהג לסגירה');
      setTimeout(() => setFeedbackMsg(null), 3000);
      return;
    }

    const res = await manualCloseOrder({
      text: manualCloseModal.orderText,
      price: manualCloseModal.orderPrice,
      driverId: manualCloseModal.selectedDriverId,
      stationId: currentStation.station_id,
      clientPhone: manualCloseModal.clientPhone,
      commissionPercent: manualCloseModal.customCommissionPercent,
    });

    if (res.success) {
      setManualCloseModal({
        isOpen: false,
        orderText: '',
        orderPrice: 0,
        clientPhone: '',
        selectedDriverId: null,
        customCommissionPercent: 10.0,
      });
      setRawText('');
      setSelectedCustomPrice(null);
      setFeedbackMsg(`✅ הנסיעה נסגרה ידנית על הנהג ונרשם חיוב של ₪${res.debtAmount}!`);
    } else {
      setFeedbackMsg(res.error || 'שגיאה בסגירה ידנית');
    }
    setTimeout(() => setFeedbackMsg(null), 5000);
  };

  // Selected driver card for manual close preview
  const manualDriverSelected = (users || []).find((u) => u.user_id === manualCloseModal.selectedDriverId);

  const filteredDriversForManual = (users || []).filter((u) => {
    if (u.role === 'admin') return false;
    if (!driverSearchQuery) return true;
    const q = driverSearchQuery.toLowerCase();
    return (
      (u.full_name || '').toLowerCase().includes(q) ||
      (u.phone || '').includes(q) ||
      String(u.user_id).includes(q) ||
      (u.telegram_username || '').toLowerCase().includes(q)
    );
  });

  return (
    <div className="space-y-6">
      {/* Station Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-sm flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-600/20 border border-blue-500/30 flex items-center justify-center text-blue-400 text-lg">
            📢
          </div>
          <div>
            <h2 className="font-extrabold text-sm sm:text-base text-white flex items-center gap-2">
              <span>עמדת סדרן: {currentStation.name}</span>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-300 border border-blue-500/30 font-mono">
                {currentStation.commission_percent}% עמלה
              </span>
            </h2>
            <p className="text-xs text-slate-400">
              פרסום חכם מבוסס NLP, 7 אפיקי ניתוב וניהול הצעות נהגים בזמן אמת
            </p>
          </div>
        </div>

        <div className="text-xs text-slate-400 bg-slate-950 px-3 py-1.5 rounded-xl border border-slate-800">
          סדרן מחובר: <strong className="text-white">{currentUser.full_name}</strong>
        </div>
      </div>

      {feedbackMsg && (
        <div className="bg-amber-500/15 border border-amber-500/40 text-amber-200 px-4 py-3 rounded-xl flex items-center justify-between text-xs font-semibold">
          <span>{feedbackMsg}</span>
          <button onClick={() => setFeedbackMsg(null)} className="text-amber-400 hover:text-white">✕</button>
        </div>
      )}

      {/* Grid: 1. Order Creation & NLP Preview, 2. Active Orders & Bids */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Smart Order Composer (5 cols) */}
        <div className="lg:col-span-5 space-y-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-sm space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="font-bold text-sm text-white flex items-center gap-2">
                <span>✏️ יצירת קריאה ופענוח NLP</span>
              </h3>
              <span className="text-[11px] text-slate-400 font-mono">
                {rawText.length > 0 ? `${rawText.length} תווים` : ''}
              </span>
            </div>

            <textarea
              rows={4}
              value={rawText}
              onChange={(e) => {
                setRawText(e.target.value);
                setSelectedCustomPrice(null);
              }}
              placeholder="הקלד כאן את פרטי הנסיעה בחופשיות, למשל:
מ-ים ל-בב 150 שח דחוף זמן טלפון 0501234567"
              className="w-full bg-slate-950 border border-slate-700/80 rounded-xl p-3 text-xs sm:text-sm text-white placeholder-slate-500 focus:outline-none focus:border-amber-500 resize-none font-sans"
            />

            {/* Smart NLP Extracted Tags */}
            {rawText.trim().length > 0 && (
              <div className="space-y-3 pt-1 border-t border-slate-800">
                <div className="text-[11px] font-bold text-slate-300">🔍 זיהוי אוטומטי מהטקסט:</div>
                <div className="flex flex-wrap gap-2 text-xs">
                  {nlp.originCity && (
                    <span className="px-2 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300">
                      מוצא: <strong>{nlp.originCity}</strong>
                    </span>
                  )}
                  {nlp.destCity && (
                    <span className="px-2 py-1 rounded-lg bg-blue-500/10 border border-blue-500/30 text-blue-300">
                      יעד: <strong>{nlp.destCity}</strong>
                    </span>
                  )}
                  {nlp.requiresEta && (
                    <span className="px-2 py-1 rounded-lg bg-purple-500/10 border border-purple-500/30 text-purple-300 font-bold">
                      ⏱️ מילת מפתח "זמן" זוהתה (דרוש ETA)
                    </span>
                  )}
                  {nlp.clientPhone ? (
                    <span className="px-2 py-1 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 font-mono">
                      📞 טלפון: {nlp.clientPhone}
                    </span>
                  ) : (
                    <span className="px-2 py-1 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300 font-bold">
                      ⚠️ לא זוהה טלפון לקוח!
                    </span>
                  )}
                </div>

                {/* Multi-price collision handling */}
                {nlp.hasPriceCollision && (
                  <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl space-y-2">
                    <span className="text-xs text-amber-300 font-bold block">
                      ⚠️ זוהו מספר מחירים אפשריים. בחר את המחיר הנכון לקריאה:
                    </span>
                    <div className="flex flex-wrap gap-2">
                      {nlp.candidatePrices.map((p) => (
                        <button
                          key={p}
                          type="button"
                          onClick={() => setSelectedCustomPrice(p)}
                          className={`px-3 py-1 rounded-lg text-xs font-bold transition cursor-pointer ${
                            effectivePrice === p
                              ? 'bg-amber-500 text-slate-950 shadow'
                              : 'bg-slate-800 text-slate-200 hover:bg-slate-700'
                          }`}
                        >
                          ₪{p}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Price Display */}
                <div className="flex items-center justify-between bg-slate-950 p-2.5 rounded-xl border border-slate-800 text-xs">
                  <span className="text-slate-400">מחיר נסיעה שנקבע:</span>
                  <div className="flex items-center gap-1.5">
                    <input
                      type="number"
                      value={effectivePrice || ''}
                      onChange={(e) => setSelectedCustomPrice(Number(e.target.value))}
                      placeholder="0"
                      className="w-20 bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-center font-bold text-amber-400 text-sm focus:outline-none focus:border-amber-500"
                    />
                    <span className="text-slate-300 font-bold">₪</span>
                  </div>
                </div>

                {/* Customer Phone Missing Warning Banner */}
                {!nlp.hasClientPhone && (
                  <div className="p-3 bg-red-500/15 border border-red-500/40 rounded-xl space-y-2 text-xs text-red-200">
                    <div className="flex items-center gap-2 font-bold text-red-300">
                      <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
                      <span>לא זוהה טלפון לקוח!</span>
                    </div>
                    <p className="text-[11px] text-red-300/90 leading-relaxed">
                      האם להמשיך בפרסום ללא מספר לקוח, או לערוך את ההודעה כדי להוסיף טלפון?
                    </p>
                    <div className="flex gap-2 pt-1">
                      <button
                        onClick={() => setIsEditingAfterWarning(true)}
                        className="flex-1 py-1 px-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-white font-bold transition text-center"
                      >
                        ✏️ ערוך הודעה
                      </button>
                      <button
                        onClick={() => setIsEditingAfterWarning(false)}
                        className="flex-1 py-1 px-2 rounded-lg bg-red-600 hover:bg-red-500 text-white font-bold transition text-center"
                      >
                        המשך בפרסום
                      </button>
                    </div>
                  </div>
                )}

                {/* Full Live Preview with Station Signature */}
                <div className="space-y-1">
                  <span className="text-[11px] text-slate-400 font-bold">תצוגה מקדימה לפרסום:</span>
                  <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 text-xs text-slate-200 whitespace-pre-wrap font-sans">
                    {nlp.cleanedText}
                  </div>
                </div>

                {/* Eligible Drivers Count Indicator */}
                <div className="text-[11px] text-slate-400 flex items-center justify-between px-1">
                  <span>נהגים פנויים באזורי היעד:</span>
                  <strong className="text-emerald-400 font-mono">{matchingDriversCount} נהגים</strong>
                </div>

                {/* 7 Routing / Action Buttons */}
                <div className="space-y-2 pt-2 border-t border-slate-800">
                  <span className="text-[11px] text-slate-400 font-bold block">בחר אפיק ניתוב ופרסום:</span>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <button
                      onClick={() => handleRouteAction('all')}
                      className="py-2.5 px-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold transition flex items-center justify-center gap-1 shadow cursor-pointer text-center"
                    >
                      📢 פרסם לכולם
                    </button>
                    <button
                      onClick={() => handleRouteAction('zone_and_groups')}
                      className="py-2.5 px-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold transition flex items-center justify-center gap-1 shadow cursor-pointer text-center"
                    >
                      📍 פנויים באזור + קבוצות
                    </button>
                    <button
                      onClick={() => handleRouteAction('groups_only')}
                      className="py-2.5 px-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold transition flex items-center justify-center gap-1 border border-slate-700 cursor-pointer text-center"
                    >
                      👥 רק בקבוצות ({botGroups.length})
                    </button>
                    <button
                      onClick={() => handleRouteAction('zone_only')}
                      className="py-2.5 px-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold transition flex items-center justify-center gap-1 shadow cursor-pointer text-center"
                    >
                      🚗 רק לפנויים באזור
                    </button>
                    <button
                      onClick={() => handleRouteAction('manual')}
                      className="col-span-2 py-2.5 px-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold transition flex items-center justify-center gap-1 shadow cursor-pointer text-center"
                    >
                      🤝 סגירה ידנית על נהג (ללא פרסום)
                    </button>
                    <button
                      onClick={() => {
                        setRawText('');
                        setSelectedCustomPrice(null);
                      }}
                      className="col-span-2 py-2 px-2 rounded-xl bg-slate-800/80 hover:bg-red-500/20 text-slate-400 hover:text-red-300 font-medium transition flex items-center justify-center gap-1 cursor-pointer text-center"
                    >
                      ❌ ביטול שליחה ומחיקה
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Station Active Orders & Driver Bidding (7 cols) */}
        <div className="lg:col-span-7 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-sm text-white flex items-center gap-2">
              <span>📋 קריאות פעילות והצעות נהגים ({openOrders.length})</span>
            </h3>
            <span className="text-xs text-slate-400">תחנה #{currentStation.station_id}</span>
          </div>

          {openOrders.length === 0 ? (
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 text-center text-slate-400">
              <div className="w-12 h-12 rounded-2xl bg-slate-800 flex items-center justify-center mx-auto mb-3 text-2xl">
                🚖
              </div>
              <p className="font-bold text-sm text-slate-300 mb-1">אין קריאות פעילות כרגע בתחנה</p>
              <p className="text-xs text-slate-500">
                הקלד קריאה בטופס מימין ושגר אותה לאחד מאפיקי הניתוב.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {openOrders.map((order) => {
                const bids = order.bids || [];
                const isAssigned = order.status === 'assigned';
                const assignedDriver = isAssigned ? users.find((u) => u.user_id === order.driver_id) : null;
                const estCommission = calculateCommission(order.price, currentStation.commission_percent);

                return (
                  <div
                    key={order.order_id}
                    className={`bg-slate-900 border rounded-2xl p-4 shadow-sm space-y-3 transition ${
                      isAssigned ? 'border-emerald-500/50 bg-emerald-950/10' : 'border-slate-800'
                    }`}
                  >
                    {/* Order Header */}
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="font-black text-amber-400 text-sm">#{order.order_id}</span>
                        <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 font-bold">
                          ₪{order.price}
                        </span>
                        {isAssigned ? (
                          <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-bold">
                            🔒 ננעלה על נהג
                          </span>
                        ) : (
                          <span className="text-[11px] px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 border border-blue-500/30 font-bold">
                            פתוחה להצעות
                          </span>
                        )}
                        {order.requires_eta && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 font-bold">
                            ⏱️ ETA
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-1.5">
                        <button
                          onClick={() => republishOrder(order.order_id)}
                          title="פרסם שוב"
                          className="p-1.5 rounded-lg bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 transition cursor-pointer"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => cancelOrder(order.order_id)}
                          title="ביטול נסיעה"
                          className="p-1.5 rounded-lg bg-slate-800 text-slate-400 hover:text-red-400 hover:bg-slate-700 transition cursor-pointer"
                        >
                          <XCircle className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>

                    {/* Order Cleaned Text */}
                    <p className="text-xs text-slate-200 whitespace-pre-wrap font-sans bg-slate-950 p-3 rounded-xl border border-slate-800/80">
                      {order.text}
                    </p>

                    {/* Customer Phone details if assigned */}
                    {isAssigned && order.client_phone && (
                      <div className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl flex items-center justify-between text-xs text-emerald-200">
                        <div className="flex items-center gap-2">
                          <Phone className="w-4 h-4 text-emerald-400" />
                          <span>טלפון לקוח להעברה לנהג: <strong className="font-mono text-white">{order.client_phone}</strong></span>
                        </div>
                        <button
                          onClick={() => {
                            navigator.clipboard.writeText(order.client_phone || '');
                            setFeedbackMsg('📋 מספר הלקוח הועתק ללוח!');
                            setTimeout(() => setFeedbackMsg(null), 3000);
                          }}
                          className="px-2 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-[11px] flex items-center gap-1 transition"
                        >
                          <Copy className="w-3 h-3" />
                          <span>העתק</span>
                        </button>
                      </div>
                    )}

                    {/* Incoming Driver Bids Section */}
                    <div className="space-y-2 pt-2 border-t border-slate-800">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-bold text-slate-300">
                          🚗 הצעות נהגים ({bids.length})
                        </span>
                        <span className="text-[11px] text-slate-400">
                          עמלת תחנה צפויה: ₪{estCommission}
                        </span>
                      </div>

                      {bids.length === 0 ? (
                        <p className="text-xs text-slate-500 italic bg-slate-950/60 p-2.5 rounded-xl border border-slate-800/60">
                          טרם התקבלו הצעות מחיר מנהגים לקריאה זו.
                        </p>
                      ) : (
                        <div className="space-y-2">
                          {bids.map((bid) => {
                            const isBidAccepted = bid.status === 'accepted';
                            return (
                              <div
                                key={bid.driver_id}
                                className={`p-3 rounded-xl border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs ${
                                  isBidAccepted
                                    ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-200'
                                    : 'bg-slate-950 border-slate-800 text-slate-300'
                                }`}
                              >
                                <div className="space-y-1">
                                  <div className="flex items-center gap-2">
                                    <strong className="text-white text-sm">{bid.driver_name}</strong>
                                    <span className="flex items-center gap-0.5 text-amber-400 text-[11px]">
                                      <Star className="w-3 h-3 fill-amber-400" />
                                      {bid.rating.toFixed(1)}
                                    </span>
                                    {bid.telegram_username && (
                                      <span className="text-slate-400 text-[11px]">@{bid.telegram_username}</span>
                                    )}
                                  </div>
                                  <p className="text-[11px] text-slate-400">
                                    רכב: {bid.car_brand} {bid.car_model} ({bid.car_seats} מקומות) | טל: {bid.driver_phone || 'אין'}
                                  </p>
                                  {bid.eta_minutes !== undefined && (
                                    <p className="text-xs font-bold text-amber-300 flex items-center gap-1">
                                      <Clock className="w-3.5 h-3.5" />
                                      <span>זמן הגעה שהוזן: <strong>{bid.eta_minutes} דקות</strong></span>
                                    </p>
                                  )}
                                </div>

                                <div className="flex items-center gap-2 w-full sm:w-auto">
                                  {!isAssigned ? (
                                    <button
                                      onClick={() => {
                                        const res = approveDriverOrder(order.order_id, bid.driver_id);
                                        setFeedbackMsg(res.message);
                                        setTimeout(() => setFeedbackMsg(null), 5000);
                                      }}
                                      className="flex-1 sm:flex-initial px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold transition flex items-center justify-center gap-1 shadow cursor-pointer text-xs"
                                    >
                                      <CheckCircle className="w-3.5 h-3.5" />
                                      <span>אישור הנסיעה לנהג</span>
                                    </button>
                                  ) : isBidAccepted ? (
                                    <div className="flex items-center gap-2 w-full sm:w-auto">
                                      <button
                                        onClick={() => {
                                          const res = closeAndChargeOrder(order.order_id, bid.driver_id);
                                          setRatingModal({
                                            isOpen: true,
                                            orderId: order.order_id,
                                            driverId: bid.driver_id,
                                            driverName: bid.driver_name,
                                            debtAmount: res.debtAmount,
                                          });
                                        }}
                                        className="flex-1 sm:flex-initial px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold transition flex items-center justify-center gap-1 shadow cursor-pointer text-xs"
                                      >
                                        <DollarSign className="w-3.5 h-3.5" />
                                        <span>סגירה וחיוב הנהג (₪{estCommission})</span>
                                      </button>
                                    </div>
                                  ) : (
                                    <span className="text-[11px] text-slate-500 italic">הנסיעה נמכרה</span>
                                  )}
                                </div>
                              </div>
                            );
                          })}
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

      {/* Manual Close Modal (סעיף 6: סגירה ידנית על נהג) */}
      {manualCloseModal.isOpen && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full p-5 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <h4 className="font-extrabold text-base text-white flex items-center gap-2">
                <span>🤝 סגירה ידנית על נהג (ללא פרסום)</span>
              </h4>
              <button
                onClick={() => setManualCloseModal((prev) => ({ ...prev, isOpen: false }))}
                className="text-slate-400 hover:text-white"
              >
                ✕
              </button>
            </div>

            {/* Order summary */}
            <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 text-xs text-slate-300 whitespace-pre-wrap">
              {manualCloseModal.orderText}
            </div>

            {/* Price & Commission Adjustment */}
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <label className="text-slate-400 block mb-1">סכום הנסיעה (₪):</label>
                <input
                  type="number"
                  value={manualCloseModal.orderPrice}
                  onChange={(e) =>
                    setManualCloseModal((prev) => ({ ...prev, orderPrice: Number(e.target.value) }))
                  }
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white font-bold focus:outline-none focus:border-amber-500"
                />
              </div>
              <div>
                <label className="text-slate-400 block mb-1">אחוז עמלת תחנה (%):</label>
                <input
                  type="number"
                  value={manualCloseModal.customCommissionPercent}
                  onChange={(e) =>
                    setManualCloseModal((prev) => ({ ...prev, customCommissionPercent: Number(e.target.value) }))
                  }
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white font-bold focus:outline-none focus:border-amber-500"
                />
              </div>
            </div>

            {/* Driver Search Input */}
            <div>
              <label className="text-xs font-semibold text-slate-300 block mb-1.5">
                בחר נהג מהתחנה (לפי שם, טלפון, @username או מזהה):
              </label>
              <div className="relative">
                <input
                  type="text"
                  value={driverSearchQuery}
                  onChange={(e) => setDriverSearchQuery(e.target.value)}
                  placeholder="חיפוש נהג..."
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-amber-500"
                />
                <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
              </div>
            </div>

            {/* Drivers list to pick */}
            <div className="max-h-40 overflow-y-auto space-y-1.5 p-1 bg-slate-950 rounded-xl border border-slate-800">
              {filteredDriversForManual.map((d) => {
                const isSelected = manualCloseModal.selectedDriverId === d.user_id;
                return (
                  <button
                    key={d.user_id}
                    type="button"
                    onClick={() => setManualCloseModal((prev) => ({ ...prev, selectedDriverId: d.user_id }))}
                    className={`w-full text-right p-2.5 rounded-lg flex items-center justify-between text-xs transition cursor-pointer ${
                      isSelected
                        ? 'bg-amber-500 text-slate-950 font-bold'
                        : 'bg-slate-900 text-slate-200 hover:bg-slate-800'
                    }`}
                  >
                    <div>
                      <span>{d.full_name}</span>
                      <span className={`text-[10px] block ${isSelected ? 'text-slate-800' : 'text-slate-400'}`}>
                        {d.car_brand} {d.car_model} • טל: {d.phone || 'אין'}
                      </span>
                    </div>
                    <span className="font-mono text-xs">⭐ {Number(d.rating || 5.0).toFixed(1)}</span>
                  </button>
                );
              })}
            </div>

            {/* Full Driver Card Preview for Confirmation (סעיף 6) */}
            {manualDriverSelected && (
              <div className="p-3 bg-purple-500/10 border border-purple-500/30 rounded-xl space-y-1.5 text-xs text-purple-200">
                <div className="flex items-center justify-between font-bold">
                  <span>🚗 כרטיסיית נהג לאישור סופי:</span>
                  <span className="text-amber-400 font-mono">
                    עמלה לחיוב: ₪{calculateCommission(manualCloseModal.orderPrice, manualCloseModal.customCommissionPercent)}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-1 text-[11px] text-purple-300">
                  <p>נהג: <strong>{manualDriverSelected.full_name}</strong></p>
                  <p>טלפון: <strong>{manualDriverSelected.phone || 'לא הוזן'}</strong></p>
                  <p>רכב: <strong>{manualDriverSelected.car_brand} {manualDriverSelected.car_model}</strong></p>
                  <p>שנת ייצור: <strong>{manualDriverSelected.car_year || 'לא הוזן'}</strong></p>
                  <p>מקומות: <strong>{manualDriverSelected.car_seats} מקומות</strong></p>
                  <p>דירוג: <strong>{Number(manualDriverSelected.rating || 5.0).toFixed(1)} ({manualDriverSelected.total_trips || 0} נסיעות)</strong></p>
                </div>
              </div>
            )}

            <div className="flex gap-2 pt-2">
              <button
                type="button"
                onClick={handleConfirmManualClose}
                disabled={!manualCloseModal.selectedDriverId}
                className="flex-1 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-extrabold text-xs transition shadow cursor-pointer"
              >
                סגור נסיעה וחייב נהג
              </button>
              <button
                type="button"
                onClick={() => setManualCloseModal((prev) => ({ ...prev, isOpen: false }))}
                className="px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition"
              >
                ביטול
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Driver Rating Modal */}
      {ratingModal.isOpen && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-sm w-full p-5 shadow-2xl text-center space-y-4">
            <h4 className="font-extrabold text-base text-white">
              ⭐ דרג את הנהג: {ratingModal.driverName}
            </h4>
            <p className="text-xs text-slate-400">
              הנסיעה #{ratingModal.orderId} נסגרה בהצלחה וחויבה עמלה של ₪{ratingModal.debtAmount}.
              איך היה השירות של הנהג?
            </p>
            <div className="flex justify-center gap-2 py-2">
              {[1, 2, 3, 4, 5].map((stars) => (
                <button
                  key={stars}
                  onClick={() => {
                    rateDriver(ratingModal.driverId, stars);
                    setRatingModal((prev) => ({ ...prev, isOpen: false }));
                    setFeedbackMsg(`⭐ דירגת את הנהג ב-${stars} כוכבים!`);
                    setTimeout(() => setFeedbackMsg(null), 3000);
                  }}
                  className="w-10 h-10 rounded-xl bg-slate-800 hover:bg-amber-500 hover:text-slate-950 border border-slate-700 font-extrabold text-sm transition flex items-center justify-center cursor-pointer"
                >
                  {stars}
                </button>
              ))}
            </div>
            <button
              onClick={() => setRatingModal((prev) => ({ ...prev, isOpen: false }))}
              className="text-xs text-slate-500 hover:text-slate-400"
            >
              דלג על דירוג
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
