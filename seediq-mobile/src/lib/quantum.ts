/**
 * Quantum simulation core for SeedIQ Quantum Labs.
 *
 * This is a genuine (if deliberately small) state-vector simulator: the exact
 * 2-qubit state is carried as complex amplitudes and every gate is applied with
 * real linear algebra. Nothing here is a mock-up — the state vector, the
 * measurement probabilities and the 1024-shot histogram are all computed from
 * the amplitudes, so the numbers change the moment a gate angle changes.
 *
 * Basis convention: index i encodes |q0 q1> with q0 as the most significant
 * bit, i.e. 0=|00>, 1=|01>, 2=|10>, 3=|11>.
 */

export interface Complex {
  re: number;
  im: number;
}

export const ZERO: Complex = { re: 0, im: 0 };

const cAdd = (a: Complex, b: Complex): Complex => ({ re: a.re + b.re, im: a.im + b.im });
const cMul = (a: Complex, b: Complex): Complex => ({
  re: a.re * b.re - a.im * b.im,
  im: a.re * b.im + a.im * b.re,
});
const cScale = (a: Complex, s: number): Complex => ({ re: a.re * s, im: a.im * s });
const cAbs2 = (a: Complex): number => a.re * a.re + a.im * a.im;

const SQRT1_2 = Math.SQRT1_2;

/** The |00> basis state as a complex amplitude vector. */
export function zeroState(): Complex[] {
  return [
    { re: 1, im: 0 },
    { ...ZERO },
    { ...ZERO },
    { ...ZERO },
  ];
}

/**
 * Apply a single-qubit 2x2 unitary to `target` (0 or 1) of a 2-qubit state.
 * The 4x4 operator is the tensor product U ⊗ I or I ⊗ U.
 */
function applySingle(state: Complex[], target: 0 | 1, u: number[][]): Complex[] {
  const [u00, u01] = [u[0][0], u[0][1]];
  const [u10, u11] = [u[1][0], u[1][1]];
  const out: Complex[] = [
    { re: 0, im: 0 },
    { re: 0, im: 0 },
    { re: 0, im: 0 },
    { re: 0, im: 0 },
  ];
  const mask = target === 0 ? 2 : 1; // bit that distinguishes the qubit's |1> part
  for (let i = 0; i < 4; i++) {
    const bitIsOne = (i & mask) !== 0;
    const partner = bitIsOne ? i & ~mask : i | mask;
    // Row selection follows the qubit's OWN bit: a |0> component uses the
    // u[0][*] row, a |1> component uses u[1][*].
    const onPartner = bitIsOne ? u10 : u01;
    const onSelf = bitIsOne ? u11 : u00;
    out[i] = cAdd(out[i], cAdd(cScale(state[partner], onPartner), cScale(state[i], onSelf)));
  }
  return out;
}

/** Ry(θ) — rotation around the Y axis. */
export function ry(theta: number): number[][] {
  const c = Math.cos(theta / 2);
  const s = Math.sin(theta / 2);
  return [
    [c, -s],
    [s, c],
  ];
}

/** Hadamard gate. */
export const H: number[][] = [
  [SQRT1_2, SQRT1_2],
  [SQRT1_2, -SQRT1_2],
];

/** Rz applied directly (needs complex diagonal entries). */
function applyRz(state: Complex[], target: 0 | 1, phi: number): Complex[] {
  const mask = target === 0 ? 2 : 1;
  const loPhase: Complex = { re: Math.cos(-phi / 2), im: Math.sin(-phi / 2) };
  const hiPhase: Complex = { re: Math.cos(phi / 2), im: Math.sin(phi / 2) };
  return state.map((amp, i) => cMul(amp, (i & mask) !== 0 ? hiPhase : loPhase));
}

/** CNOT with `control` -> `target`, the entangling gate. */
function applyCnot(state: Complex[], control: 0 | 1, target: 0 | 1): Complex[] {
  const cMask = control === 0 ? 2 : 1;
  const tMask = target === 0 ? 2 : 1;
  const out = state.map((a) => ({ ...a }));
  for (let i = 0; i < 4; i++) {
    if ((i & cMask) !== 0 && (i & tMask) === 0) {
      const j = i | tMask;
      out[i] = state[j];
      out[j] = state[i];
    }
  }
  return out;
}

export interface CircuitAngles {
  /** Ry angle for qubit 0 / qubit 1, in radians. */
  ry0: number;
  ry1: number;
  /** Rz angle for qubit 0 / qubit 1, in radians. */
  rz0: number;
  rz1: number;
  /** Add a CNOT so the qubits become entangled. */
  entangle: boolean;
}

export const CIRCUIT_LAYERS = ["Ry", "H", "Rz", "M"] as const;
export type CircuitLayer = (typeof CIRCUIT_LAYERS)[number];

