"""
Figure 2: 지역별 상대 감소율 '중앙값' 단계구분도 (시간대별 별도, 등간격).

- 각 1km 격자를 '교차 면적이 가장 큰' 시군구에 배정(경계 격자 처리).
- 시군구별 상대 감소율(dec_pct) 중앙값을 산정.
- 메인 지도: 경북 8개 시·군 + 대구광역시(자치구 통합) = 9개 지역.
- 삽도(inset): 대구광역시만 확대, 자치구(중·동·서·남·북·수성·달서구, 달성·군위군) 단위.
- 시간대별 3종 생성:
    (A) regional_decrease_<period>.png          : 메인 + 옆 삽도
    (B) regional_decrease_<period>_noinset.png  : 삽도 없이 메인만 (PPT용)
    (C) regional_decrease_<period>_overlay.png  : 삽도를 대구 위치에 겹쳐 배치

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


def regional_stat(period, assign):
    """시군구별 dec_pct 중앙값(코드→값)과 격자단위 merge df를 반환.
    dec_pct가 NaN(상위5%=0 등 산정불가)인 격자는 제외."""
    pct = gpd.read_file(PCT_GPKG.format(period=period))[["GRID_CD", "dec_pct"]]
    pct["GRID_CD"] = pct["GRID_CD"].astype(str)
    df = pct.merge(assign.rename("SIGUNGU_CD"), left_on="GRID_CD",
                   right_index=True).dropna(subset=["dec_pct"])
    med = df.groupby("SIGUNGU_CD")["dec_pct"].median()
    return med, df


def draw_main(ax, mr, cmap, norm, label_fs, show_box=True, box_bounds=None):
    """메인 지도(9개 지역) 그리기."""
    mr.plot(ax=ax, column="val", cmap=cmap, norm=norm, edgecolor="#2c2c2c",
            linewidth=1.2, legend=False, missing_kwds={"color": "#eeeeee"})
    for _, r in mr.iterrows():
        c = r.geometry.representative_point()
        lab = r["SIGUNGU_NM"] + (f"\n{r['val']:.0f}%" if pd.notna(r["val"]) else "")
        ax.annotate(lab, xy=(c.x, c.y), ha="center", va="center", fontsize=label_fs,
                    fontweight="bold", color="#1a1a1a",
                    path_effects=[pe.withStroke(linewidth=3.5, foreground="white")])
    if show_box and box_bounds is not None:
        x0, y0, x1, y1 = box_bounds
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False,
                               edgecolor="#e03030", linewidth=3.5, zorder=5))
    ax.set_axis_off()


def draw_daegu(ax, dd, cmap, norm, label_fs, red_border=True):
    """대구 자치구 삽도 그리기."""
    dd.plot(ax=ax, column="val", cmap=cmap, norm=norm, edgecolor="#2c2c2c",
            linewidth=0.9, legend=False, missing_kwds={"color": "#eeeeee"})
    for _, r in dd.iterrows():
        c = r.geometry.representative_point()
        lab = r["SIGUNGU_NM"].replace("군위군", "군위").replace("달성군", "달성") \
              + (f"\n{r['val']:.0f}%" if pd.notna(r["val"]) else "")
        ax.annotate(lab, xy=(c.x, c.y), ha="center", va="center", fontsize=label_fs,
                    fontweight="bold", color="#1a1a1a",
                    path_effects=[pe.withStroke(linewidth=2.2, foreground="white")])
    if red_border:
        for s in ax.spines.values():
            s.set_edgecolor("#e03030"); s.set_linewidth(3.5)
    ax.set_xticks([]); ax.set_yticks([])


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
    # 세분화 버전: 경북 8개 시·군 + 대구 자치구 9개 (대구 통합 안 함)
    fine_regions = pd.concat([gb, daegu_districts], ignore_index=True)

    for period in PERIODS:
        med, df = regional_stat(period, assign)
        daegu_val = df[df["SIGUNGU_CD"].isin(DAEGU_CODES)]["dec_pct"].median()  # 대구 통합=중앙값

        mr = main_regions.copy()
        mr["val"] = mr["SIGUNGU_CD"].map(lambda c: daegu_val if c == "DAEGU" else med.get(c, np.nan))
        dd = daegu_districts.copy()
        dd["val"] = dd["SIGUNGU_CD"].map(lambda c: med.get(c, np.nan))
        mrf = fine_regions.copy()                            # 대구 자치구까지 세분화
        mrf["val"] = mrf["SIGUNGU_CD"].map(lambda c: med.get(c, np.nan))
        dminx, dminy, dmaxx, dmaxy = daegu_geom.bounds

        # 등간격 공통 구간(메인+삽도 전체 값 기준)
        allv = np.concatenate([mr["val"].dropna().values, dd["val"].dropna().values])
        vmin, vmax = float(np.nanmin(allv)), float(np.nanmax(allv))
        bounds = np.linspace(vmin, vmax, N_CLASSES + 1)
        cmap = plt.get_cmap(CMAP, N_CLASSES)
        norm = matplotlib.colors.BoundaryNorm(bounds, cmap.N)

        def add_vlegend(fig, ax_cb):
            ax_cb.set_axis_off()
            sm = matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap); sm.set_array([])
            cb = fig.colorbar(sm, ax=ax_cb, orientation="vertical", fraction=0.6, aspect=16, pad=0.05)
            cb.set_label("상대 감소율 중앙값 (%)", fontsize=15)
            cb.set_ticks(bounds); cb.set_ticklabels([f"{b:.0f}" for b in bounds])
            cb.ax.tick_params(labelsize=13)

        # ── (A) 메인 + 삽도(옆 배치) + 세로 범례 ──
        fig = plt.figure(figsize=(17, 8.2), facecolor="white")
        gs = fig.add_gridspec(1, 3, width_ratios=[1.7, 1.05, 0.18], wspace=0.0)
        ax = fig.add_subplot(gs[0, 0]); ax_in = fig.add_subplot(gs[0, 1]); ax_cb = fig.add_subplot(gs[0, 2])
        fig.subplots_adjust(left=0.005, right=0.995, top=0.995, bottom=0.005)
        draw_main(ax, mr, cmap, norm, label_fs=17, show_box=True,
                  box_bounds=(dminx, dminy, dmaxx, dmaxy))
        draw_daegu(ax_in, dd, cmap, norm, label_fs=11)
        add_vlegend(fig, ax_cb)
        # 삽도 축척 = 메인 대구 × 확대배율
        INSET_ZOOM = 1.3
        fig.canvas.draw()
        fig_w_in, fig_h_in = fig.get_size_inches()
        mpos = ax.get_position(); mx0, mx1 = ax.get_xlim(); my0, my1 = ax.get_ylim()
        s_main = max((mx1 - mx0) / (mpos.width * fig_w_in), (my1 - my0) / (mpos.height * fig_h_in))
        s_in = s_main / INSET_ZOOM; pad = 0.06
        dw = (dmaxx - dminx) * (1 + 2 * pad); dh = (dmaxy - dminy) * (1 + 2 * pad)
        ax_in.set_xlim(dminx - (dmaxx - dminx) * pad, dmaxx + (dmaxx - dminx) * pad)
        ax_in.set_ylim(dminy - (dmaxy - dminy) * pad, dmaxy + (dmaxy - dminy) * pad)
        ax_in.set_aspect("auto")
        wf = (dw / s_in) / fig_w_in; hf = (dh / s_in) / fig_h_in
        ax_in.set_position([mpos.x0 + mpos.width + 0.005, mpos.y0 + mpos.height / 2 - hf / 2, wf, hf])
        outA = f"{OUT_DIR}/regional_decrease_{period}.png"
        plt.savefig(outA, dpi=200, facecolor="white", bbox_inches="tight", pad_inches=0.02); plt.close(fig)
        print("저장:", outA)

        # ── (B) 삽도 없이, 대구를 자치구로 세분화한 단일 지도 (PPT용) + 세로 범례 ──
        fig = plt.figure(figsize=(13, 8.6), facecolor="white")
        gs = fig.add_gridspec(1, 2, width_ratios=[1, 0.12], wspace=0.0)
        ax = fig.add_subplot(gs[0, 0]); ax_cb = fig.add_subplot(gs[0, 1])
        fig.subplots_adjust(left=0.005, right=0.995, top=0.995, bottom=0.005)
        # 대구 자치구는 라벨이 작게(겹침 방지), 경북 시·군은 크게
        mrf.plot(ax=ax, column="val", cmap=cmap, norm=norm, edgecolor="#2c2c2c",
                 linewidth=1.0, legend=False, missing_kwds={"color": "#eeeeee"})
        for _, r in mrf.iterrows():
            c = r.geometry.representative_point()
            is_daegu = r["SIGUNGU_CD"].startswith("22")
            fs = 11 if is_daegu else 18
            lab = r["SIGUNGU_NM"] + (f"\n{r['val']:.0f}%" if pd.notna(r["val"]) else "")
            ax.annotate(lab, xy=(c.x, c.y), ha="center", va="center", fontsize=fs,
                        fontweight="bold", color="#1a1a1a",
                        path_effects=[pe.withStroke(linewidth=3, foreground="white")])
        ax.set_axis_off()
        add_vlegend(fig, ax_cb)
        outB = f"{OUT_DIR}/regional_decrease_{period}_noinset.png"
        plt.savefig(outB, dpi=200, facecolor="white", bbox_inches="tight", pad_inches=0.02); plt.close(fig)
        print("저장:", outB)

        # ── (C) 삽도를 대구 위치에 겹쳐 배치 + 세로 범례 ──
        fig = plt.figure(figsize=(13, 8.6), facecolor="white")
        gs = fig.add_gridspec(1, 2, width_ratios=[1, 0.12], wspace=0.0)
        ax = fig.add_subplot(gs[0, 0]); ax_cb = fig.add_subplot(gs[0, 1])
        fig.subplots_adjust(left=0.005, right=0.995, top=0.995, bottom=0.005)
        draw_main(ax, mr, cmap, norm, label_fs=19, show_box=False)
        add_vlegend(fig, ax_cb)
        fig.canvas.draw()
        fig_w_in, fig_h_in = fig.get_size_inches()
        mpos = ax.get_position(); mx0, mx1 = ax.get_xlim(); my0, my1 = ax.get_ylim()
        # 대구 bbox의 figure 좌표(겹쳐 배치 기준점)
        def data_to_fig(x, y):
            fx = mpos.x0 + (x - mx0) / (mx1 - mx0) * mpos.width
            fy = mpos.y0 + (y - my0) / (my1 - my0) * mpos.height
            return fx, fy
        ZOOM_C = 2.2
        cxd = (dminx + dmaxx) / 2; cyd = (dminy + dmaxy) / 2
        fcx, fcy = data_to_fig(cxd, cyd)
        s_main = max((mx1 - mx0) / (mpos.width * fig_w_in), (my1 - my0) / (mpos.height * fig_h_in))
        s_in = s_main / ZOOM_C; pad = 0.06
        dw = (dmaxx - dminx) * (1 + 2 * pad); dh = (dmaxy - dminy) * (1 + 2 * pad)
        wf = (dw / s_in) / fig_w_in; hf = (dh / s_in) / fig_h_in
        ax_ov = fig.add_axes([fcx - wf / 2, fcy - hf / 2, wf, hf])
        ax_ov.set_xlim(dminx - (dmaxx - dminx) * pad, dmaxx + (dmaxx - dminx) * pad)
        ax_ov.set_ylim(dminy - (dmaxy - dminy) * pad, dmaxy + (dmaxy - dminy) * pad)
        ax_ov.set_aspect("auto")
        draw_daegu(ax_ov, dd, cmap, norm, label_fs=11)
        outC = f"{OUT_DIR}/regional_decrease_{period}_overlay.png"
        plt.savefig(outC, dpi=200, facecolor="white", bbox_inches="tight", pad_inches=0.02); plt.close(fig)
        print("저장:", outC)

        print(f"  [{period}] 지역 중앙값(%): " +
              ", ".join(f"{n}={v:.0f}" for n, v in zip(mr['SIGUNGU_NM'], mr['val']) if pd.notna(v)))

        # ── 검토: 지역별 유효 격자 수 · 중앙값 · 100%(나쁜날 접근0) 격자 비율 ──
        name_map = dict(zip(sig_t["SIGUNGU_CD"], sig_t["SIGUNGU_NM"]))
        print(f"  [{period}] 지역별 유효격자수 / 중앙값 / 100%격자비율")
        for code, sub in df.groupby("SIGUNGU_CD"):
            v = sub["dec_pct"]
            nm = "대구-" + name_map.get(code, code) if str(code).startswith("22") else name_map.get(code, code)
            print(f"    {nm:<10} n={len(v):>4}  중앙값={v.median():5.0f}%  "
                  f"100%격자={100*(v>=99.999).mean():4.0f}%  평균={v.mean():5.0f}%")


if __name__ == "__main__":
    main()
