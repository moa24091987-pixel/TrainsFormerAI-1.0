VirusTotal  - https://www.virustotal.com/gui/file/00837b8f306158c41cb1c667b6be960738b0968945da9622a3c99d39569ff57e?nocache=1
DrWeb - https://online834.drweb.com/cache/?i=120f022f6555e590731bfa493f159b46

TrainsFormerAI: Autonomous AI Suite with Neuroshift Engine
TrainsFormerAI is a privacy-focused, standalone AI software suite designed to run locally on consumer hardware. Powered by the custom Neuroshift engine, it allows users to interact with Large Language Models (LLMs) completely offline, with zero censorship and dynamic local context injection.


Key Features
- Total Privacy: 100 percent offline. Your data never leaves your machine.
- Neuroshift Engine: A custom-built inference layer optimized for low-end hardware.
- Dynamic Context Injection: Instantly teach the AI new information by simply adding local .txt or documentation files.
- Zero Censorship: No hardcoded moral filters or system-level restrictions.
- Hardware Optimized: Designed to run on as little as 4GB of RAM.
The Neuroshift Technology
Unlike traditional RAG (Retrieval-Augmented Generation) which can be slow and resource-heavy on local machines, the Neuroshift engine utilizes a dynamic context injection method. It streamlines the attention mechanism to prioritize local data, providing near-instant responses even on older CPUs.

System Requirements
Minimum:
- CPU: Dual-core (Intel i3 5th Gen / Ryzen 3)
- RAM: 4 GB
- OS: Windows 10/11 or Linux
- GPU: Not required (Runs on CPU)
Recommended:
- RAM: 8 GB or more
- GPU: NVIDIA GeForce GTX 960 or newer (for CUDA acceleration)
Installation

1. 
Install dependencies:
pip install (library take from requirements.txt)  

2. 
Run the application:
TrainsformerAI.py
How to use Context Injection
Simply place your text files (.txt) into the (Documents\TrainsFormerAI\education). The Neuroshift engine will automatically index them and use them as a knowledge base for all future queries.
