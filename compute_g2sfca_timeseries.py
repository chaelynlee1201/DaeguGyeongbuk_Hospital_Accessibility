"""
2026년 7~8월 평일 42일 각각에 대해 Gaussian 2SFCA 접근성을 계산한다(시계열).

목적: 하루치가 아니라 평일 42일 분포를 만들어, 격자별 접근성 점수의
5/50/95 분위 지도를 산출하기 위한 "날짜별 원자료"를 생성한다.
(분위 집계·시각화는 aggregate_g2sfca_timeseries.py에서 별도로 수행.)

방법론(기존 g2sfca 노트북과 동일, 추가 스케일 상수 없음):
  Gaussian 거리조락  g(t) = (exp(-0.5(t/d0)^2) - exp(-0.5)) / (1 - exp(-0.5)),  t>d0 이면 0
  Step1(시설별)   R_j = N_DOCTOR_j / Σ_i ( TOT_POP_i * g(t_시설→격자) )
  Step2(격자별)   A_i = Σ_j ( R_j * g(t_격자→시설) )
  d0 = 60분, 출발 매일 09:00, departure_time_window = 3시간
  * 방향별 통행시간 분리: Step1은 시설→격자(f2g), Step2는 격자→시설(g2f)

데이터:
  GTFS   : NAS /mnt/cowork/Daegyung_GTFS_Scrapping/gtfs 에서 날짜별 zip 자동 탐색
  OSM    : data/raw_gtfs_network/daegyeong.osm.pbf
  공급   : data/medical_facilities_filtered (대상 20km 버퍼 내 N_DOCTOR>0)
  수요   : data/grid_1km_population_daegugyeongbuk (TOT_POP>0)

실행(서버, 백그라운드 권장):
  conda activate r5py
  nohup python compute_g2sfca_timeseries.py > g2sfca_ts.log 2>&1 &
  # 또는 tmux 안에서 실행. 중단돼도 재실행하면 끝난 날짜는 건너뛴다(체크포인트).
"""
import os
import gc
import io
import glob
import zipfile
import datetime
import time

import numpy as np
import geopandas as gpd
import pandas as pd
import r5py

# ── 설정 ────────────────────────────────────────────────────────────────────
# r5py는 JDK가 필요하다. conda(r5py 환경)를 activate 하면 JAVA_HOME이 자동 설정되므로
# 여기서 하드코딩하지 않는다. 필요한 경우에만 아래 주석을 풀어 환경변수를 지정한다.
# os.environ["JAVA_HOME"] = "/path/to/jdk"

GTFS_DIR = "/mnt/cowork/Daegyung_GTFS_Scrapping/gtfs"
OSM_PBF = "data/raw_gtfs_network/daegyeong.osm.pbf"
FAC_SHP = "data/medical_facilities_filtered/medical_facilities_filtered.shp"
GRID_SHP = "data/grid_1km_population_daegugyeongbuk/grid_1km_population_daegugyeongbuk.shp"
SIGUNGU_SHP = "data/BND_SIGUNGU_PG/BND_SIGUNGU_PG.shp"

OUT_DIR = "data/g2sfca_timeseries"
PERDATE_DIR = f"{OUT_DIR}/perdate"
GTFS_CLEAN_DIR = f"{OUT_DIR}/gtfs_clean"  # 참조 무결성 정제한 GTFS 복사본 캐시

TRVL_TIME = 60          # Gaussian 임계 통행시간 d0 (분)
DEPART_HOUR = 9         # 매일 출발 시각(09:00 오전 첨두)
DEPART_WINDOW_H = 3     # departure_time_window (시간)
MAX_TIME_MIN = 60       # 60분 초과(도달불가) 쌍은 반환되지 않음 → sparse
WALK_SPEED = 4.5
MAX_WALK_MIN = 15
MAX_RIDES = 5
CHUNK_SIZE = 1500       # origin 청크 크기(메모리 제한)
BUFFER_KM = 20

# 대상 지역 17개 행정경계(대구·경북 10개 시·군·구) 코드
TARGET_CODES = [
    "22010", "22020", "22030", "22040", "22050", "22060", "22070", "22510", "22520",
    "37050", "37030", "37070", "37100", "37560", "37570", "37580", "37590",
]

# 2026년 7~8월 평일 42일 (공휴일 제외: 7/17 제헌절, 8/15 광복절(토), 8/17 대체공휴일)
DATES = [
    "20260701", "20260702", "20260703", "20260706", "20260707", "20260708", "20260709",
    "20260710", "20260713", "20260714", "20260715", "20260716", "20260720", "20260721",
    "20260722", "20260723", "20260724", "20260727", "20260728", "20260729", "20260730",
    "20260731", "20260803", "20260804", "20260805", "20260806", "20260807", "20260810",
    "20260811", "20260812", "20260813", "20260814", "20260818", "20260819", "20260820",
    "20260821", "20260824", "20260825", "20260826", "20260827", "20260828", "20260831",
]


