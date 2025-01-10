# C2ML

## Script architecture

C2ML
├── datareading
│   └── ccdcdata.json
├── extrfinetune
│   ├── cftm.py
│   ├── chl.py
│   ├── cjtj.py
│   ├── config.json
│   ├── cstrucout.py
│   ├── ctotable.py
│   └── prompt
│       ├── elsedatatable.py
│       ├── elsehl.py
│       ├── jtjprompt.py
│       └── sstru.py
├── refer
│   ├── ACS_crawler.py
│   ├── Elsevier_crawler.py
│   ├── RSC_crawler.py
│   ├── Springer_crawler.py
│   ├── Wiley_crawler.py
│   ├── config.json
│   └── Datasets
│       └── Publisher
│           ├── aaas.xlsx
│           ├── acs.xlsx
│           ├── elsevier.xlsx
│           ├── pnas.xlsx
│           ├── rsc.xlsx
│           ├── springer.xlsx
│           └── wiley.xlsx
├── request
│   ├── main.py
│   ├── config/
│   ├── core
│   │   ├── data_processor.py
│   │   ├── query_parser.py
│   │   └── query_system.py
│   └── utils
│       ├── constants.py
│       ├── pdf_processor.py
│       ├── rdoi.py
│       ├── re_cif.py
│       └── vis_cif.py
└── ulanggraph
    ├── data_processorllm.py
    ├── file_processor.py
    ├── workflow_core.py
    ├── workflow_manager.py
    ├── prompt
    │   └── totext.py
