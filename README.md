<p align="center">
    <br>
    <img src="docs/_static/logo.png" width="400"/>
    <br>
<p>

<div align="center">
  <a href="https://github.com/salesforce/botsim/releases"><img alt="Latest Release" src="https://img.shields.io/github/release/salesforce/LAVIS.svg" /></a>
  <a href="https://opensource.salesforce.com/botsim/index.html">
  <img alt="docs" src="https://github.com/salesforce/LAVIS/actions/workflows/docs.yaml/badge.svg"/>
  <a href="https://opensource.org/licenses/BSD-3-Clause">
  <img alt="license" src="https://img.shields.io/badge/License-BSD_3--Clause-blue.svg"/>
  </a>
</div>

<div align="center">
<a href="https://arxiv.org/abs/2211.11982">System Demo Paper</a>,
<a href="https://arxiv.org/abs/2211.11982">Technical Report</a>,
<a href="https://salesforce-botsim.herokuapp.com/">Demo</a>,
<a href="https://opensource.salesforce.com/botsim//latest/index.html">Documentation</a>,
<a href="">Blog</a>
</div>


# BotSIM:  An End-to-End Bot Simulation Toolkit for Commercial Task-Oriented Dialog Systems


## Table of Contents
1. [Introduction](#introduction)
2. [Installation](#installation)
3. [Getting Started](#getting-started)
4. [Tutorials](#tutorial)
4. [Documentation](#documentation)
5. [System Demo Paper and Technical Report](#system-demo-paper-and-technical-report)


## Introduction
BotSIM is a Bot SIMulation toolkit for performing large-scale data-efficient end-to-end evaluation, diagnosis and remediation of commercial task-oriented dialog (TOD) systems to accelerate bot development and evaluation, reduce cost and time-to-market.
As a modular framework, BotSIM can be extended by bot developers to support new bot platforms. As a toolkit, it offers an easy-to-use App and a suite of command line tools for bot admins or practitioners to readily perform evaluation and remediation of their bots.

Key features of BotSIM include:

- **Multi-stage bot evaluation**: BotSIM can be used for both pre-deployment testing and potentially post-deployment performance monitoring.
- **Data-efficient dialogue generation**: Equipped with a deep network based paraphrasing model, BotSIM can generate an extensive set of test intent queries from the limited number of input intent utterances, which can be used to evaluate the bot intent model at scale.
- **End-to-end bot evaluation via dialogue simulation**: Through automatic chatbot simulation, BotSIM can identify existing issues of the bot and evaluate both the natural language understanding (NLU) performance (for instance, intent or NER error rates) and the end-to-end dialogue performance such as goal completion rates.
- **Bot health report dashboard**: The bot health report dashboard presents a multi-granularity top-down view of bot performance consisting of historical performance, current  bot test performance and dialogue-specific performance. Together with the analytical tools, they help bot practitioners quickly identify the most urgent issues and properly plan their resources for troubleshooting.
- **Easy extension to new bot platform**: BotSIM was built with a modular task-agnostic design, with multiple platform support in mind, so it can be easily extended to support new bot platforms. BotSIM currently supports  [Salesforce Einstein BotBuilder](https://help.salesforce.com/s/articleView?id=sf.bots_service_intro.htm&type=5) and [Google DialogFlow CX](https://cloud.google.com/dialogflow/cx/docs/basics)

## Installation

1. (Optional) Creating conda environment
```bash
   conda create -n botsim python=3.9
   conda activate botsim
```

2. Cloning and building dependencies
``` bash
   git clone https://github.com/salesforce/botsim.git
   cd BotSIM
   pip install .
```

## Getting Started
### Streamlit Web App
The Streamlit Web App can be used to 
<p align="center" width="100%">
    <img width="100%" src="docs/BotSIM_App.png">
</p>

The following commands can be used to run BotSIM as a Streamlit Web App locally:
```bash
  export PYTHONPATH=./:$PYTHONPATH
  export DATABASE_URL="db/botsim_sqlite_demo.db"
  streamlit run botsim/streamlit_app/app.py
```
The App can also be deplpyed as a docker image:
```
  # build the docker image
  docker build -t botsim-streamlit .
  # run the docker container
  docker run -p 8501:8501 botsim-streamlit
```
### Command Line Tools
Alternatively, users can also use the command line tools to deep-dive into BotSIM's generation-simulation-remediation pipeline.

## Tutorial
We provide the following tutorials in the tutorial section of the documentation. 
- Using Streamlit Web App
- Using BotSIM command line tools
- Navigating through bot health dashboard
- Applying remedidation suggestions

## Documentation 
For more details of the system components and advanced usages, please refer to [code documentation]((https://opensource.salesforce.com/botsim//latest/index.html#)]).
We welcome the contribution from the open-source community to improve the toolkit! To support new bot platforms, please also follow the guidelines detailed in the code documentation.

## System Demo Paper and Technical Report
You can find more details in our technical report and  system demo paper.
If you're using BotSIM in your research or applications, please cite using this BibTeX for technical report:
```
@article{guangsen2022-botsim-tr,
  author    = {Guangsen Wang and Shafiq Joty and Junnan Li and Steven Hoi},
  title     = {BotSIM: An End-to-End Bot Simulation Toolkit for Commercial Task-Oriented Dialog Systems},
  year      = {2022},
  doi       = {},
  url       = {},
  archivePrefix = {arXiv},
}
```
or the following BibTex for our system demo paper:
```
@article{guangsen2022-botsim-demo,
  author    = {Guangsen Wang and Samson Tan and Shafqi Joty and Guang Wu and Jimmy Au and Steven Hoi},
  title     = {BotSIM: An End-to-End Bot Simulation Framework for Commercial Task-Oriented Dialog Systems},
  year      = {2022},
  doi       = {},
  url       = {},
  archivePrefix = {arXiv},
}
```

## Contact Us
Feel free to contact botsim@salesforce.com for any comments, issues or suggestions.

## License
[BSD 3-Clause License](LICENSE.txt)
