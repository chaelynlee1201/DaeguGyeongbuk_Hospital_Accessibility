"""
연구 방법 슬라이드용 지도 생성.
 (1) 연구 지역 경계 — 대구·경북 10개 시·군·구(17개 행정경계), 시군구명 라벨
 (2) 필터링된 의료시설 분포 — 7종·총의사수>0, 20km 버퍼 내 (단색 점)
 (3) 1km 인구 단계구분도 (분위 5단계)
 (4) 분석 사용 격자(인구>0) 단색
 (5) 의사수 비례 원(proportional symbol) 의료시설 지도
 (6) 분석 대상 격자(노란색) + 대구·경북권 clip 도로망(파란색) (pyrosm 필요)
 (7) 1km 인구 단계구분도 + 대구·경북권 clip 도로망(두꺼운 파란색)
 (8) 베이스맵(경계 스타일) + 연한 인구 단계구분도 + 연한 회색 도로망, 대구 통합 라벨

실행(서버):
  conda activate GTFS
  python make_study_area_maps.py
"""
import geopandas as gpd
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

SIGUNGU_SHP = "data/BND_SIGUNGU_PG/BND_SIGUNGU_PG.shp"
OUT_DIR = "data/study_area_maps"
SUPPLY_GPKG = "data/g2sfca_timeseries/supply_ref.gpkg"   # compute가 만든 최종 공급 시설
DEMAND_GPKG = "data/g2sfca_timeseries/demand_ref.gpkg"   # 분석 사용(인구>0) 격자
GRID_SHP = "data/grid_1km_population_daegugyeongbuk/grid_1km_population_daegugyeongbuk.shp"
OSM_PBF = "data/raw_gtfs_network/daegyeong.osm.pbf"
TARGET_CODES = [
    "22010", "22020", "22030", "22040", "22050", "22060", "22070", "22510", "22520",
    "37050", "37030", "37070", "37100", "37560", "37570", "37580", "37590",
]
BUFFER_KM = 20

import os
os.makedirs(OUT_DIR, exist_ok=True)


def set_korean_font():
    from matplotlib import font_manager as fm
    for name in ["NanumGothic", "Noto Sans CJK KR", "Noto Sans KR", "Malgun Gothic",
                 "AppleGothic", "UnDotum", "NanumBarunGothic"]:
        if name in {f.name for f in fm.fontManager.ttflist}:
            plt.rcParams["font.family"] = name
            break
    else:
        print("[경고] 한글 폰트 없음 — 라벨 깨질 수 있음")
    plt.rcParams["axes.unicode_minus"] = False


def load_osm_roads(clip_geom_5179):
    """OSM .pbf에서 도로망(line)을 읽어 대상 지역(clip_geom_5179)으로 clip한
    EPSG:5179 GeoDataFrame 반환. pyrosm 필요. 없거나 실패하면 None."""
    try:
        from pyrosm import OSM
    except ImportError:
        print("[경고] pyrosm 미설치 → 도로망 생략. 설치: conda install -c conda-forge pyrosm")
        return None
    try:
        osm = OSM(OSM_PBF)
        roads = osm.get_network(network_type="driving")   # 차량 통행 도로
        if roads is None or len(roads) == 0:
            print("[경고] OSM 도로망이 비어 있음")
            return None
        # 주요 간선도로만: highway 태그 상위 등급
        major = ["motorway", "trunk", "primary", "secondary",
                 "motorway_link", "trunk_link", "primary_link", "secondary_link"]
        if "highway" in roads.columns:
            roads = roads[roads["highway"].isin(major)]
        roads = roads.to_crs("EPSG:5179")
        clip = gpd.GeoSeries([clip_geom_5179], crs="EPSG:5179")
        roads = gpd.clip(roads, clip)                     # 대구·경북권 경계로 clip
        print(f"OSM 간선도로: {len(roads):,}개 (대상 지역 clip 후)")
        return roads
    except Exception as e:
        print(f"[경고] OSM 도로망 로드 실패: {e}")
        return None


