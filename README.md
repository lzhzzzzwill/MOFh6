# <img src="https://github.com/lzhzzzzwill/MOFh6/blob/main/icon/app.PNG" alt="MOFh6 Logo" width="80"> MOFh6
MOFh6 is an intelligent, multi-agent system designed to transform unstructured scientific literature on metal–organic frameworks (MOFs) into structured, analysis-ready synthesis and property data.
By combining large language models (LLMs) and rule-based agents, MOFh6 delivers high-accuracy, cost-efficient extraction, paving the way for scalable, data-driven materials discovery.

## Script architecture

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

## folder function

### datareading
- The core meta data of MOFh6, click on [datareading](https://github.com/lzhzzzzwill/MOFh6/tree/main/datareading) to learn more.

If you want to use this tool, please cite:
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
