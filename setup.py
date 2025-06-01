from setuptools import setup, find_packages

setup(
    name="agent01_attempt",
    version="0.1",    packages=find_packages(include=["src*", "celery*"]),
    install_requires=[
        "python-dotenv",
        "pymongo",
        "google-generativeai"
    ]
)
