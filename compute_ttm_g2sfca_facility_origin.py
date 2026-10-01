"""
r5py TravelTimeMatrix을 이용해 의료시설 → 1km 인구 격자 방향(시설이 origin)의 대중교통
통행시간을 계산한다. Gaussian 2SFCA Step1(공급 대비 수요 비율)의 mobility 입력으로 쓴다.

GTFS 스케줄 기반 대중교통망에서는 A→B와 B→A 통행시간이 다를 수 있어(경로/배차 비대칭),
compute_ttm_g2sfca.py에서 이미 계산해 둔 격자→시설 방향(Step2용)과는 별도로
시설→격자 방향을 새로 계산한다.

출발일시: 2026-08-14(금) 09:00:00, departure_time_window=3시간 — compute_ttm_g2sfca.py와 동일
Origin: 대상 지역(17개 시군구) 경계 20km 버퍼 내 의료시설(총의사수>0, 3,487개)
Destination: 1km 인구 격자 중 총인구수>0 (4,987개)

max_time=60분으로 제한해 60분 초과(도달불가) 쌍은 결과에서 자동으로 제외된다.
"""
import os

os.environ["JAVA_HOME"] = "/Users/chaelyn/miniforge3/envs/jdk21/lib/jvm"

import datetime
import time

import geopandas as gpd
import pandas as pd
import r5py

CHUNK_SIZE = 1500
OUT_DIR = "data/g2sfca_20260814_0900"
OUT_CSV = f"{OUT_DIR}/mobility_facility_to_grid.csv"
BUFFER_KM = 20

os.makedirs(OUT_DIR, exist_ok=True)


def log(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


t0 = time.time()

grid = gpd.read_file("data/grid_1km_population_daegugyeongbuk/grid_1km_population_daegugyeongbuk.shp")
grid = grid[grid["TOT_POP"] > 0].copy()

fac = gpd.read_file(
    "data/medical_facilities_filtered/medical_facilities_filtered.shp", encoding="cp949"
)
sigungu = gpd.read_file("data/BND_SIGUNGU_PG/BND_SIGUNGU_PG.shp", encoding="cp949")
target_codes = [
    "22010", "22020", "22030", "22040", "22050", "22060", "22070", "22510", "22520",
    "37050", "37030", "37070", "37100", "37560", "37570", "37580", "37590",
]
target_union_5179 = sigungu[sigungu["SIGUNGU_CD"].isin(target_codes)].to_crs("EPSG:5179").union_all()
buf = target_union_5179.buffer(BUFFER_KM * 1000)
fac = fac[fac.intersects(buf)].copy()

origins = fac.to_crs("EPSG:4326").copy().reset_index(drop=True)
origins["id"] = "F" + origins.index.astype(str)
# facilities_supply.gpkg(compute_ttm_g2sfca.py 산출물)와 동일한 시설 순서/ID 매핑을 그대로 재현
origins = origins[["id", "geometry"]]

destinations = grid.copy()
destinations["geometry"] = destinations.geometry.centroid
destinations = destinations.to_crs("EPSG:4326")
destinations = destinations.rename(columns={"GRID_CD": "id"})[["id", "geometry"]]

log(f"origins(의료시설, 버퍼 {BUFFER_KM}km): {len(origins)}, destinations(1km 격자, 인구>0): {len(destinations)}")

net = r5py.TransportNetwork(
    "data/raw_gtfs_network/daegyeong.osm.pbf",
    ["data/raw_gtfs_network/daegyung_gtfs_20260814.zip"],
)
log(f"network built ({time.time()-t0:.1f}s)")

DEPARTURE = datetime.datetime(2026, 8, 14, 9, 0, 0)
DEPARTURE_WINDOW = datetime.timedelta(hours=3)

n_chunks = (len(origins) + CHUNK_SIZE - 1) // CHUNK_SIZE
results = []

done_ids = set()
if os.path.exists(OUT_CSV):
    prev = pd.read_csv(OUT_CSV)
    results.append(prev)
    done_ids = set(prev["FAC_ID"])
    log(f"기존 결과 {len(prev)}행({len(done_ids)}개 origin) 로드, 이어서 진행")

t_start = time.time()
for i in range(n_chunks):
    chunk = origins.iloc[i * CHUNK_SIZE:(i + 1) * CHUNK_SIZE]
    chunk = chunk[~chunk["id"].isin(done_ids)]
    if chunk.empty:
        continue

    t_chunk = time.time()
    ttm = r5py.TravelTimeMatrix(
        net,
        origins=chunk[["id", "geometry"]],
        destinations=destinations,
        departure=DEPARTURE,
        departure_time_window=DEPARTURE_WINDOW,
        transport_modes=[r5py.TransportMode.TRANSIT, r5py.TransportMode.WALK],
        speed_walking=4.5,
        max_time=datetime.timedelta(minutes=60),
        max_time_walking=datetime.timedelta(minutes=15),
        max_public_transport_rides=5,
    )
    ttm = ttm.rename(columns={"from_id": "FAC_ID", "to_id": "GRID_ID", "travel_time": "TT_MIN"})
    ttm = ttm.dropna(subset=["TT_MIN"])  # 60분 초과(도달불가) 쌍은 저장하지 않음(희소 테이블 유지)

    results.append(ttm)
    pd.concat(results, ignore_index=True).to_csv(OUT_CSV, index=False)

    elapsed = time.time() - t_start
    done_origins = (i + 1) * CHUNK_SIZE if i < n_chunks - 1 else len(origins)
    rate = done_origins / elapsed if elapsed > 0 else 0
    remaining = (len(origins) - done_origins) / rate if rate > 0 else float("nan")
    log(f"청크 {i+1}/{n_chunks} 완료 (origin {len(chunk)}개, {len(ttm)}행, {time.time()-t_chunk:.1f}s) | "
        f"누적 origin {done_origins}/{len(origins)} | 예상 잔여 {remaining/60:.1f}분")

log(f"전체 완료: {time.time()-t0:.1f}s, 총 {sum(len(r) for r in results)}행")
