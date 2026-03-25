from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as file:
    long_description = file.read()

with open("requirements.txt", "r", encoding="utf-8") as file:
    requirements = [line.strip() for line in file if line.strip() and not line.startswith("#")]

setup(
    name="bear-review",
    version="2.0.0",
    author="Codex",
    author_email="noreply@example.com",
    description="代码优先的个人复盘与通知系统，支持 SQLite / Notion 任务源",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "bear-review=src.main:main",
            "task-master=src.main:main",
            "bear-capture=src.capture:main",
            "bear-capture-web=src.capture:main",
        ],
    },
)
