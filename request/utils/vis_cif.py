import os
import logging
from typing import Optional, Union

from pymatgen.core import Structure
from pymatgen.io.cif import CifParser
import py3Dmol
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt5.QtWebEngineWidgets import QWebEngineView

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class CrystalViewer:
    """处理 CIF 文件并生成晶体结构可视化"""
    
    def __init__(self, cif_file_path: str):
        """
        初始化查看器
        
        Args:
            cif_file_path: CIF文件路径
        """
        if not os.path.exists(cif_file_path):
            raise FileNotFoundError(f"CIF file not found: {cif_file_path}")
            
        self.cif_file_path = cif_file_path
        self.structure: Optional[Structure] = None
        self._app = None  # 存储QApplication实例

    def read_cif_file(self, initial_tolerance: float = 1.0, 
                     max_tolerance: float = 10.0, 
                     step: float = 1.0) -> Optional[Structure]:
        """
        读取CIF文件并返回结构对象，动态调整 occupancy_tolerance
        
        Args:
            initial_tolerance: 初始容差值
            max_tolerance: 最大容差值
            step: 容差递增步长
            
        Returns:
            Structure对象或None（如果读取失败）
        """
        try:
            tolerance = initial_tolerance
            while tolerance <= max_tolerance:
                try:
                    parser = CifParser(self.cif_file_path, occupancy_tolerance=tolerance)
                    structures = parser.parse_structures(primitive=False)
                    if structures:
                        logging.info(f"Successfully loaded CIF file: {self.cif_file_path} "
                                   f"(occupancy_tolerance={tolerance})")
                        self.structure = structures[0]
                        return self.structure
                except Exception as e:
                    logging.warning(f"Failed to load CIF file (occupancy_tolerance={tolerance}): {e}")
                tolerance += step

            logging.error(f"Failed to parse file {self.cif_file_path}, "
                        f"exceeded max tolerance {max_tolerance}")
            return None
            
        except Exception as e:
            logging.error(f"Error reading CIF file: {str(e)}")
            return None

    def generate_3dmol_html(self) -> Optional[str]:
        """
        使用 py3Dmol 生成交互式晶体结构的 HTML 字符串
        
        Returns:
            HTML字符串或None（如果生成失败）
        """
        if not self.structure:
            if not self.read_cif_file():
                logging.error("No structure loaded, cannot generate 3Dmol HTML")
                return None

        try:
            # 导出为 CIF 格式字符串
            cif_str = self.structure.to(fmt="cif")
            
            # 创建 py3Dmol 视图
            view = py3Dmol.view(width=800, height=600)
            view.addModel(cif_str, "cif")  # 使用 CIF 格式加载
            view.setStyle({
                "stick": {},  # 棒状模型
                "sphere": {"radius": 0.3}  # 添加原子球体
            })
            view.addUnitCell()  # 添加晶胞边框
            view.zoomTo()  # 自动调整视图
            
            return view._make_html()
            
        except Exception as e:
            logging.error(f"Failed to generate 3Dmol HTML: {str(e)}")
            return None

    def show_structure(self) -> bool:
        """
        显示结构窗口
        
        Returns:
            布尔值表示是否成功显示
        """
        try:
            html_content = self.generate_3dmol_html()
            if not html_content:
                return False

            # 确保只创建一个QApplication实例
            if QApplication.instance() is None:
                self._app = QApplication([])
            else:
                self._app = QApplication.instance()

            window = CrystalViewerApp(html_content)
            window.show()
            self._app.exec_()
            return True

        except Exception as e:
            logging.error(f"Failed to show structure: {str(e)}")
            return False


class CrystalViewerApp(QMainWindow):
    """PyQt5 窗口显示 py3Dmol 交互式视图"""
    
    def __init__(self, html_content: str):
        """
        初始化视图窗口
        
        Args:
            html_content: 要显示的HTML内容
        """
        super().__init__()
        self.setWindowTitle("3D Crystal Structure Viewer")
        self.setGeometry(100, 100, 900, 700)

        # 创建主窗口小部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 创建布局
        layout = QVBoxLayout(central_widget)

        # 创建 WebEngineView 显示 HTML
        self.web_view = QWebEngineView()
        self.web_view.setHtml(html_content)
        layout.addWidget(self.web_view)