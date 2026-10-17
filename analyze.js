// Pixel forensics on icon layers. Run from seediq-mobile so jimp-compact resolves.
const Jimp = require("jimp-compact");
const fs = require("fs");
const path = require("path");

const W = "/Users/apple/SeedIQ/.iconwork";

function analyze(file) {
  return Jimp.read(file).then((img) => {
    const { width: w, height: h, data } = img.bitmap;
    let n = 0, opaque = 0, white = 0, nearWhite = 0;
    let rs = 0, gs = 0, bs = 0;
    let minX = w, minY = h, maxX = -1, maxY = -1; // bbox of "content" = opaque & not near-white
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const i = (y * w + x) * 4;
        const r = data[i], g = data[i + 1], b = data[i + 2], a = data[i + 3];
        n++;
        if (a > 8) {
          opaque++;
          rs += r; gs += g; bs += b;
          const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
          if (mx > 250 && mn > 245) white++;
          if (r > 235 && g > 235 && b > 235) {
            nearWhite++;
          } else {
            if (x < minX) minX = x; if (y < minY) minY = y;
            if (x > maxX) maxX = x; if (y > maxY) maxY = y;
          }
        }
      }
    }
    const op = opaque || 1;
    return {
      file: path.basename(file),
      size: `${w}x${h}`,
      cm: `${w}x${h}`,
      opaquePct: ((opaque / n) * 100).toFixed(1) + "%",
      pureWhitePct: ((white / n) * 100).toFixed(1) + "%",
      nearWhitePct: ((nearWhite / n) * 100).toFixed(1) + "%",
      meanRGB: `rgb(${(rs / op).toFixed(0)},${(gs / op).toFixed(0)},${(bs / op).toFixed(0)})`,
      nonWhiteBBox: maxX < 0 ? "NONE (fully white/transparent)" : `x[${minX}..${maxX}] y[${minY}..${maxY}] = ${(maxX - minX + 1)}x${(maxY - minY + 1)}px`,
      contentAreaPct: maxX < 0 ? "0%" : ((((maxX - minX + 1) * (maxY - minY + 1)) / n) * 100).toFixed(1) + "%",
    };
  });
}

const files = process.argv.slice(2);
(async () => {
  for (const f of files) {
    try {
      console.log(JSON.stringify(await analyze(f)));
    } catch (e) {
      console.log(JSON.stringify({ file: f, error: String(e.message || e) }));
    }
  }
})();
