What is BotSIM?
####################################

BotSIM is a modular, open-source *Bot SIM*\ ulation toolkit to serve as a one-stop solution for  
large-scale data-efficient end-to-end evaluation, diagnosis and remediation of commercial task-oriented dialog systems (chatbots). 

As a simulation framework, bot developers can extend BotSIM to support new bot platforms. As a toolkit, BotSIM can be readily used  
by bot admins or practitioners to perform testing and remediation of their bots.

Key features of BotSIM include:

- **Multi-stage bot evaluation**: BotSIM can be used for both pre-deployment testing and potentially post-deployment performance monitoring.
- **Data-efficient dialogue generation**: Equipped with a deep network based paraphrasing model, BotSIM can generate an extensive set of test intent queries from the limited number of input intent utterances, which can be used to evaluate the bot intent model at scale.
- **End-to-end bot evaluation via dialogue simulation**: Through automatic chatbot simulation, BotSIM can identify existing issues of the bot and evaluate both the natural language understanding (NLU) performance (for instance, intent or NER error rates) and the end-to-end dialogue performance such as goal completion rates.
- **Bot health report dashboard**: The bot health report dashboard presents a multi-granularity top-down view of bot performance consisting of historical performance, current  bot test performance and dialogue-specific performance. Together with the analytical tools, they help bot practitioners quickly identify the most urgent issues and properly plan their resources for troubleshooting.
- **Easy extension to new bot platform**: BotSIM was built with a modular task-agnostic design, with multiple platform support in mind, so it can be easily extended to support new bot platforms. (\*BotSIM currently supports  `Salesforce Einstein BotBuilder <https://help.salesforce.com/s/articleView?id=sf.bots_service_intro.htm&type=5>`_ and `Google DialogFlow CX <https://cloud.google.com/dialogflow/cx/docs/basics>`_.)  

BotSIM can significantly accelerate commercial bot development and evaluation, reduce cost and time-to-market by: 1) reducing efforts for test dialog creation and human-bot conversation; 2) enabling a better understanding of both Natural Language Understanding (NLU) and end-to-end performance via extensive dialog simulation; 3) improving bot troubleshooting process with actionable suggestions from simulation results analysis.



BotSIM  Architecture
####################################

.. image:: _static/BotSIM_Arch.png
  :width: 550

BotSIM's "generation-simulation-remediation" pipeline is shown above. 

- **Generator** takes bot designs and intent utterances as input and produces the required  configuration files and dialog goals for dialog simulation.
- **Simulator** performs agenda-based dialog simulation through bot APIs.
- **Remediator** generates health reports, performs analyses, and provides actionable insights to troubleshoot and improve dialog systems.


BotSIM System Design
####################################

.. image:: _static/BotSIM_design.png
  :width: 550

The key design principles of BotSIM include modularity, extensibility and usability so that the framework can be easily adopted by both bot end users and developers. 
The framework comprises three layers, namely the infrastructure layer, the adaptor layer and the toolkit layer.

Infrastructure layer
**************************************************
The infrastructure layer is designed to offer fundamental model support for the framework. 
It comprises two major categories: the natural language understanding (NLU), natural language generation (NLG) models 
and the key modules including the generator, the simulator and the remediator.

- ``botsim.models`` contains BotSIM's  NLU and NLG models. From a dialogue system perspective, BotSIM can be viewed as a counterpart to a chatbot: it needs to "understand" chatbot messages (NLU) and "respond" in natural languages (NLG). 
  Currently, fuzzy matching-based NLU and template-based NLG models are provided for efficiency reasons. Developers can also incorporate more advanced NLU and NLG models.. 
- ``botsim.modules`` consists of the three key  modules to power BotSIM's "generation-simulation-remediation" pipeline. 

    - ``botsim.modules.generator`` supports two major functionalities: 1) ``parser`` to parse bot metadata to infer dialog acts and dialog-act maps (BotSIM's NLU); 2) ``paraphraser`` to generate paraphrases of the input intent utterances to be used as intent queries in the simulation goals to probe bots' intent model.
    - ``botsim.modules.simulator`` implements the dialog-act level agenda-based user simulation in ``abus``. It also defines a simulation API client interface ``simulation_client_base``
    - ``botsim.modules.remediator`` analyzes the simulation dialogs and produces the performance metrics and conversational analytics to support the dashboard visualisation. 

Adaptor Layer: accommodating  new bot platforms
**************************************************
Built on top of the infrastructure layer, the adaptor layer is designed for easy extension of BotSIM to new bot platforms. The two most important platform-specific components of the layer include

- ``parser`` acts as an "adaptor" to unify bot definitions (e.g. conversation flows, intents/tasks) from different platforms to a common representation of dialog act maps. The dialog act maps are used as BotSIM NLU to map  bot messages to dialog acts. Note the implementations of the parser are highly platform-dependent and require bot developers to have access to bot APIs and bot design documentations. We have provided the implementations of BotBuilder and DialogFlow CX parser as references.
- ``simulation_client`` is the other platform-dependent component for BotSIM to exchange conversations  with bots via API calls. Similar to the parser, the implementation of the client depends on the design of the bot APIs and requires developers to choose appropriate APIs to implement the simulator client. 


Application Layer
**************************************************
The application layer is designed to significantly flatten the learning curves of BotSIM for both bot developers/practitioners and end users. 

- ``botsim.cli`` contains a set of command line tools for practitioners to learn more about the  major BotSIM components. The "generation-simulation-evaluation" pipeline has been split into multiple stages to expose the required inputs and expected outputs. They serve as basic building blocks for bot practitioners to build their customized pipelines.
- ``botsim.streamlit_app`` is a multi-page easy-to-use Web app. The motivation is to offer  BotSIM not just as a framework for developers but also as an easy-to-use  app to end users such as bot admins without diving into  technical details. The app can be deployed as a docker container or to the Heroku platform. We use Streamlit for supporting the front-end pages. Flask is used to support the backend APIs for Streamlit to invoke BotSIM functionalities. The app is also equipped with a SQL database to store  simulation status and historical performance across multiple platforms. 



Getting Started
#################################
Installation
********************
1. (Optional) Creating conda environment

  .. code-block:: bash

    conda create -n botsim python=3.9
    conda activate botsim

2. Cloning and building dependencies

  .. code-block:: bash

    git clone https://github.com/salesforce/botsim.git
    cd botsim
    pip install .

Running Streamlit App
***********************
.. image:: _static/BotSIM_App.png
  :width: 550

1. Running Streamlit App locally

.. code-block:: bash

  export PYTHONPATH=./:$PYTHONPATH
  export DATABASE_URL="db/botsim_sqlite_demo.db"
  streamlit run botsim/streamlit_app/app.py

2. Optionally, the app can also be deployed as a docker container

.. code-block:: bash
  
  device=cpu # change device to gpu to build a GPU docker image
  docker build --build-arg device=$device -t botsim-streamlit .
  docker build -t botsim-streamlit .
  docker run -p 8501:8501 botsim-streamlit

Alternatively, users can also use the command line tools to gain more flexibility. 
More details of how to run the command line tools are given later in the tutorial section.