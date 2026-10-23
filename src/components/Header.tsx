import React from 'react';
import { useApp } from '../context/AppContext';
import { ROLE_NAMES, Role } from '../types';
import {
  Car,
  Shield,
  Radio,
  Building,
  UserCheck,
  RotateCcw,
  Smartphone,
  LayoutDashboard,
  Bot,
  UserPlus,
  AlertCircle,
} from 'lucide-react';

interface HeaderProps {
  activeTab: 'driver' | 'dispatcher' | 'admin';
  setActiveTab: (tab: 'driver' | 'dispatcher' | 'admin') => void;
  onOpenRegister: () => void;
  onOpenGuide: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  setActiveTab,
  onOpenRegister,
  onOpenGuide,
}) => {
  const { currentUser, users, stations, switchUser, resetToInitialData, isTelegramWebApp } = useApp();

  const currentStation = (stations || []).find((s) => s.station_id === currentUser?.station_id);

  const getRoleIcon = (role?: Role) => {
    switch (role) {
      case 'admin':
        return <Shield className="w-4 h-4 text-amber-400" />;
      case 'station_manager':
        return <Building className="w-4 h-4 text-purple-400" />;
      case 'dispatcher':
        return <Radio className="w-4 h-4 text-blue-400" />;
      case 'user':
      default:
        return <Car className="w-4 h-4 text-emerald-400" />;
    }
  };

  const getRoleBadgeColor = (role?: Role) => {
    switch (role) {
      case 'admin':
        return 'bg-amber-500/10 text-amber-300 border-amber-500/30';
      case 'station_manager':
        return 'bg-purple-500/10 text-purple-300 border-purple-500/30';
      case 'dispatcher':
        return 'bg-blue-500/10 text-blue-300 border-blue-500/30';
      case 'user':
      default:
        return 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30';
    }
  };

  return (
    <header className="sticky top-0 z-40 bg-slate-900/90 backdrop-blur-md border-b border-slate-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16 gap-3">
          {/* Logo & Station Title */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-amber-500 to-amber-600 flex items-center justify-center text-slate-950 font-bold shadow-lg shadow-amber-500/20">
              🚖
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-extrabold text-lg text-white tracking-tight">Kobi ERP Bot</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700">
                  {currentStation ? currentStation.name : 'מערכת כללית'} {currentStation ? `(${currentStation.commission_percent}% עמלה)` : ''}
                </span>
              </div>
              <p className="text-xs text-slate-400 hidden sm:block">
                מערכת שיגור וניהול חכם לתחנות מוניות, שליחים וחובות
              </p>
            </div>
          </div>

          {/* Conditional Navigation Tabs - מידור קפדני לפי Role */}
          <div className="flex items-center bg-slate-950/80 p-1 rounded-xl border border-slate-800 text-xs">
            {/* 1. כרטיסיית הנהג - פתוחה לכל המשתמשים */}
            <button
              onClick={() => setActiveTab('driver')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-bold transition-all ${
                activeTab === 'driver'
                  ? 'bg-amber-500 text-slate-950 shadow-sm'
                  : 'text-slate-300 hover:text-white hover:bg-slate-800/60'
              }`}
            >
              <Car className="w-3.5 h-3.5" />
              <span>עמדת נהג</span>
            </button>

            {/* 2. כרטיסיית סדרן - נהג רגיל לא רואה ב-DOM! רק סדרן, מנהל תחנה ומנהל מערכת */}
            {(currentUser?.role === 'dispatcher' || currentUser?.role === 'station_manager' || currentUser?.role === 'admin') && (
              <button
                onClick={() => setActiveTab('dispatcher')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-bold transition-all ${
                  activeTab === 'dispatcher'
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'text-slate-300 hover:text-white hover:bg-slate-800/60'
                }`}
              >
                <Radio className="w-3.5 h-3.5" />
                <span>עמדת סדרן</span>
              </button>
            )}

            {/* 3. כרטיסיית ניהול מערכת - אך ורק מנהל מערכת (Super Admin) רואה ב-DOM! */}
            {currentUser?.role === 'admin' && (
              <button
                onClick={() => setActiveTab('admin')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-black transition-all ${
                  activeTab === 'admin'
                    ? 'bg-gradient-to-r from-amber-500 to-amber-600 text-slate-950 shadow-sm'
                    : 'text-amber-400 hover:text-amber-300 hover:bg-slate-800/60'
                }`}
              >
                <Shield className="w-3.5 h-3.5" />
                <span>ניהול מערכת (God Mode)</span>
              </button>
            )}
          </div>

          {/* User Profile Switcher & Actions */}
          <div className="flex items-center gap-3">
            {/* החלפת משתמש זמינה אך ורק ל-admin מורשה - נחסם לחלוטין מ-DOM של משתמשים/סדרנים */}
            {currentUser?.role === 'admin' && (
              <div className="hidden md:flex items-center gap-2">
                <span className="text-xs text-slate-400">החלף משתמש:</span>
                <select
                  value={currentUser?.user_id ?? 0}
                  onChange={(e) => switchUser(Number(e.target.value))}
                  className="bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-amber-500 cursor-pointer"
                >
                  {(users || []).map((u) => (
                    <option key={u.user_id} value={u.user_id}>
                      {u.full_name || `משתמש #${u.user_id}`} ({ROLE_NAMES[u.role] || u.role})
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Current user badge */}
            <div
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-semibold ${getRoleBadgeColor(
                currentUser?.role
              )}`}
            >
              {getRoleIcon(currentUser?.role)}
              <span className="truncate max-w-[120px]">{currentUser?.full_name || 'משתמש'}</span>
            </div>

            {/* Telegram WebApp indicator if opened inside Telegram */}
            {isTelegramWebApp && (
              <span className="hidden sm:inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-sky-500/10 border border-sky-500/30 text-sky-300 text-[11px] font-bold">
                📱 טלגרם Mini App
              </span>
            )}

            {/* BotFather Guide & Link Button - זמין למנהלים בלבד */}
            {currentUser?.role === 'admin' && (
              <button
                onClick={onOpenGuide}
                className="px-2.5 py-1.5 rounded-lg bg-blue-600/20 hover:bg-blue-600 text-blue-300 hover:text-white border border-blue-500/30 text-xs font-bold transition flex items-center gap-1.5 shadow-sm cursor-pointer"
                title="קבל את הקישור ל-BotFather בטלגרם"
              >
                <Smartphone className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">חיבור ל-BotFather</span>
              </button>
            )}

            {/* Quick Actions - הרשמת נהג ידנית זמינה רק ל-admin או station_manager */}
            {(currentUser?.role === 'admin' || currentUser?.role === 'station_manager') && (
              <button
                onClick={onOpenRegister}
                title="הרשמת נהג חדש (FSM)"
                className="p-1.5 rounded-lg bg-slate-800 text-slate-300 hover:text-amber-400 hover:bg-slate-700 border border-slate-700 transition cursor-pointer"
              >
                <UserPlus className="w-4 h-4" />
              </button>
            )}

            {/* איפוס נתונים - הרשאת admin בלבד */}
            {currentUser?.role === 'admin' && (
              <button
                onClick={() => {
                  if (window.confirm('האם לאפס את כל הנתונים לברירת המחדל של הבוט?')) {
                    resetToInitialData();
                  }
                }}
                title="איפוס נתונים לברירת מחדל"
                className="p-1.5 rounded-lg bg-slate-800 text-slate-400 hover:text-red-400 hover:bg-slate-700 border border-slate-700 transition cursor-pointer"
              >
                <RotateCcw className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </div>
    </header>
  );
};

