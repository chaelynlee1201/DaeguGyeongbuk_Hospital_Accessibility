"""
Figure 2: 지역별 상대 감소율 평균 단계구분도 (시간대별 별도, 등간격).

- 각 1km 격자를 '교차 면적이 가장 큰' 시군구에 배정(경계 격자 처리).
- 시군구별 상대 감소율(dec_pct) 평균을 산정.
- 메인 지도: 경북 8개 시·군 + 대구광역시(자치구 통합) = 9개 지역.
- 삽도(inset): 대구광역시만 확대, 자치구(중·동·서·남·북·수성·달서구, 달성·군위군) 단위.
- 메인/삽도 색 구간(등간격)·범례 동일.

입력:
  data/g2sfca_timeseries/g2sfca_ts_grid_percentiles_{0900,1200}.gpkg  (GRID_CD, dec_pct)
  data/grid_1km_population_daegugyeongbuk/...shp  (격자 폴리곤, GRID_CD)
  data/BND_SIGUNGU_PG/...shp

실행(서버):
  conda activate GTFS
  python make_regional_decrease_maps.py
"""
import os
import numpy as np
import geopandas as gpd
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import Rectangle

GRID_SHP = "data/grid_1km_population_daegugyeongbuk/grid_1km_population_daegugyeongbuk.shp"
SIGUNGU_SHP = "data/BND_SIGUNGU_PG/BND_SIGUNGU_PG.shp"
PCT_GPKG = "data/g2sfca_timeseries/g2sfca_ts_grid_percentiles_{period}.gpkg"
OUT_DIR = "data/regional_maps"
PERIODS = {"0900": "09:00 출발", "1200": "12:00 출발"}

DAEGU_CODES = ["22010", "22020", "22030", "22040", "22050", "22060", "22070", "22510", "22520"]
GYEONGBUK_CODES = ["37030", "37050", "37070", "37100", "37560", "37570", "37580", "37590"]
TARGET_CODES = DAEGU_CODES + GYEONGBUK_CODES
N_CLASSES = 5
CMAP = "OrRd"

os.makedirs(OUT_DIR, exist_ok=True)


def set_korean_font():
    from matplotlib import font_manager as fm
    for name in ["NanumGothic", "Noto Sans CJK KR", "Noto Sans KR", "Malgun Gothic",
                 "AppleGothic", "UnDotum", "NanumBarunGothic"]:
        if name in {f.name for f in fm.fontManager.ttflist}:
            plt.rcParams["font.family"] = name
            break
    else:
        print("[경고] 한글 폰트 없음")
    plt.rcParams["axes.unicode_minus"] = False


def assign_grid_to_sigungu(grid, sig):
    """각 격자를 교차 면적이 최대인 시군구(SIGUNGU_CD)에 배정 → GRID_CD별 코드 매핑."""
    ov = gpd.overlay(grid[["GRID_CD", "geometry"]], sig[["SIGUNGU_CD", "geometry"]],
                     how="intersection", keep_geom_type=True)
    ov["a"] = ov.geometry.area
    idx = ov.groupby("GRID_CD")["a"].idxmax()
    best = ov.loc[idx, ["GRID_CD", "SIGUNGU_CD"]].set_index("GRID_CD")["SIGUNGU_CD"]
    return best


def regional_means(period, grid, assign):
    """시군구별 dec_pct 평균(시군구 코드 → 값). dec_pct는 결과 gpkg에서 조인."""
    pct = gpd.read_file(PCT_GPKG.format(period=period))[["GRID_CD", "dec_pct"]]
    pct["GRID_CD"] = pct["GRID_CD"].astype(str)
    df = pct.merge(assign.rename("SIGUNGU_CD"), left_on="GRID_CD", right_index=True)
    # dec_pct가 NaN(상위5%=0 등 산정불가)인 격자는 평균에서 제외
    means = df.dropna(subset=["dec_pct"]).groupby("SIGUNGU_CD")["dec_pct"].mean()
    return means


