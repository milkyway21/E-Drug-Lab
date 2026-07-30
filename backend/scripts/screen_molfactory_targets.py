#!/usr/bin/env python3
"""
MolFactory 目标分子筛选 + 排名脚本
=====================================
1. 从 similar mols/ 图片名解析 (excel_id, csv_id, similarity) 三元组
2. 在 3 个 similarity CSV 中匹配（excel_id + csv_id + tanimoto 三者都对应）
3. 提取目标分子的 canonical SMILES
4. 合并 3 个 MolFactory CSV 作为筛选池
5. 用 E32 最强权重（grpo_sup cycle_7 + greedy_sup cycle_7）对全池排名
6. 统计目标分子在排名中的位置（平均排名 / 中位排名 / top-N%）
"""

import os, sys, re, json, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict

os.environ['CUDA_VISIBLE_DEVICES'] = '5'  # 用 GPU 5 做推理

ROOT = Path('/data/ye/e-drug-lab')
MOLFACTORY = ROOT / 'molfactory'
SIMILAR_MOLS_DIR = MOLFACTORY / 'similar mols'
OUTPUT_DIR = ROOT / 'backend/outputs/vav1_rl_project/validation/molfactory_screen_20260706'

# ── E32 最强权重 ──
BEST_CHECKPOINTS = {
    'e32_grpo_sup': str(ROOT / 'backend/outputs/vav1_rl_project/validation/glare_e32_paper_al_20260630/e32_grpo_sup/checkpoints/cycle_7.pt'),
    'e32_greedy_sup': str(ROOT / 'backend/outputs/vav1_rl_project/validation/glare_e32_paper_al_20260630/e32_greedy_sup/checkpoints/cycle_7.pt'),
}

# ── 3 个 similarity pair CSV ──
SIMILARITY_CSVS = [
    MOLFACTORY / 'MolFactory_0702_0148_similarity_pairs_noH_all.csv',
    MOLFACTORY / 'MolFactory_0702_0404_similarity_pairs_noH_all.csv',
    MOLFACTORY / 'similarity_pairs_noH_all.csv',
]

# ── 3 个 MolFactory 主 CSV（筛选池）──
POOL_CSVS = [
    MOLFACTORY / 'MolFactory_0702_0137.csv',
    MOLFACTORY / 'MolFactory_0702_0148.csv',
    MOLFACTORY / 'MolFactory_0702_0404.csv',
]


def parse_image_filenames():
    """解析 similar mols/ 目录下所有 PNG 文件名，返回 (excel_id, csv_id, similarity) 列表。"""
    triples = []
    pattern = re.compile(r'^\d+_(.+?)__MolFactory_(.+?)__sim_(.+?)\.png$')
    for fname in sorted(os.listdir(SIMILAR_MOLS_DIR)):
        m = pattern.match(fname)
        if m:
            excel_id = m.group(1)
            csv_id = m.group(2)
            sim = float(m.group(3))
            triples.append((excel_id, csv_id, sim, fname))
        else:
            print(f'  ⚠ 无法解析: {fname}')
    return triples


def load_similarity_dfs():
    """加载 3 个 similarity CSV，统一列名，返回合并 DataFrame。"""
    frames = []
    for csv_path in SIMILARITY_CSVS:
        df = pd.read_csv(csv_path)
        # 统一 excel_id, csv_id 为字符串
        df['excel_id'] = df['excel_id'].astype(str).str.strip()
        df['csv_id'] = df['csv_id'].astype(str).str.strip()
        # 统一相似度列名
        if 'tanimoto_morgan_r2_2048_noH' in df.columns:
            df['tanimoto'] = df['tanimoto_morgan_r2_2048_noH']
        df['source_csv'] = csv_path.name
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    print(f'相似度 CSV 合并: {len(combined)} 行 (来自 {len(frames)} 个文件)')
    return combined


