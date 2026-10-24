import React from 'react';
import { useApp } from '../context/AppContext';
import { ROLE_NAMES, Role } from '../types';
import {
  Car,
  Shield,
  Radio,
  Building,
  RotateCcw,
  MessageSquare,
  Ban,
} from 'lucide-react';

export type MainTab = 'driver' | 'dispatcher' | 'station_manager' | 'admin' | 'support';

interface HeaderProps {
  activeTab: MainTab;
  setActiveTab: (tab: MainTab) => void;
  onOpenRegister?: () => void;
  onOpenGuide?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  setActiveTab,
}) => {
  const { currentUser, users, stations, switchUser, refreshAllData, isTelegramWebApp } = useApp();

  const currentStation = (stations || []).find((s) => s.station_id === currentUser?.station_id);
  const isBlocked = Number(currentUser?.is_blocked) === 1;

  const getRoleIcon = (role?: Role) => {
    if (isBlocked) return <Ban className="w-3.5 h-3.5 text-red-400" />;
    switch (role) {
      case 'admin':
        return <Shield className="w-3.5 h-3.5 text-amber-400" />;
      case 'station_manager':
        return <Building className="w-3.5 h-3.5 text-purple-400" />;
      case 'dispatcher':
        return <Radio className="w-3.5 h-3.5 text-blue-400" />;
      case 'user':
      default:
        return <Car className="w-3.5 h-3.5 text-emerald-400" />;
    }
  };

  const getRoleBadgeColor = (role?: Role) => {
    if (isBlocked) return 'bg-red-500/15 text-red-300 border-red-500/40';
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

  const isDispatcherAllowed = !isBlocked && (currentUser?.role === 'dispatcher' || currentUser?.role === 'station_manager' || currentUser?.role === 'admin');
  const isStationManagerAllowed = !isBlocked && (currentUser?.role === 'station_manager' || currentUser?.role === 'admin');
  const isAdminAllowed = !isBlocked && currentUser?.role === 'admin';

  return (
    <header className="bg-slate-900 border-b border-slate-800">
      <div className="max-w-7xl mx-auto px-3 sm:px-6 py-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2.5">
          {/* Logo & Title */}
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-amber-500 to-amber-600 flex items-center justify-center text-slate-950 font-black shadow-md">
              🚖
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-extrabold text-sm sm:text-base text-white tracking-tight">Kobi ERP</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700 font-mono">
                  {currentStation ? currentStation.name : 'תחנה ראשית'}
                </span>
              </div>
              <p className="text-[11px] text-slate-400 hidden sm:block">
                ניהול ושיגור נסיעות, חובות ומערכת סדרנים
              </p>
            </div>
          </div>

          {/* User badge & Quick Tools */}
          <div className="flex items-center gap-2">
            {/* User switch (Admin only) */}
            {isAdminAllowed && users.length > 0 && (
              <div className="hidden lg:flex items-center gap-1.5">
                <span className="text-[11px] text-slate-400">החלף:</span>
                <select
                  value={currentUser?.user_id ?? 0}
                  onChange={(e) => switchUser(Number(e.target.value))}
                  className="bg-slate-800 border border-slate-700 text-slate-200 text-[11px] rounded-lg px-2 py-1 focus:outline-none cursor-pointer"
                >
                  {(users || []).map((u) => (
                    <option key={u.user_id} value={u.user_id}>
                      {u.full_name || `משתמש #${u.user_id}`} ({u.is_blocked ? '🚫 חסום' : ROLE_NAMES[u.role] || u.role})
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* User status badge */}
            <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-semibold ${getRoleBadgeColor(currentUser?.role)}`}>
              {getRoleIcon(currentUser?.role)}
              <span className="truncate max-w-[110px]">
                {currentUser?.full_name || 'משתמש'} {isBlocked ? '(חסום)' : ''}
              </span>
            </div>

            {/* Refresh button */}
            <button
              onClick={() => refreshAllData()}
              title="רענן נתונים"
              className="p-1.5 rounded-lg bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 border border-slate-700 transition cursor-pointer"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>

            {/* Telegram WebApp indicator */}
            {isTelegramWebApp && (
              <span className="hidden md:inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-sky-500/10 border border-sky-500/30 text-sky-300 text-[10px] font-bold">
                📱 Mini App
              </span>
            )}
          </div>
        </div>

        {/* Navigation Tabs - רק למשתמשים שאינם חסומים */}
        {!isBlocked && (
          <div className="mt-2.5 pt-2 border-t border-slate-800/80 flex items-center gap-1.5 overflow-x-auto scrollbar-none">
            {/* 1. כרטיסיית הנהג - פתוחה לכל המשתמשים הפעילים */}
            <button
              onClick={() => setActiveTab('driver')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition whitespace-nowrap cursor-pointer ${
                activeTab === 'driver'
                  ? 'bg-amber-500 text-slate-950 shadow-sm'
                  : 'bg-slate-800/80 text-slate-300 hover:text-white hover:bg-slate-800'
              }`}
            >
              <Car className="w-3.5 h-3.5" />
              <span>🚗 עמדת נהג</span>
            </button>

            {/* 2. כרטיסיית סדרן - רק לסדרן, מנהל תחנה ומנהל מערכת! */}
            {isDispatcherAllowed && (
              <button
                onClick={() => setActiveTab('dispatcher')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition whitespace-nowrap cursor-pointer ${
                  activeTab === 'dispatcher'
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'bg-slate-800/80 text-slate-300 hover:text-white hover:bg-slate-800'
                }`}
              >
                <Radio className="w-3.5 h-3.5" />
                <span>📢 עמדת סדרן</span>
              </button>
            )}

            {/* 3. כרטיסיית מנהל תחנה - אך ורק למנהל תחנה ומנהל מערכת! */}
            {isStationManagerAllowed && (
              <button
                onClick={() => setActiveTab('station_manager')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition whitespace-nowrap cursor-pointer ${
                  activeTab === 'station_manager'
                    ? 'bg-purple-600 text-white shadow-sm'
                    : 'bg-slate-800/80 text-slate-300 hover:text-white hover:bg-slate-800'
                }`}
              >
                <Building className="w-3.5 h-3.5" />
                <span>🏢 ניהול תחנה</span>
              </button>
            )}

            {/* 4. כרטיסיית ניהול מערכת גלובלי - אך ורק מנהל מערכת (Super Admin)! */}
            {isAdminAllowed && (
              <button
                onClick={() => setActiveTab('admin')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-black transition whitespace-nowrap cursor-pointer ${
                  activeTab === 'admin'
                    ? 'bg-gradient-to-r from-amber-500 to-amber-600 text-slate-950 shadow-sm'
                    : 'bg-slate-800/80 text-amber-400 hover:text-amber-300 hover:bg-slate-800'
                }`}
              >
                <Shield className="w-3.5 h-3.5" />
                <span>👑 ניהול מערכת (God Mode)</span>
              </button>
            )}

            {/* 5. כרטיסיית שירות, מדריך למשתמש ותקנון פרטיות */}
            <button
              onClick={() => setActiveTab('support')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition whitespace-nowrap cursor-pointer ${
                activeTab === 'support'
                  ? 'bg-emerald-500 text-slate-950 shadow-sm'
                  : 'bg-slate-800/80 text-slate-300 hover:text-white hover:bg-slate-800'
              }`}
            >
              <MessageSquare className="w-3.5 h-3.5" />
              <span>💬 שירות, מדריך ופרטיות</span>
            </button>
          </div>
        )}
      </div>
    </header>
  );
};
