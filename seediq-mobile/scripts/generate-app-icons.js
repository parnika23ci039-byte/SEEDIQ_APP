/**
 * SeedIQ — canonical launcher icon generator.
 *
 * Source of truth: ~/Downloads/SeedIQ logo.jpeg (736x919) — the real client logo.
 * The logo is a photographic mark (sunlit sapling crossing into a teal circuit glow).
 * It is NEVER redrawn: we only crop to a square region and scale. Masking (circle /
 * rounded-rect) is the standard Android treatment and does not alter the artwork.
 *
 * Outputs:
 *   android/app/src/main/res/mipmap-*dpi/ic_launcher.png            (legacy, rounded)
 *   android/app/src/main/res/mipmap-*dpi/ic_launcher_round.png      (legacy, circle)
 *   android/app/src/main/res/mipmap-*dpi/ic_launcher_foreground.png (adaptive FG, full bleed)
 *   android/app/src/main/res/drawable-*dpi/splashscreen_logo.png    (splash badge)
 *   assets/icon.png, assets/adaptive-icon.png,
 *   assets/splash-icon.png, assets/favicon.png
 */
const Jimp = require("jimp-compact");
const fs = require("fs");
const os = require("os");
const path = require("path");

// Usage:  node scripts/generate-app-icons.js ["/path/to/SeedIQ logo.jpeg"]
const SRC = process.argv[2] || path.join(os.homedir(), "Downloads/SeedIQ logo.jpeg");
const ROOT = path.resolve(__dirname, "..");
const RES = path.join(ROOT, "android/app/src/main/res");
const ASSETS = path.join(ROOT, "assets");
const WORK = path.join(os.tmpdir(), "seediq-icon-work");

// Crop that frames the plant crown + circuit glow as tightly as is safe.
// 620x620 @ (20,240) was chosen by rendering candidates at the TRUE 132px launcher
// size (48dp on a 440dpi screen): a full-width crop left the sapling a thin stem at
// launcher size, while this crop keeps it bold AND leaves headroom inside the
// adaptive-icon mask so no leaf is clipped by any launcher mask shape.
const CROP_X = 20;
const CROP_Y = 240;
const CROP_SIDE = 620;

const DENSITIES = [
  ["mdpi", 1],
  ["hdpi", 1.5],
  ["xhdpi", 2],
  ["xxhdpi", 3],
  ["xxxhdpi", 4],
];

const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);

function squareCover(x, y, size, rad) {
  const loX = rad, hiX = size - 1 - rad, loY = rad, hiY = size - 1 - rad;
  let qx = 0, qy = 0;
  if (x < loX) qx = loX - x; else if (x > hiX) qx = x - hiX;
  if (y < loY) qy = loY - y; else if (y > hiY) qy = y - hiY;
  if (qx === 0 || qy === 0) return 1;
  return clamp01(rad + 0.5 - Math.hypot(qx, qy));
}

function circleCover(x, y, size) {
  const c = (size - 1) / 2;
  return clamp01(size / 2 - Math.hypot(x - c, y - c) + 0.5);
}

/**
 * Render `art` (already square, artPx wide) into a `size`x`size` RGBA canvas,
 * either full bleed or centred inside a padded area, clipped by `shape`.
 */
function compose({ art, size, artPx, shape, radiusPct = 0, padPct = 0 }) {
  const out = new Jimp(size, size, 0x00000000);
  const aw = art.bitmap.width, ah = art.bitmap.height;
  const a = art.bitmap.data;
  const o = out.bitmap.data;
  const usable = Math.round(size * (1 - 2 * padPct));
  const ox = Math.round((size - usable) / 2);
  const scale = usable / artPx;
  const rad = radiusPct * usable;

  for (let y = 0; y < usable; y++) {
    const sy = Math.min(ah - 1, Math.floor(y / scale));
    for (let x = 0; x < usable; x++) {
      const sx = Math.min(aw - 1, Math.floor(x / scale));
      const si = (sy * aw + sx) * 4;
      const dx = ox + x, dy = ox + y;
      const di = (dy * size + dx) * 4;

      let cover;
      if (shape === "circle") cover = circleCover(dx - ox, dy - ox, usable);
      else if (shape === "rounded") cover = squareCover(x, y, usable, rad);
      else cover = 1;

      if (cover <= 0) continue;
      o[di] = a[si];
      o[di + 1] = a[si + 1];
      o[di + 2] = a[si + 2];
      o[di + 3] = Math.round(a[si + 3] * cover);
    }
  }
  return out;
}