def main():
    set_korean_font()
    sig = gpd.read_file(SIGUNGU_SHP, encoding="cp949").to_crs("EPSG:5179")
    target = sig[sig["SIGUNGU_CD"].isin(TARGET_CODES)].copy()
    others = sig[~sig["SIGUNGU_CD"].isin(TARGET_CODES)].copy()

    # 라벨용 그룹: 대구(코드 22*)는 하나로 합쳐 '대구광역시', 경북(37*)은 시·군 개별
    def label_groups():
        daegu = target[target["SIGUNGU_CD"].str.startswith("22")]
        groups = [("대구광역시", daegu.union_all())]
        for _, r in target[target["SIGUNGU_CD"].str.startswith("37")].iterrows():
            groups.append((r["SIGUNGU_NM"], r.geometry))
        return groups

    # ── (1) 연구 지역 경계 지도 ──
    fig, ax = plt.subplots(figsize=(11, 12), facecolor="white")
    minx, miny, maxx, maxy = target.total_bounds
    mx, my = (maxx - minx) * 0.12, (maxy - miny) * 0.12
    others.plot(ax=ax, color="#f2f2f2", edgecolor="#cccccc", linewidth=0.5, zorder=0)
    target.plot(ax=ax, color="#cfe3f2", edgecolor="#2c2c2c", linewidth=1.3, zorder=1)
    for name, geom in label_groups():
        c = geom.representative_point()
        ax.annotate(name, xy=(c.x, c.y), ha="center", va="center",
                    fontsize=12, fontweight="bold", color="#1a1a1a", zorder=3,
                    path_effects=[pe.withStroke(linewidth=3, foreground="white")])
    ax.set_xlim(minx - mx, maxx + mx); ax.set_ylim(miny - my, maxy + my)
    ax.set_title("연구 지역: 대구·경북", fontsize=20, fontweight="bold", pad=8)
    ax.set_axis_off()
    # 간이 스케일바(20km)
    sb = 20000; x0 = minx - mx + (maxx - minx) * 0.04; y0 = miny - my + (maxy - miny) * 0.04
    ax.plot([x0, x0 + sb], [y0, y0], color="black", lw=3, zorder=5)
    ax.text(x0 + sb / 2, y0 + (maxy - miny) * 0.012, "20 km", ha="center", fontsize=10, zorder=5)
    plt.tight_layout()
    out1 = f"{OUT_DIR}/study_area_boundary.png"
    plt.savefig(out1, dpi=200, facecolor="white", bbox_inches="tight"); plt.close(fig)
    print("저장:", out1)

    # ── (2) 필터링된 의료시설 분포 지도 ──
    fac = gpd.read_file(SUPPLY_GPKG).to_crs("EPSG:5179")   # 이미 7종·의사>0·20km버퍼 필터 완료
    buf = target.union_all().buffer(BUFFER_KM * 1000)

    fig, ax = plt.subplots(figsize=(11, 12), facecolor="white")
    # 배경(회색) 없이, 대상 지역만 연한 파란색으로 채우고 경계선 표시
    gpd.GeoSeries([buf], crs="EPSG:5179").plot(ax=ax, color="none",
                                               edgecolor="#e07b39", linewidth=1.2,
                                               linestyle="--", zorder=1)
    target.plot(ax=ax, color="#dbeafe", edgecolor="#2c2c2c", linewidth=1.3, zorder=2)

    # 원 크기 ∝ 총의사수 (면적 비례: markersize ∝ 의사수)
    import math
    dmax = float(fac["N_DOCTOR"].max())
    msize = 8 + (fac["N_DOCTOR"] / dmax) * 900
    ax.scatter(fac.geometry.x, fac.geometry.y, s=msize, facecolor="#c0392b",
               edgecolor="white", linewidth=0.3, alpha=0.55, zorder=3)

    # study_area_boundary와 동일 라벨(대구 통합 + 경북 시·군)
    for name, geom in label_groups():
        c = geom.representative_point()
        ax.annotate(name, xy=(c.x, c.y), ha="center", va="center",
                    fontsize=12, fontweight="bold", color="#1a1a1a", zorder=4,
                    path_effects=[pe.withStroke(linewidth=3, foreground="white")])

    bminx, bminy, bmaxx, bmaxy = buf.bounds
    bx, by = (bmaxx - bminx) * 0.05, (bmaxy - bminy) * 0.05
    ax.set_xlim(bminx - bx, bmaxx + bx); ax.set_ylim(bminy - by, bmaxy + by)
    ax.set_axis_off()
    legvals = sorted({int(round(v)) for v in [max(1, dmax * 0.1), dmax * 0.4, dmax] if v >= 1})
    handles = [Line2D([0], [0], marker="o", color="none", markerfacecolor="#c0392b",
                      alpha=0.55, markeredgecolor="white",
                      markersize=math.sqrt(8 + (v / dmax) * 900), label=f"의사 {v}명")
               for v in legvals]
    handles.append(Line2D([0], [0], color="#e07b39", lw=2.0, ls="--", label="20km 버퍼"))
    ax.legend(handles=handles, loc="lower left", fontsize=15, frameon=True,
              title="총의사수", title_fontsize=16, labelspacing=2.0, borderpad=1.2,
              handletextpad=1.5)
    plt.tight_layout()
    out2 = f"{OUT_DIR}/medical_facilities_supply.png"
    plt.savefig(out2, dpi=200, facecolor="white", bbox_inches="tight"); plt.close(fig)
    print("저장:", out2)

    # 참고 통계
    print(f"\n공급 시설 {len(fac):,}개 | 의사수 합 {int(fac['N_DOCTOR'].sum()):,}")

    # ── (3),(4) 인구 격자 지도 2종 (경계 위에 격자) ──
    grid = gpd.read_file(GRID_SHP).to_crs("EPSG:5179")
    used = grid[grid["TOT_POP"] > 0].copy()          # 분석 사용 격자(인구>0)
    excluded = grid[~(grid["TOT_POP"] > 0)].copy()   # 분석 제외 격자(인구 0)
    gminx, gminy, gmaxx, gmaxy = target.total_bounds
    gmx, gmy = (gmaxx - gminx) * 0.1, (gmaxy - gminy) * 0.1

    def base(ax):
        others.plot(ax=ax, color="#f7f7f7", edgecolor="#dddddd", linewidth=0.4, zorder=0)
        target.boundary.plot(ax=ax, color="#2c2c2c", linewidth=1.2, zorder=3)
        ax.set_xlim(gminx - gmx, gmaxx + gmx); ax.set_ylim(gminy - gmy, gmaxy + gmy)
        ax.set_axis_off()

    # (3) 인구수 단계구분도 (분위 5단계; mapclassify 없이 numpy 분위로 경계 산정)
    fig, ax = plt.subplots(figsize=(11, 12), facecolor="white")
    base(ax)
    qs = np.unique(np.nanpercentile(used["TOT_POP"].values, [0, 20, 40, 60, 80, 100]))
    cmap_pop = plt.get_cmap("YlOrRd", len(qs) - 1)
    norm_pop = matplotlib.colors.BoundaryNorm(qs, cmap_pop.N)
    used.plot(ax=ax, column="TOT_POP", cmap=cmap_pop, norm=norm_pop,
              legend=True, edgecolor="none", linewidth=0, zorder=2,
              legend_kwds={"label": "총인구수(명)", "shrink": 0.5})
    ax.set_title(f"1km 격자 인구 분포 (인구>0 격자 {len(used):,}개)",
                 fontsize=18, fontweight="bold", pad=8)
    plt.tight_layout()
    out3 = f"{OUT_DIR}/population_grid_choropleth.png"
    plt.savefig(out3, dpi=200, facecolor="white", bbox_inches="tight"); plt.close(fig)
    print("저장:", out3)

    # (4) 분석 사용 격자만 (단색)
    fig, ax = plt.subplots(figsize=(11, 12), facecolor="white")
    base(ax)
    used.plot(ax=ax, color="#4a7fb5", edgecolor="none", linewidth=0, zorder=2)
    ax.set_title(f"분석 대상 격자 (인구>0, {len(used):,}개)",
                 fontsize=18, fontweight="bold", pad=8)
    ax.legend(handles=[Patch(facecolor="#4a7fb5", edgecolor="none",
                             label=f"분석 대상 격자 ({len(used):,}개)")],
              loc="lower left", fontsize=10, frameon=True)
    plt.tight_layout()
    out4 = f"{OUT_DIR}/population_grid_used.png"
    plt.savefig(out4, dpi=200, facecolor="white", bbox_inches="tight"); plt.close(fig)
    print("저장:", out4)

    print(f"\n전체 1km 격자 {len(grid):,}개 중 인구>0(분석 사용) {len(used):,}개 "
          f"| 인구합 {int(used['TOT_POP'].sum()):,}")

    # ── (5) 의사 수 비례 원(proportional symbol) 의료시설 지도 ──
    fac_c = fac.copy()
    fac_c["cx"] = fac_c.geometry.x; fac_c["cy"] = fac_c.geometry.y
    dmax = float(fac_c["N_DOCTOR"].max())
    # 원 면적 ∝ 의사수 (반지름 ∝ sqrt) — markersize는 면적 개념
    fac_c["msize"] = 8 + (fac_c["N_DOCTOR"] / dmax) * 900
    fig, ax = plt.subplots(figsize=(11, 12), facecolor="white")
    others.plot(ax=ax, color="#f7f7f7", edgecolor="#dddddd", linewidth=0.4, zorder=0)
    target.plot(ax=ax, color="#eef4f8", edgecolor="#2c2c2c", linewidth=1.2, zorder=1)
    ax.scatter(fac_c["cx"], fac_c["cy"], s=fac_c["msize"], facecolor="#c0392b",
               edgecolor="white", linewidth=0.3, alpha=0.55, zorder=3)
    ax.set_xlim(gminx - gmx, gmaxx + gmx); ax.set_ylim(gminy - gmy, gmaxy + gmy)
    ax.set_title(f"의료시설 및 총의사수 (시설 {len(fac_c):,}개)",
                 fontsize=18, fontweight="bold", pad=8)
    ax.set_axis_off()
    # 범례: 대표 의사수 3개 원 크기
    import math
    legvals = sorted({int(round(v)) for v in
                      [max(1, dmax * 0.1), dmax * 0.4, dmax] if v >= 1})
    handles = [Line2D([0], [0], marker="o", color="none", markerfacecolor="#c0392b",
                      alpha=0.55, markeredgecolor="white",
                      markersize=math.sqrt(8 + (v / dmax) * 900),
                      label=f"의사 {v}명") for v in legvals]
    ax.legend(handles=handles, loc="lower left", fontsize=9, frameon=True,
              title="총의사수", labelspacing=1.4, borderpad=1.0)
    plt.tight_layout()
    out5 = f"{OUT_DIR}/facilities_proportional_doctors.png"
    plt.savefig(out5, dpi=200, facecolor="white", bbox_inches="tight"); plt.close(fig)
    print("저장:", out5)

    # ── (6) 분석 포함 격자(흰색) + 제외 격자(회색) + 주요 간선도로(중간 파랑) ──
    ROAD_BLUE = "#4292c6"     # 참고 지도(그림1)의 중간 파랑
    roads = load_osm_roads(target.union_all())            # 대상 지역 경계로 clip, 간선만
    fig, ax = plt.subplots(figsize=(11, 12), facecolor="white")
    # 회색 배경 없이 경계 바운더리만
    target.boundary.plot(ax=ax, color="#2c2c2c", linewidth=1.2, zorder=3)
    excluded.plot(ax=ax, color="#c8c8c8", edgecolor="none", linewidth=0, zorder=1)
    used.plot(ax=ax, color="white", edgecolor="none", linewidth=0, zorder=2)
    if roads is not None:
        roads.plot(ax=ax, color=ROAD_BLUE, linewidth=1.0, alpha=0.95, zorder=4)
    # study_area_boundary와 동일 라벨(대구 통합)
    for name, geom in label_groups():
        c = geom.representative_point()
        ax.annotate(name, xy=(c.x, c.y), ha="center", va="center",
                    fontsize=12, fontweight="bold", color="#1a1a1a", zorder=6,
                    path_effects=[pe.withStroke(linewidth=3, foreground="white")])
    ax.set_xlim(gminx - gmx, gmaxx + gmx); ax.set_ylim(gminy - gmy, gmaxy + gmy)
    ax.set_axis_off()
    handles = [Patch(facecolor="#c8c8c8", edgecolor="none", label="분석 제외 격자")]
    ax.legend(handles=handles, loc="lower left", fontsize=13, frameon=True,
              labelspacing=1.2, borderpad=1.0)
    plt.tight_layout()
    out6 = f"{OUT_DIR}/grid_with_roads.png"
    plt.savefig(out6, dpi=200, facecolor="white", bbox_inches="tight"); plt.close(fig)
    print("저장:", out6)

    # ── (7) 인구 단계구분도 + 대구·경북권 clip 도로망(두꺼운 파란색) ──
    fig, ax = plt.subplots(figsize=(11, 12), facecolor="white")
    base(ax)
    used.plot(ax=ax, column="TOT_POP", cmap=cmap_pop, norm=norm_pop,
              legend=True, edgecolor="none", linewidth=0, zorder=1,
              legend_kwds={"label": "총인구수(명)", "shrink": 0.5})
    if roads is not None:
        roads.plot(ax=ax, color="#1f6feb", linewidth=1.0, alpha=0.8, zorder=2)
        rlabel = "OSM 도로망"
    else:
        rlabel = "(도로망 생략)"
    ax.set_title(f"1km 인구 분포 + 도로망  [{rlabel}]",
                 fontsize=18, fontweight="bold", pad=8)
    if roads is not None:
        ax.legend(handles=[Line2D([0], [0], color="#1f6feb", lw=2.5, label="도로망(OSM)")],
                  loc="lower left", fontsize=10, frameon=True)
    plt.tight_layout()
    out7 = f"{OUT_DIR}/population_grid_with_roads.png"
    plt.savefig(out7, dpi=200, facecolor="white", bbox_inches="tight"); plt.close(fig)
    print("저장:", out7)

    # ── (8) study_area_boundary 스타일 베이스맵 + 연한 인구 단계구분도 + 연한 회색 도로망 ──
    fig, ax = plt.subplots(figsize=(11, 12), facecolor="white")
    others.plot(ax=ax, color="#f2f2f2", edgecolor="#cccccc", linewidth=0.5, zorder=0)
    target.plot(ax=ax, color="none", edgecolor="#2c2c2c", linewidth=1.3, zorder=1)
    # 연한 인구 단계구분도
    used.plot(ax=ax, column="TOT_POP", cmap=cmap_pop, norm=norm_pop,
              legend=True, edgecolor="none", linewidth=0, alpha=0.55, zorder=2,
              legend_kwds={"label": "총인구수(명)", "shrink": 0.5})
    # 연한 회색 clip 도로망(보통 두께)
    if roads is not None:
        roads.plot(ax=ax, color="#9aa0a6", linewidth=0.7, alpha=0.6, zorder=3)
    # 대구 통합 라벨
    for name, geom in label_groups():
        c = geom.representative_point()
        ax.annotate(name, xy=(c.x, c.y), ha="center", va="center",
                    fontsize=12, fontweight="bold", color="#1a1a1a", zorder=5,
                    path_effects=[pe.withStroke(linewidth=3, foreground="white")])
    ax.set_xlim(minx - mx, maxx + mx); ax.set_ylim(miny - my, maxy + my)
    # 스케일바(20km)
    ax.plot([x0, x0 + sb], [y0, y0], color="black", lw=3, zorder=6)
    ax.text(x0 + sb / 2, y0 + (maxy - miny) * 0.012, "20 km", ha="center", fontsize=10, zorder=6)
    ax.set_title("연구 지역 · 인구 분포 · 도로망", fontsize=20, fontweight="bold", pad=8)
    ax.set_axis_off()
    plt.tight_layout()
    out8 = f"{OUT_DIR}/study_area_population_roads.png"
    plt.savefig(out8, dpi=200, facecolor="white", bbox_inches="tight"); plt.close(fig)
    print("저장:", out8)


if __name__ == "__main__":
    main()