export interface SimulationResult {
  angles: CircuitAngles;
  stateVector: Complex[];
  probabilities: number[];
  counts: number[];
  shots: number;
  /** Number of gate layers applied, including the entangling layer. */
  depth: number;
  gateCount: number;
  /** P(q0 = 1) — the variational read-out. */
  probQubit0: number;
  /** P(q1 = 1). */
  probQubit1: number;
  /** Most likely basis state index. */
  dominantIndex: number;
  /** Largest single-basis probability. */
  dominantProbability: number;
  /** Read-out fidelity: probability concentrated in the dominant outcome. */
  fidelity: number;
  /** Entanglement entropy in bits (Schmidt decomposition, 0–1 bit here). */
  entropy: number;
  /** Expressibility proxy: normalised Shannon entropy of the distribution. */
  expressibility: number;
  /** Reduced Bloch vector of qubit 0: [x, y, z] from the density matrix. */
  bloch0: [number, number, number];
  /** Reduced Bloch vector of qubit 1: [x, y, z]. */
  bloch1: [number, number, number];
}

export const BASIS_LABELS = ["|00⟩", "|01⟩", "|10⟩", "|11⟩"] as const;

/**
 * Reduced Bloch vector of one qubit, obtained by tracing out the other one:
 * ρ = (I + r·σ)/2 with r = (2·Re ρ01, -2·Im ρ01, ρ00 - ρ11).
 * A pure single-qubit state lands on the unit sphere; entanglement shrinks it.
 */
export function blochVector(state: Complex[], qubit: 0 | 1): [number, number, number] {
  const bit = qubit === 0 ? 2 : 1;
  let rho00 = 0;
  let rho11 = 0;
  let re01 = 0;
  let im01 = 0;
  for (let t = 0; t < 4; t++) {
    const one = (t & bit) !== 0;
    const amp = state[t];
    if (one) {
      rho11 += cAbs2(amp);
      continue;
    }
    rho00 += cAbs2(amp);
    // ρ[0][1] = Σ a_{|0>} · conj(a_{|1>}) over the traced-out qubit.
    const partner = state[t | bit];
    re01 += amp.re * partner.re + amp.im * partner.im;
    im01 += amp.re * partner.im - amp.im * partner.re;
  }
  return [2 * re01, -2 * im01, rho00 - rho11];
}

/**
 * Entanglement entropy (bits) of the two-qubit pure state, from the Schmidt
 * coefficients — the singular values of the 2×2 amplitude matrix, whose squared
 * eigenvalues are found analytically. 0 bits = product state, 1 bit = maximally
 * entangled (a Bell state).
 */
export function entanglementEntropy(state: Complex[]): number {
  const [a, b, c, d] = state; // |00>, |01>, |10>, |11>
  const e = cAbs2(a) + cAbs2(c);
  const f = cAbs2(b) + cAbs2(d);
  const gRe = a.re * b.re + a.im * b.im + c.re * d.re + c.im * d.im;
  const gIm = a.re * b.im - a.im * b.re + c.re * d.im - c.im * d.re;
  const half = (e + f) / 2;
  const rad = Math.sqrt(Math.max(0, ((e - f) / 2) ** 2 + gRe * gRe + gIm * gIm));
  const lambda = (x: number) => (x > 1e-12 ? -x * (Math.log(x) / Math.LN2) : 0);
  const total = lambda(Math.min(1, Math.max(0, half + rad))) + lambda(Math.min(1, Math.max(0, half - rad)));
  return Math.min(1, Math.max(0, total));
}

/**
 * Expressibility proxy: the normalised Shannon entropy of the measurement
 * distribution (1 = spread evenly over all four basis states, 0 = one outcome).
 */
export function expressibility(probabilities: number[]): number {
  let h = 0;
  for (const p of probabilities) if (p > 1e-12) h += -p * (Math.log(p) / Math.LN2);
  return Math.min(1, Math.max(0, h / 2)); // log2(4) = 2 bits
}

/** Apply the circuit: Ry ⊗ Ry, then H ⊗ H, then Rz ⊗ Rz, then optional CNOT. */
export function buildState(angles: CircuitAngles): Complex[] {
  let state = zeroState();
  state = applySingle(state, 0, ry(angles.ry0));
  state = applySingle(state, 1, ry(angles.ry1));
  state = applySingle(state, 0, H);
  state = applySingle(state, 1, H);
  state = applyRz(state, 0, angles.rz0);
  state = applyRz(state, 1, angles.rz1);
  if (angles.entangle) state = applyCnot(state, 0, 1);
  return state;
}

/** Exact measurement distribution over the four basis states. */
export function probabilitiesOf(state: Complex[]): number[] {
  const probs = state.map(cAbs2);
  const total = probs.reduce((a, b) => a + b, 0);
  if (total <= 0) return [1, 0, 0, 0];
  return probs.map((p) => p / total);
}

