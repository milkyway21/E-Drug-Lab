# 赛事简介



代谢相关脂肪性肝病（MASLD）为当前全球患病率最高的慢性肝病，该病可逐步发展为脂肪性肝炎、肝纤维化，乃至肝硬化和肝癌。尽管MASLD治疗近年来已有突破，部分药物已获得监管批准并进入临床应用，但其适应症主要覆盖特定纤维化阶段或特定患者亚群。对于疾病早期阶段，即肝细胞脂质过载与脂毒性尚具可逆性的窗口期，仍缺乏特异性强、安全性高且可及性好的小分子干预手段。

本赛题聚焦 MASLD 发生发展早期的关键肝细胞事件——脂质过载及其相关脂毒性压力，构建可规模化、可量化、可实验验证的低毒性肝细胞降脂化合物发现任务。参赛智能体不要求直接解决完整 MASLD的完整复杂病理网络，而是基于 HepG2细胞-FFA（游离脂肪酸）肝细胞脂质累积模型，从大规模小分子库中识别出既可降低肝细胞脂质蓄积、又在有效浓度下不显著损伤细胞活力的候选分子。该任务旨在为MASLD早期干预候选物发现提供低成本、高通量、可闭环迭代的新范式。

本赛题由上海人工智能实验室与临港实验室联合出题，采用“先提名、后验证”的流程。参赛 AI 智能体需在指定化合物库中通过推理完成候选分子提名，说明排序依据、作用机制假说及实验验证方案。随后，组委会将在 HepG2-FFA脂质蓄积体系中对提名分子进行实验检测，综合降脂效应与细胞毒性两项指标，判断真正有效且低毒的分子。最终目标为获得可用于后续机制确证及成药开发的低毒性降脂候选物。

## 实验判读要点
降脂效应与细胞毒性须分别评估。在肝细胞脂质筛选过程中，常见问题在于：部分化合物导致脂滴信号下降的原因并非调控脂代谢，而是直接损伤或杀死细胞。若缺乏细胞毒性数据作为对照，此类化合物容易被误判为有效命中。因此，区分真实降脂作用与毒性所致假阳性的能力，直接决定筛选结果的可靠性。因此，实验验证将同时检测降脂效应与细胞活力。仅在未明显损伤细胞活力的前提下实现脂质蓄积降低的分子，方计为有效命中。

<div style="position:relative; overflow:hidden; margin:22px 0 26px; padding:26px 28px; border-radius:8px; background:linear-gradient(105deg,rgba(7,18,35,.96) 0%,rgba(8,43,68,.9) 48%,rgba(8,64,56,.82) 100%); border:1px solid rgba(95,210,230,.22); box-shadow:0 18px 42px -30px rgba(0,15,35,.9); color:#fff;">
  <h3 style="margin:0 0 18px; color:#fff; font-family:'Noto Serif SC', var(--font-serif), serif; font-size:22px; font-weight:650; line-height:1.45;">生命科学 AI 智能体构建参考资源 ｜元生 OriGene</h3>
  <div style="display:flex; align-items:center; flex-wrap:wrap; gap:24px; margin:0 0 16px;">
    <img src="https://openxlab.oss-cn-shanghai.aliyuncs.com/ai4scomp/life.png" alt="元生 OriGene" style="display:block; flex:0 0 auto; width:190px; max-width:100%; height:auto; object-fit:contain;">
    <p style="flex:1 1 320px; min-width:220px; margin:0; color:rgba(218,247,255,.82); font-size:15px; line-height:1.85;">「元生」OriGene 系列 AI 科学家平台以大模型驱动的多智能体协同框架为核心，提供从文献检索、工具调用、证据整合、智能推理到假说生成的全链条支持，可有效赋能疾病靶点发现及机制解析等任务。</p>
  </div>
  <p style="margin:0 0 16px; color:rgba(218,247,255,.82); font-size:15px; line-height:1.85;">作为本赛道开放的可选开发资源，OriGene‑SkillHub 与 OriGene-MCP 可为参赛团队构建自主 AI agent 提供工具组件与流程参考。参赛者可自由选择使用、扩展，或基于其他模型与框架开展创新探索。</p>
  <div style="margin:0 0 16px; padding:16px 18px; border-radius:8px; background:rgba(255,255,255,.06); border:1px solid rgba(95,210,230,.18);">
    <p style="margin:0 0 10px; color:rgba(255,255,255,.92); font-size:15px; font-weight:650; line-height:1.6;">资源入口：</p>
    <ul style="margin:0; padding-left:20px; color:rgba(218,247,255,.78); font-size:14px; line-height:1.9; overflow-wrap:anywhere; word-break:break-word;">
      <li><a href="https://origene.lglab.ac.cn/" target="_blank" rel="noopener noreferrer" style="color:#20d6c8; font-weight:600; text-decoration:none;">OriGene产品平台</a></li>
      <li><a href="https://origene.lglab.ac.cn/skill-hub" target="_blank" rel="noopener noreferrer" style="color:#20d6c8; font-weight:600; text-decoration:none;">OriGene-SkillHub技能共享中心</a></li>
      <li><a href="https://github.com/GENTEL-lab/OrigeneMCP" target="_blank" rel="noopener noreferrer" style="color:#20d6c8; font-weight:600; text-decoration:none;">OriGeneMCP开源工具包</a>，已接入<a href="https://discovery.intern-ai.org.cn/org/ailab/workspace/iframe?url=https://scphub.intern-ai.org.cn/" target="_blank" rel="noopener noreferrer" style="color:#20d6c8; font-weight:600; text-decoration:none;">书生科学发现平台</a></li>
      <li><a href="https://www.biorxiv.org/content/10.1101/2025.06.03.657658v1" target="_blank" rel="noopener noreferrer" style="color:#20d6c8; font-weight:600; text-decoration:none;">参考文献</a></li>
    </ul>
  </div>
  <p style="margin:0; color:rgba(218,247,255,.62); font-size:13px; font-style:italic; line-height:1.8;">说明：该资源为可选开发支持，参赛团队可自由选择技术路线，鼓励构建具有自主方法特色的 AI agent；赛事评分不以是否使用OriGene相关资源作为依据。</p>