def log(msg):
    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def gaussian(dij, d0):
    """Gaussian distance decay (dij: Series, d0: 스칼라). t>d0 이면 0."""
    val = (np.exp(-0.5 * (dij / d0) ** 2) - np.exp(-0.5)) / (1 - np.exp(-0.5))
    return val.where(dij <= d0, 0.0)


def find_gtfs(date):
    """NAS에서 해당 날짜 문자열을 포함하는 GTFS zip을 탐색(중첩 폴더 허용)."""
    hits = sorted(glob.glob(f"{GTFS_DIR}/**/*{date}*.zip", recursive=True))
    return hits[0] if hits else None


def _read_zip_csv(zf, name):
    if name not in zf.namelist():
        return None
    with zf.open(name) as fh:
        return pd.read_csv(fh, dtype=str, keep_default_na=False)


def clean_gtfs(src_zip, date):
    """GTFS의 깨진 참조(dangling reference)를 제거한 복사본을 만들어 경로를 반환.
    R5는 참조 무결성을 엄격히 검사하므로, 존재하지 않는 route/service/stop/trip을
    가리키는 레코드를 연쇄적으로 솎아낸다. 결과는 GTFS_CLEAN_DIR에 캐시한다.
    (NAS 원본은 수정하지 않음.)"""
    os.makedirs(GTFS_CLEAN_DIR, exist_ok=True)
    # r5py는 입력 파일을 basename 기준으로 캐시(심볼릭 링크)하므로, 원본과 반드시
    # 다른 파일명을 써야 원본 캐시와 충돌하지 않는다 → '_clean' 접미사 필수.
    out_zip = f"{GTFS_CLEAN_DIR}/daegyung_gtfs_{date}_clean.zip"
    if os.path.exists(out_zip):
        return out_zip

    with zipfile.ZipFile(src_zip) as zf:
        tables = {n: _read_zip_csv(zf, n) for n in zf.namelist() if n.endswith(".txt")}

    routes = tables.get("routes.txt")
    trips = tables.get("trips.txt")
    stop_times = tables.get("stop_times.txt")
    stops = tables.get("stops.txt")
    calendar = tables.get("calendar.txt")
    caldates = tables.get("calendar_dates.txt")
    agency = tables.get("agency.txt")

    service_ids = set()
    if calendar is not None and "service_id" in calendar:
        service_ids |= set(calendar["service_id"])
    if caldates is not None and "service_id" in caldates:
        service_ids |= set(caldates["service_id"])
    stop_ids = set(stops["stop_id"]) if stops is not None else set()

    removed = {}

    # routes → agency
    if routes is not None and agency is not None and "agency_id" in routes.columns and "agency_id" in agency.columns:
        aset = set(agency["agency_id"])
        before = len(routes)
        routes = routes[routes["agency_id"].isin(aset)]
        removed["routes"] = before - len(routes)
        tables["routes.txt"] = routes
    route_ids = set(routes["route_id"]) if routes is not None else set()

    # trips → routes, service
    if trips is not None:
        before = len(trips)
        if route_ids:
            trips = trips[trips["route_id"].isin(route_ids)]
        if service_ids:
            trips = trips[trips["service_id"].isin(service_ids)]
        removed["trips"] = before - len(trips)
        tables["trips.txt"] = trips
    trip_ids = set(trips["trip_id"]) if trips is not None else set()

    # stop_times → trips, stops
    if stop_times is not None:
        before = len(stop_times)
        stop_times = stop_times[stop_times["trip_id"].isin(trip_ids)]
        if stop_ids:
            stop_times = stop_times[stop_times["stop_id"].isin(stop_ids)]
        removed["stop_times"] = before - len(stop_times)
        tables["stop_times.txt"] = stop_times

        # 정류장 2개 미만 trip 제거(운행 불가) 후 stop_times 재정합
        cnt = stop_times.groupby("trip_id").size()
        valid = set(cnt[cnt >= 2].index)
        if trips is not None:
            before = len(trips)
            trips = trips[trips["trip_id"].isin(valid)]
            removed["trips_lt2stops"] = before - len(trips)
            tables["trips.txt"] = trips
            trip_ids = set(trips["trip_id"])
            stop_times = stop_times[stop_times["trip_id"].isin(trip_ids)]
            tables["stop_times.txt"] = stop_times

    # frequencies → trips
    freq = tables.get("frequencies.txt")
    if freq is not None and "trip_id" in freq.columns:
        tables["frequencies.txt"] = freq[freq["trip_id"].isin(trip_ids)]

    # transfers → stops
    tr = tables.get("transfers.txt")
    if tr is not None and stop_ids:
        for c in ("from_stop_id", "to_stop_id"):
            if c in tr.columns:
                tr = tr[tr[c].isin(stop_ids)]
        tables["transfers.txt"] = tr

    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zo:
        for name, df in tables.items():
            if df is None:
                continue
            buf = io.StringIO()
            df.to_csv(buf, index=False)
            zo.writestr(name, buf.getvalue())

    removed = {k: v for k, v in removed.items() if v}
    log(f"  GTFS 정제: 제거 {removed if removed else '없음'} → {os.path.basename(out_zip)}")
    return out_zip


