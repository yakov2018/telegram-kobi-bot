import React, { useState } from 'react';
import { useApp } from '../context/AppContext';
import { ROLE_NAMES, Role } from '../types';
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
} from 'lucide-react';

export const AdminPanel: React.FC = () => {
  const {
    currentUser,
    users,
    stations,
    debts,
    orders,
    broadcasts,
    createStation,
    updateUserRoleAndStation,
    resolveDebtAppeal,
    sendBroadcast,
  } = useApp();

  const [activeTab, setActiveTab] = useState<'stations' | 'users' | 'appeals' | 'broadcast'>('stations');
  const [searchUser, setSearchUser] = useState('');

  // New station state
  const [stationName, setStationName] = useState('');
  const [stationComm, setStationComm] = useState('10.0');
  const [stationSuccess, setStationSuccess] = useState<string | null>(null);

  // Broadcast state
  const [broadcastText, setBroadcastText] = useState('');
  const [broadcastSuccess, setBroadcastSuccess] = useState<string | null>(null);

  const pendingAppeals = debts.filter((d) => d.appeal_status === 'pending');

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
      alert('נא להזין אחוז עמלה תקין');
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

  return (
    <div className="space-y-6">
      {/* Admin God Mode Header */}
      <div className="bg-slate-800/90 rounded-2xl p-5 border border-slate-700 shadow-lg flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-amber-400 font-bold text-sm">
            <Shield className="w-4 h-4" />
            <span>פאנל מנהל מערכת (God Mode)</span>
          </div>
          <h2 className="text-xl font-extrabold text-white mt-1">
            שליטה ארצית בכלל התחנות, העובדים, העמלות והערעורים
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            מחובר כעת: <strong className="text-white">{currentUser.full_name}</strong> (מזהה {currentUser.user_id})
          </p>
        </div>

        {/* Tab Navigation */}
        <div className="flex flex-wrap gap-1.5 bg-slate-900/90 p-1.5 rounded-xl border border-slate-800">
          <button
            onClick={() => setActiveTab('stations')}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 ${
              activeTab === 'stations'
                ? 'bg-amber-500 text-slate-950'
                : 'text-slate-300 hover:text-white hover:bg-slate-800'
            }`}
          >
            <Building className="w-3.5 h-3.5" />
            <span>תחנות ועמלות</span>
          </button>
          <button
            onClick={() => setActiveTab('users')}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 ${
              activeTab === 'users'
                ? 'bg-amber-500 text-slate-950'
                : 'text-slate-300 hover:text-white hover:bg-slate-800'
            }`}
          >
            <Users className="w-3.5 h-3.5" />
            <span>הרשאות משתמשים ({users.length})</span>
          </button>
          <button
            onClick={() => setActiveTab('appeals')}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 relative ${
              activeTab === 'appeals'
                ? 'bg-amber-500 text-slate-950'
                : 'text-slate-300 hover:text-white hover:bg-slate-800'
            }`}
          >
            <Scale className="w-3.5 h-3.5" />
            <span>ערעורי חוב</span>
            {pendingAppeals.length > 0 && (
              <span className="bg-red-500 text-white text-[10px] px-1.5 py-0.2 rounded-full font-bold">
                {pendingAppeals.length}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveTab('broadcast')}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 ${
              activeTab === 'broadcast'
                ? 'bg-amber-500 text-slate-950'
                : 'text-slate-300 hover:text-white hover:bg-slate-800'
            }`}
          >
            <Radio className="w-3.5 h-3.5" />
            <span>שידור Broadcast</span>
          </button>
        </div>
      </div>

      {/* Tab 1: Stations & Commissions */}
      {activeTab === 'stations' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Create Station Form (➕ פתיחת תחנה חדשה) */}
          <div className="lg:col-span-5 bg-slate-800/90 rounded-2xl p-5 border border-slate-700 shadow-md">
            <h3 className="font-bold text-base text-white mb-2 flex items-center gap-2">
              <Plus className="w-4 h-4 text-amber-400" />
              <span>פתיחת תחנה חדשה במערכת</span>
            </h3>
            <p className="text-xs text-slate-400 mb-4">
              הגדר שם תחנה ואחוז עמלה שיחויב אוטומטית מכל נהג על סגירת קריאה
            </p>

            {stationSuccess && (
              <div className="mb-4 bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 px-3 py-2 rounded-xl text-xs font-medium">
                {stationSuccess}
              </div>
            )}

            <form onSubmit={handleCreateStation} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                  שם התחנה (למשל: תחנת מרכז השפלה):
                </label>
                <input
                  type="text"
                  required
                  value={stationName}
                  onChange={(e) => setStationName(e.target.value)}
                  placeholder="הקלד שם תחנה..."
                  className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-amber-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                  אחוז עמלת תחנה (למשל: 10.5):
                </label>
                <div className="relative">
                  <input
                    type="number"
                    step="0.5"
                    min="0"
                    max="50"
                    required
                    value={stationComm}
                    onChange={(e) => setStationComm(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-amber-500"
                  />
                  <Percent className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-2.5" />
                </div>
              </div>

              <button
                type="submit"
                className="w-full bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold py-2.5 rounded-xl transition text-xs flex items-center justify-center gap-1.5 shadow"
              >
                <Plus className="w-4 h-4" />
                <span>הקם תחנה חדשה</span>
              </button>
            </form>
          </div>

          {/* Existing Stations List */}
          <div className="lg:col-span-7 bg-slate-800/90 rounded-2xl p-5 border border-slate-700 shadow-md">
            <h3 className="font-bold text-base text-white mb-4 flex items-center gap-2">
              <Building className="w-4 h-4 text-blue-400" />
              <span>תחנות פעילות במערכת ({stations.length})</span>
            </h3>

            <div className="space-y-3">
              {stations.map((st) => {
                const stationDrivers = users.filter((u) => u.station_id === st.station_id && u.role === 'user');
                const stationOrders = orders.filter((o) => o.station_id === st.station_id);
                return (
                  <div
                    key={st.station_id}
                    className="bg-slate-900/90 border border-slate-700 rounded-xl p-4 flex items-center justify-between"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs bg-slate-800 text-slate-300 px-2 py-0.5 rounded border border-slate-700">
                          #{st.station_id}
                        </span>
                        <h4 className="font-bold text-sm text-white">{st.name}</h4>
                      </div>
                      <div className="text-xs text-slate-400 mt-1 flex items-center gap-4">
                        <span>👥 נהגים: {stationDrivers.length}</span>
                        <span>📋 סה"כ קריאות: {stationOrders.length}</span>
                      </div>
                    </div>

                    <div className="text-left">
                      <span className="text-xs text-slate-400 block">עמלת תחנה</span>
                      <span className="text-base font-extrabold text-amber-400">
                        {st.commission_percent}%
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: User Roles & Permissions (👥 ניהול הרשאות משתמשים) */}
      {activeTab === 'users' && (
        <div className="bg-slate-800/90 rounded-2xl p-5 border border-slate-700 shadow-md">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
            <div>
              <h3 className="font-bold text-base text-white flex items-center gap-2">
                <Users className="w-4 h-4 text-amber-400" />
                <span>ניהול הרשאות ומשתמשים (God Mode)</span>
              </h3>
              <p className="text-xs text-slate-400">
                שינוי תפקיד מיידי: מנהל מערכת, מנהל תחנה, סדרן, נהג, או חסימת משתמש (Blocked)
              </p>
            </div>

            <div className="relative">
              <input
                type="text"
                placeholder="חפש לפי שם / טלפון / ID..."
                value={searchUser}
                onChange={(e) => setSearchUser(e.target.value)}
                className="bg-slate-900 border border-slate-700 text-xs rounded-xl pr-8 pl-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-amber-500 w-full sm:w-64"
              />
              <Search className="w-3.5 h-3.5 text-slate-400 absolute right-2.5 top-2.5" />
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-right text-xs">
              <thead>
                <tr className="border-b border-slate-700 text-slate-400 font-semibold">
                  <th className="py-2.5 px-3">מזהה (ID)</th>
                  <th className="py-2.5 px-3">שם מלא</th>
                  <th className="py-2.5 px-3">טלפון</th>
                  <th className="py-2.5 px-3">תפקיד נוכחי</th>
                  <th className="py-2.5 px-3">שיוך תחנה</th>
                  <th className="py-2.5 px-3">חוב נוכחי</th>
                  <th className="py-2.5 px-3">סטטוס חסימה</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {filteredUsers.map((u) => (
                  <tr key={u.user_id} className="hover:bg-slate-900/50 transition">
                    <td className="py-2.5 px-3 font-mono text-slate-400">{u.user_id}</td>
                    <td className="py-2.5 px-3 font-bold text-white">
                      {u.full_name}
                      {u.user_id === currentUser.user_id && (
                        <span className="text-[10px] text-amber-400 mr-1.5">(אתה)</span>
                      )}
                    </td>
                    <td className="py-2.5 px-3 text-slate-300 font-mono">{u.phone}</td>
                    <td className="py-2.5 px-3">
                      <select
                        value={u.is_blocked ? 'blocked' : u.role}
                        onChange={(e) =>
                          updateUserRoleAndStation(
                            u.user_id,
                            e.target.value as Role | 'blocked',
                            u.station_id
                          )
                        }
                        className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-slate-200 text-xs focus:outline-none focus:border-amber-500"
                      >
                        <option value="admin">מנהל מערכת (admin)</option>
                        <option value="station_manager">מנהל תחנה (station_manager)</option>
                        <option value="dispatcher">סדרן (dispatcher)</option>
                        <option value="user">נהג / שליח (user)</option>
                        <option value="blocked">🚫 חסום (blocked)</option>
                      </select>
                    </td>
                    <td className="py-2.5 px-3">
                      <select
                        value={u.station_id}
                        onChange={(e) =>
                          updateUserRoleAndStation(u.user_id, u.role, Number(e.target.value))
                        }
                        className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-slate-200 text-xs focus:outline-none focus:border-amber-500"
                      >
                        {stations.map((st) => (
                          <option key={st.station_id} value={st.station_id}>
                            #{st.station_id} {st.name}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="py-2.5 px-3 font-mono">
                      <span className={u.debt_balance > 500 ? 'text-red-400 font-bold' : 'text-slate-300'}>
                        ₪{u.debt_balance.toFixed(2)}
                      </span>
                    </td>
                    <td className="py-2.5 px-3">
                      {u.is_blocked ? (
                        <span className="inline-flex items-center gap-1 text-red-400 font-bold">
                          <Lock className="w-3 h-3" /> חסום
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-emerald-400 font-medium">
                          <Unlock className="w-3 h-3" /> פעיל
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 3: Debt Appeals Inbox (סעיף 5 בבוט) */}
      {activeTab === 'appeals' && (
        <div className="bg-slate-800/90 rounded-2xl p-5 border border-slate-700 shadow-md">
          <h3 className="font-bold text-base text-white mb-2 flex items-center gap-2">
            <Scale className="w-4 h-4 text-amber-400" />
            <span>תיבת ערעורי נהגים להכרעת הנהלה ({pendingAppeals.length})</span>
          </h3>
          <p className="text-xs text-slate-400 mb-4">
            אישור ערעור מוחק את החוב מיידית מיתרת הנהג. דחיית ערעור מותירה את החוב לתשלום.
          </p>

          {pendingAppeals.length === 0 ? (
            <div className="p-8 text-center bg-slate-900/60 rounded-xl border border-slate-800">
              <CheckCircle className="w-10 h-10 text-emerald-400 mx-auto mb-2" />
              <p className="text-sm font-bold text-slate-200">אין ערעורים הממתינים לבדיקה</p>
              <p className="text-xs text-slate-500 mt-1">כל בקשות הביטול טופלו במלואן.</p>
            </div>
          ) : (
            <div className="space-y-4">
              {pendingAppeals.map((debt) => {
                const driver = users.find((u) => u.user_id === debt.driver_id);
                return (
                  <div
                    key={debt.debt_id}
                    className="bg-slate-900 border border-slate-700/80 rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-4"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-sm text-white">
                          ערעור על חיוב #{debt.debt_id}
                        </span>
                        <span className="text-xs bg-amber-500/10 text-amber-400 border border-amber-500/30 px-2 py-0.5 rounded font-mono font-bold">
                          ₪{debt.amount.toFixed(2)}
                        </span>
                        <span className="text-xs text-slate-400">עבור קריאה #{debt.order_id}</span>
                      </div>

                      <div className="text-xs text-slate-300 mt-1">
                        נהג: <strong>{driver ? driver.full_name : 'לא ידוע'}</strong> | טלפון: {driver?.phone} | רכב: {driver?.car_brand} {driver?.car_model}
                      </div>

                      <div className="mt-2 text-xs bg-slate-950 p-2.5 rounded-lg border border-slate-800 text-slate-300">
                        <span className="text-amber-400 font-bold">נימוק הנהג: </span>
                        {debt.appeal_reason}
                      </div>
                    </div>

                    <div className="flex items-center gap-2 self-end md:self-auto">
                      <button
                        onClick={() => resolveDebtAppeal(debt.debt_id, true)}
                        className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold px-3.5 py-2 rounded-xl transition flex items-center gap-1.5 shadow"
                      >
                        <CheckCircle className="w-3.5 h-3.5" />
                        <span>אשר ביטול (מחק חוב)</span>
                      </button>
                      <button
                        onClick={() => resolveDebtAppeal(debt.debt_id, false)}
                        className="bg-red-600/80 hover:bg-red-600 text-white text-xs font-bold px-3.5 py-2 rounded-xl transition flex items-center gap-1.5"
                      >
                        <XCircle className="w-3.5 h-3.5" />
                        <span>דחה ערעור (השאר חוב)</span>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Tab 4: Global Broadcast (סעיף God Broadcast בבוט) */}
      {activeTab === 'broadcast' && (
        <div className="bg-slate-800/90 rounded-2xl p-5 border border-slate-700 shadow-md">
          <h3 className="font-bold text-base text-white mb-2 flex items-center gap-2">
            <Radio className="w-4 h-4 text-amber-400" />
            <span>שידור הודעת Broadcast גלובלית</span>
          </h3>
          <p className="text-xs text-slate-400 mb-4">
            שליחת התראה לכלל המשתמשים במערכת (נהגים, סדרנים ומנהלים)
          </p>

          {broadcastSuccess && (
            <div className="mb-4 bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 px-3 py-2 rounded-xl text-xs font-medium">
              {broadcastSuccess}
            </div>
          )}

          <form onSubmit={handleSendBroadcast} className="space-y-4 max-w-2xl">
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                תוכן ההודעה לשידור:
              </label>
              <textarea
                value={broadcastText}
                onChange={(e) => setBroadcastText(e.target.value)}
                placeholder="לדוגמה: עקב עומסי תנועה חריגים באזור המרכז, מומלץ לתמחר בהתאם. יום מוצלח לכולם!"
                rows={4}
                required
                className="w-full bg-slate-900 border border-slate-700 rounded-xl p-3 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-amber-500 resize-none"
              />
            </div>

            <button
              type="submit"
              className="bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold px-5 py-2.5 rounded-xl transition text-xs flex items-center gap-2 shadow"
            >
              <Send className="w-3.5 h-3.5" />
              <span>שדר לכל המשתמשים ({users.length})</span>
            </button>
          </form>

          {/* Past Broadcasts */}
          <div className="mt-8 border-t border-slate-700 pt-4">
            <h4 className="text-xs font-bold text-slate-300 mb-3">הודעות ששודרו לאחרונה:</h4>
            <div className="space-y-2">
              {broadcasts.map((b) => (
                <div key={b.id} className="bg-slate-900 p-3 rounded-xl border border-slate-800 text-xs">
                  <div className="flex items-center justify-between text-slate-400 text-[11px] mb-1">
                    <span>שודר ע"י: {b.sender_name}</span>
                    <span>{new Date(b.created_at).toLocaleString('he-IL')}</span>
                  </div>
                  <p className="text-slate-200">{b.text}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
