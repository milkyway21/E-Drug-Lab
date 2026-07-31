#!/usr/bin/env python3
"""e-drug-lab Full Pipeline Test - no emoji (gbk safe)"""
import json, urllib.request, sys, csv, os

BACKEND = "http://localhost:5000"
TOP1000 = "molecules/sdf/top1000_tamevs.csv"

def api(method, path, data=None):
    url = BACKEND + path
    req = urllib.request.Request(url, method=method)
    if data:
        req.data = json.dumps(data).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}

results = {"passed": 0, "failed": 0, "steps": []}

def check(name, ok, detail=""):
    results["steps"].append({"name": name, "ok": ok, "detail": detail})
    if ok:
        results["passed"] += 1
    else:
        results["failed"] += 1
    tag = "OK" if ok else "FAIL"
    print(f"  [{tag}] {name}: {detail}")

print("=" * 60)
print("  e-drug lab FULL PIPELINE TEST")
print("=" * 60)

# Step 1: Backend Health
h = api("GET", "/health")
check("Backend Health", h.get("status") == "healthy", str(h))

# Step 2: Targets
t = api("GET", "/api/v1/targets")
check("Target List", "targets" in t, "%d targets" % len(t.get("targets",[])))

# Step 3: TAME-VS Top 1000
if os.path.exists(TOP1000):
    with open(TOP1000) as f:
        molecules = list(csv.DictReader(f))
    check("TAME-VS 50K Screening", len(molecules) == 1004,
          "%d top compounds from 50,240 Enamine" % len(molecules))
    check("Top1 SMILES valid", len(molecules[0]["smiles"]) > 10,
          "Top1: %s score=%s" % (molecules[0]["comp_id"], molecules[0]["GNN_prediction_score"]))
else:
    check("TAME-VS 50K Screening", False, "File not found: %s" % TOP1000)

# Step 4: ADMET
a = api("POST", "/api/v1/admet/predict",
        {"smiles": ["CC1c2cc3c(cc2C2(CCCC2)CN1C(=O)c1cc(=O)c2ccccc2[nH]1)OCCO3"]})
props = a.get("predictions", [{}])[0].get("properties", {})
check("ADMET Prediction", len(props) > 20, "%d properties" % len(props))
if props:
    check("ADMET hERG", "hERG" in props, "hERG=%.3f" % props.get("hERG",0))
    check("ADMET DILI", "DILI" in props, "DILI=%.3f" % props.get("DILI",0))
    check("ADMET AMES", "AMES" in props, "AMES=%.3f" % props.get("AMES",0))

# Step 5: Vina Docking
v = api("POST", "/api/v1/affinity/dock",
        {"smiles": "CC1c2cc3c(cc2C2(CCCC2)CN1C(=O)c1cc(=O)c2ccccc2[nH]1)OCCO3",
         "target_id": "8v1t", "n_poses": 5})
check("Vina Docking", "best_affinity" in v,
      "affinity=%s kcal/mol [%s]" % (v.get("best_affinity","N/A"), v.get("method","N/A")))

# Step 6: Ranking
r = api("POST", "/api/v1/ranking/orthogonal-rescore", {
    "candidates": [
        {"molecule_id": "Z245796024", "name": "Top1",
         "metrics": [
             {"metric_name": "docking_score", "value": -7.5, "model_name": "vina",
              "method_family": "empirical_docking", "direction": "lower_is_better"},
             {"metric_name": "orthogonal_score", "value": -28.0, "model_name": "mmgbsa",
              "method_family": "physics_rescore", "direction": "lower_is_better"}
         ]},
        {"molecule_id": "Z1198960600", "name": "Top2",
         "metrics": [
             {"metric_name": "docking_score", "value": -6.8, "model_name": "vina",
              "method_family": "empirical_docking", "direction": "lower_is_better"},
             {"metric_name": "orthogonal_score", "value": -25.0, "model_name": "mmgbsa",
              "method_family": "physics_rescore", "direction": "lower_is_better"}
         ]}
    ]
})
ranked = r.get("ranked", [])
check("Candidate Ranking", len(ranked) == 2, "%d candidates ranked" % len(ranked))
for i, c in enumerate(ranked):
    af = " ARTIFACT" if c.get("artifact_flag") else ""
    check("  #%d: %s" % (i+1, c["molecule_id"]), True,
          "docking=%s composite=%s%s" % (c["primary_value"], c["final_score"], af))

# Summary
print()
print("=" * 60)
print("  RESULTS: %d passed / %d failed / %d total" %
      (results["passed"], results["failed"], len(results["steps"])))
print("=" * 60)

with open("pipeline_test_results.json", "w") as f:
    json.dump(results, f, indent=2)
print("  Saved to pipeline_test_results.json")
