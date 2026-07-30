#!/usr/bin/env python3
"""快速跑 E41a（GRPO ens=10, 论文原版配置）。

修复已知的 CUDA label 越界问题，添加防御措施。
"""
import json, os, sys, time
import numpy as np
import torch
from pathlib import Path

GLARE_ROOT = "/data/ye/diffgui/third_party/GLARE"
os.chdir(GLARE_ROOT)
sys.path.insert(0, GLARE_ROOT)

# Stubs
import types
try: import torch_sparse  # noqa
except:
    ts=types.ModuleType("torch_sparse")
    try:
        from torch_geometric.typing import SparseTensor as _ST
        if _ST is not None: ts.SparseTensor=_ST
    except: pass
    sys.modules["torch_sparse"]=ts
try: import captum  # noqa
except:
    cm,am=types.ModuleType("captum"),types.ModuleType("captum.attr")
    class S:
        def __init__(s,*a,**k): pass
        def attribute(s,*a,**k): return torch.zeros_like(a[0]),torch.tensor(0.0)
    am.IntegratedGradients=S;cm.attr=am
    sys.modules["captum"]=cm;sys.modules["captum.attr"]=am

from argparse import Namespace
from model import Ensemble
from acquisition import acquire
from utils.utils import molecular_graph_featurizer, smiles_to_ecfp, to_torch_dataloader, random_baseline, check_featurizability
from torch.utils.data import WeightedRandomSampler
from rdkit import Chem

def norm(smi):
    mol=Chem.MolFromSmiles(smi)
    return Chem.MolToSmiles(mol) if mol else ""

OUTPUT_DIR = Path("/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e41_al")
SWXDS_CSV = "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e41_al/swxds_250k_smiles.csv"
PATENT_CSV = "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/data/processed/patent_403_cleaned.csv"
WETLAB_CSV = "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e26_patent_320_83_20260630/data/new_13_molecules.csv"
R2_TRACKING = "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e41_al/r2_smiles_tracking.json"
POSITIVE_IDS = {"0228390", "0228414", "LXC-106"}

with open(R2_TRACKING) as f: r2_map = json.load(f)["molecules"]
r2_smiles = set(r2_map.values())

import pandas as pd
seen=set(); pool=[]
# swxds
for i,row in pd.read_csv(SWXDS_CSV).iterrows():
    if i>=10000: break
    c=norm(str(row["smiles"]))
    if c and c not in seen: seen.add(c); pool.append((c,0,False,""))
# patent
for _,row in pd.read_csv(PATENT_CSV).iterrows():
    c=norm(str(row["canonical_smiles"]))
    if not c or c in seen: continue
    seen.add(c); pool.append((c,int(row["label_active"]),c in r2_smiles,f"PAT-{row.get('molecule_id','')}"))
# wetlab
for _,row in pd.read_csv(WETLAB_CSV).iterrows():
    c=norm(str(row["SMILES"]))
    if not c or c in seen: continue
    lab=1 if str(row["SDF_ID"]) in POSITIVE_IDS else 0
    seen.add(c); pool.append((c,lab,c in r2_smiles,str(row["SDF_ID"])))
# R2 explicit
for mid,smi in r2_map.items():
    c=norm(str(smi))
    if not c: continue
    if c in seen:
        for j,(s,l,r,m) in enumerate(pool):
            if s==c: pool[j]=(s,l,True,mid); break
    else: seen.add(c); pool.append((c,1,True,mid))

print(f"Pool: {len(pool)} mols ({sum(1 for _,l,_,_ in pool if l==1)} actives, {sum(1 for _,_,r,_ in pool if r)} R2)")

# Build graphs
print("Building graphs...")
graphs,labels_list,smiles_list=[],[],[]
for smi,lab,is_r2,mid in pool:
    if not check_featurizability(smi): continue
    fp=smiles_to_ecfp([smi],silent=True)
    g=molecular_graph_featurizer(smi,y=lab,fp=fp[0])
    if isinstance(g,str): continue
    g.fp=torch.tensor([fp[0]],dtype=torch.float32)
    g.xp=g.x; g.edgep_index=g.edge_index
    g.edgep_attr=getattr(g,"edge_attr",torch.empty((0,2),dtype=torch.long))
    graphs.append(g); labels_list.append(lab); smiles_list.append(smi)
print(f"  {len(graphs)} graphs")

labels_t=torch.tensor(labels_list,dtype=torch.long)
smiles_arr=np.array(smiles_list)
n_total=len(graphs)