def compute_ttm(net, origins, destinations, departure):
    """origin을 청크로 나눠 TTM 계산 후, 60분 이내(sparse) 결과만 concat해 반환.
    반환 컬럼: FROM_ID, TO_ID, TT_MIN."""
    parts = []
    n = len(origins)
    for s in range(0, n, CHUNK_SIZE):
        chunk = origins.iloc[s:s + CHUNK_SIZE]
        ttm = r5py.TravelTimeMatrix(
            net,
            origins=chunk[["id", "geometry"]],
            destinations=destinations[["id", "geometry"]],
            departure=departure,
            departure_time_window=datetime.timedelta(hours=DEPART_WINDOW_H),
            transport_modes=[r5py.TransportMode.TRANSIT, r5py.TransportMode.WALK],
            speed_walking=WALK_SPEED,
            max_time=datetime.timedelta(minutes=MAX_TIME_MIN),
            max_time_walking=datetime.timedelta(minutes=MAX_WALK_MIN),
            max_public_transport_rides=MAX_RIDES,
        )
        ttm = ttm.rename(
            columns={"from_id": "FROM_ID", "to_id": "TO_ID", "travel_time": "TT_MIN"}
        ).dropna(subset=["TT_MIN"])
        parts.append(ttm[["FROM_ID", "TO_ID", "TT_MIN"]])
    return pd.concat(parts, ignore_index=True)


def build_supply_demand():
    """공급(시설)·수요(격자) 레퍼런스를 1회 구축하고 OUT_DIR에 저장(모든 날짜 공통 ID 유지)."""
    os.makedirs(PERDATE_DIR, exist_ok=True)
    supply_path = f"{OUT_DIR}/supply_ref.gpkg"
    demand_path = f"{OUT_DIR}/demand_ref.gpkg"

    if os.path.exists(supply_path) and os.path.exists(demand_path):
        supply = gpd.read_file(supply_path).set_index("id")
        demand = gpd.read_file(demand_path).set_index("GRID_CD")
        supply.index = supply.index.astype(str)
        demand.index = demand.index.astype(str)
        log(f"레퍼런스 로드: 공급 {len(supply)}개, 수요 {len(demand)}개")
        return supply, demand

    # 수요: 인구>0 격자
    grid = gpd.read_file(GRID_SHP)
    demand = grid[grid["TOT_POP"] > 0].copy().reset_index(drop=True).set_index("GRID_CD")
    demand.index = demand.index.astype(str)

    # 공급: 대상 20km 버퍼 내 & 의사수>0 시설 (파일 순서 기반 안정적 ID 부여)
    fac = gpd.read_file(FAC_SHP, encoding="cp949")
    sigungu = gpd.read_file(SIGUNGU_SHP, encoding="cp949")
    target = sigungu[sigungu["SIGUNGU_CD"].isin(TARGET_CODES)].to_crs("EPSG:5179").union_all()
    buf = target.buffer(BUFFER_KM * 1000)
    fac5179 = fac.to_crs("EPSG:5179")
    fac = fac[fac5179.intersects(buf).values].copy()
    fac = fac[fac["N_DOCTOR"] > 0].copy().reset_index(drop=True)
    fac["id"] = "F" + fac.index.astype(str)
    keep = [c for c in ["id", "FAC_NM", "FAC_TYPE", "N_DOCTOR", "geometry"] if c in fac.columns]
    supply = fac[keep].set_index("id")

    supply.reset_index().to_file(supply_path, driver="GPKG")
    demand.reset_index().to_file(demand_path, driver="GPKG")
    log(f"레퍼런스 구축·저장: 공급 {len(supply)}개(의사수 합 {supply['N_DOCTOR'].sum():,}), "
        f"수요 {len(demand)}개(인구 합 {int(demand['TOT_POP'].sum()):,})")
    return supply, demand


