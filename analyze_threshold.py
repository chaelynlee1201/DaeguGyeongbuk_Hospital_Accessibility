"""
임계 통행시간 설정 진단: 격자별 '가장 가까운 1번째·3번째 의료시설까지의 통행시간' 분포.

- 대표일 2026-08-11(화) 09:00 기준, 격자(origin)→시설(destination) 멀티모달 통행시간.
- 세부 파라미터는 실제 분석과 동일(도보 4.5km/h, 총 도보 30분, 환승 5회, window 2시간).
- max_time만 300분(5시간)으로 넉넉히 → 60분 너머 분포까지 관찰.
- 격자별로 도달 가능한 시설 통행시간을 오름차순 정렬해, 시설 1개/3개를 포함하는
  최소 통행시간(= 1번째/3번째로 가까운 시설까지의 시간)을 추출.
- 히스토그램 2장(1번째/3번째) + 누적도달률 보조선 + 도달불가 격자 수 보고.

실행(서버):
  conda activate GTFS
  python analyze_threshold.py
"""
import os
import datetime

import numpy as np
import pandas as pd
import geopandas as gpd
import r5py

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# compute 스크립트의 경로·GTFS 유틸 재사용
from compute_g2sfca_timeseries import GTFS_DIR, OSM_PBF, find_gtfs, clean_gtfs  # noqa

OUT_DIR = "data/threshold_analysis"
SUPPLY_GPKG = "data/g2sfca_timeseries/supply_ref.gpkg"
DEMAND_GPKG = "data/g2sfca_timeseries/demand_ref.gpkg"

DATE = "20260811"
HOUR = 9
MAX_TIME_MIN = 300          # 5시간
DEPART_WINDOW_H = 2
WALK_SPEED = 4.5
MAX_WALK_MIN = 30           # 실제 분석과 동일
MAX_RIDES = 5
CHUNK = 1500

os.makedirs(OUT_DIR, exist_ok=True)


def set_korean_font():
    from matplotlib import font_manager as fm
    for name in ["NanumGothic", "Noto Sans CJK KR", "Noto Sans KR", "Malgun Gothic",
                 "AppleGothic", "UnDotum", "NanumBarunGothic"]:
        if name in {f.name for f in fm.fontManager.ttflist}:
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


def to_points_4326(gdf, id_col):
    g = gdf.copy()
    if g.geometry.geom_type.iloc[0] != "Point":
        g["geometry"] = g.geometry.centroid
    g = g.to_crs("EPSG:4326")
    out = g.reset_index()[[id_col, "geometry"]].rename(columns={id_col: "id"})
    out["id"] = out["id"].astype(str)
    return out


