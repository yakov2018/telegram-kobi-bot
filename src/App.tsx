import React, { useState, useEffect } from 'react';
import { useApp } from './context/AppContext';
import { Header } from './components/Header';
import { DriverPanel } from './components/DriverPanel';
import { DispatcherPanel } from './components/DispatcherPanel';
import { AdminDashboard } from './components/AdminDashboard';
import { StationManagerDashboard } from './components/StationManagerDashboard';
import { RegistrationModal } from './components/RegistrationModal';
import { MiniAppGuideModal } from './components/MiniAppGuideModal';

export const AppContent: React.FC = () => {
  const { currentUser, isAuthLoading, isAuthenticated, authError } = useApp();
  const [activeTab, setActiveTab] = useState<'driver' | 'dispatcher' | 'admin'>('driver');
  const [isRegisterOpen, setIsRegisterOpen] = useState(false);
  const [isGuideOpen, setIsGuideOpen] = useState(false);
  const [dispatcherSubTab, setDispatcherSubTab] = useState<'operations' | 'analytics'>('operations');

  // סנכרון כרטיסיית ברירת המחדל לפי תפקיד המשתמש
  useEffect(() => {
    if (currentUser?.role === 'admin') {
      setActiveTab('admin');
    } else if (currentUser?.role === 'dispatcher' || currentUser?.role === 'station_manager') {
      setActiveTab('dispatcher');
    } else {
      setActiveTab('driver');
    }
  }, [currentUser?.role]);


  // 1. מסך טעינה מהשרת
  if (isAuthLoading) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6 text-center font-sans" dir="rtl">
        <div className="w-16 h-16 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-3xl mb-4 animate-bounce">
          🚖
        </div>
        <h2 className="text-xl font-extrabold text-white mb-2">טוען נתונים מהשרת...</h2>
        <p className="text-xs text-slate-400 max-w-sm mb-6">
          מאמת משתמש מול מסד הנתונים בענן
        </p>
        <div className="w-56 h-1.5 bg-slate-800 rounded-full overflow-hidden">
          <div className="w-full h-full bg-gradient-to-r from-amber-500 to-amber-300 animate-pulse" />
        </div>
      </div>
    );
  }

  // 2. קריטי: אם האימות או ה-API נכשל, מציגים שגיאה ברורה ללא נפילה לנתוני דמה
  if (authError || !isAuthenticated || !currentUser || currentUser.user_id === 0) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6 text-center font-sans" dir="rtl">
        <div className="w-16 h-16 rounded-2xl bg-red-500/10 border border-red-500/30 flex items-center justify-center text-3xl mb-4">
          ⚠️
        </div>
        <h2 className="text-xl font-extrabold text-red-400 mb-2">שגיאה בטעינת נתונים מהשרת</h2>
        <p className="text-xs text-slate-300 max-w-md mb-6 leading-relaxed">
          {authError || 'אימות ה-Mini App נכשל מול מסד הנתונים. נא לפתוח את האפליקציה ישירות מכפתור התפריט בבוט הטלגרם.'}
        </p>
        <button
          onClick={() => window.location.reload()}
          className="px-5 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs transition shadow-md"
        >
          🔄 נסה שוב
        </button>
      </div>
    );
  }

  // אבטחה קפדנית על ניווט בין כרטיסיות (Protected Tabs)
  const isDispatcherAllowed = currentUser?.role === 'dispatcher' || currentUser?.role === 'station_manager' || currentUser?.role === 'admin';
  const isAdminAllowed = currentUser?.role === 'admin';

  // חישוב הכרטיסייה הבטוחה: אם נהג רגיל מנסה להפעיל כרטיסיית סדרן או אדמין - נכפה מיד 'driver'
  const safeTab: 'driver' | 'dispatcher' | 'admin' =
    (activeTab === 'admin' && !isAdminAllowed)
      ? 'driver'
      : (activeTab === 'dispatcher' && !isDispatcherAllowed)
        ? 'driver'
        : activeTab;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans" dir="rtl">
      {/* תפריט עליון עם כרטיסיות מותנות לפי Role */}
      <Header
        activeTab={safeTab}
        setActiveTab={(tab) => {
          if (tab === 'admin' && !isAdminAllowed) return;
          if (tab === 'dispatcher' && !isDispatcherAllowed) return;
          setActiveTab(tab);
        }}
        onOpenRegister={() => setIsRegisterOpen(true)}
        onOpenGuide={() => setIsGuideOpen(true)}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* כרטיסיית נהג - זמינה לכלל המשתמשים */}
        {safeTab === 'driver' && <DriverPanel />}

        {/* כרטיסיית סדרן - מרונדרת אך ורק אם מותר לסדרן, מנהל תחנה או מנהל מערכת! */}
        {safeTab === 'dispatcher' && isDispatcherAllowed && (
          <div className="space-y-4">
            {/* עבור מנהל תחנה או סופר אדמין, מאפשר מעבר בין עמדת שיגור לבין פאנל סטטיסטיקות תחנה */}
            {(currentUser?.role === 'station_manager' || currentUser?.role === 'admin') && (
              <div className="flex items-center justify-between bg-slate-900 border border-slate-800 p-2.5 rounded-2xl">
                <span className="text-xs font-bold text-white px-2">תצוגת סדרן / תחנה:</span>
                <div className="flex gap-1.5">
                  <button
                    onClick={() => setDispatcherSubTab('operations')}
                    className={`px-3 py-1.5 rounded-xl text-xs font-bold transition ${
                      dispatcherSubTab === 'operations' ? 'bg-blue-600 text-white shadow' : 'bg-slate-800 text-slate-300 hover:text-white'
                    }`}
                  >
                    שיגור וקריאות פעילות
                  </button>
                  <button
                    onClick={() => setDispatcherSubTab('analytics')}
                    className={`px-3 py-1.5 rounded-xl text-xs font-bold transition ${
                      dispatcherSubTab === 'analytics' ? 'bg-purple-600 text-white shadow' : 'bg-slate-800 text-slate-300 hover:text-white'
                    }`}
                  >
                    סטטיסטיקות וסדרנים
                  </button>
                </div>
              </div>
            )}

            {dispatcherSubTab === 'analytics' && (currentUser?.role === 'station_manager' || currentUser?.role === 'admin') ? (
              <StationManagerDashboard />
            ) : (
              <DispatcherPanel />
            )}
          </div>
        )}

        {/* כרטיסיית ניהול מערכת - מרונדרת אך ורק ל-Super Admin! */}
        {safeTab === 'admin' && isAdminAllowed && <AdminDashboard />}
      </main>

      <RegistrationModal isOpen={isRegisterOpen} onClose={() => setIsRegisterOpen(false)} />
      <MiniAppGuideModal isOpen={isGuideOpen} onClose={() => setIsGuideOpen(false)} />
    </div>
  );
};

export default AppContent;
