// Generate candidate icon foregrounds from the authoritative client logo.
// Run from seediq-mobile so jimp-compact resolves.
const Jimp = require("jimp-compact");
const fs = require("fs");

const SRC = "/Users/apple/Downloads/SeedIQ logo.jpeg";
const OUT = "/Users/apple/SeedIQ/.iconwork";

(async () => {
  const src = await Jimp.read(SRC);
  const W = src.bitmap.width;   // 736
  const H = src.bitmap.height;  // 919
  const S = W;                  // square side
  const maxOff = H - S;         // 183
  console.log(`source ${W}x${H}, square side ${S}, max y-offset ${maxOff}`);

  const offsets = [0, 45, 91, 137, 183];
  for (const y of offsets) {
    const img = await Jimp.read(SRC);
    img.crop(0, y, S, S);
    img.resize(1024, 1024, Jimp.RESIZE_BICUBIC);
    await img.writeAsync(`${OUT}/cand_y${y}.png`);
    console.log(`cand_y${y}.png  crop y=${y}..${y + S}`);
  }

  // Exposure check: is the crop's rendered brightness fine for a launcher?
  for (const y of offsets) {
    const img = await Jimp.read(`${OUT}/cand_y${y}.png`);
    const { width: w, height: h, data } = img.bitmap;
    let r = 0, g = 0, b = 0, dark = 0, n = 0;
    for (let i = 0; i < data.length; i += 4) {
      r += data[i]; g += data[i + 1]; b += data[i + 2];
      if (data[i] + data[i + 1] + data[i + 2] < 120) dark++;
      n++;
    }
    console.log(
      `y=${y}  mean rgb(${(r / n).toFixed(0)},${(g / n).toFixed(0)},${(b / n).toFixed(0)})  veryDarkPct=${((dark / n) * 100).toFixed(1)}%`
    );
  }
})();
