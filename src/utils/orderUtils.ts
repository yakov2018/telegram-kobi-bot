/**
 * מנוע NLP ופענוח קריאות מלא לבוט ול-Mini App (תואם 100% ל-bot.py)
 */

export const POPULAR_CITIES = [
  'ירושלים',
  'בני ברק',
  'פתח תקווה',
  'תל אביב',
  'מודיעין עילית',
  'בית שמש',
  'אשדוד',
  'חיפה',
  'נתניה',
  'הרצליה',
  'חולון',
  'בת ים',
  'ראשון לציון',
  'אלעד',
  'רמת גן',
  'גבעתיים',
  'ביתר עילית',
  'רחובות',
];

export const CITY_ALIASES: Record<string, string> = {
  'ים': 'ירושלים',
  'י-ם': 'ירושלים',
  'עיר הקודש': 'ירושלים',
  'בב': 'בני ברק',
  'ב"ב': 'בני ברק',
  'פת': 'פתח תקווה',
  'פ"ת': 'פתח תקווה',
  'תא': 'תל אביב',
  'ת"א': 'תל אביב',
  'קס': 'מודיעין עילית',
  'ק"ס': 'מודיעין עילית',
  'ספר': 'מודיעין עילית',
  'אשד': 'אשדוד',
  'אשדו': 'אשדוד',
  'בש': 'באר שבע',
  'ב"ש': 'בית שמש',
  'חי': 'חיפה',
  'נת': 'נתניה',
  'הרצ': 'הרצליה',
  'ראשלצ': 'ראשון לציון',
  'ראשל"צ': 'ראשון לציון',
  'חולון': 'חולון',
  'בת ים': 'בת ים',
};

/**
 * 1. זיהוי מספר טלפון לקוח ב-Regex קפדני:
 * - טלפון ישראלי מלא (05X, 02/03/04/08/09, +972)
 * - שלוחה / קוד פנים '0' או '1'
 */
export function extractIsraeliPhone(text: string): string {
  if (!text) return '';

  // א. טלפון ישראלי מלא
  const fullPattern = /(?:\+?972[- ]?0?|0)(?:5[0-9]|[23489]|7[2-9])[- ]?\d{3}[- ]?\d{4}\b/;
  const mFull = text.match(fullPattern);
  if (mFull) {
    return mFull[0].replace(/[^\d+]/g, '');
  }

  // ב. שלוחה/פנים '0' או '1' מפורש לפי תיוג
  const lblPattern = /(?:טלפון|טל|פלאפון|נייד|שלוחה|קוד)[:\s]*([01])\b/;
  const mLbl = text.match(lblPattern);
  if (mLbl) {
    return mLbl[1];
  }

  // ג. ספרה 0 או 1 מבודדת לחלוטין שאינה מחיר
  const isoPattern = /(?:^|\s)([01])(?:\s|$)/;
  const mIso = text.match(isoPattern);
  if (mIso) {
    const idx = mIso.index || 0;
    const subBefore = text.slice(0, idx);
    if (!/[₪ש]\s*$/.test(subBefore)) {
      return mIso[1];
    }
  }

  return '';
}

/**
 * 2. זיהוי דרישת 'זמן' / ETA
 */
export function detectRequiresEta(text: string): boolean {
  if (!text) return false;
  const timeKeywords = ['זמן', 'זמנים', 'דקות', "דק'", 'דק', 'תוך', 'דחוף', 'eta', 'מיידי', 'עכשיו'];
  for (const kw of timeKeywords) {
    const re = new RegExp(`(?:^|\\s|[^\\w])${kw}(?:$|\\s|[^\\w])`, 'i');
    if (re.test(text)) return true;
  }
  return false;
}

/**
 * 3. חילוץ מחירים וזיהוי התנגשות (Collision)
 */
export function extractCandidatePrices(text: string, clientPhone?: string): number[] {
  if (!text) return [];
  const candidatePrices: number[] = [];

  // א. מחירים עם סימון ₪ או ש"ח
  const currPattern = /(?:₪|ש"ח|שח|שקל|שקלים)\s*(\d{2,4})\b|\b(\d{2,4})\s*(?:₪|ש"ח|שח|שקל|שקלים)/g;
  let match: RegExpExecArray | null;
  while ((match = currPattern.exec(text)) !== null) {
    const val = parseFloat(match[1] || match[2]);
    if (val >= 20 && val <= 5000) {
      candidatePrices.push(val);
    }
  }

  // ב. ספרות כלליות 2-4 ספרות ללא שנים (1950-2030) וללא מספר טלפון
  if (candidatePrices.length === 0) {
    const numTokens = text.match(/\b\d{2,4}\b/g) || [];
    for (const token of numTokens) {
      const num = parseFloat(token);
      if (num >= 20 && num <= 5000) {
        if (num >= 1950 && num <= 2030) continue; // שנה
        if (clientPhone && clientPhone.includes(token)) continue; // חלק מהטלפון
        candidatePrices.push(num);
      }
    }
  }

  // הסרת כפילויות
  return Array.from(new Set(candidatePrices));
}