def main():
    set_korean_font()
    grid = gpd.read_file(GRID_SHP).to_crs("EPSG:5179")
    grid["GRID_CD"] = grid["GRID_CD"].astype(str)
    sig = gpd.read_file(SIGUNGU_SHP, encoding="cp949").to_crs("EPSG:5179")
    sig_t = sig[sig["SIGUNGU_CD"].isin(TARGET_CODES)].copy()

    # 격자→시군구 면적 최대 배정(1회)
    assign = assign_grid_to_sigungu(grid, sig_t)
    print(f"격자 배정 완료: {len(assign):,}개")

    # 메인 지도용 지오메트리: 경북 8개(개별) + 대구 1개(통합)
    gb = sig_t[sig_t["SIGUNGU_CD"].isin(GYEONGBUK_CODES)][["SIGUNGU_CD", "SIGUNGU_NM", "geometry"]].copy()
    daegu_geom = sig_t[sig_t["SIGUNGU_CD"].isin(DAEGU_CODES)].union_all()
    daegu_row = gpd.GeoDataFrame({"SIGUNGU_CD": ["DAEGU"], "SIGUNGU_NM": ["대구광역시"],
                                  "geometry": [daegu_geom]}, crs=sig.crs)
    main_regions = pd.concat([gb, daegu_row], ignore_index=True)
    daegu_districts = sig_t[sig_t["SIGUNGU_CD"].isin(DAEGU_CODES)][
        ["SIGUNGU_CD", "SIGUNGU_NM", "geometry"]].copy()

    for period in PERIODS:
        means = regional_means(period, grid, assign)
        # 대구 통합값 = 대구 자치구에 배정된 격자 전체의 평균(코드 묶어 재계산)
        pct = gpd.read_file(PCT_GPKG.format(period=period))[["GRID_CD", "dec_pct"]]
        pct["GRID_CD"] = pct["GRID_CD"].astype(str)
        df = pct.merge(assign.rename("SIGUNGU_CD"), left_on="GRID_CD", right_index=True).dropna(subset=["dec_pct"])
        daegu_mean = df[df["SIGUNGU_CD"].isin(DAEGU_CODES)]["dec_pct"].mean()

        mr = main_regions.copy()
        mr["val"] = mr["SIGUNGU_CD"].map(lambda c: daegu_mean if c == "DAEGU" else means.get(c, np.nan))
        dd = daegu_districts.copy()
        dd["val"] = dd["SIGUNGU_CD"].map(lambda c: means.get(c, np.nan))

        # 등간격 공통 구간(메인+삽도 전체 값 기준)
        allv = np.concatenate([mr["val"].dropna().values, dd["val"].dropna().values])
        vmin, vmax = float(np.nanmin(allv)), float(np.nanmax(allv))
        bounds = np.linspace(vmin, vmax, N_CLASSES + 1)
        cmap = plt.get_cmap(CMAP, N_CLASSES)
        norm = matplotlib.colors.BoundaryNorm(bounds, cmap.N)

        # 레이아웃: 좌(메인 지도) | 우(삽도 + 세로 범례) — 삽도가 메인을 가리지 않게
        fig = plt.figure(figsize=(17, 11), facecolor="white")
        gs = fig.add_gridspec(1, 3, width_ratios=[1.7, 1.05, 0.18],
                              wspace=0.0)
        ax = fig.add_subplot(gs[0, 0])       # 메인(좌)
        ax_in = fig.add_subplot(gs[0, 1])    # 삽도(가운데)
        ax_cb = fig.add_subplot(gs[0, 2])    # 세로 범례(우)
        fig.subplots_adjust(left=0.005, right=0.995, top=0.995, bottom=0.005)

        # 메인 지도
        mr.plot(ax=ax, column="val", cmap=cmap, norm=norm, edgecolor="#2c2c2c",
                linewidth=1.2, legend=False, missing_kwds={"color": "#eeeeee"})
        for _, r in mr.iterrows():
            c = r.geometry.representative_point()
            lab = r["SIGUNGU_NM"] + (f"\n{r['val']:.0f}%" if pd.notna(r["val"]) else "")
            ax.annotate(lab, xy=(c.x, c.y), ha="center", va="center", fontsize=15,
                        fontweight="bold", color="#1a1a1a",
                        path_effects=[pe.withStroke(linewidth=3, foreground="white")])
        # 메인에 대구 확대영역 사각형 표시(참고 이미지처럼)
        dminx, dminy, dmaxx, dmaxy = daegu_geom.bounds
        ax.add_patch(Rectangle((dminx, dminy), dmaxx - dminx, dmaxy - dminy,
                               fill=False, edgecolor="#e03030", linewidth=3.5, zorder=5))
        ax.set_axis_off()

        # 삽도(우상): 대구 자치구 (동일 norm·cmap)
        dd.plot(ax=ax_in, column="val", cmap=cmap, norm=norm, edgecolor="#2c2c2c",
                linewidth=0.8, legend=False, missing_kwds={"color": "#eeeeee"})
        for _, r in dd.iterrows():
            c = r.geometry.representative_point()
            lab = r["SIGUNGU_NM"].replace("군위군", "군위").replace("달성군", "달성") \
                  + (f"\n{r['val']:.0f}%" if pd.notna(r["val"]) else "")
            ax_in.annotate(lab, xy=(c.x, c.y), ha="center", va="center", fontsize=7.5,
                           fontweight="bold", color="#1a1a1a",
                           path_effects=[pe.withStroke(linewidth=1.8, foreground="white")])
        for s in ax_in.spines.values():
            s.set_edgecolor("#e03030"); s.set_linewidth(3.5)
        ax_in.set_xticks([]); ax_in.set_yticks([])

        # 공통 범례(우): 세로 등간격 색 구간
        ax_cb.set_axis_off()
        sm = matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap); sm.set_array([])
        cb = fig.colorbar(sm, ax=ax_cb, orientation="vertical", fraction=0.5,
                          aspect=16, pad=0.05)
        cb.set_label("상대 감소율 평균 (%)", fontsize=12)
        cb.set_ticks(bounds); cb.set_ticklabels([f"{b:.0f}" for b in bounds])

        # ── 삽도 축척 = 메인의 대구 축척 × 확대배율 ──
        INSET_ZOOM = 1.3     # 메인 대구 대비 삽도 확대배율
        fig.canvas.draw()
        fig_w_in, fig_h_in = fig.get_size_inches()
        mpos = ax.get_position()
        mx0, mx1 = ax.get_xlim(); my0, my1 = ax.get_ylim()
        s_main = max((mx1 - mx0) / (mpos.width * fig_w_in),
                     (my1 - my0) / (mpos.height * fig_h_in))
        s_in = s_main / INSET_ZOOM        # 축척을 작게 → 대구가 크게 그려짐
        pad = 0.06
        dw = (dmaxx - dminx) * (1 + 2 * pad); dh = (dmaxy - dminy) * (1 + 2 * pad)
        ax_in.set_xlim(dminx - (dmaxx - dminx) * pad, dmaxx + (dmaxx - dminx) * pad)
        ax_in.set_ylim(dminy - (dmaxy - dminy) * pad, dmaxy + (dmaxy - dminy) * pad)
        ax_in.set_aspect("auto")
        w_in = dw / s_in; h_in = dh / s_in
        wf = w_in / fig_w_in; hf = h_in / fig_h_in
        # 메인 바로 옆(간격 최소)에 세로 중앙 배치
        ipos = ax_in.get_position()
        left = mpos.x0 + mpos.width + 0.005          # 메인 우측 경계 바로 옆
        cy = mpos.y0 + mpos.height / 2               # 메인 세로 중심
        ax_in.set_position([left, cy - hf / 2, wf, hf])

        out = f"{OUT_DIR}/regional_decrease_{period}.png"
        plt.savefig(out, dpi=200, facecolor="white", bbox_inches="tight", pad_inches=0.02)
        plt.close(fig)
        print("저장:", out)
        print(f"  [{period}] 지역 평균(%): " +
              ", ".join(f"{n}={v:.0f}" for n, v in zip(mr['SIGUNGU_NM'], mr['val']) if pd.notna(v)))


if __name__ == "__main__":
    main()
