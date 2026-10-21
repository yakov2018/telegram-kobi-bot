/**
 * Utilities for loading and searching Israel cities and vehicle datasets asynchronously
 */

let cachedCities: string[] | null = null;
let cachedVehicles: Record<string, string[]> | null = null;

export async function getIsraelCities(): Promise<string[]> {
  if (cachedCities) return cachedCities;
  try {
    const res = await fetch('/data/israel_cities.json');
    if (res.ok) {
      cachedCities = await res.json();
      return cachedCities || [];
    }
  } catch (err) {
    console.warn('Could not load israel_cities.json, using fallback:', err);
  }
  return [
    'ירושלים',
    'בני ברק',
    'מודיעין עילית',
    'פתח תקווה',
    'תל אביב - יפו',
    'אשדוד',
    'בית שמש',
    'ביתר עילית',
    'אלעד',
    'נתניה',
    'חולון',
    'בת ים',
    'ראשון לציון',
    'חיפה',
    'רחובות'
  ];
}

export async function getVehicleBrandsAndModels(): Promise<Record<string, string[]>> {
  if (cachedVehicles) return cachedVehicles;
  try {
    const res = await fetch('/data/vehicle_brands_models.json');
    if (res.ok) {
      cachedVehicles = await res.json();
      return cachedVehicles || {};
    }
  } catch (err) {
    console.warn('Could not load vehicle_brands_models.json, using fallback:', err);
  }
  return {
    'טויוטה': ['קורולה', 'פריוס', 'יאריס', 'ראב 4', 'קאמרי'],
    'יונדאי': ['איוניק', 'אלנטרה', 'i10', 'i20', 'טוסון', 'סונטה'],
    'קיה': ['פיקנטו', 'נירו', 'ספורטאז\'', 'ריו'],
    'סקודה': ['אוקטביה', 'סופרב', 'קודיאק', 'פאביה'],
    'אחר (הזנה ידנית)': ['דגם אחר']
  };
}
