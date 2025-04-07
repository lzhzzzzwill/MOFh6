import time
import json
from datetime import datetime
from huggingface_hub import HfApi
import os
import requests
from typing import Union

class HuggingFaceDatasetDownloader:
    def __init__(self, config_path: Union[str, dict], download_folder: str, max_requests_per_hour: int = 100):
        """初始化下载器"""
        try:
            if isinstance(config_path, str):
                with open(config_path, "r") as f:
                    config_data = json.load(f)
            else:
                config_data = config_path

            self.token = config_data.get("HF_TOKEN")
            if not self.token:
                raise ValueError("HF_TOKEN not found in config")

            self.dataset_repos = config_data.get("DATASET_REPOS")
            if not self.dataset_repos:
                raise ValueError("DATASET_REPOS not found in config")
            
            # 确保 dataset_repos 是列表
            if isinstance(self.dataset_repos, str):
                self.dataset_repos = [self.dataset_repos]

            self.download_folder = download_folder
            self.max_requests_per_hour = max_requests_per_hour
            self.api = HfApi()

            os.makedirs(self.download_folder, exist_ok=True)
            
        except Exception as e:
            raise RuntimeError(f"Failed to initialize downloader: {str(e)}")

    def download_file(self, file_name: str) -> bool:
        """下载单个文件"""
        for repo in self.dataset_repos:
            try:
                print(f"Checking repository {repo}...")
                dataset_info = self.api.list_repo_files(
                    repo_id=repo,
                    repo_type="dataset",
                    token=self.token
                )

                if file_name in dataset_info:
                    file_url = f"https://huggingface.co/datasets/{repo}/resolve/main/{file_name}"
                    local_path = os.path.join(self.download_folder, file_name)

                    response = requests.get(
                        file_url,
                        headers={"Authorization": f"Bearer {self.token}"},
                        stream=True
                    )
                    response.raise_for_status()

                    with open(local_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    print(f"Successfully downloaded from {repo}")
                    return True
            except Exception as e:
                print(f"Failed to download from {repo}: {str(e)}")
                continue

        print(f"File {file_name} not found in any repository")
        return False