import React, { useState } from 'react';
import { useApp } from '../context/AppContext';
import { CAR_BRANDS } from '../types';
import { UserCheck, X, Car, Calendar, Phone, CheckCircle, AlertCircle } from 'lucide-react';

interface RegistrationModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const RegistrationModal: React.FC<RegistrationModalProps> = ({ isOpen, onClose }) => {
  const { registerUser } = useApp();

  const [step, setStep] = useState<number>(1);
  const [formData, setFormData] = useState({
    name: '',
    birth_year: '',
    phone: '',
    brand: 'טויוטה',
    custom_brand: '',
    model: '',
    year: '2021',
    seats: 5,
  });
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleNext = () => {
    setError(null);

    if (step === 1) {
      if (!formData.name.trim()) {
        setError('נא להזין שם מלא.');
        return;
      }
      setStep(2);
    } else if (step === 2) {
      const year = parseInt(formData.birth_year, 10);
      if (isNaN(year) || formData.birth_year.length !== 4) {
        setError('נא להזין שנת לידה חוקית בארבע ספרות (למשל: 1995).');
        return;
      }
      const age = 2026 - year;
      if (age < 18) {
        setError('❌ המערכת לגילאי 18+ בלבד.');
        return;
      }
      setStep(3);
    } else if (step === 3) {
      const cleanPhone = formData.phone.replace(/[-+ ]/g, '');
      if (!cleanPhone.startsWith('05') && !cleanPhone.startsWith('9725')) {
        setError('⚠️ מספר ישראלי חובה (מתחיל ב-05 או 9725).');
        return;
      }
      if (cleanPhone.length < 10) {
        setError('נא להזין מספר טלפון באורך מלא.');
        return;
      }
      setStep(4);
    } else if (step === 4) {
      const finalBrand = formData.brand === 'אחר (הקלדה ידנית)' ? formData.custom_brand : formData.brand;
      if (!finalBrand.trim()) {
        setError('נא לבחור או להקליד את חברת הרכב.');
        return;
      }
      setStep(5);
    } else if (step === 5) {
      if (!formData.model.trim()) {
        setError('נא להקליד דגם רכב (למשל: סונטה היברידית, קורולה, אוקטביה).');
        return;
      }
      setStep(6);
    } else if (step === 6) {
      const carYear = parseInt(formData.year, 10);
      if (isNaN(carYear) || carYear < 2000 || carYear > 2027) {
        setError('נא להזין שנת ייצור חוקית של הרכב.');
        return;
      }
      setStep(7);
    } else if (step === 7) {
      const finalBrand = formData.brand === 'אחר (הקלדה ידנית)' ? formData.custom_brand : formData.brand;
      registerUser({
        full_name: formData.name.trim(),
        birth_year: parseInt(formData.birth_year, 10),
        phone: formData.phone.trim(),
        car_brand: finalBrand,
        car_model: formData.model.trim(),
        car_year: parseInt(formData.year, 10),
        car_seats: formData.seats,
      });
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 shadow-2xl relative">
        <button
          onClick={onClose}
          className="absolute top-4 left-4 text-slate-400 hover:text-white transition"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Wizard Header */}
        <div className="text-center mb-6">
          <div className="w-12 h-12 rounded-2xl bg-amber-500/20 text-amber-400 flex items-center justify-center mx-auto mb-2">
            <Car className="w-6 h-6" />
          </div>
          <h3 className="text-lg font-extrabold text-white">הרשמת נהג / שליח חדש</h3>
          <p className="text-xs text-slate-400 mt-1">תהליך הרשמה מלא כפי שמוגדר בבוט טלגרם (FSM: Reg)</p>

          {/* Progress dots */}
          <div className="flex items-center justify-center gap-1.5 mt-3">
            {[1, 2, 3, 4, 5, 6, 7].map((s) => (
              <span
                key={s}
                className={`w-2 h-2 rounded-full transition-all ${
                  s === step
                    ? 'w-6 bg-amber-400'
                    : s < step
                    ? 'bg-emerald-400'
                    : 'bg-slate-700'
                }`}
              />
            ))}
          </div>
        </div>

        {error && (
          <div className="mb-4 bg-red-500/15 border border-red-500/40 text-red-300 p-2.5 rounded-xl text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Steps */}
        <div className="space-y-4">
          {step === 1 && (
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                👋 שלב 1/7: הקלד את שמך המלא
              </label>
              <input
                type="text"
                autoFocus
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="למשל: דוד לוי"
                className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-amber-500"
              />
            </div>
          )}

          {step === 2 && (
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                📅 שלב 2/7: שנת לידה (18+ בלבד)
              </label>
              <input
                type="number"
                autoFocus
                placeholder="לדוגמה 1996"
                value={formData.birth_year}
                onChange={(e) => setFormData({ ...formData, birth_year: e.target.value })}
                className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-amber-500"
              />
            </div>
          )}

          {step === 3 && (
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                📱 שלב 3/7: מספר טלפון ישראלי (05... או 9725...)
              </label>
              <input
                type="tel"
                autoFocus
                placeholder="למשל: 0541234567"
                value={formData.phone}
                onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-amber-500"
              />
            </div>
          )}

          {step === 4 && (
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                🚗 שלב 4/7: בחר חברת רכב
              </label>
              <div className="grid grid-cols-2 gap-2 mb-2">
                {CAR_BRANDS.map((b) => (
                  <button
                    key={b}
                    type="button"
                    onClick={() => setFormData({ ...formData, brand: b })}
                    className={`py-2 px-2.5 rounded-xl text-xs font-semibold border transition ${
                      formData.brand === b
                        ? 'bg-amber-500/20 border-amber-500 text-amber-300'
                        : 'bg-slate-950 border-slate-700 text-slate-300 hover:bg-slate-800'
                    }`}
                  >
                    {b}
                  </button>
                ))}
              </div>

              {formData.brand === 'אחר (הקלדה ידנית)' && (
                <input
                  type="text"
                  placeholder="הקלד שם חברת רכב (למשל: סובארו, מאזדה)"
                  value={formData.custom_brand}
                  onChange={(e) => setFormData({ ...formData, custom_brand: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-amber-500 mt-2"
                />
              )}
            </div>
          )}

          {step === 5 && (
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                ✍️ שלב 5/7: דגם רכב חופשי
              </label>
              <input
                type="text"
                autoFocus
                placeholder="לדוגמה: סונטה היברידית, קורולה קרוס"
                value={formData.model}
                onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-amber-500"
              />
            </div>
          )}

          {step === 6 && (
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                📅 שלב 6/7: שנת ייצור הרכב
              </label>
              <input
                type="number"
                autoFocus
                placeholder="למשל: 2022"
                value={formData.year}
                onChange={(e) => setFormData({ ...formData, year: e.target.value })}
                className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-amber-500"
              />
            </div>
          )}

          {step === 7 && (
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-2">
                💺 שלב 7/7: כמה מקומות ישיבה ברכב?
              </label>
              <div className="grid grid-cols-4 gap-2">
                {[4, 5, 6, 7].map((num) => (
                  <button
                    key={num}
                    type="button"
                    onClick={() => setFormData({ ...formData, seats: num })}
                    className={`py-3 rounded-xl font-extrabold text-sm border transition flex flex-col items-center gap-1 ${
                      formData.seats === num
                        ? 'bg-amber-500 text-slate-950 border-amber-500'
                        : 'bg-slate-950 border-slate-700 text-slate-200 hover:bg-slate-800'
                    }`}
                  >
                    <span>{num}</span>
                    <span className="text-[10px] font-normal">נוסעים</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Action buttons */}
          <div className="flex gap-2 pt-2">
            {step > 1 && (
              <button
                type="button"
                onClick={() => setStep(step - 1)}
                className="px-4 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-bold transition"
              >
                חזרה
              </button>
            )}
            <button
              type="button"
              onClick={handleNext}
              className="flex-1 bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold py-2.5 rounded-xl transition text-xs flex items-center justify-center gap-1.5 shadow"
            >
              {step === 7 ? (
                <>
                  <CheckCircle className="w-4 h-4" />
                  <span>השלם הרשמה וכנס למערכת</span>
                </>
              ) : (
                <span>המשך לשלב הבא</span>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