/** Sample the distribution — a real 1024-shot measurement, not a formula. */
export function sampleCounts(probabilities: number[], shots = 1024): number[] {
  const counts = [0, 0, 0, 0];
  for (let s = 0; s < shots; s++) {
    const r = Math.random();
    let acc = 0;
    let picked = probabilities.length - 1;
    for (let i = 0; i < probabilities.length; i++) {
      acc += probabilities[i];
      if (r < acc) {
        picked = i;
        break;
      }
    }
    counts[picked] += 1;
  }
  return counts;
}

export function simulate(angles: CircuitAngles, shots = 1024): SimulationResult {
  const stateVector = buildState(angles);
  const probabilities = probabilitiesOf(stateVector);
  const counts = sampleCounts(probabilities, shots);
  const probQubit0 = probabilities[2] + probabilities[3];
  const probQubit1 = probabilities[1] + probabilities[3];
  let dominantIndex = 0;
  probabilities.forEach((p, i) => {
    if (p > probabilities[dominantIndex]) dominantIndex = i;
  });
  return {
    angles,
    stateVector,
    probabilities,
    counts,
    shots,
    depth: angles.entangle ? 4 : 3,
    gateCount: angles.entangle ? 9 : 8,
    probQubit0,
    probQubit1,
    dominantIndex,
    dominantProbability: probabilities[dominantIndex],
    fidelity: probabilities[dominantIndex],
    entropy: entanglementEntropy(stateVector),
    expressibility: expressibility(probabilities),
    bloch0: blochVector(stateVector, 0),
    bloch1: blochVector(stateVector, 1),
  };
}

// ---------------------------------------------------------------------------
// Angle encoding — the "V" in VQC
// ---------------------------------------------------------------------------

const clamp01 = (v: number) => (Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : 0);

export interface AgronomicFeatures {
  /** kg/ha */
  nitrogen: number;
  /** kg/ha */
  phosphorus: number;
  /** kg/ha */
  potassium: number;
  /** °C */
  temperature: number;
  /** % */
  humidity: number;
  /** 0–14 */
  ph: number;
  /** mm */
  rainfall: number;
  /** % seed moisture */
  moisture: number;
  /** g seed weight */
  weight: number;
}

/**
 * Angle encoding of the agronomic features (data re-uploading style):
 * each feature is scaled into [0, 2π) and becomes a rotation angle.
 *
 *   Ry(q0) ← nitrogen      Ry(q1) ← seed moisture
 *   Rz(q0) ← soil pH       Rz(q1) ← humidity
 */
export function encodeFeatures(f: AgronomicFeatures): CircuitAngles {
  const TWO_PI = Math.PI * 2;
  return {
    ry0: TWO_PI * clamp01(f.nitrogen / 140),
    ry1: TWO_PI * clamp01(f.moisture / 25),
    rz0: TWO_PI * clamp01(f.ph / 14),
    rz1: TWO_PI * clamp01(f.humidity / 100),
    entangle: true,
  };
}

/** Same mapping, reported as a human-readable list for the UI. */
export function encodingBreakdown(
  f: AgronomicFeatures,
): { label: string; value: string; angle: string }[] {
  const a = encodeFeatures(f);
  const deg = (rad: number) => `${((rad * 180) / Math.PI).toFixed(1)}°`;
  return [
    { label: "Ry — q0", value: `N ${f.nitrogen} kg/ha`, angle: deg(a.ry0) },
    { label: "Ry — q1", value: `moisture ${f.moisture}%`, angle: deg(a.ry1) },
    { label: "Rz — q0", value: `pH ${f.ph}`, angle: deg(a.rz0) },
    { label: "Rz — q1", value: `humidity ${f.humidity}%`, angle: deg(a.rz1) },
  ];
}

/**
 * Soil-parameter angle embedding used by the playground's Input Parameters
 * panel — the same four soil values the crop model consumes:
 *
 *   Ry(q0) ← nitrogen    Ry(q1) ← phosphorus
 *   Rz(q0) ← potassium   Rz(q1) ← soil pH
 */
export function encodeSoilParameters(
  nitrogen: number,
  phosphorus: number,
  potassium: number,
  ph: number,
): CircuitAngles {
  const TWO_PI = Math.PI * 2;
  return {
    ry0: TWO_PI * clamp01(nitrogen / 140),
    ry1: TWO_PI * clamp01(phosphorus / 140),
    rz0: TWO_PI * clamp01(potassium / 205),
    rz1: TWO_PI * clamp01(ph / 14),
    entangle: true,
  };
}

export const VQC_THRESHOLD = 0.5;

/**
 * The variational read-out: the circuit's own measurement statistics decide
 * whether the parameterisation looks favourable.
 */
export function vqcOutcome(result: SimulationResult): { probability: number; favourable: boolean } {
  const probability = result.probQubit0;
  return { probability, favourable: probability >= VQC_THRESHOLD };
}
