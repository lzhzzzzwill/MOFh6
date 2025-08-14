# Major function

The initial stage of MOFh6’s text-processing pipeline involves acquiring reference materials in strict compliance with institutional subscription policies, ensuring legal and ethical access to scientific literature.

## 0. The suggested script is as follows:
#### ACS_crawler.py

#### Elsevier_crawler.py
##### *If you use windows, you should download the script "Elsevier_crawler.py” at [refer_win](https://github.com/heniyiqishizhong/MOF_llm/tree/main/refer_win), and then modify.* 暂时没加入转换txt。。。

```python
line 23: with open(r"./refer/config.json") as con_file:
line 37: download_dir = r'./ulanggragh/input'  
line 91: with open(r'./refer/pathe.json', 'r', encoding='utf-8') as file:
line 146: subprocess.Popen([r'.../soffice.exe', '--headless', '--accept=socket,host=localhost,port=2002;urp;StarOffice.ComponentContext'])
line 152: os.environ['UNO_PATH'] = r'.../LibreOffice/program/'
line 154: subprocess.run(['python', r'.../unoconv-master/unoconv-master/unoconv', '-f', 'pdf', file_path], check=True)
line 288: chrome_driver_path = r'.../chromedriver.exe'
```

#### RSC_crawler.py

#### Springer_crawler.py
##### *If you use windows, you should download the script "Springer_crawler.py” at [refer_win](https://github.com/heniyiqishizhong/MOF_llm/tree/main/refer_win), and then modify.
```python
line 44 DEFAULT_LIBREOFFICE_PATH = r"...\\soffice.exe"
line 45 DEFAULT_UNO_PROGRAM_DIR  = r"...\\LibreOffice\\program"
line 46 DEFAULT_UNOCONV_PATH     = r"...\\LibreOffice\\unoconv-master\\unoconv"
line 47 DEFAULT_CHROMEDRIVER     = r"...\\chromedriver.exe"
line 205 download_dir = './ulanggraph/input'
```

#### Wiley_crawler.py
##### *If you use windows, you should download the script "Wiley_crawler” at [refer_win](https://github.com/heniyiqishizhong/MOF_llm/tree/main/refer_win), and then modify.* 

```python
line 106: download_dir = r'./ulanggragh/input'
line 109: config_path = r'./refer/config.json'
line 200: chrome_driver_path = r'.../chromedriver.exe' 
```

## 1. Construction of meta dataset

- We provide crawler scripts for data mining from the following publications

  - [American Chemical  Society (ACS)](https://solutions.acs.org/solutions/text-and-data-mining/): ACS_crawler.py

  - [Royal Society of Chemistry (RSC)](https://www.rsc.org/journals-books-databases/research-tools/text-and-data-mining/): RSC_crawler.py

  - [Elsevier](https://dev.elsevier.com/): Elsevier_crawler.py

  - [Wiley](https://onlinelibrary.wiley.com/library-info/resources/text-and-datamining): Wiley_crawler.py

  - [Springer Science and Business Media LLC (Springer)](https://www.springernature.com/gp/researchers/text-and-data-mining): Springer_crawler.py

- **Note**: *you need to apply for API keys themselves to run these scripts.*

### Auxiliary content
- Config.json: The publishers' TDM tokens, which require users to obtain them by themselves.
- Pathe.json: A repository that covers most of Elsevier publishers' xpath.

## Software requirements

- [LibreOffice](https://zh-cn.libreoffice.org/download/source-code/): An open-source office software suite for converting basic document formats.
  - [unoconv](https://github.com/unoconv/unoconv): An open-source command-line tool that utilizes the functionality of LibreOffice/PenOffice to convert document form.
- [Google chrome](https://www.google.cn/intl/en_uk/chrome/): Download supporting materials.
- [Chromedriver](https://developer.chrome.google.cn/docs/chromedriver/get-started?hl=zh-tw): Support for Chrome.

# Warning

- This project is based on a scientific literature dataset subscribed by our institution. Due to copyright restrictions, you must obtain this data through your own institution. We cannot directly provide the dataset, but we can provide web crawler code and basic CCDC code.