def main():
    set_korean_font()
    supply = gpd.read_file(SUPPLY_GPKG).set_index("id"); supply.index = supply.index.astype(str)
    demand = gpd.read_file(DEMAND_GPKG).set_index("GRID_CD"); demand.index = demand.index.astype(str)
    fac_pts = to_points_4326(supply, "id")
    grid_pts = to_points_4326(demand, "GRID_CD")
    n_grid = len(grid_pts)
    print(f"격자 {n_grid}, 시설 {len(fac_pts)} | 대표일 {DATE} {HOUR:02d}:00, max {MAX_TIME_MIN}분")

    gtfs = find_gtfs(DATE)
    if gtfs is None:
        raise SystemExit(f"GTFS 없음: {DATE}")
    net = r5py.TransportNetwork(OSM_PBF, [clean_gtfs(gtfs, DATE)])
    departure = datetime.datetime(int(DATE[:4]), int(DATE[4:6]), int(DATE[6:8]), HOUR, 0, 0)

    # 격자→시설 통행시간(5시간 이내) 계산
    parts = []
    for s in range(0, n_grid, CHUNK):
        chunk = grid_pts.iloc[s:s + CHUNK]
        ttm = r5py.TravelTimeMatrix(
            net, origins=chunk[["id", "geometry"]], destinations=fac_pts[["id", "geometry"]],
            departure=departure, departure_time_window=datetime.timedelta(hours=DEPART_WINDOW_H),
            transport_modes=[r5py.TransportMode.TRANSIT, r5py.TransportMode.WALK],
            speed_walking=WALK_SPEED, max_time=datetime.timedelta(minutes=MAX_TIME_MIN),
            max_time_walking=datetime.timedelta(minutes=MAX_WALK_MIN),
            max_public_transport_rides=MAX_RIDES,
        ).rename(columns={"from_id": "GRID_ID", "to_id": "FAC_ID", "travel_time": "TT_MIN"})
        parts.append(ttm.dropna(subset=["TT_MIN"])[["GRID_ID", "TT_MIN"]])
        print(f"  청크 {s//CHUNK+1}: 누적 {sum(len(p) for p in parts):,}행")
    ttm = pd.concat(parts, ignore_index=True)

    # 격자별 1번째·3번째 최소 통행시간
    def nth_min(group, n):
        v = np.sort(group.values)
        return v[n - 1] if len(v) >= n else np.nan
    g1 = ttm.groupby("GRID_ID")["TT_MIN"].apply(lambda s: nth_min(s, 1)).reindex(grid_pts["id"])
    g3 = ttm.groupby("GRID_ID")["TT_MIN"].apply(lambda s: nth_min(s, 3)).reindex(grid_pts["id"])

    out = pd.DataFrame({"GRID_CD": grid_pts["id"].values,
                        "t_nearest1": g1.values, "t_nearest3": g3.values})
    out.to_csv(f"{OUT_DIR}/nearest_times_{DATE}_{HOUR:02d}.csv", index=False)

    for col, nth in [("t_nearest1", 1), ("t_nearest3", 3)]:
        vals = out[col].dropna().values
        unreachable = int(out[col].isna().sum())
        print(f"\n[시설 {nth}개 포함 최소시간] 도달가능 {len(vals)}/{n_grid} "
              f"| {nth}개 미만 도달불가 {unreachable} ({100*unreachable/n_grid:.1f}%)")
        if len(vals):
            for p in [25, 50, 75, 90, 95]:
                print(f"    {p}분위: {np.percentile(vals, p):.0f}분")
            for thr in [30, 45, 60, 90, 120]:
                print(f"    {thr}분 이내 도달 격자: {100*(vals <= thr).mean():.1f}% "
                      f"(전체 대비 {100*(vals <= thr).sum()/n_grid:.1f}%)")

        # 히스토그램 + 누적도달률
        fig, ax = plt.subplots(figsize=(9, 5.5), facecolor="white")
        binw = 10
        bins = np.arange(0, (np.nanmax(vals) // binw + 2) * binw, binw) if len(vals) else [0, 10]
        ax.hist(vals, bins=bins, color="#4a7fb5", edgecolor="white", alpha=0.85)
        ax.set_xlabel("통행시간 (분)", fontsize=12)
        ax.set_ylabel("격자 수", fontsize=12)
        ax.set_title(f"의료시설 {nth}개 포함 최소 통행시간 분포 — {DATE} {HOUR:02d}:00",
                     fontsize=14, fontweight="bold")
        for thr in (30, 60):
            ax.axvline(thr, color="#c0392b", lw=1.5, ls="--")
            ax.text(thr, ax.get_ylim()[1]*0.95, f"{thr}분", color="#c0392b",
                    ha="center", va="top", fontsize=10, fontweight="bold")
        # 누적도달률(보조축)
        ax2 = ax.twinx()
        xs = np.sort(vals)
        ax2.plot(xs, 100*np.arange(1, len(xs)+1)/n_grid, color="#e07b39", lw=2)
        ax2.set_ylabel("누적 도달 격자 비율 (%, 전체 대비)", fontsize=12, color="#e07b39")
        ax2.set_ylim(0, 100); ax2.tick_params(axis="y", labelcolor="#e07b39")
        fig.text(0.99, 0.01, f"도달불가 {unreachable}격자({100*unreachable/n_grid:.1f}%) 제외",
                 ha="right", fontsize=9, color="#777")
        plt.tight_layout()
        outp = f"{OUT_DIR}/hist_nearest{nth}_{DATE}_{HOUR:02d}.png"
        plt.savefig(outp, dpi=180, facecolor="white", bbox_inches="tight"); plt.close(fig)
        print("    저장:", outp)


if __name__ == "__main__":
    main()