async function artFromSource(size) {
  const img = await Jimp.read(SRC);
  img.crop(CROP_X, CROP_Y, CROP_SIDE, CROP_SIDE);
  img.resize(size, size, Jimp.RESIZE_BICUBIC);
  return img;
}

async function write(img, file) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  await img.writeAsync(file);
  const st = fs.statSync(file);
  return `${path.relative(ROOT, file)}  ${img.bitmap.width}x${img.bitmap.height}  ${(st.size / 1024).toFixed(1)} KB`;
}

(async () => {
  const log = [];
  fs.mkdirSync(WORK, { recursive: true });

  // One master render of the artwork, reused for every layer (identical pixels
  // means the launcher icon and the in-app logo can never diverge).
  const master = await artFromSource(Math.round(CROP_SIDE * 2)); // 1472px master
  const masterPath = path.join(WORK, "master_artwork.png");
  await master.writeAsync(masterPath);

  for (const [d, mult] of DENSITIES) {
    // --- adaptive foreground: full bleed, 108dp canvas ---
    const fgPx = Math.round(108 * mult);
    const fgArt = await artFromSource(fgPx);
    log.push(await write(compose({ art: fgArt, size: fgPx, artPx: fgPx, shape: "square" }),
      path.join(RES, `mipmap-${d}/ic_launcher_foreground.png`)));

    // --- legacy ic_launcher: 48dp, rounded corners (transparent outside) ---
    const legacyPx = Math.round(48 * mult);
    const legacyArt = await artFromSource(legacyPx);
    log.push(await write(compose({ art: legacyArt, size: legacyPx, artPx: legacyPx, shape: "rounded", radiusPct: 0.18 }),
      path.join(RES, `mipmap-${d}/ic_launcher.png`)));

    // --- legacy ic_launcher_round: 48dp, circle ---
    log.push(await write(compose({ art: legacyArt, size: legacyPx, artPx: legacyPx, shape: "circle" }),
      path.join(RES, `mipmap-${d}/ic_launcher_round.png`)));

    // --- splash badge: 288dp, inset with breathing room on #283618 ---
    const splashPx = Math.round(288 * mult);
    const splashArt = await artFromSource(splashPx);
    log.push(await write(compose({ art: splashArt, size: splashPx, artPx: splashPx, shape: "rounded", radiusPct: 0.14, padPct: 0.09 }),
      path.join(RES, `drawable-${d}/splashscreen_logo.png`)));
  }

  // --- Expo config assets (so a future prebuild regenerates the same icons) ---
  const a1024 = await artFromSource(1024);
  log.push(await write(compose({ art: a1024, size: 1024, artPx: 1024, shape: "rounded", radiusPct: 0.18 }),
    path.join(ASSETS, "icon.png")));
  log.push(await write(compose({ art: a1024, size: 1024, artPx: 1024, shape: "square" }),
    path.join(ASSETS, "adaptive-icon.png")));
  log.push(await write(compose({ art: a1024, size: 1024, artPx: 1024, shape: "rounded", radiusPct: 0.14, padPct: 0.09 }),
    path.join(ASSETS, "splash-icon.png")));
  const a256 = await artFromSource(256);
  log.push(await write(compose({ art: a256, size: 256, artPx: 256, shape: "rounded", radiusPct: 0.18 }),
    path.join(ASSETS, "favicon.png")));

  console.log(log.join("\n"));
  console.log(`\n${log.length} icon files written.`);
})();
