# MOFh6

## Script architecture

```markdwon
📁 datareading
📁 extrfinetune
│   ├── cftm.py
│   ├── chl.py
│   ├── cjtj.py
│   ├── cstrucout.py
│   ├── ctotable.py
│   📁 finetunetable
│   📁 prompt
│   │   ├── elsedatatable.py
│   │   ├── elsehl.py
│   │   ├── jtjprompt.py
│   │   ├── sstru.py
│   │   ├── sstru1.py
📁 icon
├── main.py
📁 refer
│   ├── ACS_crawler.py
│   ├── Elsevier_crawler.py
│   ├── RSC_crawler.py
│   ├── Springer_crawler.py
│   ├── Wiley_crawler.py
📁 request
│   📁 config
│   │   ├── config.py
│   📁 core
│   │   ├── data_processor.py
│   │   ├── query_parser.py
│   │   ├── query_system.py
│   ├── main.py
│   📁 prompt
│   │   ├── query.py
│   📁 utils
│   │   ├── constants.py
│   │   ├── pdf_processor.py
│   │   ├── rdoi.py
│   │   ├── re_cif.py
│   │   ├── vis_cif.py
📁 ulanggraph
│   ├── data_processorllm.py
│   ├── file_processor.py
│   ├── main.py
│   📁 prompt
│   │   ├── totext.py
│   ├── workflow_core.py
│   ├── workflow_manager.py
```

The software copyright is currently under review.

If you want to use this tool, please cite:
```bibtex
@misc{lin2025reshapingmofstextmining,
      title={Reshaping MOFs Text Mining with a Dynamic Multi-Agent Framework of Large Language Agents}, 
      author={Zuhong Lin and Daoyuan Ren and Kai Ran and Sun Jing and Xiaotiang Huang and Haiyang He and Pengxu Pan and Xiaohang Zhang and Ying Fang and Tianying Wang and Minli Wu and Zhanglin Li and Xiaochuan Zhang and Haipu Li and Jingjing Yao},
      year={2025},
      eprint={2504.18880},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2504.18880}, 
}

