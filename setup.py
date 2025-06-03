# setup.py - 可选的包安装文件
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="task-master-ai",
    version="1.0.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="智能任务总结系统",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/task-master-ai",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.11",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "task-master=src.main:main",
        ],
    },
)
