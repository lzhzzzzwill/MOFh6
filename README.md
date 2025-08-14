# <img src="https://github.com/lzhzzzzwill/MOFh6/blob/main/icon/app.PNG" alt="MOFh6 Logo" width="80"> MOFh6
<img src="https://github.com/lzhzzzzwill/MOFh6/blob/main/icon/toc.png" alt="MOFh6 TOC" width="600">
From the challenge of sifting through vast, ambiguous MOF literature to the clarity of structured, actionable data, **MOFh6** emerges as the solution. It is an intelligent, multi-agent system that transforms unstructured scientific text on metal–organic frameworks (MOFs) into analysis-ready synthesis and property data. By combining large language models (LLMs) with rule-based agents, MOFh6 delivers high-accuracy, cost-efficient extraction, enabling scalable, data-driven materials discovery.

MOFh6 operates within an **enterprise-inspired framework**, where each role mirrors a corporate function:

- **CEO** – Responsible for central coordination, leveraging the Langgraph framework to orchestrate all agents and tools.  
- **CMO** – Oversees data management and user interaction, ensuring a smooth and accessible user experience.  
- **COO** – Comprising human experts, focuses on data annotation and workflow design for high-quality inputs.  
- **CTO** – Constituted by LLM agents, leads the integration and deployment of core technological capabilities.
<img src="https://github.com/lzhzzzzwill/MOFh6/blob/main/icon/MOFh6frame.png" alt="MOFh6frame" width="600">

# Script architecture

```markdwon
📁 MOFh6
├── 📁 datareading
├── 📁 extrfinetune
│   ├── cftm.py
│   ├── chl.py
│   ├── cjtj.py
│   ├── cstrucout.py
│   ├── ctotable.py
│   └── 📁 prompt
│       ├── elsedatatable.py
│       ├── elsehl.py
│       ├── jtjprompt.py
│       └── sstru1.py
├── 📁 icon
├── main.py
├── 📁 refer
│   ├── ACS_crawler.py
│   ├── Elsevier_crawler.py
│   ├── RSC_crawler.py
│   ├── Springer_crawler.py
│   └── Wiley_crawler.py
├── 📁 request
│   ├── 📁 config
│   │   └── config.py
│   ├── 📁 core
│   │   ├── data_processor.py
│   │   ├── query_parser.py
│   │   └── query_system.py
│   ├── main.py
│   ├── 📁 prompt
│   │   └── query.py
│   └── 📁 utils
│       ├── constants.py
│       ├── pdf_processor.py
│       ├── rdoi.py
│       ├── re_cif.py
│       └── vis_cif.py
└── 📁 ulanggraph
    ├── data_processorllm.py
    ├── file_processor.py
    ├── main.py
    ├── 📁 prompt
    │   └── totext.py
    ├── workflow_core.py
    └── workflow_manager.py
```

# folder&script function
## Core Tasks of MOFh6

I. **Synthesis Extraction** – Retrieve detailed synthesis descriptions for specified MOFs.  
II. **Pore Structure Analysis** – Obtain pore structure parameters for the target MOFs.  
III. **Structure Visualization** – Generate visual representations of the specified MOFs.  

<img src="https://github.com/lzhzzzzwill/MOFh6/blob/main/icon/MOFh6pipline.png" alt="MOFh6 Pipeline" width="600">

### datareading
- The core meta data of MOFh6, click on [📁 datareading](https://github.com/lzhzzzzwill/MOFh6/tree/main/datareading) to learn more.
COO – Focuses on data annotation and workflow design. All COO-curated and annotated datasets are stored in the [💾 MOFh6test](https://github.com/rendaoyuan/MOFh6test) repository.

### extrfinetune
- CTO – Comprising MOFh6’s core LLM agent, is primarily responsible for Task I, which involves extracting synthesis information of specified MOFs from full-length scientific literature,
click on [📁 extrfinetune](https://github.com/lzhzzzzwill/MOFh6/tree/main/extrfinetune) to learn more.

### refer
- Retrieving scientific literature through compliance-driven data-mining scripts to supply source material for the MOFh6 workflow,
click on [📁 refer](https://github.com/lzhzzzzwill/MOFh6/tree/main/refer) to learn more.

### request
- CTO – Comprising MOFh6’s core LLM agent, is primarily responsible for Task II and Task III, delivering pore structure parameters of specified MOFs and enabling in-depth structural exploration within MOFh6.

### ulanggraph
- CEO appointed by LangGraph to coordinate and manage the execution of all agents and tools.

### [📜 main.py](https://github.com/lzhzzzzwill/MOFh6/blob/main/main.py)
- CMO – Oversees data management and user interaction. To run MOFh6 locally, users should review the folder&script function above to configure the environment correctly.
  - MOFh6 is developed and tested on macOS M2. To run on Windows, only minor adjustments in [📁 refer](https://github.com/lzhzzzzwill/MOFh6/tree/main/refer) are needed.
```python
# Python environment
# Recommended: Python 3.10
# Install dependencies
pip install -r requirements.txt
```
- For quick access without local configuration, the CMO also provides an online [💻 app](https://huggingface.co/spaces/Willlzh/MOFh6), enabling immediate use in any syste without installation.

### If you want to use this tool, please cite:
```bibtex
@misc{lin2025reshapingmofstextmining,
      title={Reshaping MOFs text mining with a dynamic multi-agents framework of large language model}, 
      author={Zuhong Lin and Daoyuan Ren and Kai Ran and Jing Sun and Songlin Yu and Xuefeng Bai and Xiaotian Huang and Haiyang He and Pengxu Pan and Ying Fang and Zhanglin Li and Haipu Li and Jingjing Yao},
      year={2025},
      eprint={2504.18880},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2504.18880}, 
}
```

- The software copyright is currently under review.
