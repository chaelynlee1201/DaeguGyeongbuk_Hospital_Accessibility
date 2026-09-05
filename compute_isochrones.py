"""
r5py Isochrones를 이용해, 대상 지역 20km 버퍼 내 의료시설(3,887개)을 origin으로 하는
30분·60분 등시간대(isochrone)를 계산한다.

r5py.Isochrones는 origin을 여러 개 넣으면 "이들 중 어느 것으로부터든 최소 이동시간" 기준
통합 isochrone을 반환한다 (문서 확인됨). 즉 "대상 지역 내 가장 가까운 의료시설까지
30분/60분 내 도달 가능한 영역"을 그대로 계산해준다.

origin당 약 1초로 TravelTimeMatrix보다 훨씬 느려서(destinations 수와 무관하게 origin 수가
비용을 지배), 전체 3,887개를 한 번에 돌리면 약 65~113분 소요되고 이 값이 통짜 계산이라
중간에 실패하면 처음부터 다시 해야 한다. 이전 TravelTimeMatrix 작업에서 컴퓨터가 잠들어
프로세스가 죽는 걸 겪었으므로, 이번에도 origin을 청크(500개)로 나눠 처리하고 청크마다
결과를 별도 파일로 저장해 중단 시 재개할 수 있게 한다.

Isochrones가 반환하는 geometry는 MULTILINESTRING(등고선)이라, shapely.ops.polygonize로
닫힌 폴리곤으로 변환한 뒤, 청크 간에는 폴리곤 union으로 합친다
(min(A∪B) 영역 = min(A)의 영역 ∪ min(B)의 영역이 성립하므로 청크 분할이 수학적으로 안전).

실행: caffeinate로 절전 방지, 백그라운드 실행, 진행 상황은 로그 파일에 기록.
"""
import os

os.environ["JAVA_HOME"] = "/Users/chaelyn/miniforge3/envs/jdk21/lib/jvm"

import datetime
import time

import geopandas as gpd
import r5py
from shapely.ops import polygonize, unary_union

CHUNK_SIZE = 500
BUFFER_KM = 20
OUT_DIR = "data/isochrones_20260901_0900"
CHUNK_DIR = f"{OUT_DIR}/chunks"

os.makedirs(CHUNK_DIR, exist_ok=True)


def log(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


t0 = time.time()

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

origins = fac.to_crs("EPSG:4326").copy()
origins = origins.reset_index(drop=True)
origins["id"] = "F" + origins.index.astype(str)
origins = origins[["id", "geometry"]]

log(f"origins (destination-region 시설, buffer {BUFFER_KM}km): {len(origins)}")

net = r5py.TransportNetwork(
    "data/raw_gtfs_network/daegyeong.osm.pbf",
    ["data/raw_gtfs_network/daegyung_gtfs_20260901.zip"],
)
log(f"network built ({time.time()-t0:.1f}s)")

DEPARTURE = datetime.datetime(2026, 9, 1, 9, 0, 0)
ISOCHRONE_MINUTES = [30, 60]

n_chunks = (len(origins) + CHUNK_SIZE - 1) // CHUNK_SIZE
t_start = time.time()

for i in range(n_chunks):
    chunk_path = f"{CHUNK_DIR}/chunk_{i:03d}.gpkg"
    if os.path.exists(chunk_path):
        continue

    chunk = origins.iloc[i * CHUNK_SIZE:(i + 1) * CHUNK_SIZE]
    t_chunk = time.time()

    iso = r5py.Isochrones(
        net,
        origins=chunk,
        isochrones=[datetime.timedelta(minutes=m) for m in ISOCHRONE_MINUTES],
        departure=DEPARTURE,
        departure_time_window=datetime.timedelta(hours=1),
        transport_modes=[r5py.TransportMode.TRANSIT, r5py.TransportMode.WALK],
        speed_walking=4.5,
        max_time_walking=datetime.timedelta(minutes=15),
        max_public_transport_rides=5,
    )

    rows = []
    for _, row in iso.iterrows():
        minutes = int(row["travel_time"].total_seconds() // 60)
        polys = list(polygonize(row.geometry))
        if polys:
            rows.append({"minutes": minutes, "geometry": unary_union(polys)})

    chunk_gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326")
    chunk_gdf.to_file(chunk_path, driver="GPKG")

    elapsed = time.time() - t_start
    done = (i + 1) * CHUNK_SIZE if i < n_chunks - 1 else len(origins)
    rate = done / elapsed if elapsed > 0 else 0
    remaining = (len(origins) - done) / rate if rate > 0 else float("nan")
    log(f"청크 {i+1}/{n_chunks} 완료 ({len(chunk)}개, {time.time()-t_chunk:.1f}s) | "
        f"예상 잔여 {remaining/60:.1f}분")

log("모든 청크 완료 — 최종 union 시작")

all_chunks = [gpd.read_file(f"{CHUNK_DIR}/chunk_{i:03d}.gpkg") for i in range(n_chunks)]
merged = gpd.GeoDataFrame(
    __import__("pandas").concat(all_chunks, ignore_index=True), crs="EPSG:4326"
)

final_rows = []
for minutes in ISOCHRONE_MINUTES:
    sub = merged[merged["minutes"] == minutes]
    final_rows.append({"minutes": minutes, "geometry": unary_union(sub.geometry.tolist())})

final_gdf = gpd.GeoDataFrame(final_rows, crs="EPSG:4326")
final_gdf.to_file(f"{OUT_DIR}/isochrones_final.gpkg", driver="GPKG")
log(f"최종 isochrone 저장 완료: {OUT_DIR}/isochrones_final.gpkg")
log(f"전체 완료: {time.time()-t0:.1f}s")
