#!/usr/bin/env python3
"""
Yield Contract Drift Guard — SeedIQ
==================================

Pins the verified yield contract and fails loudly if ANY layer silently drifts
away from it:

    ICRISAT-derived dataset  ->  preprocessing  ->  23-feature manifest
        ->  trained yield RF  ->  Flask yield API  ->  Android payload

The guard is strictly READ-ONLY. It never regenerates a dataset, never trains,
never rewrites the registry, and asserts (by hash) that no file under ``data/``
or ``models/`` changed while it ran.

The contract itself (pinned in PINNED below) is the one verified at
``RUN-20261007-200925``: real ICRISAT Karnataka district-level data, no Season,
``Crop + Area_Hectares`` inputs, 23 features (Area_Hectares + 22 crop dummies),
classical RF as the user-facing figure, quantum retained as experimental.

Run:
    python tests/test_yield_contract_guard.py          # from SeedIQ/
    ~/SeedIQ/.freebuff/venv/bin/python tests/test_yield_contract_guard.py

Exit status: 0 = contract intact, 1 = drift detected (details printed).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

# --------------------------------------------------------------------------
# Locations: run from the SeedIQ project root regardless of the caller's cwd.
# --------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)  # needed to unpickle artifacts that reference qml_model

DATA_DIR = 'data'
MODELS_DIR = 'models'

ICRISAT_SOURCE = os.path.join(DATA_DIR, 'ICRISAT-District Level Data.csv')
DERIVED_YIELD = os.path.join(DATA_DIR, 'yield_icrisat_karnataka.csv')
LEGACY_SYNTHETIC_YIELD = os.path.join(DATA_DIR, 'crop_production_karnataka.csv')
SEED_DATASET = os.path.join(DATA_DIR, 'seed_viability_data.csv')
CROP_DATASET = os.path.join(DATA_DIR, 'Crop_recommendation.csv')

MANIFEST_PATH = os.path.join(MODELS_DIR, 'yield_feature_manifest.json')
YIELD_RF_PATH = os.path.join(MODELS_DIR, 'yield_prediction', 'randomforest_model.pkl')
REGISTRY_PATH = 'training_registry.json'
PREPROCESSING_PATH = 'data_preprocessing.py'

# The EXPERIMENTAL district contract's own artifact namespace. It is pinned here
# only to prove it exists and stays separate; it never replaces the served model.
EXPERIMENTAL_MODEL = os.path.join(MODELS_DIR, 'experimental', 'district_yield_model.pkl')
EXPERIMENTAL_MANIFEST = os.path.join(MODELS_DIR, 'experimental', 'district_yield_manifest.json')

MOBILE_APP_DIR = os.path.join(os.path.dirname(ROOT), 'seediq-mobile')
MOBILE_YIELD_AI = os.path.join(MOBILE_APP_DIR, 'app', 'yield-ai.tsx')
MOBILE_QUANTUM = os.path.join(MOBILE_APP_DIR, 'app', 'quantum.tsx')

# --------------------------------------------------------------------------
# THE PINNED CONTRACT — change these only as a deliberate contract change.
# --------------------------------------------------------------------------
PINNED = {
    'dataset_columns': ['Crop', 'District', 'Year', 'Area_Hectares', 'Yield_Tonnes'],
    'target_column': 'Yield_Tonnes',
    'input_schema': ['Crop', 'Area_Hectares'],
    'n_features': 23,
    'records': 5585,
    'crops': 22,
    'districts': 19,
    'years': 18,
    'year_min': 2000,
    'year_max': 2017,
    'dataset': 'data/yield_icrisat_karnataka.csv',
    'provenance_must_contain': ['ICRISAT'],
    'season_required': False,
    'season_deprecated': True,
    'dataset_synthetic': False,
    # Model M: the served artifact is a LogPerHaRegressor wrapper around
    # HistGradientBoostingRegressor fitted on log(yield per hectare). It is no
    # longer a (StandardScaler, RF) Pipeline, so the guard pins the wrapper, the
    # inner estimator, its approved hyper-parameters and the exp(pred)*area
    # inverse instead of pipeline step names.
    'wrapper_class': 'LogPerHaRegressor',
    'inner_estimator': 'HistGradientBoostingRegressor',
    'inner_hyperparams': {'max_iter': 400, 'learning_rate': 0.08},
    'quantum_experimental': True,
}

# --------------------------------------------------------------------------
# Harness
# --------------------------------------------------------------------------
_RESULTS = []  # (status, name, detail)
_GROUP = None


def group(name):
    global _GROUP
    _GROUP = name
    print(f'\n\033[1m{name}\033[0m')


def check(name, fn):
    """Run fn(); record PASS on return, FAIL on AssertionError/Exception."""
    try:
        detail = fn()
        _RESULTS.append(('PASS', f'{_GROUP}: {name}', detail or ''))
        print(f'  [PASS] {name}' + (f'\n         {detail}' if detail else ''))
    except Exception as exc:  # noqa: BLE001 - a guard must report any failure loudly
        kind = type(exc).__name__
        msg = str(exc) or kind
        _RESULTS.append(('FAIL', f'{_GROUP}: {name}', msg))
        print(f'  [FAIL] {name}\n         {kind}: {msg}')


def require(condition, message):
    if not condition:
        raise AssertionError(message)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def snapshot_tree(*dirs):
    """sha256 + size + mtime for every tracked file, so drift is provable."""
    snap = {}
    for d in dirs:
        for dirpath, dirnames, filenames in os.walk(d):
            dirnames[:] = [x for x in dirnames if x != '__pycache__']
            for fn in filenames:
                if fn.endswith('.pyc'):
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    st = os.stat(p)
                    snap[p] = (sha256(p), st.st_size, int(st.st_mtime))
                except OSError as exc:  # unreadable file is itself drift-worthy
                    snap[p] = (f'UNREADABLE:{exc}', -1, -1)
    for p in (REGISTRY_PATH, MANIFEST_PATH):
        if os.path.exists(p):
            st = os.stat(p)
            snap[p] = (sha256(p), st.st_size, int(st.st_mtime))
    return snap


def load_json(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return json.load(fh)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _request(method, url, payload=None, timeout=90):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {'Accept': 'application/json'}
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode('utf-8', 'replace')
            return resp.status, (json.loads(body) if body.strip().startswith(('{', '[')) else body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', 'replace')
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, body


class Server:
    """Boot app.py as a subprocess on a private port; always shut it down."""

    def __init__(self, port):
        self.port = port
        self.proc = None
        self.base = f'http://127.0.0.1:{port}'

    def __enter__(self):
        env = dict(os.environ)
        env['PORT'] = str(self.port)
        env['HOST'] = '127.0.0.1'
        env['FLASK_DEBUG'] = 'False'
        env['PYTHONUNBUFFERED'] = '1'
        self.log = open(os.path.join('/tmp', 'yield_guard_server.log'), 'wb')
        self.proc = subprocess.Popen(
            [sys.executable, 'app.py'], cwd=ROOT, env=env,
            stdout=self.log, stderr=subprocess.STDOUT,
        )
        deadline = time.time() + 120
        last = ''
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(
                    f'app.py exited early (rc={self.proc.returncode}); see '
                    f'/tmp/yield_guard_server.log'
                )
            try:
                # /api/model_metrics is session-gated (401 without a login), so it
                # can never confirm readiness. /api/health is the public probe the
                # Render/Railway orchestration uses.
                status, _ = _request('GET', f'{self.base}/api/health', timeout=5)
                if status == 200:
                    return self
                last = f'HTTP {status}'
            except Exception as exc:  # noqa: BLE001 - server not up yet
                last = type(exc).__name__
            time.sleep(1.0)
        raise RuntimeError(f'Flask did not become ready within 120s (last: {last})')

    def __exit__(self, *exc_info):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
        if getattr(self, 'log', None):
            self.log.close()
        return False


# --------------------------------------------------------------------------
# 1. Dataset schema guard
# --------------------------------------------------------------------------
def guard_dataset(pd):
    group('1. Dataset schema guard')

    def schema_exact():
        df = pd.read_csv(DERIVED_YIELD, nrows=5)
        got = list(df.columns)
        require(
            got == PINNED['dataset_columns'],
            f'derived yield columns drifted: expected {PINNED["dataset_columns"]}, got {got}',
        )
        return f'columns exactly {PINNED["dataset_columns"]}'

    check('derived dataset has exactly the expected columns (order-sensitive)', schema_exact)

    def no_season():
        df = pd.read_csv(DERIVED_YIELD, nrows=1)
        bad = [c for c in df.columns if 'season' in str(c).lower()]
        require(not bad, f'Season column(s) reintroduced into the yield dataset: {bad}')
        return 'no Season column present'

    check('no Season column reintroduced', no_season)

    def composition():
        df = pd.read_csv(DERIVED_YIELD)
        require(len(df) == PINNED['records'],
                f'row count drifted: expected {PINNED["records"]}, got {len(df)}')
        crops = df['Crop'].nunique()
        dists = df['District'].nunique()
        years = df['Year'].nunique()
        require(crops == PINNED['crops'], f'crop count drifted: {crops} != {PINNED["crops"]}')
        require(dists == PINNED['districts'], f'district count drifted: {dists} != {PINNED["districts"]}')
        require(years == PINNED['years'], f'year count drifted: {years} != {PINNED["years"]}')
        ymin, ymax = int(df['Year'].min()), int(df['Year'].max())
        require((ymin, ymax) == (PINNED['year_min'], PINNED['year_max']),
                f'year range drifted: {ymin}-{ymax}')
        dupes = int(df.duplicated(subset=['District', 'Crop', 'Year']).sum())
        require(dupes == 0, f'{dupes} duplicate (District, Crop, Year) keys')
        require(int(df[['Area_Hectares', 'Yield_Tonnes']].isna().sum().sum()) == 0, 'NaNs present')
        require(bool((df['Area_Hectares'] > 0).all()), 'non-positive Area_Hectares present')
        require(bool((df['Yield_Tonnes'] > 0).all()), 'non-positive Yield_Tonnes present')
        return (f'{len(df)} rows | {crops} crops | {dists} districts | {years} years '
                f'({ymin}-{ymax}) | 0 dupes | 0 NaNs')

    check('composition, target and feature columns match the pinned contract', composition)

    def source_intact():
        require(os.path.exists(ICRISAT_SOURCE), f'missing source: {ICRISAT_SOURCE}')
        size = os.path.getsize(ICRISAT_SOURCE)
        require(size > 0, 'source ICRISAT file is empty')
        return f'source present, read-only (sha256 {sha256(ICRISAT_SOURCE)[:16]}, {size} B)'

    check('source ICRISAT file is present and non-empty (read-only)', source_intact)


# --------------------------------------------------------------------------
# 2. Feature-manifest guard
# --------------------------------------------------------------------------
def guard_manifest(pd):
    group('2. Feature-manifest guard')
    m = load_json(MANIFEST_PATH)

    def fields():
        require(m.get('input_schema') == PINNED['input_schema'],
                f'input_schema drifted: {m.get("input_schema")}')
        require(m.get('target') == PINNED['target_column'],
                f'target drifted: {m.get("target")}')
        require(m.get('season_required') is PINNED['season_required'],
                f'season_required drifted: {m.get("season_required")}')
        require(m.get('season_deprecated') is PINNED['season_deprecated'],
                f'season_deprecated drifted: {m.get("season_deprecated")}')
        require(m.get('dataset_synthetic') is PINNED['dataset_synthetic'],
                f'dataset_synthetic drifted: {m.get("dataset_synthetic")}')
        prov = str(m.get('dataset_provenance') or '')
        for needle in PINNED['provenance_must_contain']:
            require(needle in prov, f'provenance missing {needle!r}: {prov!r}')
        return f'inputs={PINNED["input_schema"]} target={PINNED["target_column"]} season_required=False season_deprecated=True'

    check('manifest matches the Crop + Area_Hectares contract', fields)

    def feature_count():
        cols = m.get('feature_columns')
        require(isinstance(cols, list), 'feature_columns is not a list')
        require(len(cols) == PINNED['n_features'],
                f'feature count drifted: {len(cols)} != {PINNED["n_features"]}')
        require(cols[0] == 'Area_Hectares', f'first feature must be Area_Hectares, got {cols[0]!r}')
        require(not [c for c in cols if 'season' in str(c).lower()],
                'Season feature column reintroduced in manifest')
        require(len(set(cols)) == len(cols), 'duplicate feature columns in manifest')
        return f'{len(cols)} features, first={cols[0]!r}, no Season'

    check(f'manifest declares exactly {PINNED["n_features"]} features with no Season', feature_count)

    def order_and_vocab():
        cols = m['feature_columns']
        opts = m.get('crop_options')
        require(isinstance(opts, list) and len(opts) == PINNED['crops'],
                f'crop_options drifted: {len(opts) if isinstance(opts, list) else opts}')
        expected = ['Area_Hectares'] + [f'Crop_{c}' for c in opts]
        require(cols == expected,
                'feature_columns no longer equal Area_Hectares + one dummy per crop option (order matters)')
        return f'feature order == Area_Hectares + {len(opts)} Crop_* dummies'

    check('feature column ORDER is Area_Hectares + one dummy per crop option', order_and_vocab)

    def vocab_matches_dataset():
        df = pd.read_csv(DERIVED_YIELD, usecols=['Crop'])
        dataset_crops = set(df['Crop'].unique())
        manifest_crops = set(m['crop_options'])
        missing = dataset_crops - manifest_crops
        extra = manifest_crops - dataset_crops
        require(not missing, f'dataset crops missing from manifest: {sorted(missing)}')
        require(not extra, f'manifest crops absent from dataset: {sorted(extra)}')
        return f'manifest crop vocabulary == dataset crop vocabulary ({len(dataset_crops)} crops)'

    check('manifest crop vocabulary matches the dataset exactly', vocab_matches_dataset)

    def counts_match():
        require(m.get('records') == PINNED['records'], f'records drifted: {m.get("records")}')
        require(m.get('districts') == PINNED['districts'], f'districts drifted: {m.get("districts")}')
        require(m.get('years') == PINNED['years'], f'years drifted: {m.get("years")}')
        require(str(m.get('dataset')) == PINNED['dataset'], f'dataset drifted: {m.get("dataset")}')
        sem = str(m.get('semantics') or '').lower()
        require('district' in sem, 'semantics no longer states district-level data')
        require('not field-level' in sem, 'semantics no longer denies field-level semantics')
        require('not live' in sem, 'semantics no longer denies live data')
        return 'records/districts/years/dataset pinned; semantics states district-level, NOT field-level, NOT live'

    check('manifest counts, dataset path and honesty semantics are pinned', counts_match)

    return m


# --------------------------------------------------------------------------
# 3. Model compatibility guard
# --------------------------------------------------------------------------
def guard_model(m, pd):
    group('3. Model compatibility guard')

    def loadable():
        require(os.path.exists(YIELD_RF_PATH), f'missing artifact: {YIELD_RF_PATH}')
        import joblib
        model = joblib.load(YIELD_RF_PATH)
        require(model is not None, 'artifact loaded as None')
        require(hasattr(model, 'predict'), 'artifact has no predict()')
        return model

    holder = {}

    def _load():
        holder['model'] = loadable()
        return f'loaded {YIELD_RF_PATH}'

    check('trained yield artifact loads', _load)
    if 'model' not in holder:
        check('model feature count matches the manifest', lambda: (_ for _ in ()).throw(
            AssertionError('skipped: artifact failed to load')))
        return
    model = holder['model']

    def dims():
        n_wrap = getattr(model, 'n_features_in_', None)
        require(n_wrap is not None, 'model exposes no n_features_in_')
        require(n_wrap == PINNED['n_features'],
                f'model n_features_in_ drifted: {n_wrap} != {PINNED["n_features"]}')
        cls_name = type(model).__name__
        require(cls_name == PINNED['wrapper_class'],
                f'yield wrapper class drifted: {cls_name} != {PINNED["wrapper_class"]}')
        inner = getattr(model, 'regressor_', None)
        require(inner is not None, 'wrapper exposes no fitted regressor_')
        inner_name = type(inner).__name__
        require(inner_name == PINNED['inner_estimator'],
                f'inner estimator drifted: {inner_name} != {PINNED["inner_estimator"]}')
        params = inner.get_params()
        for key, expected in PINNED['inner_hyperparams'].items():
            require(params.get(key) == expected,
                    f'inner hyper-parameter {key} drifted: '
                    f'{params.get(key)} != {expected}')
        n_inner = getattr(inner, 'n_features_in_', None)
        if n_inner is not None:
            require(n_inner == PINNED['n_features'],
                    f'inner estimator n_features_in_ drifted: {n_inner}')
        return (f'{cls_name} wrapping {inner_name}({PINNED["inner_hyperparams"]}) | '
                f'n_features_in_ == {n_wrap} on both wrapper and inner estimator')

    check(f'model.n_features_in_ == {PINNED["n_features"]}', dims)

    def manifest_match():
        cols = m['feature_columns']
        n_pipe = getattr(model, 'n_features_in_', None)
        require(n_pipe == len(cols),
                f'model expects {n_pipe} features but manifest declares {len(cols)}')
        return f'model width ({n_pipe}) == manifest width ({len(cols)})'

    check('model feature count matches the manifest exactly', manifest_match)

    def predicts_in_manifest_order():
        cols = m['feature_columns']
        row = {c: 0.0 for c in cols}
        row['Area_Hectares'] = 100.0
        if 'Crop_Rice' in row:
            row['Crop_Rice'] = 1.0
        X = pd.DataFrame([row], columns=cols)
        pred = float(model.predict(X)[0])
        require(pred == pred, 'prediction is NaN')
        require(pred > 0, f'prediction must be positive, got {pred}')
        # Model M's documented inverse: predict() MUST equal exp(inner) * area.
        import math
        inner = getattr(model, 'regressor_', None)
        require(inner is not None, 'wrapper exposes no fitted regressor_')
        manual = math.exp(float(inner.predict(X)[0])) * 100.0
        require(abs(manual - pred) <= max(1e-9, 1e-9 * abs(pred)),
                f'wrapper does not apply exp(pred)*area: predict() {pred} != {manual}')
        return (f'manifest-ordered frame of {len(cols)} features predicts {pred:.4f} t '
                f'(Rice @ 100 ha); equals exp(inner)*area exactly')

    check('a manifest-ordered feature frame predicts a sane value', predicts_in_manifest_order)


# --------------------------------------------------------------------------
# 4 & 5. API contract + quantum API guards (live server)
# --------------------------------------------------------------------------
def _yield_payload(area=100.0, **extra):
    payload = {'crop': 'Rice', 'area_hectares': area}
    payload.update(extra)
    return payload


def guard_api(server, m):
    group('4. API contract guard')
    base = server.base

    def seasonless():
        status, body = _request('POST', f'{base}/api/yield-prediction', _yield_payload())
        require(status == 200, f'season-less payload returned HTTP {status}: {str(body)[:200]}')
        _require_result_shape(body)
        return f'HTTP 200, classical={body["result"]["classical"]}'

    check('POST {crop, area_hectares} succeeds with Season absent', seasonless)

    def no_500_without_season():
        status, body = _request('POST', f'{base}/api/yield-prediction',
                               {'crop': 'Rice', 'area_hectares': 100.0})
        require(status != 400, 'Season is being required again (HTTP 400 without it)')
        require(status == 200, f'unexpected HTTP {status} without Season')
        return 'Season is NOT required'

    check('Season is not required', no_500_without_season)

    def season_ignored():
        s1, b1 = _request('POST', f'{base}/api/yield-prediction', _yield_payload())
        s2, b2 = _request('POST', f'{base}/api/yield-prediction', _yield_payload(season='Rabi'))
        require(s1 == 200 and s2 == 200, f'statuses {s1}/{s2}')
        for key in ('classical', 'quantum'):
            require(b1['result'].get(key) == b2['result'].get(key),
                    f'season changed {key}: {b1["result"].get(key)} vs {b2["result"].get(key)}')
        require(b1['result'].get('ensemble') == b2['result'].get('ensemble'),
                'season changed the ensemble figure')
        note = str(b2['result'].get('error') or '')
        require('deprecat' in note.lower(), 'no deprecation note returned when season is supplied')
        return 'season supplied -> identical prediction, only a deprecation note differs'

    check('a supplied Season remains ignored and does not alter the prediction', season_ignored)

    def headline_is_classical():
        status, body = _request('POST', f'{base}/api/yield-prediction', _yield_payload())
        require(status == 200, f'HTTP {status}')
        res = body['result']
        require(res['ensemble'] == res['classical'],
                f'ensemble ({res["ensemble"]}) is no longer the classical figure '
                f'({res["classical"]}) — quantum must not be averaged into the headline')
        require(isinstance(res['classical'], (int, float)) and res['classical'] > 0,
                'classical is not a positive number')
        require(res['units'] == 'tonnes per hectare', f'units drifted: {res.get("units")}')
        return f'ensemble == classical == {res["classical"]} t/ha'

    check('classical RF remains the user-facing headline (ensemble == classical)', headline_is_classical)

    def contract_block_matches_manifest():
        status, body = _request('POST', f'{base}/api/yield-prediction', _yield_payload())
        require(status == 200, f'HTTP {status}')
        contract = body.get('contract')
        require(isinstance(contract, dict), 'response has no contract block')
        require(contract.get('inputs') == PINNED['input_schema'],
                f'API input_schema drifted: {contract.get("inputs")}')
        require(contract.get('season_required') is False, 'API now requires Season')
        require(contract.get('season_deprecated') is True, 'API season_deprecated flag drifted')
        require(contract.get('dataset_synthetic') is False, 'API reports yield as synthetic')
        require(contract.get('dataset') == PINNED['dataset'],
                f'API dataset drifted: {contract.get("dataset")}')
        prov = str(contract.get('dataset_provenance') or '')
        require('ICRISAT' in prov, f'API provenance no longer names ICRISAT: {prov!r}')
        api_crops = contract.get('crops')
        require(api_crops == m['crop_options'],
                'API crop vocabulary no longer matches the manifest (order/contents)')
        require(body.get('crops') == m['crop_options'], 'top-level crops no longer match the manifest')
        return 'contract block == manifest (inputs, season flags, provenance, 22 crops)'

    check('API contract block matches the published manifest', contract_block_matches_manifest)


def _require_result_shape(body):
    require(isinstance(body, dict), 'response is not a JSON object')
    res = body.get('result')
    require(isinstance(res, dict), 'response has no result object')
    for key in ('classical', 'quantum', 'ensemble', 'quantum_available',
                'quantum_experimental', 'units'):
        require(key in res, f'result is missing the {key!r} key')
    require(isinstance(res['quantum_experimental'], bool), 'quantum_experimental must be a bool')
    require(res['quantum_experimental'] is (res['quantum'] is not None),
            'quantum_experimental no longer tracks whether a quantum value exists')
    if res['quantum'] is not None:
        note = str(res.get('quantum_note') or '')
        require('experimental' in note.lower(), 'quantum_note missing its experimental wording')


def guard_units_and_semantics(server):
    """The served figure is tonnes/hectare; total tonnes is labelled arithmetic."""
    group('4b. Units & area-semantics guard')
    base = server.base

    def labelled_units():
        status, body = _request('POST', f'{base}/api/yield-prediction', _yield_payload(area=4.0))
        require(status == 200, f'HTTP {status}')
        res = body['result']
        require(res.get('units') == 'tonnes per hectare', f'units drifted: {res.get("units")}')
        require(res.get('yield_per_hectare') == res.get('ensemble'),
                'yield_per_hectare no longer equals the reported per-hectare figure')
        require(res.get('total_units') == 'tonnes', f'total units missing/drifted: {res.get("total_units")}')
        expected = round(float(res['ensemble']) * 4.0, 2)
        require(abs(float(res['total_tonnes']) - expected) < 0.05,
                f'total_tonnes ({res["total_tonnes"]}) is not per-hectare x area ({expected})')
        return f't/ha={res["yield_per_hectare"]} x 4 ha = {res["total_tonnes"]} t (labelled)'

    check('per-hectare and total tonnes are reported separately and consistently', labelled_units)

    def district_basis_is_stated():
        status, body = _request('POST', f'{base}/api/yield-prediction', _yield_payload())
        require(status == 200, f'HTTP {status}')
        res = body['result']
        require(res.get('estimate_basis') == 'district_aggregate_annual_statistics',
                f'estimate_basis drifted: {res.get("estimate_basis")}')
        require(res.get('is_extrapolation') is True,
                'a district-average per-hectare figure applied to a field must be flagged '
                'as an extrapolation')
        require(res.get('caveats'), 'an extrapolated total must carry a caveat')
        require('district' in str(res.get('basis_description') or '').lower()
                or 'district' in str(res.get('semantics') or '').lower(),
                'the district-level basis is no longer described in the response')
        return 'district-level basis + extrapolation flag + caveat are reported'

    check('the response states the district-level basis and the extrapolation', district_basis_is_stated)

    def unknown_district_weather_is_not_invented():
        status, body = _request('GET', f'{base}/api/weather/NotARealDistrict')
        require(status == 200, f'HTTP {status}')
        require(isinstance(body, dict), 'weather response is not a JSON object')
        require(body.get('available') is False,
                'an unknown district must report available=False, not fabricated readings')
        for key in ('temp', 'hum', 'rain'):
            require(body.get(key) is None,
                    f'{key} was invented ({body.get(key)!r}) for an unknown district')
        return 'unknown district -> available=False with null values (no silent defaults)'

    check('unknown-district weather is not silently defaulted', unknown_district_weather_is_not_invented)

    def known_district_weather_is_labelled():
        status, body = _request('GET', f'{base}/api/weather/Mandya')
        require(status == 200, f'HTTP {status}')
        require(body.get('available') is True, 'a table entry must report available=True')
        require('not measurements' in str(body.get('source') or '')
                or 'indicative' in str(body.get('source') or ''),
                f'source label missing: {body.get("source")!r}')
        return f'Mandya reports source={body.get("source")!r}'

    check('table-backed weather values are labelled as indicative', known_district_weather_is_labelled)


def guard_experimental_contract(server):
    """The EXPERIMENTAL district-level endpoint, and its difference from the served one."""
    group('4c. Experimental district-contract guard')
    base = server.base
    url = f'{base}/api/yield-prediction/experimental'

    def artifact_present():
        require(os.path.exists(EXPERIMENTAL_MODEL), f'missing artifact: {EXPERIMENTAL_MODEL}')
        require(os.path.exists(EXPERIMENTAL_MANIFEST), f'missing manifest: {EXPERIMENTAL_MANIFEST}')
        return f'{os.path.basename(EXPERIMENTAL_MODEL)} + manifest present'

    check('experimental artifact and manifest exist', artifact_present)

    def contract_block():
        status, body = _request('GET', url)
        require(status == 200, f'GET returned HTTP {status}: {str(body)[:200]}')
        contract = body.get('contract') or {}
        require(contract.get('name') == 'experimental-district-yield-v1',
                f'contract name drifted: {contract.get("name")}')
        require(contract.get('inputs') == ['crop', 'district', 'area_hectares'],
                f'experimental inputs drifted: {contract.get("inputs")}')
        require(contract.get('level') == 'district', 'experimental level must be district')
        require(contract.get('is_field_level_prediction') is False,
                'a district-level estimate must never be labelled field-level')
        require(contract.get('area_is_a_model_feature') is False,
                'the area must not be a model feature in the experimental contract')
        require(contract.get('season_supported') is False, 'season must not be supported')
        require(contract.get('dataset_synthetic') is False,
                'the experimental yield dataset is real ICRISAT data')
        require('season' in (contract.get('unsupported_inputs') or {}),
                'the unsupported-inputs list must name season')
        return (f'inputs={contract["inputs"]} level={contract["level"]} '
                f'area_is_feature=False season_supported=False')

    check('GET advertises the experimental contract and its limits', contract_block)

    def post_roundtrip():
        status, body = _request('POST', url, {'crop': 'Rice', 'district': 'Bangalore',
                                             'area_hectares': 4.0})
        require(status == 200, f'HTTP {status}: {str(body)[:200]}')
        res = body.get('result') or {}
        require(res.get('units') == 'tonnes per hectare', f'units drifted: {res.get("units")}')
        require(res.get('total_units') == 'tonnes', 'total_units missing')
        require(res.get('level') == 'district', 'level drifted')
        require(res.get('is_field_level_prediction') is False, 'field-level claim leaked in')
        require(isinstance(res.get('yield_per_hectare'), (int, float)), 'no per-hectare figure')
        expected = float(res['yield_per_hectare']) * 4.0
        require(abs(float(res['total_tonnes']) - expected) < 0.05,
                f'total_tonnes ({res["total_tonnes"]}) != t/ha x area ({expected})')
        require(res.get('is_extrapolation') is True, 'extrapolation flag missing')
        require(res.get('caveats'), 'caveat missing')
        require(res.get('inputs_used') == ['crop', 'district'],
                f'inputs_used drifted: {res.get("inputs_used")}')
        require(res.get('inputs_ignored') == [], 'no input may be silently ignored')
        return f'Rice@Bangalore 4 ha = {res["total_tonnes"]} t ({res["yield_per_hectare"]} t/ha)'

    check('POST returns a labelled district-level estimate', post_roundtrip)

    def area_independence():
        s1, b1 = _request('POST', url, {'crop': 'Rice', 'district': 'Bangalore',
                                        'area_hectares': 0.5})
        s2, b2 = _request('POST', url, {'crop': 'Rice', 'district': 'Bangalore',
                                        'area_hectares': 5000.0})
        require(s1 == 200 and s2 == 200, f'statuses {s1}/{s2}')
        a = float(b1['result']['yield_per_hectare'])
        b = float(b2['result']['yield_per_hectare'])
        require(a == b,
                f'per-hectare estimate moved with the field area ({a} vs {b}) — the area is '
                f'a model feature again')
        ratio = float(b2['result']['total_tonnes']) / float(b1['result']['total_tonnes'])
        require(abs(ratio - 10000.0) < 1.0,
                f'total tonnes does not scale with area (ratio {ratio})')
        return f't/ha identical at 0.5 ha and 5000 ha ({a}); totals scale x{ratio:.0f}'

    check('the per-hectare estimate is independent of the requested area', area_independence)

    def rejects_unsupported():
        cases = [
            ({'crop': 'Rice', 'district': 'Bangalore', 'area_hectares': 2.0, 'season': 'Rabi'},
             'season', 400),
            ({'crop': 'Quinoa', 'district': 'Bangalore', 'area_hectares': 2.0}, 'crop', 400),
            ({'crop': 'Rice', 'district': 'Atlantis', 'area_hectares': 2.0}, 'district', 400),
            ({'crop': 'Rice', 'district': 'Bangalore'}, 'area_hectares', 400),
            ({'crop': 'Rice', 'district': 'Bangalore', 'area_hectares': 2.0, 'rainfall': 200},
             'rainfall', 400),
            ({'crop': 'Rice', 'district': 'Bangalore', 'area_hectares': -1}, 'greater than 0', 400),
        ]
        for payload, needle, expected in cases:
            status, body = _request('POST', url, payload)
            require(status == expected,
                    f'{payload} -> HTTP {status}, expected {expected}')
            text = str(body)
            require(needle.lower() in text.lower(),
                    f'{payload} error does not mention {needle!r}: {text[:200]}')
        return f'{len(cases)} unsupported/invalid payloads rejected with explicit messages'

    check('unsupported inputs are refused explicitly (never silently ignored)', rejects_unsupported)

    def served_contract_untouched():
        status, body = _request('POST', f'{base}/api/yield-prediction', _yield_payload())
        require(status == 200, f'HTTP {status}')
        contract = body['contract']
        require(contract.get('inputs') == PINNED['input_schema'],
                'the experimental work changed the SERVED input contract')
        require(contract.get('season_required') is False, 'served season_required drifted')
        require(contract.get('season_deprecated') is True, 'served season_deprecated drifted')
        return 'served contract still Crop + Area_Hectares with season deprecated'

    check('the served endpoint contract is unchanged by the experimental work',
          served_contract_untouched)


def guard_quantum_api(server):
    group('5. Quantum API guard')
    base = server.base

    def uses_area_hectares():
        payload = {'crop': 'Rice', 'nitrogen': 90, 'phosphorus': 42, 'potassium': 43,
                   'temperature': 25, 'humidity': 80, 'ph': 6.5, 'rainfall': 200,
                   'moisture': 12, 'weight': 35}
        s1, b1 = _request('POST', f'{base}/api/quantum-ml',
                          dict(payload, area_hectares=150.0))
        require(s1 == 200, f'HTTP {s1}: {str(b1)[:200]}')
        res = b1.get('result') or {}
        require('error' not in res, f'quantum-ml returned an error: {res.get("error")}')
        require('yield_xgb' in res, 'quantum-ml no longer reports the classical yield leg')
        s2, b2 = _request('POST', f'{base}/api/quantum-ml',
                          {k: v for k, v in payload.items() if k != 'area_hectares'} | {'area': 150.0})
        require(s2 == 200, f'legacy alias payload HTTP {s2}')
        require(b2.get('result', {}).get('yield_xgb') == res['yield_xgb'],
                'area_hectares and the legacy area alias disagree')
        return f'area_hectares honored (yield_xgb={res["yield_xgb"]}); legacy alias unchanged'

    check('POST /api/quantum-ml consumes area_hectares', uses_area_hectares)

    def quantum_not_headline():
        status, body = _request('POST', f'{base}/api/yield-prediction', _yield_payload())
        require(status == 200, f'HTTP {status}')
        res = body['result']
        require(res['ensemble'] == res['classical'],
                'quantum is influencing the headline prediction again')
        q = res.get('quantum')
        if q is None:
            return 'quantum unavailable -> headline is classical only'
        if abs(float(q) - float(res['classical'])) > 1e-9:
            require(res['ensemble'] == res['classical'],
                    'quantum differs from classical yet was averaged into the headline')
            return (f'quantum ({q}) excluded from the headline '
                    f'(classical={res["classical"]}, flagged experimental)')
        return 'quantum matches classical; headline remains classical'

    check('quantum remains experimental and never the headline', quantum_not_headline)

    def flags_preserved():
        status, body = _request('POST', f'{base}/api/yield-prediction', _yield_payload())
        require(status == 200, f'HTTP {status}')
        _require_result_shape(body)
        res = body['result']
        return (f'quantum_experimental={res["quantum_experimental"]}, '
                f'quantum_note={"present" if "quantum_note" in res else "absent (no quantum value)"}')

    check('quantum_experimental / quantum_note behavior preserved', flags_preserved)


# --------------------------------------------------------------------------
# 6. Provenance guard
# --------------------------------------------------------------------------
def guard_provenance():
    group('6. Provenance guard')
    registry = load_json(REGISTRY_PATH)
    require(isinstance(registry, list) and registry, 'registry is empty or malformed')
    # The registry is append-only, so the NEWEST run is the run of its last entry.
    # (Sorting run ids would silently inspect an older run if ids were ever renamed.)
    require(registry[-1].get('run_id'), 'last registry entry carries no run_id')
    latest = registry[-1]['run_id']
    entries = [e for e in registry if e.get('run_id') == latest]

    def yield_provenance():
        yield_entries = [e for e in entries if e.get('domain') == 'yield']
        require(yield_entries, f'latest run {latest} has no yield entries')
        for e in yield_entries:
            prov = str(e.get('dataset_provenance') or '')
            for needle in PINNED['provenance_must_contain']:
                require(needle in prov,
                        f'{e.get("model_name")} provenance no longer names {needle}: {prov!r}')
            require(e.get('dataset_synthetic') is False,
                    f'{e.get("model_name")} reports dataset_synthetic={e.get("dataset_synthetic")} '
                    f'(yield must be real/provided)')
            require(str(e.get('target') or '').startswith('Yield_Tonnes'),
                    f'{e.get("model_name")} target drifted: {e.get("target")}')
        return f'{len(yield_entries)} yield entries in {latest} are ICRISAT-sourced, dataset_synthetic=False'

    check('latest-run yield entries identify ICRISAT and are not synthetic', yield_provenance)

    def seed_still_synthetic():
        seed_entries = [e for e in entries if e.get('domain') == 'seed']
        require(seed_entries, 'latest run has no seed entries')
        for e in seed_entries:
            prov = str(e.get('dataset_provenance') or '')
            require('synthetic' in prov.lower(),
                    f'{e.get("model_name")} provenance no longer marks seed as synthetic: {prov!r}')
            require(e.get('dataset_synthetic') is True,
                    f'{e.get("model_name")} reports dataset_synthetic={e.get("dataset_synthetic")} '
                    f'— synthetic seed data must not be reported as real')
        return f'{len(seed_entries)} seed entries still flagged synthetic-generated (not real)'

    check('seed data is still reported as synthetic, never as real', seed_still_synthetic)

    def meta_composition():
        meta = [e for e in entries if e.get('domain') == 'meta']
        require(meta, 'latest run has no meta entry')
        entry = meta[-1]
        comp = entry.get('dataset_composition')
        require(isinstance(comp, dict), 'meta entry has no dataset_composition block')
        require(comp.get('yield', {}).get('synthetic') is False,
                f'meta reports the yield leg as synthetic: {comp.get("yield")}')
        require(comp.get('crop', {}).get('synthetic') is False,
                f'meta reports the crop leg as synthetic: {comp.get("crop")}')
        require(comp.get('seed', {}).get('synthetic') is True,
                f'meta reports the seed leg as real: {comp.get("seed")}')
        require('ICRISAT' in str(comp.get('yield', {}).get('provenance') or ''),
                'meta composition no longer names ICRISAT for the yield leg')
        return 'meta composition: crop=real, yield=ICRISAT/real, seed=synthetic'

    check('meta composite provenance is intact (only the seed leg synthetic)', meta_composition)

    def target_unchanged():
        meta = [e for e in entries if e.get('domain') == 'meta'][-1]
        target = str(meta.get('target') or '')
        require('three user-facing classical outputs correct' in target,
                f'meta target drifted: {target!r}')
        return f'meta target pinned: {target!r}'

    check('meta target is unchanged', target_unchanged)


# --------------------------------------------------------------------------
# 7. Dataset immutability guard
# --------------------------------------------------------------------------
def guard_immutability(before):
    group('7. Dataset immutability guard')
    after = snapshot_tree(DATA_DIR, MODELS_DIR)
    changed, added, removed = [], [], []
    for path, sig in before.items():
        if path not in after:
            removed.append(path)
        elif after[path] != sig:
            changed.append(path)
    for path in after:
        if path not in before:
            added.append(path)

    def nothing_changed():
        require(not changed, f'modified DURING the guard run: {changed}')
        require(not removed, f'deleted DURING the guard run: {removed}')
        require(not added, f'created DURING the guard run: {added}')
        return (f'{len(before)} files under {DATA_DIR}/ and {MODELS_DIR}/ byte-identical, '
                f'0 modified / 0 added / 0 removed during the run')

    check('no dataset or model file changed while the guard ran (read-only)', nothing_changed)

    def source_and_derived_untouched():
        require(sha256(ICRISAT_SOURCE) == before[ICRISAT_SOURCE][0],
                'the source ICRISAT dataset was modified')
        require(sha256(DERIVED_YIELD) == before[DERIVED_YIELD][0],
                'the derived ICRISAT yield dataset was modified')
        return 'source + derived ICRISAT datasets unmodified'

    check('source and derived ICRISAT datasets are unmodified', source_and_derived_untouched)

    def preprocessing_routes_to_real_data():
        with open(PREPROCESSING_PATH, 'r', encoding='utf-8') as fh:
            src = fh.read()
        require('yield_icrisat_karnataka.csv' in src,
                'data_preprocessing.py no longer routes yield to the ICRISAT-derived table')
        active = re.search(r"['\"]yield['\"]\s*:\s*['\"]([^'\"]+)['\"]", src)
        require(active and active.group(1) == os.path.basename(DERIVED_YIELD),
                f'active yield table drifted: {active.group(1) if active else None}')
        require(os.path.basename(LEGACY_SYNTHETIC_YIELD) in src,
                'the legacy synthetic fallback disappeared (compatibility note lost)')
        return f'canonical yield == {os.path.basename(DERIVED_YIELD)} (synthetic file only a fallback)'

    check('preprocessing still selects the real dataset, not the synthetic fallback',
          preprocessing_routes_to_real_data)


# --------------------------------------------------------------------------
# 8. Android contract guard
# --------------------------------------------------------------------------
def guard_android():
    group('8. Android contract guard')
    require(os.path.isdir(MOBILE_APP_DIR), f'mobile app directory not found: {MOBILE_APP_DIR}')

    def yield_payload():
        with open(MOBILE_YIELD_AI, 'r', encoding='utf-8') as fh:
            src = fh.read()
        require('/api/yield-prediction' in src, 'yield-ai.tsx no longer calls /api/yield-prediction')
        body = re.search(r'body:\s*\{(.*?)\}', src, re.DOTALL)
        require(body, 'could not locate the request body literal in yield-ai.tsx')
        literal = body.group(1)
        require('area_hectares' in literal, 'Android yield payload no longer sends area_hectares')
        require(re.search(r'\bcrop\b', literal), 'Android yield payload no longer sends crop')
        require('season' not in literal.lower(),
                'Android yield payload sends season, which must remain a local-only label')
        return 'yield-ai.tsx posts {crop, area_hectares} with no season field'

    check('Android yield payload is still {crop, area_hectares}', yield_payload)

    def quantum_payload():
        with open(MOBILE_QUANTUM, 'r', encoding='utf-8') as fh:
            src = fh.read()
        require('/api/quantum-ml' in src, 'quantum.tsx no longer calls /api/quantum-ml')
        require(re.search(r'form\.append\(\s*["\']area_hectares["\']', src),
                'quantum.tsx no longer sends area_hectares')
        require(re.search(r'form\.append\(\s*["\']crop["\']', src),
                'quantum.tsx no longer sends crop')
        sent_season = re.search(r'^\s*form\.append\(\s*["\']season["\']', src, re.MULTILINE)
        require(not sent_season, 'quantum.tsx sends a season field again')
        return 'quantum.tsx sends area_hectares + crop, no season'

    check('Android quantum payload uses area_hectares and sends no season', quantum_payload)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    print('=' * 72)
    print('SEEDIQ YIELD CONTRACT DRIFT GUARD')
    print('ICRISAT dataset -> preprocessing -> 23-feature manifest -> yield RF')
    print('                     -> Flask yield API -> Android payload')
    print('=' * 72)

    try:
        import pandas as pd  # noqa: PLC0415 - guard needs the project's pandas
    except ImportError as exc:
        print(f'\n[FATAL] pandas is required to run this guard: {exc}')
        return 1

    before = snapshot_tree(DATA_DIR, MODELS_DIR)

    guard_dataset(pd)
    manifest = guard_manifest(pd)
    guard_model(manifest, pd)
    guard_provenance()

    port = free_port()
    server = None
    try:
        print(f'\n\033[1mStarting Flask on 127.0.0.1:{port} for live API guards...\033[0m')
        server = Server(port).__enter__()
        print('  server ready')
        guard_api(server, manifest)
        guard_units_and_semantics(server)
        guard_experimental_contract(server)
        guard_quantum_api(server)
    except Exception as exc:  # noqa: BLE001 - server failure must fail the run loudly
        _RESULTS.append(('FAIL', 'API guards: server', str(exc) or type(exc).__name__))
        print(f'  [FAIL] API guards could not run: {type(exc).__name__}: {exc}')
    finally:
        if server is not None:
            server.__exit__(None, None, None)
            print('  server stopped')

    guard_immutability(before)
    guard_android()

    passed = sum(1 for r in _RESULTS if r[0] == 'PASS')
    failed = [r for r in _RESULTS if r[0] == 'FAIL']
    print('\n' + '=' * 72)
    print(f'SUMMARY: {passed}/{len(_RESULTS)} contract checks passed')
    if failed:
        print('\nDRIFT DETECTED:')
        for _, name, detail in failed:
            print(f'  - {name}\n      {detail}')
    print('=' * 72)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
