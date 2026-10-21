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
  viewMode: 'erp' | 'driver' | 'telegram';
  setViewMode: (mode: 'erp' | 'driver' | 'telegram') => void;
  onOpenRegister: () => void;
  onOpenGuide: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  viewMode,
  setViewMode,
  onOpenRegister,
  onOpenGuide,
}) => {
  const { currentUser, users, stations, switchUser, resetToInitialData, isTelegramWebApp } = useApp();

  const currentStation = stations.find((s) => s.station_id === currentUser.station_id);

  const getRoleIcon = (role: Role) => {
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

  const getRoleBadgeColor = (role: Role) => {
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
                  {currentStation ? currentStation.name : 'מערכת כללית'} ({currentStation ? `${currentStation.commission_percent}% עמלה` : ''})
                </span>
              </div>
              <p className="text-xs text-slate-400 hidden sm:block">
                מערכת שיגור וניהול חכם לתחנות מוניות, שליחים וחובות
              </p>
            </div>
          </div>

          {/* View Mode Tabs - מוצג אך ורק למנהלים וסדרנים לצורכי ניהול ותפעול */}
          {(currentUser.role === 'admin' || currentUser.role === 'dispatcher') && (
            <div className="flex items-center bg-slate-950/70 p-1 rounded-xl border border-slate-800">
              <button
                onClick={() => setViewMode('erp')}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  viewMode === 'erp'
                    ? 'bg-amber-500 text-slate-950 font-bold shadow'
                    : 'text-slate-300 hover:text-white hover:bg-slate-800/60'
                }`}
              >
                <LayoutDashboard className="w-3.5 h-3.5" />
                <span>פאנל ניהול ERP</span>
              </button>
              <button
                onClick={() => setViewMode('driver')}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  viewMode === 'driver'
                    ? 'bg-amber-500 text-slate-950 font-bold shadow'
                    : 'text-slate-300 hover:text-white hover:bg-slate-800/60'
                }`}
              >
                <Smartphone className="w-3.5 h-3.5" />
                <span>עמדת נהג</span>
              </button>
              <button
                onClick={() => setViewMode('telegram')}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  viewMode === 'telegram'
                    ? 'bg-blue-600 text-white font-bold shadow'
                    : 'text-slate-300 hover:text-white hover:bg-slate-800/60'
                }`}
              >
                <Bot className="w-3.5 h-3.5" />
                <span>בוט טלגרם (Live)</span>
              </button>
            </div>
          )}

          {/* User Profile Switcher */}
          <div className="flex items-center gap-3">
            {(currentUser.role === 'admin' || currentUser.role === 'dispatcher') && (
              <div className="hidden md:flex items-center gap-2">
                <span className="text-xs text-slate-400">החלף משתמש:</span>
                <select
                  value={currentUser.user_id}
                  onChange={(e) => switchUser(Number(e.target.value))}
                  className="bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-amber-500 cursor-pointer"
                >
                  {users.map((u) => (
                    <option key={u.user_id} value={u.user_id}>
                      {u.full_name} ({ROLE_NAMES[u.role] || u.role})
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Current user badge */}
            <div
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-semibold ${getRoleBadgeColor(
                currentUser.role
              )}`}
            >
              {getRoleIcon(currentUser.role)}
              <span className="truncate max-w-[120px]">{currentUser.full_name}</span>
            </div>

            {/* Telegram WebApp indicator if opened inside Telegram */}
            {isTelegramWebApp && (
              <span className="hidden sm:inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-sky-500/10 border border-sky-500/30 text-sky-300 text-[11px] font-bold">
                📱 טלגרם Mini App
              </span>
            )}

            {/* BotFather Guide & Link Button */}
            <button
              onClick={onOpenGuide}
              className="px-2.5 py-1.5 rounded-lg bg-blue-600/20 hover:bg-blue-600 text-blue-300 hover:text-white border border-blue-500/30 text-xs font-bold transition flex items-center gap-1.5 shadow-sm"
              title="קבל את הקישור ל-BotFather בטלגרם"
            >
              <Smartphone className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">חיבור ל-BotFather</span>
            </button>

            {/* Quick Actions */}
            <button
              onClick={onOpenRegister}
              title="הרשמת נהג חדש (FSM)"
              className="p-1.5 rounded-lg bg-slate-800 text-slate-300 hover:text-amber-400 hover:bg-slate-700 border border-slate-700 transition"
            >
              <UserPlus className="w-4 h-4" />
            </button>

            <button
              onClick={() => {
                if (window.confirm('האם לאפס את כל הנתונים לברירת המחדל של הבוט?')) {
                  resetToInitialData();
                }
              }}
              title="איפוס נתונים לברירת מחדל"
              className="p-1.5 rounded-lg bg-slate-800 text-slate-400 hover:text-red-400 hover:bg-slate-700 border border-slate-700 transition"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </header>
  );
};
