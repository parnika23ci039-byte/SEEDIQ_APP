// Mobile mirror of seediq-frontend/src/lib/crops.ts.
//
// The web app is the source of truth for crop names and imagery. The web file
// cannot be imported directly (its values are `/crops/...` public URLs served by
// the web server), so the same catalog is reproduced here and backed by image
// modules generated from the ORIGINAL photos by scripts/build-crop-assets.mjs.
//
// Keep CROP_VARIETIES and the resolution rules below in sync with the web file.
import { CROP_ASSET_META, CROP_IMAGE_MODULES } from "./crop-assets";

export type CropAsset = {
  name: string;
  slug: string;
  cropImageSource: number | null;
  storageImageSource: number | null;
};

/** Master crop variety list — identical to the web CROP_VARIETIES export. */
export const CROP_VARIETIES = [
  "Wheat", "Rice", "Maize", "Cotton", "Groundnut", "Sunflower", "Soybean", "Sugarcane",
  "Sorghum", "Pearl Millet", "Finger Millet", "Barley", "Oats", "Rye", "Buckwheat",
  "Quinoa", "Amaranth", "Teff", "Wild Rice", "Spelt", "Triticale", "Canola",
  "Mustard", "Sesame", "Linseed", "Safflower", "Castor", "Niger Seed", "Olive",
  "Oil Palm", "Coconut", "Chickpea", "Pigeon Pea", "Lentil", "Black Gram", "Green Gram",
  "Cowpea", "Horse Gram", "Moth Bean", "Peas", "Faba Bean", "Lupin", "Alfalfa",
  "Clover", "Timothy Grass", "Bermuda Grass", "Ryegrass", "Fescue", "Brome", "Vetch",
  "Potato", "Sweet Potato", "Cassava", "Yam", "Taro", "Beetroot", "Turnip", "Radish",
  "Carrot", "Onion", "Garlic", "Leek", "Shallot", "Tomato", "Eggplant", "Capsicum",
  "Chili", "Cucumber", "Pumpkin", "Squash", "Zucchini", "Watermelon", "Muskmelon",
  "Bitter Gourd", "Bottle Gourd", "Ridge Gourd", "Sponge Gourd", "Ash Gourd", "Snake Gourd",
  "Cabbage", "Cauliflower", "Broccoli", "Brussels Sprouts", "Kohlrabi", "Kale", "Spinach",
  "Lettuce", "Celery", "Asparagus", "Artichoke", "Apple", "Banana", "Orange",
  "Mango", "Grapes", "Pineapple", "Papaya", "Guava", "Pomegranate", "Strawberry",
  "Blueberry", "Raspberry", "Blackberry", "Cherry", "Plum", "Peach", "Pear",
  "Almond", "Walnut", "Cashew", "Pecan", "Pistachio", "Macadamia", "Hazelnut",
  "Coffee", "Tea", "Cocoa", "Tobacco", "Rubber", "Jute", "Flax", "Hemp",
  "Turmeric", "Ginger", "Cardamom", "Black Pepper", "Clove", "Cinnamon", "Nutmeg",
  "Vanilla", "Saffron", "Coriander", "Cumin", "Fennel", "Fenugreek", "Mustard Seed",
  "Abaca", "Dragon Fruit", "Ivy Gourd", "Arecanut",
];

/** Same normalisation as the web implementation. */
function normalizeKey(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[()]/g, "")
    .replace(/\s+/g, "-")
    .replace(/_+/g, "-");
}

function toAsset(meta: (typeof CROP_ASSET_META)[string]): CropAsset {
  return {
    name: meta.name,
    slug: meta.slug,
    cropImageSource: meta.hasCrop ? CROP_IMAGE_MODULES[`${meta.slug}/crop`] ?? null : null,
    storageImageSource: meta.hasStorage ? CROP_IMAGE_MODULES[`${meta.slug}/storage`] ?? null : null,
  };
}

/** Mirrors the web getCropAsset(): exact key, then fuzzy, then alias mappings. */
export function getCropAsset(cropName: string): CropAsset | null {
  if (!cropName) return null;
  const key = normalizeKey(cropName);

  if (CROP_ASSET_META[key]) return toAsset(CROP_ASSET_META[key]);

  // Fuzzy match
  for (const [k, val] of Object.entries(CROP_ASSET_META)) {
    if (key.includes(k) || k.includes(key)) {
      return toAsset(val);
    }
  }

  // Specific alias mappings (identical to web)
  if (key.includes("areca") || key.includes("arecanut"))
    return CROP_ASSET_META["areacnut"] ? toAsset(CROP_ASSET_META["areacnut"]) : null;
  if (key.includes("bottle")) return CROP_ASSET_META["bottle-guard"] ? toAsset(CROP_ASSET_META["bottle-guard"]) : null;
  if (key.includes("brinjal") || key.includes("eggplant"))
    return CROP_ASSET_META["brinjal"] ? toAsset(CROP_ASSET_META["brinjal"]) : null;
  if (key.includes("paddy") || key.includes("rice")) return CROP_ASSET_META["rice"] ? toAsset(CROP_ASSET_META["rice"]) : null;
  if (key.includes("corn") || key.includes("maize")) return CROP_ASSET_META["maize"] ? toAsset(CROP_ASSET_META["maize"]) : null;
  if (key.includes("chilli") || key.includes("chili")) return CROP_ASSET_META["chili"] ? toAsset(CROP_ASSET_META["chili"]) : null;
  if (key.includes("tur") || key.includes("pigeon"))
    return CROP_ASSET_META["pigeon-pea"] ? toAsset(CROP_ASSET_META["pigeon-pea"]) : null;

  return null;
}

/** Bundled crop photo for a crop name, or null (web getCropImage equivalent). */
export function getCropImageSource(cropName: string): number | null {
  return getCropAsset(cropName)?.cropImageSource ?? null;
}

/** Bundled storage photo for a crop name, or null (web getStorageImage equivalent). */
export function getStorageImageSource(cropName: string): number | null {
  return getCropAsset(cropName)?.storageImageSource ?? null;
}