</div>

# 数据集

## 化合物库

- [百度云下载链接](https://pan.baidu.com/s/17ZEq56X9VP_6OYtxnnQ3BA?pwd=q3uc)
- 百度云下载链接提取码：q3uc
- 内容：化合物结构（SDF格式），作为智能体提名候选分子的来源。

## 实验验证读出（HepG2 体系）

提名分子将在 HepG2 脂质蓄积体系中接受检测，包含两项读出指标：

- 脂质蓄积：化合物处理后细胞内脂质堆积水平的变化（脂滴或中性脂含量），用于判断降脂效应。
- 细胞毒性：相同条件下的细胞活力，用于排除因细胞毒性导致脂滴信号下降的假阳性。

## 关键约束

- 有效命中标准：在不明显损伤细胞活力的前提下降低脂质蓄积。仅关注脂滴下降而忽略毒性，会将单纯杀伤细胞的化合物误判为有效，故两项指标须一并判断。

## 阳性结果去向

- 经实验确认的有效候选化合物，可用于赛后的机制确证、构效优化及开发。

# 三、赛题任务

参赛智能体需在化合物库中完成候选分子的提名与论证，主要内容如下。

- 候选提名：从化合物库中筛选并排序具有降脂潜力的分子，说明排序依据，包括但不限于结构特征、已知活性注释、相关文献、靶点或通路证据。
- 毒性考量：在提名阶段评估分子的潜在细胞毒性，优先选择可能低毒的分子，并说明判断依据。
- 机制假说：为候选分子提出可检验的作用机制、靶点或通路，例如从头脂合成（SREBP-1c、ACC、FASN、SCD1）、脂肪酸氧化（PPARα、AMPK、CPT1）、脂质摄取与外排、自噬等。

# 赛程安排

大赛举办时间为 2026 年 7 月 15 日至 2026 年 9 月 30 日，各阶段具体安排如下。

## 报名及作品提交

| 时间 | 提交内容 | 提交要求 |
| --- | --- | --- |
| 2026年7月17日 - 7月31日 | 候选分子提名清单（csv） | 排序后的Top 10候选分子列表，说明每个分子的提名依据，以及对降脂效应和潜在细胞毒性的判断。 |
|  | 机制与验证方案（PDF） | 候选分子的作用机制、靶点或通路假说，以及对该作用机制进行实验验证的方案。 |
|  | 方法学与复现材料（择一或组合） | 方法学描述报告；源码仓库（GitHub）、容器镜像（Docker）、可调用 API（附文档）或可访问的 Web 应用（附 URL 及说明），用于展示智能体工作流程。 |
|  | 其他材料（如适用） | 运行日志、数据使用声明等。 |

## 专家评审与实验验证

| 时间 | 阶段 | 内容 |
| --- | --- | --- |
| 2026年8月1日 - 8月15日 | 专家书面评审 | 由 AI、生物学及药学专家对提交材料进行评审打分，确定进入实验验证阶段的队伍及其待测分子。 |
| 2026年8月15日 - 9月20日 | 实验验证 | 组委会在 HepG2-FFA 体系中检测入选队伍提名的分子，测定降脂效应和细胞毒性，确认其中真正有效且低毒的命中。 |
| 2026年9月21日 - 9月30日 | 结果分析 | 专家评审团对结果进行综合分析评价，确定最终得分和获奖团队名单。 |

## 成果展示

| 时间 | 阶段 | 内容 |
| --- | --- | --- |
| 2026年9月30日 | 名次公布 | 大赛官网、Intern Science 小红书账号等渠道发布结果。 |
|  | 上传平台 | 公布结果后，将相关模型和智能体发布至科学发现平台。 |

# 比赛评分

| 评分维度 | 分值 | 说明 |
| --- | --- | --- |
| 候选化合物发现效果与智能体科学推理能力 | 60 | 提名分子在实验验证中被确认为有效低毒命中的效果得分×新颖性得分。 |
| 机制解释与后续验证方案 | 20 | 智能体在提名和推理过程中的科学性、合理性与可解释性。候选分子的作用机制与通路假说的合理性及可检验性；后续验证方案的科学性、可行性与转化价值。 |
| 方法学、智能体与可复现性 | 20 | 方法的创新性、合理性；智能体工作流程的完整度；结果的可复现性及工程化程度。 |
