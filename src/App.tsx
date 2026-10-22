import React, { useState } from 'react';
import { useApp } from './context/AppContext';
import { Header } from './components/Header';
import { DriverPanel } from './components/DriverPanel';
import { AdminDashboard } from './components/AdminDashboard';
import { StationManagerDashboard } from './components/StationManagerDashboard';
import { RegistrationModal } from './components/RegistrationModal';
import { MiniAppGuideModal } from './components/MiniAppGuideModal';

export const AppContent: React.FC = () => {
  const { currentUser, isAuthLoading } = useApp();
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

  // סעיף 1: מנהל מערכת (admin) - גישת God Mode מלאה!
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

export default AppContent;