/**
 * 4. חתימת תחנה וסדרן (ללא תיוג @username)
 */
export function buildStationSignature(stationName: string = 'תחנה ראשית', publisherName: string = ''): string {
  const cleanPub = (publisherName || '').replace(/@[A-Za-z0-9_]+/g, '').trim() || 'סדרן המערכת';
  const cleanSt = stationName || 'תחנה ראשית';
  return `\n\n🏢 תחנה: ${cleanSt} | 👤 סדרן: ${cleanPub}`;
}

/**
 * 5. ניקוי ונירמול טקסט קריאה מלא (NLP)
 */
export function cleanOrderText(rawText: string, stationName: string = 'תחנה ראשית', publisherName: string = ''): string {
  if (!rawText) return '';
  let text = rawText;

  // חצים
  text = text.replace(/[-=]+>/g, ' ➔ ');
  text = text.replace(/<[-=]+/g, ' ➔ ');

  // החלפת קיצורי ערים
  const words = text.split(/\s+/);
  const cleanedTokens: string[] = [];

  for (const word of words) {
    let cleanW = word.replace(/[^\w\s"״'-]/g, '').trim();
    let prefix = '';
    let checkW = cleanW;

    if (cleanW.length > 2 && ['ל', 'מ', 'ב'].includes(cleanW[0]) && (CITY_ALIASES[cleanW.slice(1)] || POPULAR_CITIES.includes(cleanW.slice(1)))) {
      prefix = cleanW[0] + ' ';
      checkW = cleanW.slice(1);
    } else if (cleanW.length > 3 && ['מה', 'לה', 'בה'].includes(cleanW.slice(0, 2)) && (CITY_ALIASES[cleanW.slice(2)] || POPULAR_CITIES.includes(cleanW.slice(2)))) {
      prefix = cleanW.slice(0, 2) + ' ';
      checkW = cleanW.slice(2);
    }

    if (CITY_ALIASES[checkW]) {
      cleanedTokens.push(`${prefix}${CITY_ALIASES[checkW]}`);
    } else if (POPULAR_CITIES.includes(checkW)) {
      cleanedTokens.push(`${prefix}${checkW}`);
    } else if (POPULAR_CITIES.includes(cleanW)) {
      cleanedTokens.push(cleanW);
    } else {
      cleanedTokens.push(word);
    }
  }

  const baseText = cleanedTokens.join(' ').trim();
  const signature = buildStationSignature(stationName, publisherName);
  return `${baseText}${signature}`;
}

/**
 * 6. פונקציית פענוח מקיפה לשימוש ב-DispatcherPanel
 */
export function parseOrderNLP(rawText: string, stationName: string = 'תחנה ראשית', publisherName: string = '') {
  const text = (rawText || '').trim();
  const clientPhone = extractIsraeliPhone(text);
  const requiresEta = detectRequiresEta(text);
  const candidatePrices = extractCandidatePrices(text, clientPhone);
  const hasPriceCollision = candidatePrices.length > 1;
  const selectedPrice = candidatePrices.length > 0 ? candidatePrices[0] : 0;

  // מציאת ערים
  const foundCities: string[] = [];
  for (const [alias, std] of Object.entries(CITY_ALIASES)) {
    if (text.includes(alias) || text.includes(std)) {
      if (!foundCities.includes(std)) foundCities.push(std);
    }
  }
  for (const c of POPULAR_CITIES) {
    if (text.includes(c) && !foundCities.includes(c)) {
      foundCities.push(c);
    }
  }

  const originCity = foundCities[0] || '';
  const destCity = foundCities[1] || '';
  const cleanedText = cleanOrderText(rawText, stationName, publisherName);

  return {
    rawText,
    cleanedText,
    originCity,
    destCity,
    clientPhone,
    hasClientPhone: Boolean(clientPhone),
    requiresEta,
    candidatePrices,
    hasPriceCollision,
    selectedPrice,
    signature: buildStationSignature(stationName, publisherName),
  };
}

export function extractOrderPrice(text: string): number {
  const prices = extractCandidatePrices(text);
  return prices.length > 0 ? prices[0] : 0;
}

export function calculateCommission(price: number, commissionPercent: number = 10.0): number {
  if (price <= 0 || commissionPercent <= 0) return 0;
  return Math.round(price * (commissionPercent / 100) * 100) / 100;
}

export function calculateNewRating(currentRating: number, currentTrips: number, newStars: number): number {
  const trips = Math.max(currentTrips, 1);
  const newRating = (currentRating * (trips - 1) + newStars) / trips;
  return Math.round(newRating * 10) / 10;
}
