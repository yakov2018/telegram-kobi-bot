import React, { useState } from 'react';
import { useApp } from './context/AppContext';
import { Header } from './components/Header';
import { DispatcherPanel } from './components/DispatcherPanel';
import { DriverPanel } from './components/DriverPanel';
import { AdminPanel } from './components/AdminPanel';
import { AdminDashboard } from './components/AdminDashboard';
import { TelegramSimulator } from './components/TelegramSimulator';
import { RegistrationModal } from './components/RegistrationModal';
import { MiniAppGuideModal } from './components/MiniAppGuideModal';
import { ROLE_NAMES } from './types';
import {
  Radio,
  Car,
  Shield,
  Layers,
  Sparkles,
  Bot,
  HelpCircle,
  TrendingUp,
  MapPin,
  CheckCircle,
} from 'lucide-react';

import { StationManagerDashboard } from './components/StationManagerDashboard';

export const AppContent: React.FC = () => {
  const { currentUser, isAuthLoading, orders, users, debts, stations } = useApp();
  const [viewMode, setViewMode] = useState<'erp' | 'driver' | 'telegram'>('driver');
  const [isRegisterOpen, setIsRegisterOpen] = useState(false);
  const [isGuideOpen, setIsGuideOpen] = useState(false);

  // סעיף 1 (פרצת אבטחה): המתנה מלאה לתשובה מהשרת לפני הצגת ממשק
  if (isAuthLoading) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6 text-center">
        <div className="w-16 h-16 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-3xl mb-4 animate-bounce">
          🚖
        </div>
        <h2 className="text-xl font-extrabold text-white mb-2">מתחבר למערכת...</h2>
        <p className="text-xs text-slate-400 max-w-sm mb-6">
          מאמת הרשאות ומסנכרן נתונים וערי עבודה מול מסד הנתונים בענן
        </p>
        <div className="w-56 h-1.5 bg-slate-800 rounded-full overflow-hidden">
          <div className="w-full h-full bg-gradient-to-r from-amber-500 to-amber-300 animate-pulse" />
        </div>
      </div>
    );
  }

  // סעיף 1: מנהל מערכת (admin - אני) - גישת God Mode מלאה!
  if (currentUser.role === 'admin') {
    return <AdminDashboard />;
  }

  // סעיף 1: מנהל תחנה (station_manager) - פאנל ניהול ב-Mini App אך ורק לנתוני ה-station_id שלו!
  if (currentUser.role === 'station_manager') {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
        <Header
          viewMode="erp"
          setViewMode={() => {}}
          onOpenRegister={() => setIsRegisterOpen(true)}
          onOpenGuide={() => setIsGuideOpen(true)}
        />
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <StationManagerDashboard />
        </main>
        <RegistrationModal isOpen={isRegisterOpen} onClose={() => setIsRegisterOpen(false)} />
        <MiniAppGuideModal isOpen={isGuideOpen} onClose={() => setIsGuideOpen(false)} />
      </div>
    );
  }

  // סעיף 1: סדרן (dispatcher) - מנהל את הקריאות שלו בלבד מתוך תפריט הכפתורים בבוט. אין לו גישה לפאנל הניהול ב-Mini App!
  if (currentUser.role === 'dispatcher') {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
        <Header
          viewMode="driver"
          setViewMode={() => {}}
          onOpenRegister={() => setIsRegisterOpen(true)}
          onOpenGuide={() => setIsGuideOpen(true)}
        />
        <main className="flex-1 max-w-5xl w-full mx-auto px-4 sm:px-6 py-6 space-y-4">
          <div className="bg-blue-500/10 border border-blue-500/30 rounded-2xl p-4 flex items-center justify-between text-xs text-blue-200">
            <div className="flex items-center gap-2">
              <span className="text-xl">📻</span>
              <div>
                <p className="font-bold text-white">שלום סדרן תחנה #{currentUser.station_id || 1} ({currentUser.full_name})</p>
                <p className="text-slate-300">פרסום וניהול הקריאות מתבצע ישירות מכפתורי הצ'אט בבוט טלגרם. כאן מוצג ממשק הנהיגה האישי שלך.</p>
              </div>
            </div>
          </div>
          <DriverPanel />
        </main>
        <RegistrationModal isOpen={isRegisterOpen} onClose={() => setIsRegisterOpen(false)} />
        <MiniAppGuideModal isOpen={isGuideOpen} onClose={() => setIsGuideOpen(false)} />
      </div>
    );
  }

  // סעיף 1: נהג רגיל (user) - הרשאות בסיס לקבלת קריאות בלבד. אין לו גישה לשום פאנל ניהול!
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      <Header
        viewMode="driver"
        setViewMode={() => {}}
        onOpenRegister={() => setIsRegisterOpen(true)}
        onOpenGuide={() => setIsGuideOpen(true)}
      />
      <main className="flex-1 max-w-5xl w-full mx-auto px-4 sm:px-6 py-6">
        <DriverPanel />
      </main>
      <RegistrationModal isOpen={isRegisterOpen} onClose={() => setIsRegisterOpen(false)} />
      <MiniAppGuideModal isOpen={isGuideOpen} onClose={() => setIsGuideOpen(false)} />
    </div>
  );
};

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Navigation Header for Dispatchers */}
      <Header
        viewMode={viewMode}
        setViewMode={setViewMode}
        onOpenRegister={() => setIsRegisterOpen(true)}
        onOpenGuide={() => setIsGuideOpen(true)}
      />

      {/* Main Viewport */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Quick KPI Strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3 flex items-center justify-between">
            <div>
              <span className="text-[11px] text-slate-400 block font-medium">קריאות פתוחות</span>
              <span className="text-xl font-extrabold text-amber-400">{openOrdersCount}</span>
            </div>
            <div className="w-9 h-9 rounded-lg bg-amber-500/10 text-amber-400 flex items-center justify-center font-bold">
              🎫
            </div>
          </div>

          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3 flex items-center justify-between">
            <div>
              <span className="text-[11px] text-slate-400 block font-medium">נהגים פנויים</span>
              <span className="text-xl font-extrabold text-emerald-400">{activeDriversCount}</span>
            </div>
            <div className="w-9 h-9 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center font-bold">
              🚗
            </div>
          </div>

          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3 flex items-center justify-between">
            <div>
              <span className="text-[11px] text-slate-400 block font-medium">סה"כ נסיעות שבוצעו</span>
              <span className="text-xl font-extrabold text-blue-400">{totalCompletedTrips}</span>
            </div>
            <div className="w-9 h-9 rounded-lg bg-blue-500/10 text-blue-400 flex items-center justify-center font-bold">
              📈
            </div>
          </div>

          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3 flex items-center justify-between">
            <div>
              <span className="text-[11px] text-slate-400 block font-medium">תחנות מוגדרות</span>
              <span className="text-xl font-extrabold text-purple-400">{stations.length}</span>
            </div>
            <div className="w-9 h-9 rounded-lg bg-purple-500/10 text-purple-400 flex items-center justify-center font-bold">
              🏢
            </div>
          </div>
        </div>

        {/* View Mode 1: Dispatcher Station View */}
        {viewMode === 'erp' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between bg-slate-900/80 p-2 rounded-2xl border border-slate-800">
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setDispatcherSubTab('dispatcher')}
                  className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 ${
                    dispatcherSubTab === 'dispatcher'
                      ? 'bg-amber-500 text-slate-950 shadow'
                      : 'text-slate-300 hover:text-white hover:bg-slate-800'
                  }`}
                >
                  <Radio className="w-3.5 h-3.5" />
                  <span>עמדת סדרן (שיגור קריאות ואישור נהגים)</span>
                </button>

                <button
                  onClick={() => setDispatcherSubTab('driver')}
                  className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 ${
                    dispatcherSubTab === 'driver'
                      ? 'bg-amber-500 text-slate-950 shadow'
                      : 'text-slate-300 hover:text-white hover:bg-slate-800'
                  }`}
                >
                  <Car className="w-3.5 h-3.5" />
                  <span>מעבר לממשק נהג אישי</span>
                </button>
              </div>

              <div className="hidden lg:flex items-center gap-2 text-xs text-slate-400">
                <span>תפקידך הנוכחי:</span>
                <span className="font-bold text-amber-300">{ROLE_NAMES[currentUser.role]}</span>
              </div>
            </div>

            {dispatcherSubTab === 'dispatcher' && <DispatcherPanel />}
            {dispatcherSubTab === 'driver' && <DriverPanel />}
          </div>
        )}

        {/* View Mode 2: Dedicated Driver App View */}
        {viewMode === 'driver' && <DriverPanel />}

        {/* View Mode 3: Pixel-Perfect Telegram Bot Simulator */}
        {viewMode === 'telegram' && (
          <div className="space-y-4">
            <div className="max-w-2xl mx-auto bg-slate-900/60 p-3.5 rounded-2xl border border-slate-800 text-xs text-slate-300 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Bot className="w-4 h-4 text-blue-400" />
                <span>
                  <strong>סימולטור טלגרם חי:</strong> מריץ את קוד הבוט המקורי 1:1 עם כל פקודות ה-FSM, המקלדות והאישור!
                </span>
              </div>
              <span className="text-[11px] text-slate-400">
                משתמש מחובר: {currentUser.full_name}
              </span>
            </div>

            <TelegramSimulator />
          </div>
        )}
      </main>

      {/* Driver Registration Modal */}
      <RegistrationModal isOpen={isRegisterOpen} onClose={() => setIsRegisterOpen(false)} />

      {/* Mini App & BotFather Guide Modal */}
      <MiniAppGuideModal isOpen={isGuideOpen} onClose={() => setIsGuideOpen(false)} />

      {/* System Footer */}
      <footer className="border-t border-slate-800/80 bg-slate-900/50 py-4 mt-12 text-center text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span>🚖 Kobi ERP Bot Web</span>
            <span>•</span>
            <span>פורט בהצלחה מפרויקט הפייתון המקורי ל-React מלא</span>
          </div>
          <div className="flex items-center gap-3 text-[11px]">
            <span>עמלת תחנה אוטומטית</span>
            <span>•</span>
            <span>חסימת Auto-Freeze מעל 500 ₪</span>
            <span>•</span>
            <span>סינון עיר חכם</span>
            <span>•</span>
            <span>דירוג ממוצע משוקלל</span>
          </div>
        </div>
      </footer>
    </div>
  );
};