def match_targets(triples, sim_df):
    """
    在 similarity DataFrame 中匹配三元组。
    匹配条件：excel_id 相同 AND csv_id 相同 AND tanimoto 相似度一致（四舍五入到 3 位小数）。
    返回匹配到的 canonical SMILES 列表。
    """
    matched = []
    sim_df['tanimoto_rounded'] = sim_df['tanimoto'].round(3)

    for excel_id, csv_id, img_sim, fname in triples:
        img_sim_rounded = round(img_sim, 3)
        candidates = sim_df[
            (sim_df['excel_id'] == excel_id) &
            (sim_df['csv_id'] == csv_id) &
            (sim_df['tanimoto_rounded'] == img_sim_rounded)
        ]
        if len(candidates) == 0:
            # 尝试更宽松的匹配（相似度 ±0.001）
            candidates = sim_df[
                (sim_df['excel_id'] == excel_id) &
                (sim_df['csv_id'] == csv_id) &
                (sim_df['tanimoto_rounded'].between(img_sim_rounded - 0.001, img_sim_rounded + 0.001))
            ]
        if len(candidates) == 0:
            print(f'  ❌ 未匹配: {fname} (excel={excel_id}, csv={csv_id}, sim={img_sim})')
            continue
        if len(candidates) > 1:
            print(f'  ⚠ 多个匹配 ({len(candidates)}): {fname}，取第一个')

        row = candidates.iloc[0]
        # csv_smiles_noH_canonical 是 MolFactory 分子的 SMILES
        smiles = str(row.get('csv_smiles_noH_canonical', '')).strip()
        if not smiles:
            # fallback: 用 csv_smiles_original
            smiles = str(row.get('csv_smiles_original', '')).strip()
        if not smiles:
            print(f'  ⚠ 无 SMILES: {fname}')
            continue

        matched.append({
            'image': fname,
            'excel_id': excel_id,
            'csv_id': csv_id,
            'img_similarity': img_sim,
            'csv_tanimoto': row['tanimoto'],
            'smiles': smiles,
            'excel_pDC50': row.get('excel_pDC50', None),
            'source_csv': row.get('source_csv', ''),
        })
        print(f'  ✅ {fname} → SMILES={smiles[:60]}...')

    return matched


def build_screening_pool():
    """合并 3 个 MolFactory 主 CSV，去重，返回 (DataFrame, smiles_list)。"""
    frames = []
    for csv_path in POOL_CSVS:
        df = pd.read_csv(csv_path)
        df['source'] = csv_path.name
        # 统一 SMILES 列名
        if 'smiles' in df.columns:
            df.rename(columns={'smiles': 'SMILES'}, inplace=True)
        frames.append(df)

    pool = pd.concat(frames, ignore_index=True)
    print(f'\n筛选池原始: {len(pool)} 分子 (来自 {len(frames)} 个 CSV)')

    # 去重（按 SMILES）
    pool['SMILES_clean'] = pool['SMILES'].astype(str).str.strip()
    before = len(pool)
    pool = pool.drop_duplicates(subset='SMILES_clean', keep='first').copy()
    print(f'去重后: {len(pool)} 分子 (去除 {before - len(pool)} 重复)')

    return pool


def check_targets_in_pool(matched, pool):
    """检查目标分子是否在筛选池中，并标记。"""
    pool_smiles_set = set(pool['SMILES_clean'])
    for t in matched:
        t['in_pool'] = t['smiles'] in pool_smiles_set
        if not t['in_pool']:
            print(f'  ⚠ 目标不在池中: {t["image"]} SMILES={t["smiles"][:60]}')