def to_points_4326(gdf, id_col):
    """포인트/격자중심점을 EPSG:4326 (id, geometry)로 변환."""
    g = gdf.copy()
    if g.geometry.geom_type.iloc[0] != "Point":
        g["geometry"] = g.geometry.centroid           # 네이티브 CRS에서 중심점
    g = g.to_crs("EPSG:4326")
    out = g.reset_index()[[id_col, "geometry"]].rename(columns={id_col: "id"})
    out["id"] = out["id"].astype(str)
    return out


def process_date(date, net, fac_pts, grid_pts, supply, demand):
    """하루치 Step1(시설)·Step2(격자) 계산 후 체크포인트 CSV 저장."""
    departure = datetime.datetime(int(date[:4]), int(date[4:6]), int(date[6:8]), DEPART_HOUR, 0, 0)

    # Step1: 시설→격자 (공급 대비 수요)
    f2g = compute_ttm(net, fac_pts, grid_pts, departure)          # FROM=FAC, TO=GRID
    f2g = f2g.merge(demand[["TOT_POP"]], left_on="TO_ID", right_index=True)
    f2g["w"] = f2g["TOT_POP"] * gaussian(f2g["TT_MIN"], TRVL_TIME)
    catchment = f2g.groupby("FROM_ID")["w"].sum().reindex(supply.index).fillna(0.0)
    step1 = pd.Series(0.0, index=supply.index, name="step1")
    m = catchment > 0
    step1.loc[m] = supply.loc[m, "N_DOCTOR"] / catchment.loc[m]

    # Step2: 격자→시설 (R_j 합산)
    g2f = compute_ttm(net, grid_pts, fac_pts, departure)          # FROM=GRID, TO=FAC
    g2f = g2f.merge(step1.rename("step1"), left_on="TO_ID", right_index=True)
    g2f["w"] = g2f["step1"] * gaussian(g2f["TT_MIN"], TRVL_TIME)
    step2 = g2f.groupby("FROM_ID")["w"].sum().reindex(demand.index).fillna(0.0)

    # 저장(모든 시설/격자를 포함, 도달 없음=0)
    step1.rename("step1").reset_index().rename(columns={"index": "FAC_ID", "id": "FAC_ID"}).to_csv(
        f"{PERDATE_DIR}/step1_{date}.csv", index=False)
    step2.rename("G2SFCA").reset_index().rename(columns={"FROM_ID": "GRID_CD"}).to_csv(
        f"{PERDATE_DIR}/step2_{date}.csv", index=False)

    n_zero = int((step2 == 0).sum())
    log(f"  {date}: Step1 max={step1.max():.3f}, Step2 max={step2.max():.3f}, "
        f"접근성0 격자 {n_zero}/{len(step2)}")


def main():
    t0 = time.time()
    os.makedirs(PERDATE_DIR, exist_ok=True)
    supply, demand = build_supply_demand()

    # origin/destination 포인트(4326)는 날짜 무관하게 동일 → 1회 준비
    fac_pts = to_points_4326(supply, "id")
    grid_pts = to_points_4326(demand, "GRID_CD")
    log(f"origin/destination 준비 완료: 시설 {len(fac_pts)}, 격자 {len(grid_pts)}")

    todo = [d for d in DATES
            if not (os.path.exists(f"{PERDATE_DIR}/step1_{d}.csv")
                    and os.path.exists(f"{PERDATE_DIR}/step2_{d}.csv"))]
    log(f"대상 {len(DATES)}일 중 미완료 {len(todo)}일 처리 시작")

    for k, date in enumerate(todo, 1):
        gtfs = find_gtfs(date)
        if gtfs is None:
            log(f"  [경고] {date} GTFS를 NAS에서 못 찾음 → 건너뜀")
            continue

        t_day = time.time()
        log(f"[{k}/{len(todo)}] {date} 네트워크 구축 ({os.path.basename(gtfs)})")
        gtfs_clean = clean_gtfs(gtfs, date)  # 깨진 참조 정제한 복사본 사용
        net = r5py.TransportNetwork(OSM_PBF, [gtfs_clean])
        process_date(date, net, fac_pts, grid_pts, supply, demand)

        del net
        gc.collect()

        elapsed = time.time() - t0
        rate = k / elapsed
        remain = (len(todo) - k) / rate if rate > 0 else float("nan")
        log(f"  완료 ({time.time()-t_day:.0f}s) | 누적 {k}/{len(todo)} | 예상 잔여 {remain/60:.0f}분")

    log(f"전체 완료: {time.time()-t0:.0f}s. 다음: aggregate_g2sfca_timeseries.py 실행")


if __name__ == "__main__":
    main()
