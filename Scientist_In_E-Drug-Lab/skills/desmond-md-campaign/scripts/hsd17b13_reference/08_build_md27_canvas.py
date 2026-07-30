#!/usr/bin/env python3
"""Rebuild the HSD17B13 MD canvas from md27_summary tables."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "05_analysis/md27_summary"
CANVAS = Path(
    "/home/user/.cursor/projects/home-user-Desktop-Ye-DiffDynamic-hsvpol/"
    "canvases/hsd17b13-md12-stability.canvas.tsx"
)

POSE_NOTE = {
    "PASS": "稳定",
    "REVIEW": "边界",
    "FAIL_POSE": "原姿势失败",
}
RETENTION_NOTE = {
    "RETAINED": "接触保留",
    "WEAK_RETENTION": "弱保留",
    "ALT_POSE": "替代姿势",
    "LOST": "离位",
}


def _round(value: float | None, digits: int = 2) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return round(float(value), digits)


def _trace_for(mid: str, traces: pd.DataFrame) -> dict:
    subset = traces[traces["molecule_id"] == mid].sort_values("frame")
    sampled = subset.iloc[::20]
    if len(subset) and (
        sampled.empty or sampled.iloc[-1]["frame"] != subset.iloc[-1]["frame"]
    ):
        sampled = pd.concat([sampled, subset.tail(1)], ignore_index=True)
    return {
        "time": [round(float(x), 1) for x in sampled["time_ns"]],
        "protein": [round(float(x), 2) for x in sampled["protein_ca"]],
        "ligand": [round(float(x), 2) for x in sampled["ligand_wrt_protein"]],
        "internal": [round(float(x), 2) for x in sampled["ligand_wrt_ligand"]],
    }


def _contacts_for(mid: str, contacts: pd.DataFrame) -> list[dict]:
    subset = contacts[
        (contacts["molecule_id"] == mid)
        & (contacts["contact_type"] != "WaterBridge")
    ].head(4)
    rows = []
    for _, row in subset.iterrows():
        rows.append(
            {
                "label": (
                    f"{row['contact_type']}:{row['chain']}-"
                    f"{row['resname']}{int(row['resnum'])}"
                ),
                "occupancy": round(float(row["occupancy"]) * 100, 1),
            }
        )
    return rows


def _compound(row: pd.Series, contacts: pd.DataFrame) -> dict:
    return {
        "rank": int(row["biochemical_rank"]),
        "id": str(row["molecule_id"]),
        "pose": str(row["pose_call"]),
        "retention": str(row["binding_retention"]),
        "proteinP95": _round(row["protein_ca_p95"]),
        "ligandMedian": _round(row["ligand_rmsd_median"]),
        "ligandP95": _round(row["ligand_rmsd_p95"]),
        "ligandLate": _round(row["ligand_rmsd_late_mean"]),
        "directCoverage": _round(row["direct_contact_coverage"] * 100, 1),
        "topContact": str(row["strongest_direct_contact"] or ""),
        "topOccupancy": _round(row["strongest_direct_occupancy"] * 100, 1),
        "xp": _round(row["xp_gscore"]),
        "mmgbsa": _round(row["mmgbsa"], 1),
        "mdScore": _round(row["md_triage_score"], 1),
        "biochemScore": _round(row["biochemical_triage_score"], 1),
        "biochemTier": str(row["biochemical_tier"]),
        "cellScore": _round(row["cellular_triage_score"], 1),
        "cellTier": str(row["cellular_tier"]),
        "exposure": str(row["cell_exposure_risk"]),
        "note": str(row["wetlab_expectation"]),
        "contacts": _contacts_for(str(row["molecule_id"]), contacts),
    }


def _pick_trace_ids(metrics: pd.DataFrame) -> list[str]:
    picks: list[str] = []
    for retention in ("RETAINED", "WEAK_RETENTION", "ALT_POSE", "LOST"):
        subset = metrics[metrics["binding_retention"] == retention]
        for _, row in subset.head(2).iterrows():
            mid = str(row["molecule_id"])
            if mid not in picks:
                picks.append(mid)
    # always include absolute top and worst
    for mid in (
        str(metrics.iloc[0]["molecule_id"]),
        str(metrics.iloc[-1]["molecule_id"]),
    ):
        if mid not in picks:
            picks.append(mid)
    return picks[:8]


def build_canvas_tsx(compounds: list[dict], traces: dict[str, dict]) -> str:
    compounds_json = json.dumps(compounds, ensure_ascii=False, indent=2)
    traces_json = json.dumps(traces, ensure_ascii=False, indent=2)
    n = len(compounds)
    top3 = ", ".join(item["id"] for item in compounds[:3])
    retained = sum(1 for item in compounds if item["retention"] == "RETAINED")
    alternate = sum(1 for item in compounds if item["retention"] == "ALT_POSE")
    lost = sum(1 for item in compounds if item["retention"] == "LOST")
    default_id = compounds[0]["id"] if compounds else "T4965"

    return f'''import {{
  BarChart,
  Callout,
  Card,
  CardBody,
  CardHeader,
  Grid,
  H1,
  H2,
  H3,
  LineChart,
  Pill,
  Row,
  Stack,
  Stat,
  Table,
  Text,
  useCanvasState,
  useHostTheme,
}} from "cursor/canvas";
import type {{ TableRowTone }} from "cursor/canvas";

type Contact = {{
  label: string;
  occupancy: number;
}};

type Compound = {{
  rank: number;
  id: string;
  pose: "PASS" | "REVIEW" | "FAIL_POSE";
  retention: "RETAINED" | "WEAK_RETENTION" | "ALT_POSE" | "LOST";
  proteinP95: number;
  ligandMedian: number;
  ligandP95: number;
  ligandLate: number;
  directCoverage: number;
  topContact: string;
  topOccupancy: number;
  xp: number;
  mmgbsa: number;
  mdScore: number;
  biochemScore: number;
  biochemTier: "A" | "B" | "C" | "D";
  cellScore: number;
  cellTier: "A" | "B" | "C" | "D";
  exposure: "低" | "中" | "高";
  note: string;
  contacts: Contact[];
}};

type Trace = {{
  time: number[];
  protein: number[];
  ligand: number[];
  internal: number[];
}};

const compounds: Compound[] = {compounds_json} as Compound[];

const traces: Record<string, Trace> = {traces_json};

const poseLabel: Record<Compound["pose"], string> = {{
  PASS: "稳定",
  REVIEW: "边界",
  FAIL_POSE: "原姿势失败",
}};

const retentionLabel: Record<Compound["retention"], string> = {{
  RETAINED: "接触保留",
  WEAK_RETENTION: "弱保留",
  ALT_POSE: "替代姿势",
  LOST: "离位",
}};

function rowTone(tier: Compound["biochemTier"]): TableRowTone {{
  if (tier === "A") return "success";
  if (tier === "B") return "info";
  if (tier === "C") return "warning";
  return "danger";
}}

export default function Hsd17b13Md27Stability() {{
  const theme = useHostTheme();
  const [selectedId, setSelectedId] = useCanvasState<string>(
    "selected-trace-27",
    "{default_id}",
  );
  const [tierFilter, setTierFilter] = useCanvasState<string>(
    "tier-filter-27",
    "ALL",
  );
  const selected =
    compounds.find((item) => item.id === selectedId) ?? compounds[0];
  const trace = traces[selectedId] ?? traces["{default_id}"] ?? Object.values(traces)[0];
  const traceIds = Object.keys(traces);
  const filtered =
    tierFilter === "ALL"
      ? compounds
      : compounds.filter((item) => item.biochemTier === tierFilter);

  const retainedCount = {retained};
  const alternateCount = {alternate};
  const lostCount = {lost};

  return (
    <Stack
      gap={{22}}
      style={{{{
        padding: 24,
        maxWidth: 1480,
        margin: "0 auto",
        color: theme.text.primary,
      }}}}
    >
      <Stack gap={{6}}>
        <H1>HSD17B13 · {n}分子 50 ns 动力学稳定性</H1>
        <Text tone="secondary">
          Phase A 全量：2 ns平衡 + 50 ns生产；分析时丢弃生产段前10%（约5 ns）。
          来源：Desmond SEA、Glide XP、Prime MM-GBSA与HepG2风险代理。
        </Text>
      </Stack>

      <Callout tone="success" title="当前结论">
        <Text>
          全量{n}分子已完成。首选梯队：{top3}。
          接触保留 {retained} 个，替代姿势 {alternate} 个，明显离位 {lost} 个。
          分数仅用于相对排序，不预测 IC50。
        </Text>
      </Callout>

      <Grid columns={{5}} gap={{18}}>
        <Stat value="{n} / 27" label="已分析" tone="info" />
        <Stat value={{retainedCount}} label="原口袋接触保留" tone="success" />
        <Stat value={{alternateCount}} label="替代姿势待复核" tone="warning" />
        <Stat value={{lostCount}} label="明显离位" tone="danger" />
        <Stat value="50 ns" label="单条生产轨迹/分子" />
      </Grid>

      <H2>综合筛选分（全{n}）</H2>
      <Card size="lg">
        <CardHeader>MD、酶学与细胞优先级横向比较</CardHeader>
        <CardBody>
          <BarChart
            horizontal
            height={{Math.max(420, {n} * 22)}}
            categories={{compounds.map((item) => item.id)}}
            series={{[
              {{
                name: "MD稳定性筛选分",
                data: compounds.map((item) => item.mdScore),
                tone: "info",
              }},
              {{
                name: "酶学优先分",
                data: compounds.map((item) => item.biochemScore),
                tone: "success",
              }},
              {{
                name: "细胞优先分",
                data: compounds.map((item) => item.cellScore),
                tone: "warning",
              }},
            ]}}
            yMin={{0}}
            yMax={{100}}
            showValues={{false}}
            referenceLines={{[
              {{ value: 75, label: "A级", tone: "success" }},
              {{ value: 60, label: "B级", tone: "info" }},
              {{ value: 45, label: "C级", tone: "warning" }},
            ]}}
          />
          <Text tone="tertiary" size="small">
            横轴：启发式筛选分（0–100）；纵轴：分子。数据范围：单条50 ns生产轨迹。
          </Text>
        </CardBody>
      </Card>

      <H2>{n}分子决策表</H2>
      <Row gap={{8}} wrap>
        {{["ALL", "A", "B", "C", "D"].map((tier) => (
          <Pill
            active={{tierFilter === tier}}
            onClick={{() => setTierFilter(tier)}}
          >
            {{tier === "ALL" ? "全部" : `酶学${{tier}}级`}}
          </Pill>
        ))}}
      </Row>
      <Table
        stickyHeader
        striped
        headers={{[
          "Rank",
          "分子",
          "姿势",
          "结合保留",
          "Lig晚期",
          "Lig p95",
          "Prot Cα p95",
          "直接接触",
          "最强接触",
          "XP",
          "MM-GBSA",
          "酶学",
          "细胞",
          "暴露",
        ]}}
        rows={{filtered.map((item) => [
          item.rank,
          item.id,
          poseLabel[item.pose],
          retentionLabel[item.retention],
          `${{item.ligandLate.toFixed(2)}} Å`,
          `${{item.ligandP95.toFixed(2)}} Å`,
          `${{item.proteinP95.toFixed(2)}} Å`,
          `${{item.directCoverage.toFixed(0)}}%`,
          item.topContact
            ? `${{item.topContact}} (${{item.topOccupancy.toFixed(0)}}%)`
            : "—",
          item.xp.toFixed(2),
          item.mmgbsa.toFixed(1),
          `${{item.biochemTier}} · ${{item.biochemScore.toFixed(1)}}`,
          `${{item.cellTier}} · ${{item.cellScore.toFixed(1)}}`,
          item.exposure,
        ])}}
        rowTone={{filtered.map((item) => rowTone(item.biochemTier))}}
        columnAlign={{[
          "right",
          "left",
          "left",
          "left",
          "right",
          "right",
          "right",
          "right",
          "left",
          "right",
          "right",
          "center",
          "center",
          "center",
        ]}}
        style={{{{ maxHeight: 640 }}}}
      />

      <H2>代表性轨迹与接触</H2>
      <Row gap={{8}} wrap>
        {{traceIds.map((id) => (
          <Pill
            active={{selectedId === id}}
            onClick={{() => setSelectedId(id)}}
          >
            {{id}}
          </Pill>
        ))}}
      </Row>

      <Grid columns="minmax(0, 1.7fr) minmax(300px, 0.8fr)" gap={{18}}>
        <Card size="lg">
          <CardHeader
            trailing={{`${{poseLabel[selected.pose]}} · ${{retentionLabel[selected.retention]}}`}}
          >
            {{selected.id}} RMSD时间序列
          </CardHeader>
          <CardBody>
            <LineChart
              height={{330}}
              categories={{trace.time.map((value) => String(value))}}
              series={{[
                {{
                  name: "蛋白 Cα RMSD",
                  data: trace.protein,
                  tone: "info",
                }},
                {{
                  name: "配体相对蛋白 RMSD",
                  data: trace.ligand,
                  tone: "danger",
                }},
                {{
                  name: "配体内部 RMSD",
                  data: trace.internal,
                  tone: "warning",
                }},
              ]}}
              beginAtZero
              referenceLines={{[
                {{ value: 2, label: "配体稳定参考 2 Å", tone: "success" }},
                {{ value: 3.5, label: "复核线 3.5 Å", tone: "warning" }},
              ]}}
            />
            <Text tone="tertiary" size="small">
              横轴：生产时间（ns，下采样）；纵轴：RMSD（Å）。来源：SEA PL_RMSD.dat。
            </Text>
          </CardBody>
        </Card>

        <Stack gap={{14}}>
          <Card>
            <CardHeader trailing={{`${{selected.directCoverage.toFixed(0)}}%`}}>
              {{selected.id}} 直接接触
            </CardHeader>
            <CardBody>
              <Table
                framed={{false}}
                headers={{["残基/类型", "占有率"]}}
                rows={{selected.contacts.map((contact) => [
                  contact.label,
                  `${{contact.occupancy.toFixed(1)}}%`,
                ])}}
                columnAlign={{["left", "right"]}}
              />
            </CardBody>
          </Card>
          <Callout
            tone={{
              selected.biochemTier === "A"
                ? "success"
                : selected.biochemTier === "D"
                  ? "danger"
                  : "warning"
            }}
            title={{`${{selected.id}} 湿实验预期`}}
          >
            {{selected.note}}
          </Callout>
        </Stack>
      </Grid>

      <H2>湿实验建议</H2>
      <Grid columns={{2}} gap={{20}}>
        <Stack gap={{8}}>
          <H3>建议顺序</H3>
          <Text>
            1. 首批酶学：前三名（{top3}）；第二批覆盖其余 A/B 级。
          </Text>
          <Text>
            2. 替代姿势分子先目视终态，再决定是否酶学。
          </Text>
          <Text>
            3. 细胞阶段优先暴露风险低的 A 级分子，并同步活率。
          </Text>
        </Stack>
        <Stack gap={{8}}>
          <H3>解释边界</H3>
          <Callout tone="warning" title="不能直接预测IC50">
            单条50 ns轨迹只支持姿势保持与接触保留判断；置信度最高为中等。
          </Callout>
          <Text>
            完整表：`HSD17B13_MD/05_analysis/md27_summary/`。
          </Text>
        </Stack>
      </Grid>
    </Stack>
  );
}}
'''


def main() -> None:
    metrics = pd.read_csv(SUMMARY / "md27_metrics.csv")
    contacts = pd.read_csv(SUMMARY / "md27_contacts.csv")
    traces_table = pd.read_csv(SUMMARY / "md27_rmsd_traces.csv")
    compounds = [_compound(row, contacts) for _, row in metrics.iterrows()]
    trace_ids = _pick_trace_ids(metrics)
    traces = {mid: _trace_for(mid, traces_table) for mid in trace_ids}
    CANVAS.parent.mkdir(parents=True, exist_ok=True)
    CANVAS.write_text(build_canvas_tsx(compounds, traces))
    print(f"Wrote canvas with n={len(compounds)} -> {CANVAS}")


if __name__ == "__main__":
    main()