def rank_with_glare(checkpoint_path, smiles_list, label, ensemble_size=3):
    """用 GLARE checkpoint 对 SMILES 列表排序。返回 {smiles: rank} 映射。"""
    from app.pipelines.vav1_rl.glare_gnn_adapter import query

    print(f'\n🔮 GLARE 推理: {label} (checkpoint={Path(checkpoint_path).parent.name}/{Path(checkpoint_path).name})')
    print(f'   分子数: {len(smiles_list)}, ensemble={ensemble_size}')

    result = query(checkpoint_path, smiles_list, ensemble_size=ensemble_size)

    if not result.get('ok', False) and 'ranked' not in result:
        print(f'   ❌ GLARE query 失败: {result.get("error", str(result)[:500])}')
        return None

    ranked = result.get('ranked', [])
    if not ranked:
        print('   ❌ 返回空结果')
        return None

    # Build rank map: SMILES → rank (1 = best)
    rank_map = {}
    for i, item in enumerate(ranked):
        smi = item.get('smiles', '') or item.get('canonical_smiles', '')
        score = item.get('select_prob') or item.get('glare_select_prob') or item.get('score', 0)
        rank_map[smi] = {
            'rank': i + 1,
            'score': float(score) if score is not None else None,
        }

    print(f'   ✅ 排名完成: {len(rank_map)} 分子已排序')
    return rank_map, ranked


def compute_target_ranks(matched, rank_map, ranked_list, pool_size):
    """计算目标分子在排名中的位置。"""
    results = []
    for t in matched:
        smi = t['smiles']
        info = rank_map.get(smi, None)
        if info is None:
            # 尝试找最接近的 SMILES（可能有规范化差异）
            # 暂时标记为未找到
            t['rank'] = None
            t['score'] = None
            t['percentile'] = None
            results.append(t)
            continue

        rank = info['rank']
        score = info['score']
        percentile = round(100 * rank / pool_size, 2)

        t['rank'] = rank
        t['score'] = score
        t['percentile'] = percentile
        results.append(t)

    return results


def print_report(matched_results, pool_size, label):
    """打印排名报告。"""
    found = [t for t in matched_results if t.get('rank') is not None]
    missing = [t for t in matched_results if t.get('rank') is None]

    print(f'\n{"="*80}')
    print(f'📊 排名报告 — {label}')
    print(f'{"="*80}')
    print(f'筛选池总数: {pool_size}')
    print(f'目标分子总数: {len(matched_results)}')
    print(f'成功排名: {len(found)}')
    print(f'未找到: {len(missing)}')

    if missing:
        print(f'\n⚠ 未在排名中找到的分子:')
        for t in missing:
            print(f'   {t["image"]}: SMILES={t["smiles"][:60]}')

    if found:
        ranks = [t['rank'] for t in found]
        percentiles = [t['percentile'] for t in found]
        scores = [t['score'] for t in found if t['score'] is not None]

        print(f'\n── 排名统计 ──')
        print(f'平均排名: {np.mean(ranks):.1f} / {pool_size}')
        print(f'中位排名: {np.median(ranks):.1f}')
        print(f'最佳排名: {min(ranks)} (top {min(percentiles):.2f}%)')
        print(f'最差排名: {max(ranks)} (top {max(percentiles):.2f}%)')
        print(f'平均百分位: top {np.mean(percentiles):.2f}%')
        print(f'中位百分位: top {np.median(percentiles):.2f}%')

        if scores:
            print(f'平均 GLARE score: {np.mean(scores):.4f}')
            print(f'中位 GLARE score: {np.median(scores):.4f}')
            print(f'最高 score: {max(scores):.4f}')
            print(f'最低 score: {min(scores):.4f}')

        # Top-N 分布
        top10 = sum(1 for r in ranks if r <= pool_size * 0.10)
        top25 = sum(1 for r in ranks if r <= pool_size * 0.25)
        top50 = sum(1 for r in ranks if r <= pool_size * 0.50)
        print(f'\n── 分位数分布 ──')
        print(f'Top 10%:  {top10}/{len(found)} ({100*top10/len(found):.1f}%)')
        print(f'Top 25%:  {top25}/{len(found)} ({100*top25/len(found):.1f}%)')
        print(f'Top 50%:  {top50}/{len(found)} ({100*top50/len(found):.1f}%)')

        # 详细列表
        print(f'\n── 逐分子详情（按排名排序）──')
        sorted_found = sorted(found, key=lambda t: t['rank'])
        print(f'{"排名":>6s} {"百分位":>8s} {"Score":>8s} {"excel_id":>12s} {"csv_id":>8s} {"sim":>7s} {"pDC50":>8s}  Image')
        print('-' * 90)
        for t in sorted_found:
            pdc50 = t.get('excel_pDC50', '')
            pdc50_str = f'{pdc50:.4f}' if isinstance(pdc50, (int, float)) and not pd.isna(pdc50) else str(pdc50)[:8]
            print(f'{t["rank"]:>6d} {t["percentile"]:>7.2f}% {t["score"] or 0:>8.4f} {t["excel_id"]:>12s} {t["csv_id"]:>8s} {t["img_similarity"]:>6.3f} {pdc50_str:>8s}  {t["image"]}')


