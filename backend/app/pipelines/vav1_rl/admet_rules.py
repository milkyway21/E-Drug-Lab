"""ADMET 22 项 pass/warning/fail 分类规则 + 多点剔除逻辑。

输入 admet_service.predict_batch 返回的 properties dict（admet-ai 原始值）。
admet-ai 的输出类型：
  - 分类端点（_Substrate/_Inhibitor/BBB/AMES/hERG/DILI/Skin/Carcinogens/HIA/Pgp）→ 0-1 概率，0.5 阈值
  - 回归端点（Caco-2/Lipophilicity/Solubility/PPBR/VDss/Half_Life/Clearance/LD50）→ 原始数值

关键毒性 endpoint：AMES / hERG / DILI / Carcinogens_Lagunin / Skin_Reaction / LD50_Zhu。
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# 分类端点：admet-ai 输出 P(positive) ∈ [0,1]
#   positive_is_bad=True  → P≥0.5 为 fail（毒性/不良）
#   positive_is_bad=False → P<0.5 为 fail（应具备的性质缺失）
# ---------------------------------------------------------------------------
CLASSIFICATION_ENDPOINTS = {
    "HIA_Hou":               {"positive_is_bad": False, "is_key_toxic": False},
    "Pgp_Substrate_Martin":  {"positive_is_bad": False, "is_key_toxic": False},
    "Pgp_Inhibitor_Martin":  {"positive_is_bad": True,  "is_key_toxic": False},
    "CYP2C9_Substrate_CarbonMangels":  {"positive_is_bad": False, "is_key_toxic": False},
    "CYP2D6_Substrate_CarbonMangels":  {"positive_is_bad": False, "is_key_toxic": False},
    "CYP3A4_Substrate_CarbonMangels":  {"positive_is_bad": False, "is_key_toxic": False},
    "CYP2C9_Inhibitor_Ditvi": {"positive_is_bad": True, "is_key_toxic": False},
    "CYP2D6_Inhibitor_Ditvi": {"positive_is_bad": True, "is_key_toxic": False},
    "CYP3A4_Inhibitor_Ditvi": {"positive_is_bad": True, "is_key_toxic": False},
    "BBB_Martins":           {"positive_is_bad": True,  "is_key_toxic": False},
    "Carcinogens_Lagunin":   {"positive_is_bad": True,  "is_key_toxic": True},
    "AMES":                  {"positive_is_bad": True,  "is_key_toxic": True},
    "DILI":                  {"positive_is_bad": True,  "is_key_toxic": True},
    "hERG":                  {"positive_is_bad": True,  "is_key_toxic": True},
    "Skin_Reaction":         {"positive_is_bad": True,  "is_key_toxic": True},
}

# ---------------------------------------------------------------------------
# 回归端点：admet-ai 输出原始数值。
#   good_range = [lo, hi]：在范围内 pass；超出 → warning
#   low_fail：value <= low_fail → fail（值过小，如 LD50 过低=高毒）
#   high_fail：value >= high_fail → fail（值过大，如 LogD 过高）
# LD50 单位 -log(mol/kg)，越大越安全；<=0.5 视为高毒（关键毒性 severe fail）
# ---------------------------------------------------------------------------
REGRESSION_ENDPOINTS = {
    "Caco-2_Wang":             {"good_range": (-5.5, -4.0), "low_fail": None,    "high_fail": None,   "is_key_toxic": False},
    "Lipophilicity_AstraZeneca": {"good_range": (1.0, 3.5),  "low_fail": None,    "high_fail": 5.0,   "is_key_toxic": False},
    "Solubility_AqSolDB":      {"good_range": (-4.0, -0.5), "low_fail": None,    "high_fail": None,   "is_key_toxic": False},
    "PPBR_AZ":                 {"good_range": (70, 99),     "low_fail": None,    "high_fail": None,   "is_key_toxic": False},
    "VDss_Lombardo":           {"good_range": (0.5, 5.0),   "low_fail": None,    "high_fail": None,   "is_key_toxic": False},
    "Half_Life_Obach":         {"good_range": (0.5, 8.0),   "low_fail": None,    "high_fail": None,   "is_key_toxic": False},
    "Clearance_Hepatocyte_AZ": {"good_range": (0.5, 15.0),  "low_fail": None,    "high_fail": None,   "is_key_toxic": False},
    "Clearance_Microsome_AZ":  {"good_range": (0.5, 15.0),  "low_fail": None,    "high_fail": None,   "is_key_toxic": False},
    "LD50_Zhu":                {"good_range": (0.5, 5.0),   "low_fail": 0.0,     "high_fail": None,   "is_key_toxic": True},
}

SEVERE_PROB_THRESHOLD = 0.7
FAIL_PROB_THRESHOLD = 0.5
WARN_PROB_THRESHOLD = 0.3


def _classify_classification(name: str, value: float, meta: dict) -> tuple[str, bool, bool]:
    positive_is_bad = meta["positive_is_bad"]
    is_key = meta.get("is_key_toxic", False)
    if positive_is_bad:
        # 关键毒性：只有 severe fail（P>=0.7）才判 fail 并剔除；普通 fail（0.5-0.7）降级为 warning
        if value >= SEVERE_PROB_THRESHOLD and is_key:
            return "fail", True, True
        if value >= FAIL_PROB_THRESHOLD:
            # 关键毒性的普通 fail 放宽为 warning（不再直接剔）
            if is_key:
                return "warning", False, False
            return "fail", False, True
        if value >= WARN_PROB_THRESHOLD:
            return "warning", False, False
        return "pass", False, False
    else:
        if value >= 0.5:
            return "pass", False, False
        if value >= WARN_PROB_THRESHOLD:
            return "warning", False, False
        return "fail", False, True


def _classify_regression(name: str, value: float, meta: dict) -> tuple[str, bool, bool]:
    lo, hi = meta["good_range"]
    is_key = meta.get("is_key_toxic", False)
    low_fail = meta.get("low_fail")
    high_fail = meta.get("high_fail")
    if low_fail is not None and value <= low_fail:
        return "fail", is_key, True
    if high_fail is not None and value >= high_fail:
        return "fail", is_key, True
    if lo <= value <= hi:
        return "pass", False, False
    return "warning", False, False


def classify(properties: dict) -> dict:
    labels: dict[str, str] = {}
    severe_fails: list[str] = []
    fails: list[str] = []
    warnings: list[str] = []
    key_toxic_fails: list[str] = []

    for name, meta in CLASSIFICATION_ENDPOINTS.items():
        if name not in properties:
            continue
        try:
            val = float(properties[name])
        except (TypeError, ValueError):
            continue
        label, is_severe, is_fail = _classify_classification(name, val, meta)
        labels[name] = label
        if is_fail:
            fails.append(name)
            if meta.get("is_key_toxic"):
                key_toxic_fails.append(name)
            if is_severe:
                severe_fails.append(name)
        elif label == "warning":
            warnings.append(name)

    for name, meta in REGRESSION_ENDPOINTS.items():
        if name not in properties:
            continue
        try:
            val = float(properties[name])
        except (TypeError, ValueError):
            continue
        label, is_severe, is_fail = _classify_regression(name, val, meta)
        labels[name] = label
        if is_fail:
            fails.append(name)
            if meta.get("is_key_toxic"):
                key_toxic_fails.append(name)
            if is_severe:
                severe_fails.append(name)
        elif label == "warning":
            warnings.append(name)

    severe_fail_count = len(severe_fails)
    fail_count = len(fails)
    warning_count = len(warnings)

    reject_reasons = []
    rejected = False
    # 放宽：severe_fail>=3 / total_fail>=6 / 关键毒性 severe fail 才剔除
    if severe_fail_count >= 3:
        rejected = True
        reject_reasons.append(f"severe_fail_count={severe_fail_count}≥3 ({severe_fails})")
    if fail_count >= 6:
        rejected = True
        reject_reasons.append(f"total_fail_count={fail_count}≥6 ({fails})")
    # 关键毒性 endpoint 只有 severe fail（已含在 severe_fails 里）才触发剔除，普通 fail 已降级为 warning
    key_severe = [e for e in severe_fails if e in {"AMES", "hERG", "DILI", "Carcinogens_Lagunin", "Skin_Reaction", "LD50_Zhu"}]
    if len(key_severe) >= 2:
        rejected = True
        reject_reasons.append(f"关键毒性 severe fail>=2: {key_severe}")

    penalty = warning_count * 1 + (fail_count - severe_fail_count) * 3 + severe_fail_count * 8

    return {
        "endpoint_labels": labels,
        "admet_warning_count": warning_count,
        "admet_fail_count": fail_count,
        "admet_severe_fail_count": severe_fail_count,
        "admet_pass_flag": not rejected,
        "admet_reject_reason": "; ".join(reject_reasons) if rejected else None,
        "admet_penalty": penalty,
        "key_toxic_fails": key_toxic_fails,
        "severe_fails": severe_fails,
        "all_fails": fails,
        "all_warnings": warnings,
    }


def classify_batch(properties_list: list[dict]) -> list[dict]:
    return [classify(p) for p in properties_list]


def endpoint_summary() -> dict:
    return {
        "classification": CLASSIFICATION_ENDPOINTS,
        "regression": REGRESSION_ENDPOINTS,
        "severe_prob_threshold": SEVERE_PROB_THRESHOLD,
        "fail_prob_threshold": FAIL_PROB_THRESHOLD,
        "warn_prob_threshold": WARN_PROB_THRESHOLD,
    }