# Active Learning
args=Namespace(architecture="ginl",strategy="grpo",epochs=10,hidden_dim=1024,output_dim=2,
    mol_emb_dim=130,lr=3e-4,weight_decay=0.0,train_batch_size=64,infer_batch_size=512,
    ensemble_size=10,seed=0,anchored=True,l2_lambda=3e-4,grpo_lambda=7e-2,grpo_epsilon=2e-1,
    grpo_beta=1e-2,retrain=1,mode="a",cuda="0",
    mlp_fc_layer=3,gin_graph_conv_layer=3,gin_x_fc_layer=3,gin_fp_fc_layer=3,
    gcn_graph_conv_layer=5,gcn_x_fc_layer=3,gine_graph_conv_layer=3,gine_x_fc_layer=1,gine_fp_fc_layer=1,
    pretrain_file="",model_save_file="",disable_ig=False)

rng=np.random.default_rng(42)
hit_idx=np.where(labels_t.numpy()==1)[0]
start_hit=rng.choice(hit_idx,size=1,replace=False)
remain_idx=np.array([i for i in range(n_total) if i not in start_hit])
start_other=rng.choice(remain_idx,size=63,replace=False)
train_idx=np.concatenate([start_hit,start_other])
train_idx=rng.permutation(train_idx).tolist()
screen_idx=[i for i in range(n_total) if i not in train_idx]

print(f"Start: {len(train_idx)} mols, hits={int((labels_t[train_idx]==1).sum())}")
print(f"Screening: {len(screen_idx)} mols")

for cycle_i in range(1, 3):
    t0=time.time()

    # Build balanced dataloader
    train_graphs=[graphs[i] for i in train_idx]
    train_y=labels_t[train_idx]
    # Defensive: clamp labels
    train_y=train_y.clamp(0,1)
    n_pos=int((train_y==1).sum()); n_neg=int((train_y==0).sum())
    cw=[1-n_pos/max(len(train_y),1),1-n_neg/max(len(train_y),1)]
    weights=[cw[int(yi)] for yi in train_y]
    sampler=WeightedRandomSampler(weights,num_samples=len(train_y),replacement=True)
    train_loader=to_torch_dataloader(train_graphs,train_y.numpy(),
        batch_size=64,sampler=sampler,shuffle=False,pin_memory=False)

    # Screen dataloader
    screen_graphs=[graphs[i] for i in screen_idx]
    screen_y=labels_t[screen_idx].numpy()
    screen_loader=to_torch_dataloader(screen_graphs,screen_y,
        batch_size=512,shuffle=False,pin_memory=False)

    # Train
    model=Ensemble(args)
    model.train(train_loader)

    # Predict screen
    screen_logits=model.predict(screen_loader)

    # GRPO select
    mean_probs=torch.mean(torch.exp(screen_logits),dim=1)[:,1].cpu()
    random_val=torch.rand(mean_probs.shape[0])
    pick_flag=torch.where(mean_probs-random_val>0,
        torch.ones_like(mean_probs),torch.zeros_like(mean_probs))
    scored=mean_probs+pick_flag
    local_pick=torch.argsort(scored,descending=True)[:64]
    screen_smiles=smiles_arr[screen_idx]
    smiles_pick=screen_smiles[local_pick.cpu().numpy()]

    # Expand training set
    for s in smiles_pick:
        idx=int(np.where(smiles_arr==s)[0][0])
        if idx not in train_idx:
            train_idx.append(idx)
            screen_idx.remove(idx)

    n_hits=int((labels_t[train_idx]==1).sum())
    elapsed=time.time()-t0
    print(f"  Cycle {cycle_i}/2: +{len(train_idx)} mols, hits={n_hits}, time={elapsed:.0f}s")

n_screen=len(train_idx)
baseline=random_baseline(int((labels_t==1).sum()),64,64,n_total,n_screen)
ef=[h/b for h,b in zip(labels_t[train_idx].tolist(),baseline)]
print(f"\nFinal: {n_hits} hits in {n_screen} screened, EF={ef[-1]:.3f}")

result={"scheme":"E41a","label":"GRPO ens=10 (论文原版)","strategy":"grpo",
    "ensemble_size":10,"total_hit_discover":[h.item() if hasattr(h,'item') else h for h in [int((labels_t[train_idx[:64]]==1).sum()),n_hits]],
    "total_mol_screen":[64,n_screen],"enrichment_factor":ef}

out=OUTPUT_DIR/"e41a_result.json"
with open(out,"w") as f: json.dump(result,f,indent=2,default=str)
print(f"✅ Saved: {out}")
