/**
 * Order utility functions ported directly from bot.py
 */

export function cleanOrderText(rawText: string): string {
  if (!rawText) return '';
  let text = rawText;
  // Replace arrows: [ -=]+> with ' ➔ '
  text = text.replace(/[-=]+>/g, ' ➔ ');
  text = text.replace(/<[-=]+/g, ' ➔ ');
  
  // Replace common Israeli transport acronyms and nicknames
  text = text.replace(/\b(י-ם|עיר הקודש|ים)\b/g, 'ירושלים');
  text = text.replace(/\b(מ-?ים|מירושלים)\b/g, 'מ ירושלים');
  text = text.replace(/\b(ל-?ים|לירושלים)\b/g, 'ל ירושלים');
  text = text.replace(/\b(ב"ב|בב)\b/g, 'בני ברק');
  text = text.replace(/\b(לב"ב|לבב|לבני ברק)\b/g, 'ל בני ברק');
  text = text.replace(/\b(מב"ב|מבב|מבני ברק)\b/g, 'מ בני ברק');
  text = text.replace(/\b(פ"ת|פת)\b/g, 'פתח תקווה');
  text = text.replace(/\b(לפ"ת|לפת|לפתח תקווה)\b/g, 'ל פתח תקווה');
  text = text.replace(/\b(מפ"ת|מפת|מפתח תקווה)\b/g, 'מ פתח תקווה');
  text = text.replace(/\b(ת"א|תא)\b/g, 'תל אביב');
  text = text.replace(/\b(לת"א|לתא|לתל אביב)\b/g, 'ל תל אביב');
  text = text.replace(/\b(מת"א|מתא|מתל אביב)\b/g, 'מ תל אביב');
  text = text.replace(/\b(ק"ס|קס|ספר)\b/g, 'מודיעין עילית');
  text = text.replace(/\b(לק"ס|לקס|למודיעין עילית)\b/g, 'ל מודיעין עילית');
  text = text.replace(/\b(מק"ס|מקס|ממודיעין עילית)\b/g, 'מ מודיעין עילית');
  text = text.replace(/\b(ב"ש|בש)\b/g, 'בית שמש');
  text = text.replace(/\b(אשד|אשדו)\b/g, 'אשדוד');
  
  return text.trim();
}

/**
 * Extracts price in NIS using the same regex as bot.py: \b\d{2,4}\b
 * Takes the last matched 2-4 digit number, or 0
 */
export function extractOrderPrice(text: string): number {
  if (!text) return 0;
  const matches = text.match(/\b\d{2,4}\b/g);
  if (!matches || matches.length === 0) return 0;
  const lastMatch = matches[matches.length - 1];
  const price = parseFloat(lastMatch);
  return isNaN(price) ? 0 : price;
}

/**
 * Calculate station commission amount (סעיף 17 בבוט)
 */
export function calculateCommission(price: number, commissionPercent: number = 10.0): number {
  if (price <= 0 || commissionPercent <= 0) return 0;
  return Math.round((price * (commissionPercent / 100)) * 100) / 100;
}

/**
 * Calculate new driver rating average based on previous trips and new stars (סעיף 20 בבוט)
 */
export function calculateNewRating(currentRating: number, currentTrips: number, newStars: number): number {
  const trips = Math.max(currentTrips, 1);
  const newRating = ((currentRating * (trips - 1)) + newStars) / trips;
  return Math.round(newRating * 10) / 10;
}