# ── Main ──
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / 'backend'))

    # ── Step 1: 解析图片名 ──
    print('=' * 80)
    print('Step 1: 解析 similar mols/ 图片文件名')
    print('=' * 80)
    triples = parse_image_filenames()
    print(f'\n解析到 {len(triples)} 个目标分子')

    # ── Step 2: 在 similarity CSV 中匹配 ──
    print(f'\n{"="*80}')
    print('Step 2: 在 similarity pair CSV 中匹配')
    print('=' * 80)
    sim_df = load_similarity_dfs()
    matched = match_targets(triples, sim_df)
    print(f'\n匹配成功: {len(matched)}/{len(triples)}')

    if not matched:
        print('❌ 无任何匹配，退出')
        return

    # ── Step 3: 构建筛选池 ──
    print(f'\n{"="*80}')
    print('Step 3: 构建 MolFactory 合并筛选池')
    print('=' * 80)
    pool = build_screening_pool()
    pool_smiles = pool['SMILES_clean'].tolist()

    # ── Step 4: 检查目标在池中 ──
    print(f'\n{"="*80}')
    print('Step 4: 检查目标分子是否在筛选池中')
    print('=' * 80)
    check_targets_in_pool(matched, pool)

    pool_targets = [t for t in matched if t['in_pool']]
    print(f'\n在池中的目标分子: {len(pool_targets)}/{len(matched)}')

    # ── Step 5: GLARE 排名 ──
    for ckpt_name, ckpt_path in BEST_CHECKPOINTS.items():
        if not Path(ckpt_path).exists():
            print(f'\n⚠ Checkpoint 不存在: {ckpt_path}，跳过')
            continue

        rank_result = rank_with_glare(ckpt_path, pool_smiles, ckpt_name)
        if rank_result is None:
            continue

        rank_map, ranked_list = rank_result

        # ── Step 6: 计算目标排名 ──
        results = compute_target_ranks(pool_targets, rank_map, ranked_list, len(pool))
        print_report(pool_targets, len(pool), ckpt_name)

        # ── Save results ──
        out_json = OUTPUT_DIR / f'{ckpt_name}_target_ranks.json'
        # Convert numpy types for JSON
        clean_results = []
        for t in pool_targets:
            clean_results.append({
                k: (float(v) if isinstance(v, (np.floating,)) else
                    int(v) if isinstance(v, (np.integer,)) else
                    str(v) if isinstance(v, (np.bool_,)) else v)
                for k, v in t.items()
            })
        with open(out_json, 'w') as f:
            json.dump({
                'checkpoint': ckpt_name,
                'checkpoint_path': ckpt_path,
                'pool_size': len(pool),
                'n_targets': len(matched),
                'n_in_pool': len(pool_targets),
                'results': clean_results,
            }, f, indent=2, ensure_ascii=False)
        print(f'\n💾 结果已保存: {out_json}')

    print(f'\n{"="*80}')
    print('✅ 全部完成')
    print(f'{"="*80}')


if __name__ == '__main__':
    main()
