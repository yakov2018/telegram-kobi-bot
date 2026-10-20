/**
 * Order utility functions ported directly from bot.py
 */

export function cleanOrderText(rawText: string): string {
  if (!rawText) return '';
  let text = rawText;
  // Replace arrows: [ -=]+> with '-' and <[ -=]+ with '-'
  text = text.replace(/[-=]+>/g, '-');
  text = text.replace(/<[-=]+/g, '-');
  
  // Replace common Israeli transport acronyms
  text = text.replace(/\bפת\b/g, 'פתח תקווה');
  text = text.replace(/\bים\b/g, 'ירושלים');
  text = text.replace(/\bספר\b/g, 'מודיעין עילית');
  
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
