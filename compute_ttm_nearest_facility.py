"""
r5py TravelTimeMatrix을 이용해 100m 격자(건물 존재 격자) 중심점에서
가장 가까운 의료시설까지의 대중교통 통행시간을 계산한다.

출발일시: 2026-09-01 09:00:00 (오전 첨두)
Origin: data/grid_100m_daegugyeongbuk_with_buildings (144,528개) 중심점
Destination: 대상 지역(17개 시군구) 경계 20km 버퍼 내 의료시설 (경계 인접 왜곡 방지용 버퍼)

144,528개 origin x 수천 개 destination의 전체 쌍을 한 번에 들고 있으면
수억 행이 되어 메모리를 감당할 수 없으므로, origin을 청크 단위로 나눠
처리하면서 청크마다 origin별 최솟값(가장 가까운 의료시설까지의 시간)만
남기고 즉시 버린다.

실행: nohup으로 백그라운드 실행, 진행 상황은 로그 파일에 기록.
"""
import os

os.environ["JAVA_HOME"] = "/Users/chaelyn/miniforge3/envs/jdk21/lib/jvm"

import datetime
import sys
import time

import geopandas as gpd
import pandas as pd
import r5py

CHUNK_SIZE = 3000
OUT_DIR = "data/accessibility_ttm_20260901_0900"
OUT_CSV = f"{OUT_DIR}/nearest_facility_travel_time.csv"
BUFFER_KM = 20

os.makedirs(OUT_DIR, exist_ok=True)


def log(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


t0 = time.time()

grid = gpd.read_file(
    "data/grid_100m_daegugyeongbuk_with_buildings/grid_100m_daegugyeongbuk_with_buildings.shp",
    encoding="cp949",
)
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

origins = grid.copy()
origins["geometry"] = origins.geometry.centroid
origins = origins.to_crs("EPSG:4326")
# SPO_NO_CD는 시군구 경계에 걸친 셀에서 SECT_CD가 다른 중복 행이 존재해 고유하지 않음
# (원본 100m 격자 소스가 SPO_NO_CD+SECT_CD를 합쳐야 고유 키가 되는 구조).
# TravelTimeMatrix는 origin id가 고유해야 하므로 행 인덱스 기반 id를 새로 만든다.
origins = origins.reset_index(drop=True)
origins["id"] = "G" + origins.index.astype(str)
origins = origins[["id", "SPO_NO_CD", "geometry"]]

destinations = fac.to_crs("EPSG:4326").copy()
destinations["id"] = [f"F{i}" for i in range(len(destinations))]
destinations = destinations[["id", "geometry"]]

log(f"origins: {len(origins)}, destinations(buffer {BUFFER_KM}km): {len(destinations)}")

net = r5py.TransportNetwork(
    "data/raw_gtfs_network/daegyeong.osm.pbf",
    ["data/raw_gtfs_network/daegyung_gtfs_20260901.zip"],
)
log(f"network built ({time.time()-t0:.1f}s)")

DEPARTURE = datetime.datetime(2026, 9, 1, 9, 0, 0)

n_chunks = (len(origins) + CHUNK_SIZE - 1) // CHUNK_SIZE
results = []

# 중간 재시작을 위해 이미 처리된 청크가 있으면 건너뜀
done_ids = set()
if os.path.exists(OUT_CSV):
    prev = pd.read_csv(OUT_CSV)
    results.append(prev)
    done_ids = set(prev["id"])
    log(f"기존 결과 {len(prev)}개 로드, 이어서 진행")

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
        departure_time_window=datetime.timedelta(hours=1),
        transport_modes=[r5py.TransportMode.TRANSIT, r5py.TransportMode.WALK],
        speed_walking=4.5,
        max_time=datetime.timedelta(minutes=60),
        max_time_walking=datetime.timedelta(minutes=15),
        max_public_transport_rides=5,
    )
    nearest = ttm.groupby("from_id")["travel_time"].min().reset_index()
    nearest.columns = ["id", "nearest_facility_min"]

    # 이 청크에 있었지만 목적지 어디에도 60분 내 도달 못한 origin도 명시적으로 NaN으로 남김
    missing = chunk[~chunk["id"].isin(nearest["id"])][["id"]].copy()
    missing["nearest_facility_min"] = float("nan")
    nearest = pd.concat([nearest, missing], ignore_index=True)
    nearest = nearest.merge(chunk[["id", "SPO_NO_CD"]], on="id", how="left")

    results.append(nearest)
    pd.concat(results, ignore_index=True).to_csv(OUT_CSV, index=False)

    elapsed = time.time() - t_start
    done_count = sum(len(r) for r in results)
    rate = done_count / elapsed if elapsed > 0 else 0
    remaining = (len(origins) - done_count) / rate if rate > 0 else float("nan")
    log(f"청크 {i+1}/{n_chunks} 완료 ({len(chunk)}개, {time.time()-t_chunk:.1f}s) | "
        f"누적 {done_count}/{len(origins)} | 예상 잔여 {remaining/60:.1f}분")

log(f"전체 완료: {time.time()-t0:.1f}s")
